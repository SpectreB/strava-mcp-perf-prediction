"""MCP server entry point for Strava sport-science analysis."""

from mcp.server.fastmcp import FastMCP

import strava_sport_science_mcp.dependencies as deps
from strava_sport_science_mcp.tools import raw, sport_science

mcp = FastMCP(
    "strava-sport-science",
    description=(
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
async def get_training_load(days: int = 42) -> dict:
    """Analyze training load and fitness/fatigue balance.

    Computes CTL (fitness), ATL (fatigue), and TSB (form) using the Banister model.

    Use this to answer: "Am I overtraining?" or "How has my fitness evolved?"

    Args:
        days: Number of days to analyze (default 42).

    Returns:
        TrainingLoadSummary as dict.
    """
    return await sport_science.get_training_load(days)


@mcp.tool()
async def get_zone_distribution(days: int = 30) -> dict:
    """Analyze heart rate zone distribution.

    Computes the percentage of training time in each HR zone (Z1-Z5) and checks
    if training follows the 80/20 polarization rule.

    Use this to answer: "Am I training easy enough?"

    Args:
        days: Number of days to analyze (default 30).

    Returns:
        ZoneDistribution as dict.
    """
    return await sport_science.get_zone_distribution(days)


@mcp.tool()
async def get_fitness_trend(weeks: int = 8) -> dict:
    """Analyze weekly training volume and intensity trends.

    Groups activities by week and shows how distance, duration, and intensity evolve.
    Identifies week-over-week progression or regression.

    Use this to answer: "How has my training progressed?"

    Args:
        weeks: Number of weeks to analyze (default 8).

    Returns:
        FitnessTrendSummary as dict.
    """
    return await sport_science.get_fitness_trend(weeks)


@mcp.tool()
async def get_race_readiness(target_distance_km: float = 10.0) -> dict:
    """Assess readiness to race a given distance.

    Scores readiness 0-100 based on fitness, freshness, long run progress, and consistency.

    Use this to answer: "Am I ready for a 10K this weekend?"

    Common distances: 5 (5K), 10 (10K), 21.1 (half marathon), 42.2 (marathon).

    Args:
        target_distance_km: Target race distance.

    Returns:
        RaceReadiness as dict.
    """
    return await sport_science.get_race_readiness(target_distance_km)


@mcp.resource("config://settings")
async def get_settings() -> str:
    """Return the current user settings.

    Returns JSON with max_hr, resting_hr, threshold_pace_min_per_km, weight_kg.
    """
    if deps.config is None:
        raise RuntimeError("Config not initialized")
    return deps.config.model_dump_json(indent=2)


def main() -> None:
    """Run the MCP server."""
    deps.initialize()
    mcp.run()


if __name__ == "__main__":
    main()
