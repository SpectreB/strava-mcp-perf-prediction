"""Shared test fixtures."""

import random
from datetime import datetime, timedelta, timezone

import pytest

from strava_sport_science_mcp.config import UserConfig
from strava_sport_science_mcp.models.activity import Activity


@pytest.fixture
def mock_config() -> UserConfig:
    """Create a mock user config for testing."""
    return UserConfig(
        max_hr=190,
        resting_hr=60,
        threshold_pace_min_per_km=5.0,
        weight_kg=70,
    )


@pytest.fixture
def mock_activities() -> list[dict]:
    """Generate 60 days of realistic mock activities.

    Mix of:
    - 3-4 easy runs per week
    - 1 long run per week
    - 1 interval/tempo session per week
    - 1-2 cross-training (cycling) sessions
    - 1-2 rest days

    Returns:
        List of activity dicts.
    """
    random.seed(42)  # Deterministic for reproducibility

    activities: list[dict] = []
    base_time = datetime.now(timezone.utc) - timedelta(days=60)
    activity_id = 1

    # Generate 60 days of activities
    for day_offset in range(60):
        current_date = base_time + timedelta(days=day_offset)
        day_of_week = current_date.weekday()  # 0 = Monday, 6 = Sunday

        # Probability of activity on this day
        if day_of_week == 6:  # Sunday - long run
            activities.append(
                _create_activity(
                    activity_id,
                    current_date,
                    name="Long Run",
                    sport_type="Run",
                    distance=random.uniform(18000, 25000),  # 18-25 km
                    moving_time=random.randint(5400, 7200),  # 90-120 min
                    avg_hr=random.uniform(140, 150),
                    avg_speed=random.uniform(2.4, 2.8),
                    elevation=random.uniform(100, 400),
                )
            )
            activity_id += 1

        elif day_of_week == 4:  # Friday - interval/tempo
            activities.append(
                _create_activity(
                    activity_id,
                    current_date,
                    name="Interval Session",
                    sport_type="Run",
                    distance=random.uniform(6000, 10000),  # 6-10 km
                    moving_time=random.randint(1800, 2400),  # 30-40 min
                    avg_hr=random.uniform(165, 175),
                    avg_speed=random.uniform(3.3, 3.8),
                    elevation=random.uniform(50, 200),
                )
            )
            activity_id += 1

        elif day_of_week == 2:  # Wednesday - easy run or cross-training
            if random.random() < 0.6:
                activities.append(
                    _create_activity(
                        activity_id,
                        current_date,
                        name="Easy Run",
                        sport_type="Run",
                        distance=random.uniform(8000, 12000),  # 8-12 km
                        moving_time=random.randint(2400, 3600),  # 40-60 min
                        avg_hr=random.uniform(135, 145),
                        avg_speed=random.uniform(2.5, 3.0),
                        elevation=random.uniform(50, 150),
                    )
                )
            else:
                activities.append(
                    _create_activity(
                        activity_id,
                        current_date,
                        name="Cycling",
                        sport_type="Ride",
                        distance=random.uniform(40000, 60000),  # 40-60 km
                        moving_time=random.randint(5400, 7200),  # 90-120 min
                        avg_hr=random.uniform(130, 140),
                        avg_speed=random.uniform(6, 8),  # m/s = 21-28 km/h
                        elevation=random.uniform(200, 500),
                    )
                )
            activity_id += 1

        else:  # Other days - probability of easy run or rest
            if random.random() < 0.5:
                activities.append(
                    _create_activity(
                        activity_id,
                        current_date,
                        name="Easy Run",
                        sport_type="Run",
                        distance=random.uniform(8000, 12000),  # 8-12 km
                        moving_time=random.randint(2400, 3600),  # 40-60 min
                        avg_hr=random.uniform(135, 145),
                        avg_speed=random.uniform(2.5, 3.0),
                        elevation=random.uniform(50, 150),
                    )
                )
                activity_id += 1

    return activities


def _create_activity(
    activity_id: int,
    start_date: datetime,
    name: str,
    sport_type: str,
    distance: float,
    moving_time: int,
    avg_hr: float,
    avg_speed: float,
    elevation: float,
) -> dict:
    """Create a mock activity dict.

    Args:
        activity_id: Unique activity ID.
        start_date: Activity start time.
        name: Activity name.
        sport_type: Sport type (e.g., "Run").
        distance: Distance in meters.
        moving_time: Moving time in seconds.
        avg_hr: Average heart rate in bpm.
        avg_speed: Average speed in m/s.
        elevation: Total elevation gain in meters.

    Returns:
        Activity dict matching Strava API format.
    """
    max_hr = avg_hr + random.uniform(15, 25)  # Max HR is avg + 15-25

    return {
        "id": activity_id,
        "name": name,
        "sport_type": sport_type,
        "distance": distance,
        "moving_time": moving_time,
        "elapsed_time": moving_time + random.randint(60, 300),
        "total_elevation_gain": elevation,
        "average_heartrate": avg_hr,
        "max_heartrate": max_hr,
        "average_speed": avg_speed,
        "start_date": start_date.isoformat(),
        "suffer_score": random.randint(10, 100) if sport_type == "Run" else None,
    }
