"""On-disk cache for activity streams.

Streams of a recorded activity don't change, so each one is fetched from Strava once.
This keeps stream-based analysis within Strava's rate limits.
"""

import json
from pathlib import Path


def cache_dir() -> Path:
    """Directory holding cached streams (~/.cache/strava-sport-science-mcp/streams)."""
    return Path.home() / ".cache" / "strava-sport-science-mcp" / "streams"


def load(activity_id: int) -> dict | None:
    """Return cached raw streams for an activity, or None if not cached."""
    path = cache_dir() / f"{activity_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save(activity_id: int, streams: dict) -> None:
    """Cache raw streams for an activity (an empty dict records "no streams")."""
    directory = cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{activity_id}.json").write_text(json.dumps(streams))
