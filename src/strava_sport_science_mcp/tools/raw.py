"""Raw Strava API tools that expose basic activity data."""

import time
from datetime import datetime, timedelta, timezone

from strava_sport_science_mcp.dependencies import client


async def get_activities(days_back: int = 30) -> list[dict]:
    """Fetch the authenticated athlete's recent activities from Strava.

    Use this to get a list of recent workouts including distance, duration,
    heart rate, and pace. Returns up to the last `days_back` days of activities.
    Each activity includes: name, sport_type, distance (meters), moving_time (seconds),
    average_heartrate, average_speed (m/s), start_date, and total_elevation_gain.

    Args:
        days_back: Number of days to look back (default 30).

    Returns:
        List of activity dicts.
    """
    cutoff_time = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp())
    activities = await client.get_all_activities(after=cutoff_time)

    return activities


async def get_activity_detail(activity_id: int) -> dict:
    """Fetch detailed information about a specific Strava activity.

    Use this when you need the full details of a workout including laps, splits,
    best efforts, and gear used. Requires the activity ID from get_activities.

    Args:
        activity_id: The activity ID.

    Returns:
        Detailed activity dict.
    """
    return await client.get_activity(activity_id)


async def get_athlete_profile() -> dict:
    """Fetch the authenticated athlete's Strava profile.

    Returns the athlete's name, stats, location, and measurement preferences.
    Use this to personalize training advice.

    Returns:
        Athlete profile dict.
    """
    return await client.get_athlete()


async def get_activity_streams(
    activity_id: int, stream_types: str = "time,heartrate,velocity_smooth,altitude"
) -> dict:
    """Fetch time-series stream data for a specific activity.

    Returns second-by-second data for the requested stream types.
    Available types: time, heartrate, velocity_smooth, altitude, cadence, distance, latlng.
    Pass as comma-separated string. Not all streams are available for all activities
    (e.g., heartrate requires a heart rate monitor).
    Use this for deep analysis of effort distribution within a single workout.

    Args:
        activity_id: The activity ID.
        stream_types: Comma-separated stream type names.

    Returns:
        Dict of stream data keyed by type.
    """
    keys = [k.strip() for k in stream_types.split(",")]
    return await client.get_activity_streams(activity_id, keys)
