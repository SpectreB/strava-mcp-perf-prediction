"""Pydantic models for Strava activity data."""

from datetime import datetime

from pydantic import BaseModel, Field


class Activity(BaseModel):
    """A Strava activity."""

    id: int = Field(..., description="Activity ID")
    name: str = Field(..., description="Activity name")
    sport_type: str = Field(..., description="Sport type (e.g., 'Run', 'Ride')")
    distance: float = Field(..., description="Distance in meters")
    moving_time: int = Field(..., description="Moving time in seconds")
    elapsed_time: int = Field(..., description="Elapsed time in seconds")
    total_elevation_gain: float = Field(..., description="Total elevation gain in meters")
    average_heartrate: float | None = Field(
        None, description="Average heart rate in bpm (None if no HR monitor)"
    )
    max_heartrate: float | None = Field(
        None, description="Max heart rate in bpm (None if no HR monitor)"
    )
    average_speed: float = Field(..., description="Average speed in m/s")
    start_date: datetime = Field(..., description="Activity start time")
    suffer_score: int | None = Field(None, description="Strava's suffer score (0-100)")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "id": 12345,
                "name": "Morning Run",
                "sport_type": "Run",
                "distance": 10000,
                "moving_time": 3000,
                "elapsed_time": 3200,
                "total_elevation_gain": 100,
                "average_heartrate": 145.5,
                "max_heartrate": 165,
                "average_speed": 3.33,
                "start_date": "2024-05-20T07:00:00Z",
                "suffer_score": 42,
            }
        }


class ActivityStream(BaseModel):
    """Time-series stream data for an activity."""

    time: list[int] = Field(..., description="Time in seconds since start")
    heartrate: list[float] | None = Field(None, description="Heart rate in bpm")
    velocity_smooth: list[float] | None = Field(None, description="Smoothed velocity in m/s")
    altitude: list[float] | None = Field(None, description="Altitude in meters")
    cadence: list[float] | None = Field(None, description="Cadence in steps/min (running) or rpm")
    distance: list[float] | None = Field(None, description="Distance in meters")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "time": [0, 1, 2, 3],
                "heartrate": [120.0, 125.0, 130.0, 135.0],
                "velocity_smooth": [3.0, 3.1, 3.2, 3.3],
                "altitude": [100.0, 105.0, 110.0, 115.0],
                "cadence": [180, 180, 185, 185],
                "distance": [0, 3, 6, 9],
            }
        }
