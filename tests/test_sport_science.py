"""Unit tests for sport-science computations."""

import pytest

from strava_sport_science_mcp.config import UserConfig
from strava_sport_science_mcp.tools.sport_science import (
    _build_daily_tss_series,
    _calculate_tss,
    _compute_ctl_atl_tsb,
)


def test_tss_one_hour_at_threshold() -> None:
    """Test that 1 hour at threshold pace equals 100 TSS."""
    config = UserConfig(
        max_hr=190,
        resting_hr=60,
        threshold_pace_min_per_km=5.0,
        weight_kg=70,
    )

    # 1 hour at exactly threshold pace
    threshold_pace_ms = 1000 / (5.0 * 60)  # ~3.33 m/s
    activity = {
        "sport_type": "Run",
        "average_speed": threshold_pace_ms,
        "moving_time": 3600,  # 1 hour
        "average_heartrate": 165,
    }

    tss = _calculate_tss(activity, config)
    assert abs(tss - 100) < 1, f"Expected ~100 TSS, got {tss}"


def test_tss_thirty_minutes_at_threshold() -> None:
    """Test that 30 min at threshold pace is ~50 TSS."""
    config = UserConfig(
        max_hr=190,
        resting_hr=60,
        threshold_pace_min_per_km=5.0,
        weight_kg=70,
    )

    threshold_pace_ms = 1000 / (5.0 * 60)
    activity = {
        "sport_type": "Run",
        "average_speed": threshold_pace_ms,
        "moving_time": 1800,  # 30 min
        "average_heartrate": 165,
    }

    tss = _calculate_tss(activity, config)
    assert abs(tss - 50) < 1, f"Expected ~50 TSS, got {tss}"


def test_tss_slower_than_threshold() -> None:
    """Test that slower pace than threshold gives lower TSS."""
    config = UserConfig(
        max_hr=190,
        resting_hr=60,
        threshold_pace_min_per_km=5.0,
        weight_kg=70,
    )

    threshold_pace_ms = 1000 / (5.0 * 60)
    slower_pace_ms = threshold_pace_ms * 0.8  # 80% of threshold pace

    activity = {
        "sport_type": "Run",
        "average_speed": slower_pace_ms,
        "moving_time": 3600,  # 1 hour
        "average_heartrate": 145,
    }

    tss = _calculate_tss(activity, config)
    assert tss < 100, f"Expected TSS < 100, got {tss}"


def test_tss_faster_than_threshold() -> None:
    """Test that faster pace than threshold gives higher TSS."""
    config = UserConfig(
        max_hr=190,
        resting_hr=60,
        threshold_pace_min_per_km=5.0,
        weight_kg=70,
    )

    threshold_pace_ms = 1000 / (5.0 * 60)
    faster_pace_ms = threshold_pace_ms * 1.2  # 120% of threshold pace

    activity = {
        "sport_type": "Run",
        "average_speed": faster_pace_ms,
        "moving_time": 3600,  # 1 hour
        "average_heartrate": 175,
    }

    tss = _calculate_tss(activity, config)
    assert tss > 100, f"Expected TSS > 100, got {tss}"


def test_ctl_atl_convergence() -> None:
    """Test that CTL and ATL converge toward weekly average TSS."""
    config = UserConfig(
        max_hr=190,
        resting_hr=60,
        threshold_pace_min_per_km=5.0,
        weight_kg=70,
    )

    # Simulate 6 weeks of 100 TSS per day
    threshold_pace_ms = 1000 / (5.0 * 60)
    activity_template = {
        "sport_type": "Run",
        "average_speed": threshold_pace_ms,
        "moving_time": 3600,
        "average_heartrate": 165,
    }

    activities = []
    from datetime import datetime, timedelta, timezone

    base_date = datetime.now(timezone.utc) - timedelta(days=42)
    for i in range(42):
        activity = activity_template.copy()
        activity_date = base_date + timedelta(days=i)
        activity["start_date"] = activity_date.isoformat()
        activities.append(activity)

    daily_series = _build_daily_tss_series(activities, config)
    daily_loads = _compute_ctl_atl_tsb(daily_series)

    # After 42 days of consistent 100 TSS, CTL should be close to 100
    final_ctl = daily_loads[-1].ctl
    assert 90 < final_ctl < 110, f"Expected CTL ~100, got {final_ctl}"


def test_ctl_slower_growth_than_atl() -> None:
    """Test that ATL reacts faster than CTL to changes."""
    config = UserConfig(
        max_hr=190,
        resting_hr=60,
        threshold_pace_min_per_km=5.0,
        weight_kg=70,
    )

    threshold_pace_ms = 1000 / (5.0 * 60)
    activity_template = {
        "sport_type": "Run",
        "average_speed": threshold_pace_ms,
        "moving_time": 3600,
        "average_heartrate": 165,
    }

    activities = []
    from datetime import datetime, timedelta, timezone

    base_date = datetime.now(timezone.utc) - timedelta(days=21)

    # First 7 days: 100 TSS per day
    for i in range(7):
        activity = activity_template.copy()
        activity_date = base_date + timedelta(days=i)
        activity["start_date"] = activity_date.isoformat()
        activities.append(activity)

    # Next 7 days: 200 TSS per day
    activity_template_hard = activity_template.copy()
    activity_template_hard["moving_time"] = 7200  # 2 hours
    for i in range(7, 14):
        activity = activity_template_hard.copy()
        activity_date = base_date + timedelta(days=i)
        activity["start_date"] = activity_date.isoformat()
        activities.append(activity)

    # Next 7 days: back to 100 TSS
    for i in range(14, 21):
        activity = activity_template.copy()
        activity_date = base_date + timedelta(days=i)
        activity["start_date"] = activity_date.isoformat()
        activities.append(activity)

    daily_series = _build_daily_tss_series(activities, config)
    daily_loads = _compute_ctl_atl_tsb(daily_series)

    # At day 7 (after high-TSS week)
    ctl_at_7 = daily_loads[6].ctl
    atl_at_7 = daily_loads[6].atl

    # ATL should have increased more than CTL
    ctl_increase = ctl_at_7 - daily_loads[0].ctl
    atl_increase = atl_at_7 - daily_loads[0].atl

    assert atl_increase > ctl_increase, (
        f"ATL should increase faster than CTL. "
        f"CTL +{ctl_increase:.1f}, ATL +{atl_increase:.1f}"
    )


def test_tsb_equals_ctl_minus_atl() -> None:
    """Test that TSB = CTL - ATL at every point."""
    config = UserConfig(
        max_hr=190,
        resting_hr=60,
        threshold_pace_min_per_km=5.0,
        weight_kg=70,
    )

    threshold_pace_ms = 1000 / (5.0 * 60)
    activity_template = {
        "sport_type": "Run",
        "average_speed": threshold_pace_ms,
        "moving_time": 3600,
        "average_heartrate": 165,
    }

    activities = []
    from datetime import datetime, timedelta, timezone

    base_date = datetime.now(timezone.utc) - timedelta(days=30)
    for i in range(30):
        activity = activity_template.copy()
        activity_date = base_date + timedelta(days=i)
        activity["start_date"] = activity_date.isoformat()
        activities.append(activity)

    daily_series = _build_daily_tss_series(activities, config)
    daily_loads = _compute_ctl_atl_tsb(daily_series)

    for load in daily_loads:
        expected_tsb = load.ctl - load.atl
        assert abs(load.tsb - expected_tsb) < 0.01, (
            f"TSB mismatch on {load.date}: "
            f"TSB={load.tsb}, CTL-ATL={expected_tsb}"
        )
