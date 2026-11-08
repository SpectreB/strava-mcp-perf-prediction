"""MCP server entry point for Strava sport-science analysis."""

import argparse
import os
import sys

from mcp.server.fastmcp import FastMCP

import strava_sport_science_mcp.dependencies as deps
from strava_sport_science_mcp.http_app import run_http, validate_token
from strava_sport_science_mcp.tools import raw, sport_science

mcp = FastMCP(
    "strava-sport-science",
    instructions=(
        "Sports-science-aware Strava MCP server. Provides training load analysis "
        "(CTL/ATL/TSB), heart rate zone distribution, fitness trends, and race readiness "
        "scoring on top of raw Strava data."
    ),
)


@mcp.tool()
async def get_activities(days_back: int = 30) -> list[dict]:
    """Fetch recent activities from Strava.

    Use this to get a list of recent workouts including distance, duration,
    heart rate, and pace. Returns up to the last `days_back` days of activities.

    Args:
        days_back: Number of days to look back (default 30).

    Returns:
        List of activity dicts.
    """
    return await raw.get_activities(days_back)


@mcp.tool()
async def get_activity_detail(activity_id: int) -> dict:
    """Fetch detailed information about a specific Strava activity.

    Use this when you need the full details of a workout including laps, splits,
    best efforts, and gear used.

    Args:
        activity_id: The activity ID.

    Returns:
        Detailed activity dict.
    """
    return await raw.get_activity_detail(activity_id)


@mcp.tool()
async def get_athlete_profile() -> dict:
    """Fetch the authenticated athlete's Strava profile.

    Returns the athlete's name, stats, location, and measurement preferences.
    Use this to personalize training advice.

    Returns:
        Athlete profile dict.
    """
    return await raw.get_athlete_profile()


@mcp.tool()
async def get_activity_streams(
    activity_id: int, stream_types: str = "time,heartrate,velocity_smooth,altitude"
) -> dict:
    """Fetch time-series stream data for a specific activity.

    Returns second-by-second data for the requested stream types.
    Available types: time, heartrate, velocity_smooth, altitude, cadence, distance, latlng.
    Pass as comma-separated string.

    Args:
        activity_id: The activity ID.
        stream_types: Comma-separated stream type names.

    Returns:
        Dict of stream data keyed by type.
    """
    return await raw.get_activity_streams(activity_id, stream_types)


@mcp.tool()
async def get_training_load(days: int = 42, end_date: str | None = None) -> dict:
    """Analyze training load and fitness/fatigue balance.

    Computes CTL (fitness), ATL (fatigue), and TSB (form) using the Banister model.

    TSS per activity uses the best data available (power > pace > heart rate > duration);
    `tss_methods` reports which. Pass `end_date` to analyze a past period.

    Use this to answer: "Am I overtraining?" or "How has my fitness evolved?"

    Args:
        days: Number of days to analyze (default 42).
        end_date: Last day of the period as YYYY-MM-DD (default today).

    Returns:
        TrainingLoadSummary as dict.
    """
    return await sport_science.get_training_load(days, end_date)


@mcp.tool()
async def get_zone_distribution(
    days: int = 30, end_date: str | None = None, use_streams: bool = True
) -> dict:
    """Analyze intensity zone distribution.

    Computes the percentage of training time in each intensity zone (Z1-Z5) and checks
    if training follows the 80/20 polarization rule. Each activity uses the best data
    available: second-by-second power, heart rate or pace, else activity averages.
    Always relay `data_quality` to the user: it says how reliable the result is.

    Use this to answer: "Am I training easy enough?"

    Args:
        days: Number of days to analyze (default 30).
        end_date: Last day of the period as YYYY-MM-DD (default today).
        use_streams: Download second-by-second data when useful (default True).

    Returns:
        ZoneDistribution as dict.
    """
    return await sport_science.get_zone_distribution(days, end_date, use_streams)


@mcp.tool()
async def get_fitness_trend(weeks: int = 8, end_date: str | None = None) -> dict:
    """Analyze weekly training volume and intensity trends.

    Groups activities by week and shows how distance, duration, and intensity evolve.
    Identifies week-over-week progression or regression.

    Use this to answer: "How has my training progressed?"

    Args:
        weeks: Number of weeks to analyze (default 8).
        end_date: Last day of the period as YYYY-MM-DD (default today).

    Returns:
        FitnessTrendSummary as dict.
    """
    return await sport_science.get_fitness_trend(weeks, end_date)


