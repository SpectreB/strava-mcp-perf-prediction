"""Sport-science tools for training analysis."""

from datetime import date, datetime, timedelta, timezone

from strava_sport_science_mcp.dependencies import client, config
from strava_sport_science_mcp.models.metrics import (
    DailyTrainingLoad,
    FitnessTrendSummary,
    RaceReadiness,
    TrainingLoadSummary,
    WeeklyTrainingMetrics,
    ZoneBucket,
    ZoneDistribution,
)


def _calculate_tss(activity: dict, config_obj: object) -> float:
    """Calculate Training Stress Score for an activity.

    Uses a simplified rTSS formula for running, falls back to hrTSS for other sports.

    Args:
        activity: Activity dict from Strava.
        config_obj: UserConfig with max_hr and threshold_pace_min_per_km.

    Returns:
        TSS value (typically 0-500+).
    """
    moving_time_hours = activity["moving_time"] / 3600
    sport_type = activity.get("sport_type", "").lower()

    # For running activities, use pace-based rTSS
    if "run" in sport_type:
        avg_speed_ms = activity["average_speed"]

        # Threshold pace in m/s
        threshold_pace_min_per_km = config_obj.threshold_pace_min_per_km
        threshold_pace_ms = 1000 / (threshold_pace_min_per_km * 60)

        # Intensity factor
        intensity_factor = threshold_pace_ms / avg_speed_ms if avg_speed_ms > 0 else 0

        # rTSS = (hours) * IF^2 * 100
        rTSS = moving_time_hours * (intensity_factor ** 2) * 100
        return rTSS

    # For other sports with HR data, use hrTSS
    if activity.get("average_heartrate") is not None:
        avg_hr = activity["average_heartrate"]
        max_hr = config_obj.max_hr

        hrTSS = moving_time_hours * ((avg_hr / max_hr) ** 2) * 100
        return hrTSS

    # Fallback: estimate based on duration alone (moderate intensity)
    return moving_time_hours * 50


def _build_daily_tss_series(
    activities: list[dict], config_obj: object
) -> list[tuple[date, float]]:
    """Build a daily TSS series from activities.

    Args:
        activities: List of activity dicts.
        config_obj: UserConfig instance.

    Returns:
        List of (date, daily_tss) tuples in chronological order.
    """
    daily_tss: dict[date, float] = {}

    for activity in activities:
        activity_date = datetime.fromisoformat(
            activity["start_date"].replace("Z", "+00:00")
        ).date()
        tss = _calculate_tss(activity, config_obj)

        if activity_date not in daily_tss:
            daily_tss[activity_date] = 0
        daily_tss[activity_date] += tss

    # Return sorted by date
    return sorted(daily_tss.items())


def _compute_ctl_atl_tsb(
    daily_series: list[tuple[date, float]],
) -> list[DailyTrainingLoad]:
    """Compute CTL, ATL, TSB using exponential moving averages.

    Args:
        daily_series: List of (date, daily_tss) tuples.

    Returns:
        List of DailyTrainingLoad with CTL/ATL/TSB for each day.
    """
    results: list[DailyTrainingLoad] = []
    ctl = 0.0
    atl = 0.0

    for activity_date, daily_tss in daily_series:
        ctl = ctl + (daily_tss - ctl) / 42
        atl = atl + (daily_tss - atl) / 7
        tsb = ctl - atl

        results.append(
            DailyTrainingLoad(date=activity_date, tss=daily_tss, ctl=ctl, atl=atl, tsb=tsb)
        )

    return results


def _determine_training_phase(daily_loads: list[DailyTrainingLoad]) -> str:
    """Determine current training phase based on CTL trajectory.

    Args:
        daily_loads: List of DailyTrainingLoad.

    Returns:
        Phase name: "building", "maintaining", "detraining", "overreaching", "tapering".
    """
    if len(daily_loads) < 7:
        return "building"

    last_7 = daily_loads[-7:]
    ctl_first = last_7[0].ctl
    ctl_last = last_7[-1].ctl

    # Calculate CTL change over 7 days
    ctl_change_pct = ((ctl_last - ctl_first) / ctl_first * 100) if ctl_first > 0 else 0

    current_ctl = ctl_last
    current_atl = last_7[-1].atl
    current_tsb = last_7[-1].tsb

    # Determine phase
    if ctl_change_pct > 2:  # CTL rising
        if current_atl > current_ctl * 1.1:
            return "overreaching"
        else:
            return "building"
    elif -5 <= ctl_change_pct <= 2:  # CTL stable
        return "maintaining"
    else:  # CTL dropping
        if current_tsb > 5:
            return "tapering"
        else:
            return "detraining"


