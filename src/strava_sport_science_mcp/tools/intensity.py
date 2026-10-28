"""Intensity pipeline: TSS and zone time from the best data available per activity.

Each metric uses the most precise source an activity offers and falls back to coarser ones:

- TSS: power (NP / FTP) > pace (runs, rTSS) > heart rate (HR reserve vs LTHR) > duration
- Zones: power stream > HR stream > pace stream (runs)
         > average power > average HR > average pace (runs)

All zone models map to the same 5 intensity levels so they can be aggregated.
"""

from typing import Literal

from strava_sport_science_mcp.config import UserConfig

TssMethod = Literal["power", "pace", "heart_rate", "duration"]
ZoneSource = Literal[
    "power_stream", "hr_stream", "pace_stream", "power_average", "hr_average", "pace_average"
]

ZONE_NAMES = ["Z1 (Recovery)", "Z2 (Aerobic)", "Z3 (Tempo)", "Z4 (Threshold)", "Z5 (VO2max)"]

# Upper bounds of zones 1-4, relative to each model's reference value
HR_ZONE_PCT_MAX_HR = (0.60, 0.70, 0.80, 0.90)
# Coggan power zones (Z5-Z7 merged): % of FTP
POWER_ZONE_PCT_FTP = (0.55, 0.75, 0.90, 1.05)
# Friel run pace zones (129/114/106/99% of threshold pace) expressed as % of threshold speed
PACE_ZONE_PCT_THRESHOLD_SPEED = (1 / 1.29, 1 / 1.14, 1 / 1.06, 1 / 0.99)

# Stream samples further apart than this are treated as a pause, not training time
MAX_SAMPLE_GAP_S = 30
# Slower than this (m/s) counts as standing still in pace streams
MIN_MOVING_SPEED_MS = 0.5

STREAM_KEYS = ["time", "heartrate", "velocity_smooth", "watts", "moving"]


def is_run(activity: dict) -> bool:
    """Whether the activity is a run (Run, TrailRun, VirtualRun...)."""
    return "run" in str(activity.get("sport_type", "")).lower()


def _has_power(activity: dict, config: UserConfig) -> bool:
    return bool(activity.get("device_watts")) and bool(config.ftp_watts)


def threshold_speed_ms(config: UserConfig) -> float:
    """Threshold pace converted to m/s."""
    return 1000 / (config.threshold_pace_min_per_km * 60)


def format_pace(pace_min_per_km: float) -> str:
    """Format decimal min/km as m:ss/km (4.55 -> "4:33/km")."""
    minutes, seconds = divmod(round(pace_min_per_km * 60), 60)
    return f"{minutes}:{seconds:02d}/km"


# --- TSS -------------------------------------------------------------------------


def calculate_tss(activity: dict, config: UserConfig) -> tuple[float, TssMethod]:
    """Training Stress Score from the most precise source available.

    All methods follow TSS = hours * IF^2 * 100, so one hour at threshold = 100.

    Returns:
        (tss, method used).
    """
    hours = float(activity.get("moving_time", 0)) / 3600

    if _has_power(activity, config) and activity.get("weighted_average_watts"):
        intensity = float(activity["weighted_average_watts"]) / float(config.ftp_watts or 1)
        return hours * intensity**2 * 100, "power"

    speed = float(activity.get("average_speed") or 0)
    if is_run(activity) and speed > 0:
        intensity = speed / threshold_speed_ms(config)
        return hours * intensity**2 * 100, "pace"

    if activity.get("average_heartrate"):
        reserve_at_threshold = config.threshold_hr - config.resting_hr
        intensity = max(0.0, float(activity["average_heartrate"]) - config.resting_hr) / (
            reserve_at_threshold
        )
        return hours * intensity**2 * 100, "heart_rate"

    # Unknown intensity: assume a moderate effort
    return hours * 50, "duration"


# --- Zones -----------------------------------------------------------------------


def hr_zone_bounds(config: UserConfig) -> list[float]:
    """HR zone upper bounds (bpm): Strava custom zones if configured, else % of max HR."""
    if config.hr_zone_bounds and len(config.hr_zone_bounds) == 4:
        return [float(b) for b in config.hr_zone_bounds]
    return [config.max_hr * pct for pct in HR_ZONE_PCT_MAX_HR]


