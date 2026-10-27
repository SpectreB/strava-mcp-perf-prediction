"""Tests for the setup CLI helpers."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from strava_sport_science_mcp.setup_cli import (
    estimate_max_hr,
    estimate_threshold_pace,
    read_env_file,
    set_env_var,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _run(days_ago: int, km: float, minutes: float, **extra: object) -> dict:
    return {
        "sport_type": "Run",
        "distance": km * 1000,
        "moving_time": minutes * 60,
        "start_date": (NOW - timedelta(days=days_ago)).isoformat(),
        **extra,
    }


def test_threshold_pace_one_hour_run_is_its_own_pace() -> None:
    """A 60-minute run projects to exactly its own pace."""
    pace, _ = estimate_threshold_pace([_run(10, 12.0, 60)], now=NOW)  # 5:00/km
    assert abs(pace - 5.0) < 0.01


def test_threshold_pace_picks_best_projection_and_skips_short_runs() -> None:
    """Shorter efforts project to a slower 60-min pace; runs under 15 min are ignored."""
    activities = [
        _run(5, 10.0, 45),  # 4:30/km for 45 min -> ~4:35/km over 60 min
        _run(6, 3.0, 12),   # 4:00/km but too short to extrapolate
        _run(7, 8.0, 44),   # 5:30/km
        {**_run(8, 20.0, 60), "sport_type": "Ride"},  # not a run
    ]
    pace, source = estimate_threshold_pace(activities, now=NOW)
    assert source["distance"] == 10000
    assert 4.5 < pace < 4.65


def test_threshold_pace_prefers_recent_runs() -> None:
    """Runs older than a year are only used when there are no recent ones."""
    old_fast, recent_slow = _run(500, 15.0, 60), _run(30, 12.0, 60)  # 4:00 vs 5:00/km
    pace, _ = estimate_threshold_pace([old_fast, recent_slow], now=NOW)
    assert abs(pace - 5.0) < 0.01
    pace, _ = estimate_threshold_pace([old_fast], now=NOW)
    assert abs(pace - 4.0) < 0.01


def test_threshold_pace_none_without_qualifying_runs() -> None:
    assert estimate_threshold_pace([_run(1, 2.0, 10)], now=NOW) is None


def test_max_hr_uses_highest_recorded_value() -> None:
    activities = [_run(1, 10, 50, max_heartrate=181.0), _run(2, 5, 25, max_heartrate=187.4), _run(3, 5, 25)]
    hr, _ = estimate_max_hr(activities)
    assert hr == 187
    assert estimate_max_hr([_run(1, 10, 50)]) is None


def test_set_env_var_updates_existing_and_appends_missing(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# comment\nSTRAVA_CLIENT_ID=123\nSTRAVA_REFRESH_TOKEN=old\n")

    set_env_var(env, "STRAVA_REFRESH_TOKEN", "new")
    set_env_var(env, "OTHER", "x")

    assert read_env_file(env) == {"STRAVA_CLIENT_ID": "123", "STRAVA_REFRESH_TOKEN": "new", "OTHER": "x"}
    assert env.read_text().startswith("# comment\n")
    assert env.stat().st_mode & 0o777 == 0o600