async def get_training_load(days: int = 42) -> dict:
    """Analyze training load and fitness/fatigue balance over a period.

    Computes CTL (Chronic Training Load = fitness), ATL (Acute Training Load = fatigue),
    and TSB (Training Stress Balance = form/freshness) using the Banister impulse-response model.

    Use this to answer questions like:
    - "Am I overtraining?"
    - "How has my fitness evolved?"
    - "Am I in good form right now?"

    Args:
        days: Number of days to analyze (default 42).

    Returns:
        TrainingLoadSummary as dict.
    """
    if client is None or config is None:
        raise RuntimeError("Dependencies not initialized")

    cutoff_time = int(
        (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    )
    activities = await client.get_all_activities(after=cutoff_time)

    daily_series = _build_daily_tss_series(activities, config)

    if not daily_series:
        # No activities, return empty summary
        summary = TrainingLoadSummary(
            daily_loads=[],
            current_ctl=0,
            current_atl=0,
            current_tsb=0,
            phase="maintaining",
            interpretation="No training data available for the specified period.",
        )
        return summary.model_dump()

    daily_loads = _compute_ctl_atl_tsb(daily_series)
    current_ctl = daily_loads[-1].ctl
    current_atl = daily_loads[-1].atl
    current_tsb = daily_loads[-1].tsb
    phase = _determine_training_phase(daily_loads)

    # Generate interpretation
    if phase == "building":
        interpretation = (
            f"Your fitness (CTL) is at {current_ctl:.1f}, fatigue (ATL) at {current_atl:.1f}, "
            f"and form (TSB) at {current_tsb:.1f}. You're in a building phase — "
            "fitness is trending up. Keep pushing but watch for fatigue."
        )
    elif phase == "maintaining":
        interpretation = (
            f"Your fitness is stable at {current_ctl:.1f} with ATL at {current_atl:.1f}. "
            "You're in a maintaining phase. Form (TSB) is at {current_tsb:.1f}."
        )
    elif phase == "overreaching":
        interpretation = (
            f"You're overreaching: CTL is {current_ctl:.1f} but ATL is high at {current_atl:.1f}. "
            f"Form (TSB) is {current_tsb:.1f}. You're accumulating fatigue faster than fitness. "
            "Take an easy week soon."
        )
    elif phase == "tapering":
        interpretation = (
            f"You're tapering: CTL dropping but TSB rising ({current_tsb:.1f}). "
            "You're freshening up. This is good before a race."
        )
    else:  # detraining
        interpretation = (
            f"You're detraining: CTL is dropping to {current_ctl:.1f} with TSB at {current_tsb:.1f}. "
            "Fitness is decreasing. Consider increasing training frequency or intensity."
        )

    summary = TrainingLoadSummary(
        daily_loads=daily_loads,
        current_ctl=current_ctl,
        current_atl=current_atl,
        current_tsb=current_tsb,
        phase=phase,
        interpretation=interpretation,
    )

    return summary.model_dump()


async def get_zone_distribution(days: int = 30) -> dict:
    """Analyze heart rate zone distribution over a training period.

    Computes the percentage of total training time spent in each heart rate zone (Z1-Z5).
    Also calculates a polarization index to check if training follows the 80/20 rule
    (80% easy, 20% hard).

    Use this to answer questions like:
    - "Am I training easy enough?"
    - "What does my intensity distribution look like?"
    - "Am I doing too much Zone 3 (no man's land)?"

    Args:
        days: Number of days to analyze (default 30).

    Returns:
        ZoneDistribution as dict.
    """
    if client is None or config is None:
        raise RuntimeError("Dependencies not initialized")

    cutoff_time = int(
        (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    )
    activities = await client.get_all_activities(after=cutoff_time)

    max_hr = config.max_hr

    zone_times = {
        1: 0,  # < 60%
        2: 0,  # 60-70%
        3: 0,  # 70-80%
        4: 0,  # 80-90%
        5: 0,  # 90-100%
    }

    for activity in activities:
        avg_hr = activity.get("average_heartrate")

        if avg_hr is None:
            continue

        hr_pct = (avg_hr / max_hr) * 100
        moving_time = activity["moving_time"]

        # Classify activity into zone based on average HR
        if hr_pct < 60:
            zone = 1
        elif hr_pct < 70:
            zone = 2
        elif hr_pct < 80:
            zone = 3
        elif hr_pct < 90:
            zone = 4
        else:
            zone = 5

        zone_times[zone] += moving_time

    total_time = sum(zone_times.values())

    if total_time == 0:
        return ZoneDistribution(
            zones=[],
            total_time_seconds=0,
            polarization_index=0,
            assessment="No training data with heart rate available.",
        ).model_dump()

    zone_buckets = [
        ZoneBucket(
            zone_name="Z1 (Recovery)",
            zone_number=1,
            min_hr_pct=0,
            max_hr_pct=60,
            time_seconds=zone_times[1],
            percentage=(zone_times[1] / total_time) * 100,
        ),
        ZoneBucket(
            zone_name="Z2 (Aerobic)",
            zone_number=2,
            min_hr_pct=60,
            max_hr_pct=70,
            time_seconds=zone_times[2],
            percentage=(zone_times[2] / total_time) * 100,
        ),
        ZoneBucket(
            zone_name="Z3 (Tempo)",
            zone_number=3,
            min_hr_pct=70,
            max_hr_pct=80,
            time_seconds=zone_times[3],
            percentage=(zone_times[3] / total_time) * 100,
        ),
        ZoneBucket(
            zone_name="Z4 (Threshold)",
            zone_number=4,
            min_hr_pct=80,
            max_hr_pct=90,
            time_seconds=zone_times[4],
            percentage=(zone_times[4] / total_time) * 100,
        ),
        ZoneBucket(
            zone_name="Z5 (VO2max)",
            zone_number=5,
            min_hr_pct=90,
            max_hr_pct=100,
            time_seconds=zone_times[5],
            percentage=(zone_times[5] / total_time) * 100,
        ),
    ]

    easy_pct = zone_buckets[0].percentage + zone_buckets[1].percentage
    hard_pct = zone_buckets[3].percentage + zone_buckets[4].percentage
    z3_pct = zone_buckets[2].percentage
    polarization_index = easy_pct - hard_pct

    # Generate assessment
    if easy_pct >= 75 and hard_pct >= 15:
        assessment = "Well-polarized training. Good intensity distribution."
    elif z3_pct > 30:
        assessment = (
            "Too much time in Zone 3 (tempo/no man's land). "
            "Consider going easier on easy days and harder on hard days."
        )
    elif easy_pct < 60:
        assessment = (
            "Training too intensely overall. Risk of overtraining. "
            "Add more Zone 1-2 sessions."
        )
    elif hard_pct < 10:
        assessment = "Not enough high-intensity work. Consider adding interval sessions."
    else:
        assessment = "Reasonable intensity distribution. Keep it up."

    return ZoneDistribution(
        zones=zone_buckets,
        total_time_seconds=total_time,
        polarization_index=polarization_index,
        assessment=assessment,
    ).model_dump()


async def get_fitness_trend(weeks: int = 8) -> dict:
    """Analyze weekly training volume and intensity trends.

    Groups activities by week and shows how distance, duration, TSS,
    and intensity have evolved. Identifies week-over-week progression
    or regression.

    Use this to answer questions like:
    - "How has my training progressed this month?"
    - "Am I increasing mileage too fast?"
    - "What's my weekly average distance?"

    Args:
        weeks: Number of weeks to analyze (default 8).

    Returns:
        FitnessTrendSummary as dict.
    """
    if client is None or config is None:
        raise RuntimeError("Dependencies not initialized")

    cutoff_time = int(
        (datetime.now(timezone.utc) - timedelta(weeks=weeks)).timestamp()
    )
    activities = await client.get_all_activities(after=cutoff_time)

    # Group by ISO week
    weekly_data: dict[tuple[int, int], dict] = {}  # (year, week) -> data

    for activity in activities:
        activity_date = datetime.fromisoformat(
            activity["start_date"].replace("Z", "+00:00")
        ).date()
        iso_year, iso_week, _ = activity_date.isocalendar()
        key = (iso_year, iso_week)

        if key not in weekly_data:
            weekly_data[key] = {
                "distances": [],
                "moving_times": [],
                "tss_values": [],
                "hrs": [],
                "count": 0,
            }

        weekly_data[key]["distances"].append(activity["distance"])
        weekly_data[key]["moving_times"].append(activity["moving_time"])
        weekly_data[key]["tss_values"].append(_calculate_tss(activity, config))
        if activity.get("average_heartrate"):
            weekly_data[key]["hrs"].append(activity["average_heartrate"])
        weekly_data[key]["count"] += 1

    # Build weekly metrics
    weekly_metrics: list[WeeklyTrainingMetrics] = []

    for (iso_year, iso_week), data in sorted(weekly_data.items()):
        # Calculate week start and end
        jan_4 = date(iso_year, 1, 4)
        week_monday = jan_4 - timedelta(days=jan_4.weekday())
        week_start = week_monday + timedelta(weeks=iso_week - 1)
        week_end = week_start + timedelta(days=6)

        total_distance_km = sum(data["distances"]) / 1000
        total_duration_hours = sum(data["moving_times"]) / 3600
        total_tss = sum(data["tss_values"])
        avg_intensity_factor = (
            sum(data["tss_values"]) / len(data["tss_values"]) / total_duration_hours
            if total_duration_hours > 0
            else 0
        )

        distance_change_pct = None
        if weekly_metrics:
            last_week_dist = weekly_metrics[-1].total_distance_km
            if last_week_dist > 0:
                distance_change_pct = ((total_distance_km - last_week_dist) / last_week_dist) * 100

        weekly_metrics.append(
            WeeklyTrainingMetrics(
                week_start=week_start,
                week_end=week_end,
                total_distance_km=total_distance_km,
                total_duration_hours=total_duration_hours,
                total_tss=total_tss,
                activity_count=data["count"],
                avg_intensity_factor=avg_intensity_factor,
                distance_change_pct=distance_change_pct,
            )
        )

    # Determine trend
    if not weekly_metrics:
        trend_assessment = "No training data available."
    else:
        increases = sum(
            1
            for m in weekly_metrics[1:]
            if m.distance_change_pct is not None and m.distance_change_pct > 10
        )
        stables = sum(
            1
            for m in weekly_metrics[1:]
            if m.distance_change_pct is not None and -2 <= m.distance_change_pct <= 2
        )

        if increases > len(weekly_metrics) / 2:
            trend_assessment = (
                "Aggressive ramp: multiple weeks with >10% increase. Injury risk. "
                "Follow the 10% rule."
            )
        elif stables >= len(weekly_metrics) / 2:
            trend_assessment = (
                "Plateau: volume has been flat for most weeks. "
                "Consider a training stimulus."
            )
        else:
            # Check if generally progressing
            if weekly_metrics[-1].total_distance_km > weekly_metrics[0].total_distance_km:
                avg_change = sum(
                    m.distance_change_pct
                    for m in weekly_metrics[1:]
                    if m.distance_change_pct is not None
                ) / len([m for m in weekly_metrics[1:] if m.distance_change_pct is not None])
                if 5 <= avg_change <= 8:
                    trend_assessment = (
                        "Progressive overload: consistent 5-8% weekly increase. Good."
                    )
                else:
                    trend_assessment = "Variable week-to-week volume. Aim for more consistency."
            else:
                trend_assessment = "Volume trending down. Consider increasing training."

    return FitnessTrendSummary(
        weeks=weekly_metrics,
        trend_assessment=trend_assessment,
    ).model_dump()


async def get_race_readiness(target_distance_km: float = 10.0) -> dict:
    """Assess readiness to race a given distance.

    Scores race readiness from 0 to 100 based on four factors:
    fitness level, freshness, recent long runs, and training consistency.

    Use this to answer questions like:
    - "Am I ready for a 10K this weekend?"
    - "Can I run a half marathon next month?"
    - "What should I improve before my race?"

    Common distances: 5 (5K), 10 (10K), 21.1 (half marathon), 42.2 (marathon).

    Args:
        target_distance_km: Target race distance (default 10).

    Returns:
        RaceReadiness as dict.
    """
    if client is None or config is None:
        raise RuntimeError("Dependencies not initialized")

    # Get training load data (last 42 days)
    cutoff_time = int(
        (datetime.now(timezone.utc) - timedelta(days=42)).timestamp()
    )
    activities = await client.get_all_activities(after=cutoff_time)

    daily_series = _build_daily_tss_series(activities, config)
    daily_loads = _compute_ctl_atl_tsb(daily_series)

    current_ctl = daily_loads[-1].ctl if daily_loads else 0
    current_atl = daily_loads[-1].atl if daily_loads else 0
    current_tsb = daily_loads[-1].tsb if daily_loads else 0

    # Score 1: Fitness
    target_ctl_benchmarks = {
        5: 30,
        10: 40,
        21.1: 55,
        42.2: 70,
    }

    # Find the closest benchmarks
    distances = sorted(target_ctl_benchmarks.keys())
    if target_distance_km <= distances[0]:
        target_ctl = target_ctl_benchmarks[distances[0]]
    elif target_distance_km >= distances[-1]:
        target_ctl = target_ctl_benchmarks[distances[-1]]
    else:
        # Linear interpolation
        for i in range(len(distances) - 1):
            d1, d2 = distances[i], distances[i + 1]
            if d1 <= target_distance_km <= d2:
                ctl1 = target_ctl_benchmarks[d1]
                ctl2 = target_ctl_benchmarks[d2]
                target_ctl = ctl1 + (ctl2 - ctl1) * (
                    (target_distance_km - d1) / (d2 - d1)
                )
                break

    fitness_score = min(25, (current_ctl / target_ctl) * 25)

    # Score 2: Freshness
    if current_tsb < -30:
        freshness_score = 0.0
    elif current_tsb <= -10:
        freshness_score = (current_tsb + 30) / 2  # 0->10
    elif current_tsb <= 0:
        freshness_score = 10 + (current_tsb + 10)  # 10->20
    elif current_tsb <= 15:
        freshness_score = 20 + (current_tsb / 15) * 5  # 20->25
    else:
        freshness_score = 15  # Penalty for being too fresh

    freshness_score = max(0, min(25, freshness_score))

    # Score 3: Long run
    long_run_cutoff = (
        datetime.now(timezone.utc) - timedelta(days=21)
    ).timestamp()
    recent_activities = [
        a for a in activities
        if float(datetime.fromisoformat(
            a["start_date"].replace("Z", "+00:00")
        ).timestamp()) >= long_run_cutoff
    ]

    longest_run = max(
        (a["distance"] / 1000 for a in recent_activities if "run" in a.get("sport_type", "").lower()),
        default=0,
    )

    # Adjust target for marathon
    target_long_run = min(target_distance_km * 0.75, 35) if target_distance_km > 30 else target_distance_km * 0.75

    if longest_run >= target_long_run:
        long_run_score = 25.0
    elif longest_run >= target_long_run * (2 / 3):
        long_run_score = 15.0
    elif longest_run >= target_long_run * 0.4:
        long_run_score = 8.0
    else:
        long_run_score = 0.0

    # Score 4: Consistency
    recent_28_days = (
        datetime.now(timezone.utc) - timedelta(days=28)
    ).timestamp()
    recent_all = [
        a for a in activities
        if float(datetime.fromisoformat(
            a["start_date"].replace("Z", "+00:00")
        ).timestamp()) >= recent_28_days
    ]

    training_days = len(set(
        datetime.fromisoformat(
            a["start_date"].replace("Z", "+00:00")
        ).date()
        for a in recent_all
    ))

    consistency_ratio = training_days / 28
    if consistency_ratio >= 0.7:
        consistency_score = 25.0
    elif consistency_ratio >= 0.5:
        consistency_score = 18.0
    elif consistency_ratio >= 0.35:
        consistency_score = 10.0
    else:
        consistency_score = 3.0

    overall_score = fitness_score + freshness_score + long_run_score + consistency_score

    # Generate verdict
    if overall_score >= 85:
        verdict = "Race ready"
    elif overall_score >= 70:
        verdict = "Mostly ready"
    elif overall_score >= 50:
        verdict = "Undertrained"
    else:
        verdict = "Not ready"

    # Generate recommendations
    recommendations = []
    if fitness_score < 15:
        recommendations.append(
            f"Fitness is below target for {target_distance_km}km. More consistent training needed."
        )
    if freshness_score < 10:
        recommendations.append(
            "You're carrying too much fatigue. Take 2-3 easy days before racing."
        )
    if long_run_score < 15:
        recommendations.append(
            f"Your longest recent run is too short. Do a long run of at least {target_long_run:.1f}km."
        )
    if consistency_score < 15:
        recommendations.append("Training has been inconsistent. Aim for 4+ sessions per week.")

    if not recommendations:
        recommendations.append("You're well-prepared for this race distance.")

    return RaceReadiness(
        overall_score=overall_score,
        fitness_score=fitness_score,
        freshness_score=freshness_score,
        long_run_score=long_run_score,
        consistency_score=consistency_score,
        target_distance_km=target_distance_km,
        verdict=verdict,
        recommendations=recommendations,
    ).model_dump()