@mcp.tool()
async def get_race_readiness(
    target_distance_km: float = 10.0, end_date: str | None = None
) -> dict:
    """Assess readiness to race a given distance.

    Scores readiness 0-100 based on fitness, freshness, long run progress, and consistency.

    Use this to answer: "Am I ready for a 10K this weekend?"

    Common distances: 5 (5K), 10 (10K), 21.1 (half marathon), 42.2 (marathon).

    Args:
        target_distance_km: Target race distance.
        end_date: Assess readiness as of this day, YYYY-MM-DD (default today).

    Returns:
        RaceReadiness as dict.
    """
    return await sport_science.get_race_readiness(target_distance_km, end_date)


@mcp.resource("config://settings")
async def get_settings() -> str:
    """Return the current user settings.

    Returns JSON with max_hr, resting_hr, threshold_pace_min_per_km, weight_kg,
    lthr, ftp_watts and hr_zone_bounds.
    """
    if deps.config is None:
        raise RuntimeError("Config not initialized")
    return deps.config.model_dump_json(indent=2)


# Shared rules for prompts: the LLM interprets the tools' numbers, it never computes its own
_GROUNDING_RULES = """
Rules:
- Only use numbers returned by the tools; never estimate or compute metrics yourself.
- Relay each tool's data caveats (`data_quality`, `tss_methods`) in plain words, and lower
  your confidence when results rely on activity averages or default settings.
- Answer in the user's language, concisely, ending with 3 concrete recommendations.
"""


@mcp.prompt(title="Race readiness review")
def race_readiness_review(target_distance_km: float = 10.0, race_date: str = "") -> str:
    """Assess whether the athlete is ready for an upcoming race and how to prepare."""
    race = f"a {target_distance_km:g} km race"
    if race_date:
        race += f" on {race_date}"
    return f"""Assess my readiness for {race}.

1. Call get_race_readiness(target_distance_km={target_distance_km:g}) and explain the overall
   score and its four components (fitness, freshness, long run, consistency).
2. Call get_training_load(days=42) to explain my current fitness (CTL), fatigue (ATL) and
   form (TSB), and the training phase.
3. Call get_fitness_trend(weeks=8) to check recent volume and long-run progression.
4. {"Given the days left before the race date, say whether to build, maintain or taper." if race_date else "Say what I should focus on before racing."}
{_GROUNDING_RULES}"""


@mcp.prompt(title="Training block review")
def training_block_review(weeks: int = 8, end_date: str = "") -> str:
    """Review a block of training: load progression, intensity balance and injury risk."""
    period = f"the {weeks} weeks ending {end_date}" if end_date else f"my last {weeks} weeks"
    end_arg = f', end_date="{end_date}"' if end_date else ""
    return f"""Review my training over {period}.

1. Call get_fitness_trend(weeks={weeks}{end_arg}): weekly volume, progression, and any week
   above +10% distance (injury risk).
2. Call get_training_load(days={weeks * 7}{end_arg}): how fitness and fatigue evolved.
3. Call get_zone_distribution(days={weeks * 7}{end_arg}): intensity balance against the
   80/20 rule.
4. Summarize what went well, what to change, and whether the load was sustainable.
{_GROUNDING_RULES}"""


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    env = os.environ.get
    parser = argparse.ArgumentParser(
        prog="strava-sport-science-mcp",
        description="Strava sport-science MCP server (stdio by default).",
    )
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default=env("STRAVA_MCP_TRANSPORT", "stdio"),
        help="stdio (local client launches the server) or http (streamable HTTP, personal use)",
    )
    parser.add_argument(
        "--host", default=env("STRAVA_MCP_HOST", "127.0.0.1"),
        help="HTTP bind address (default 127.0.0.1; keep it and expose via a tunnel)",
    )
    parser.add_argument("--port", type=int, default=int(env("STRAVA_MCP_PORT", "8000")))
    parser.add_argument(
        "--allowed-host", action="append", dest="allowed_hosts",
        default=[h for h in env("STRAVA_MCP_ALLOWED_HOSTS", "").split(",") if h],
        help="Public hostname the server is reached through (repeatable), e.g. mcp.example.com",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the MCP server over stdio (default) or HTTP."""
    args = _parse_args(argv)

    if args.transport == "http":
        # Fail before touching Strava if the endpoint would be unprotected
        try:
            token = validate_token(os.environ.get("STRAVA_MCP_AUTH_TOKEN"))
        except ValueError as e:
            sys.exit(str(e))
        deps.initialize()
        run_http(mcp, args.host, args.port, token, args.allowed_hosts)
        return

    deps.initialize()
    mcp.run()


if __name__ == "__main__":
    main()
