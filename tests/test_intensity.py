"""Tests for the intensity pipeline (TSS and zones with data-source fallbacks)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from strava_sport_science_mcp.config import UserConfig
from strava_sport_science_mcp.tools.intensity import (
    activity_zone_times,
    calculate_tss,
    format_pace,
    hr_zone_bounds,
    normalize_streams,
    pace_zone_bounds,
    stream_zone_times,
    zone_index,
)

CONFIG = UserConfig(max_hr=200, resting_hr=50, threshold_pace_min_per_km=5.0, ftp_watts=250)
THRESHOLD_SPEED = 1000 / 300  # 5:00/km in m/s


def _activity(**fields: object) -> dict:
    return {"sport_type": "Run", "moving_time": 3600, "distance": 10000, **fields}


# --- TSS fallbacks -----------------------------------------------------------------


def test_tss_prefers_power_when_ftp_and_power_meter() -> None:
    ride = _activity(sport_type="Ride", device_watts=True, weighted_average_watts=250,
                     average_heartrate=150, average_speed=8.0)
    assert calculate_tss(ride, CONFIG) == pytest.approx((100.0, "power"))


def test_tss_ignores_estimated_power_and_missing_ftp() -> None:
    estimated = _activity(sport_type="Ride", device_watts=False, weighted_average_watts=250,
                          average_heartrate=170)
    assert calculate_tss(estimated, CONFIG)[1] == "heart_rate"
    no_ftp = UserConfig(max_hr=200, resting_hr=50)
    with_meter = {**estimated, "device_watts": True}
    assert calculate_tss(with_meter, no_ftp)[1] == "heart_rate"


def test_tss_run_uses_pace_then_heart_rate_then_duration() -> None:
    assert calculate_tss(_activity(average_speed=THRESHOLD_SPEED), CONFIG) == pytest.approx(
        (100.0, "pace")
    )
    # Treadmill run without distance/speed falls back to heart rate
    assert calculate_tss(_activity(average_speed=0, average_heartrate=150), CONFIG)[1] == (
        "heart_rate"
    )
    assert calculate_tss(_activity(average_speed=0), CONFIG) == pytest.approx((50.0, "duration"))


def test_hr_tss_is_100_per_hour_at_threshold_hr() -> None:
    """Default LTHR is 90% of max HR (180 bpm here)."""
    swim = _activity(sport_type="Swim", average_heartrate=180)
    assert calculate_tss(swim, CONFIG)[0] == pytest.approx(100.0)
    easy = _activity(sport_type="Swim", average_heartrate=115)  # half of HR reserve
    assert calculate_tss(easy, CONFIG)[0] == pytest.approx(25.0)


# --- Zone models -------------------------------------------------------------------


def test_zone_index_boundaries() -> None:
    bounds = [100.0, 120.0, 140.0, 160.0]
    assert [zone_index(v, bounds) for v in (99, 100, 139.9, 160, 300)] == [0, 1, 2, 4, 4]


def test_hr_zone_bounds_prefer_strava_custom_zones() -> None:
    assert hr_zone_bounds(CONFIG) == pytest.approx([120, 140, 160, 180])
    custom = UserConfig(max_hr=200, hr_zone_bounds=[130, 150, 165, 178])
    assert hr_zone_bounds(custom) == [130, 150, 165, 178]


def test_pace_zones_follow_friel_percentages() -> None:
    bounds = pace_zone_bounds(CONFIG)
    # Z4 starts at 106% of threshold pace (5:18/km), Z5 at 99% (4:57/km)
    assert 1000 / bounds[2] / 60 == pytest.approx(5.0 * 1.06)
    assert 1000 / bounds[3] / 60 == pytest.approx(5.0 * 0.99)


def test_format_pace() -> None:
    assert format_pace(4.55) == "4:33/km"
    assert format_pace(5.0) == "5:00/km"


# --- Stream zone times -------------------------------------------------------------


def test_stream_zone_times_skip_pauses_and_stopped_samples() -> None:
    streams = {
        "time": [0, 10, 20, 30, 200, 210],  # 30 -> 200 is a pause
        "heartrate": [110, 130, 150, 170, 190, 190],
        "moving": [True, True, False, True, True, True],
    }
    times = stream_zone_times(streams, "heartrate", hr_zone_bounds(CONFIG))
    # Z1: 0-10 (110), Z2: 10-20 (130); 20-30 not moving; 30-200 gap; Z5: 200-210 (190)
    assert times == [10, 10, 0, 0, 10]


def test_normalize_streams_flattens_key_by_type_response() -> None:
    raw = {"time": {"data": [0, 1], "series_type": "time"}, "heartrate": {"data": []}}
    assert normalize_streams(raw) == {"time": [0, 1]}


# --- Zone source selection ---------------------------------------------------------


def _steady_streams(key: str, value: float, seconds: int = 600) -> dict[str, list]:
    return {"time": list(range(0, seconds + 1, 5)), key: [value] * (seconds // 5 + 1)}


def test_zone_source_priority_power_hr_pace_streams() -> None:
    ride = _activity(sport_type="Ride", device_watts=True, weighted_average_watts=200)
    streams = {**_steady_streams("watts", 300), "heartrate": [130] * 121}
    times, source = activity_zone_times(ride, streams, CONFIG) or ([], "")
    assert source == "power_stream" and times[4] == 600  # 300 W = 120% FTP

    run = _activity(average_speed=3.0, has_heartrate=True)
    streams = {**_steady_streams("heartrate", 130), "velocity_smooth": [THRESHOLD_SPEED] * 121}
    assert (activity_zone_times(run, streams, CONFIG) or ([], ""))[1] == "hr_stream"

    run_no_hr = _activity(average_speed=3.0)
    streams = _steady_streams("velocity_smooth", THRESHOLD_SPEED)
    times, source = activity_zone_times(run_no_hr, streams, CONFIG) or ([], "")
    assert source == "pace_stream" and times[3] == 600  # threshold pace = Z4


def test_zone_source_falls_back_to_averages() -> None:
    hr_run = _activity(average_speed=3.0, average_heartrate=165)
    times, source = activity_zone_times(hr_run, None, CONFIG) or ([], "")
    assert source == "hr_average"
    assert times == [0, 0, 0, 3600, 0]  # 165 bpm = 82.5% of max HR -> Z4 (80-90%)

    pace_run = _activity(average_speed=THRESHOLD_SPEED * 0.8)  # easy pace
    times, source = activity_zone_times(pace_run, None, CONFIG) or ([], "")
    assert source == "pace_average" and times[1] == 3600

    ride_no_data = _activity(sport_type="Ride", average_speed=8.0)
    assert activity_zone_times(ride_no_data, None, CONFIG) is None


# --- End-to-end zone distribution and end_date -------------------------------------


class _FakeStravaClient:
    """Two runs: one with HR streams, one pace-only without streams; plus a ride with no data."""

    def __init__(self) -> None:
        self.now = datetime.now(UTC)
        self.stream_calls: list[int] = []
        self.activities = [
            {"id": 1, "sport_type": "Run", "moving_time": 600, "distance": 2000,
             "average_speed": 3.3, "has_heartrate": True, "average_heartrate": 130,
             "start_date": (self.now - timedelta(days=2)).isoformat()},
            {"id": 2, "sport_type": "Run", "moving_time": 1200, "distance": 3000,
             "average_speed": THRESHOLD_SPEED * 0.8,
             "start_date": (self.now - timedelta(days=4)).isoformat()},
            {"id": 3, "sport_type": "Ride", "moving_time": 3600, "distance": 30000,
             "average_speed": 8.0, "start_date": (self.now - timedelta(days=5)).isoformat()},
            {"id": 4, "sport_type": "Run", "moving_time": 3600, "distance": 12000,
             "average_speed": 3.33, "start_date": (self.now - timedelta(days=90)).isoformat()},
        ]

    async def get_all_activities(
        self, after: int | None = None, before: int | None = None
    ) -> list[dict]:
        def ts(a: dict) -> float:
            return datetime.fromisoformat(a["start_date"]).timestamp()

        return [a for a in self.activities
                if (after is None or ts(a) > after) and (before is None or ts(a) < before)]

    async def get_activity_streams(self, activity_id: int, keys: list[str]) -> dict:
        self.stream_calls.append(activity_id)
        if activity_id == 1:
            return {"time": {"data": list(range(0, 601, 5))},
                    "heartrate": {"data": [130.0] * 121}}
        raise RuntimeError("Strava API error (HTTP 404): Record Not Found")


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _FakeStravaClient:
    import strava_sport_science_mcp.dependencies as deps
    from strava_sport_science_mcp import stream_cache

    client = _FakeStravaClient()
    monkeypatch.setattr(deps, "client", client)
    monkeypatch.setattr(deps, "config", CONFIG)
    monkeypatch.setattr(stream_cache, "cache_dir", lambda: tmp_path / "streams")
    return client


async def test_zone_distribution_mixes_sources_and_reports_quality(
    fake_env: _FakeStravaClient,
) -> None:
    from strava_sport_science_mcp.tools.sport_science import get_zone_distribution

    result = await get_zone_distribution(days=30)

    assert result["data_sources"] == {"hr_stream": 1, "pace_average": 1}
    assert result["excluded_activities"] == 1  # the ride without HR/power
    assert result["total_time_seconds"] == 1800
    zones = {z["zone_number"]: z["time_seconds"] for z in result["zones"]}
    assert zones[2] == 1800  # 130 bpm = 65% max HR; 80% threshold speed = Friel Z2
    assert "1 of 2 activities analysed second by second" in result["data_quality"]
    assert "pace zones" in result["data_quality"]

    # Streams are cached (incl. "no streams" 404s): a second call makes no API requests
    calls = len(fake_env.stream_calls)
    await get_zone_distribution(days=30)
    assert len(fake_env.stream_calls) == calls


async def test_zone_distribution_without_streams_uses_averages(
    fake_env: _FakeStravaClient,
) -> None:
    from strava_sport_science_mcp.tools.sport_science import get_zone_distribution

    result = await get_zone_distribution(days=30, use_streams=False)
    assert result["data_sources"] == {"hr_average": 1, "pace_average": 1}
    assert fake_env.stream_calls == []


async def test_end_date_analyzes_a_past_window(fake_env: _FakeStravaClient) -> None:
    from strava_sport_science_mcp.tools.sport_science import get_training_load

    end = (fake_env.now - timedelta(days=85)).date()
    result = await get_training_load(days=14, end_date=end.isoformat())

    loads = result["daily_loads"]
    assert [load["date"] for load in (loads[0], loads[-1])] == [end - timedelta(days=13), end]
    assert len(loads) == 14  # full window even though the first activity is inside it
    # Only the run from 90 days ago is in the window; recent activities are after end_date
    assert result["tss_methods"] == {"pace": 1}
    assert sum(load["tss"] for load in loads) == pytest.approx(100, rel=0.01)


async def test_invalid_end_date_is_rejected(fake_env: _FakeStravaClient) -> None:
    from strava_sport_science_mcp.tools.sport_science import get_fitness_trend

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        await get_fitness_trend(end_date="07/06/2026")
