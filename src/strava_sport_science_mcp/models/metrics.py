"""Pydantic models for computed training metrics."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class DailyTrainingLoad(BaseModel):
    """Daily training load metrics."""

    date: date = Field(..., description="Date")
    tss: float = Field(..., description="Training Stress Score (0-500+ typical)")
    ctl: float = Field(..., description="Chronic Training Load (fitness)")
    atl: float = Field(..., description="Acute Training Load (fatigue)")
    tsb: float = Field(..., description="Training Stress Balance (form/freshness)")


class TrainingLoadSummary(BaseModel):
    """Summary of training load over a period."""

    daily_loads: list[DailyTrainingLoad] = Field(..., description="Daily TSS/CTL/ATL/TSB values")
    current_ctl: float = Field(..., description="Current CTL (fitness)")
    current_atl: float = Field(..., description="Current ATL (fatigue)")
    current_tsb: float = Field(..., description="Current TSB (freshness)")
    phase: Literal[
        "building", "maintaining", "detraining", "overreaching", "tapering"
    ] = Field(..., description="Current training phase")
    interpretation: str = Field(..., description="Plain-text interpretation of current state")


class ZoneBucket(BaseModel):
    """Heart rate zone bucket."""

    zone_name: str = Field(..., description="Zone name (Z1, Z2, etc.)")
    zone_number: int = Field(..., description="Zone number (1-5)")
    min_hr_pct: float = Field(..., description="Min HR as % of max HR")
    max_hr_pct: float = Field(..., description="Max HR as % of max HR")
    time_seconds: int = Field(..., description="Time in zone (seconds)")
    percentage: float = Field(..., description="Percentage of total time")


class ZoneDistribution(BaseModel):
    """Heart rate zone distribution."""

    zones: list[ZoneBucket] = Field(..., description="HR zones and time spent in each")
    total_time_seconds: int = Field(..., description="Total training time (seconds)")
    polarization_index: float = Field(..., description="Easy % minus hard % (80/20 ideal)")
    assessment: str = Field(..., description="Assessment of intensity distribution")


class WeeklyTrainingMetrics(BaseModel):
    """Weekly training summary."""

    week_start: date = Field(..., description="Start of ISO week")
    week_end: date = Field(..., description="End of ISO week")
    total_distance_km: float = Field(..., description="Total distance (km)")
    total_duration_hours: float = Field(..., description="Total moving time (hours)")
    total_tss: float = Field(..., description="Total TSS for week")
    activity_count: int = Field(..., description="Number of training sessions")
    avg_intensity_factor: float = Field(..., description="Average intensity factor")
    distance_change_pct: float | None = Field(
        None, description="Week-over-week distance change %"
    )


class FitnessTrendSummary(BaseModel):
    """Weekly fitness trend."""

    weeks: list[WeeklyTrainingMetrics] = Field(..., description="Weekly metrics")
    trend_assessment: str = Field(..., description="Assessment of trend (progressive, plateau, etc.)")


class RaceReadiness(BaseModel):
    """Race readiness assessment."""

    overall_score: float = Field(..., ge=0, le=100, description="Overall readiness 0-100")
    fitness_score: float = Field(..., ge=0, le=25, description="Fitness component 0-25")
    freshness_score: float = Field(..., ge=0, le=25, description="Freshness component 0-25")
    long_run_score: float = Field(..., ge=0, le=25, description="Long run readiness 0-25")
    consistency_score: float = Field(..., ge=0, le=25, description="Training consistency 0-25")
    target_distance_km: float = Field(..., description="Target race distance (km)")
    verdict: str = Field(..., description="Verdict (ready, mostly ready, undertrained, not ready)")
    recommendations: list[str] = Field(..., description="Specific areas to address")