def power_zone_bounds(config: UserConfig) -> list[float]:
    """Power zone upper bounds (W) from FTP."""
    return [float(config.ftp_watts or 0) * pct for pct in POWER_ZONE_PCT_FTP]


def pace_zone_bounds(config: UserConfig) -> list[float]:
    """Pace zone upper bounds as speeds (m/s) from threshold pace."""
    threshold = threshold_speed_ms(config)
    return [threshold * pct for pct in PACE_ZONE_PCT_THRESHOLD_SPEED]


def zone_index(value: float, upper_bounds: list[float]) -> int:
    """0-based zone (0-4) for a value given the upper bounds of zones 1-4."""
    for i, bound in enumerate(upper_bounds):
        if value < bound:
            return i
    return len(upper_bounds)


def normalize_streams(raw: dict) -> dict[str, list]:
    """Flatten Strava's key_by_type response ({"heartrate": {"data": [...]}}) to lists."""
    streams: dict[str, list] = {}
    for key, value in raw.items():
        data = value.get("data") if isinstance(value, dict) else value
        if isinstance(data, list) and data:
            streams[key] = data
    return streams


def stream_zone_times(
    streams: dict[str, list], key: str, upper_bounds: list[float], min_value: float = 0.0
) -> list[float]:
    """Seconds per zone from a stream, skipping pauses and non-moving samples."""
    times = streams.get("time", [])
    values = streams.get(key, [])
    moving = streams.get("moving")
    zone_times = [0.0] * 5

    for i in range(min(len(times), len(values)) - 1):
        if moving is not None and i < len(moving) and not moving[i]:
            continue
        dt = times[i + 1] - times[i]
        value = values[i]
        if dt <= 0 or dt > MAX_SAMPLE_GAP_S or value is None or value < min_value:
            continue
        zone_times[zone_index(float(value), upper_bounds)] += dt

    return zone_times


def activity_zone_times(
    activity: dict, streams: dict[str, list] | None, config: UserConfig
) -> tuple[list[float], ZoneSource] | None:
    """Seconds per zone (Z1-Z5) for one activity, from the best source available.

    Args:
        activity: Activity summary from Strava.
        streams: Normalized streams for the activity, or None if not fetched.
        config: User settings (zone references).

    Returns:
        (seconds per zone, source), or None if the activity has no intensity data.
    """
    run = is_run(activity)
    power = _has_power(activity, config)

    if streams:
        candidates: list[tuple[bool, str, list[float], float, ZoneSource]] = [
            (power, "watts", power_zone_bounds(config), 0.0, "power_stream"),
            (True, "heartrate", hr_zone_bounds(config), 0.0, "hr_stream"),
            (run, "velocity_smooth", pace_zone_bounds(config), MIN_MOVING_SPEED_MS, "pace_stream"),
        ]
        for enabled, key, bounds, min_value, source in candidates:
            if enabled and key in streams:
                zone_times = stream_zone_times(streams, key, bounds, min_value)
                if sum(zone_times) > 0:
                    return zone_times, source

    duration = float(activity.get("moving_time", 0))
    if duration <= 0:
        return None

    average: tuple[float, list[float], ZoneSource] | None = None
    if power and activity.get("weighted_average_watts"):
        average = (float(activity["weighted_average_watts"]), power_zone_bounds(config),
                   "power_average")
    elif activity.get("average_heartrate"):
        average = (float(activity["average_heartrate"]), hr_zone_bounds(config), "hr_average")
    elif run and float(activity.get("average_speed") or 0) > 0:
        average = (float(activity["average_speed"]), pace_zone_bounds(config), "pace_average")

    if average is None:
        return None
    value, bounds, source = average
    zone_times = [0.0] * 5
    zone_times[zone_index(value, bounds)] = duration
    return zone_times, source


def wants_streams(activity: dict, config: UserConfig) -> bool:
    """Whether fetching streams would improve on the activity's averages."""
    return bool(
        activity.get("has_heartrate")
        or _has_power(activity, config)
        or (is_run(activity) and float(activity.get("distance") or 0) > 0)
    )
