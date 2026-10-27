"""Interactive setup: Strava OAuth authorization and settings calibration.

Usage:
    strava-sport-science-setup              # auth, then calibrate
    strava-sport-science-setup auth         # authorize and store refresh token in .env
    strava-sport-science-setup calibrate    # estimate settings from activities
"""

import argparse
import asyncio
import os
import re
import sys
import time
import webbrowser
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from strava_sport_science_mcp.auth import StravaAuth
from strava_sport_science_mcp.config import UserConfig
from strava_sport_science_mcp.strava_client import StravaClient

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
SCOPES = "read,activity:read_all,profile:read_all"
CALLBACK_PORT = 8722

# Runs shorter than this are too short to extrapolate to a 60-minute effort
MIN_RUN_SECONDS = 15 * 60
MIN_RUN_METERS = 3000
RIEGEL_EXPONENT = 1.06
PACE_LOOKBACK_DAYS = 365


# --- .env handling -------------------------------------------------------------

_ENV_LINE = re.compile(r'^\s*(?:export\s+)?(\w+)\s*=\s*["\']?([^"\'\r\n]*)["\']?\s*$', re.M)


def read_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from a .env file (missing file -> empty dict)."""
    if not path.exists():
        return {}
    return dict(_ENV_LINE.findall(path.read_text()))


def set_env_var(path: Path, key: str, value: str) -> None:
    """Set or append KEY=value in a .env file, creating it with 0600 permissions."""
    text = path.read_text() if path.exists() else ""
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=.*$", re.M)
    if pattern.search(text):
        text = pattern.sub(lambda _: f"{key}={value}", text)
    else:
        text = text.rstrip("\n") + ("\n" if text else "") + f"{key}={value}\n"
    path.write_text(text)
    path.chmod(0o600)


def _is_placeholder(value: str | None) -> bool:
    return not value or "your_" in value or value.endswith("_here")


# --- auth ------------------------------------------------------------------------


def _wait_for_callback(port: int, timeout_s: int = 300) -> dict[str, str]:
    """Serve one OAuth redirect on localhost and return its query parameters."""
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            params = parse_qs(urlparse(self.path).query)
            if "code" not in params and "error" not in params:
                self.send_response(404)
                self.end_headers()
                return
            result.update({k: v[0] for k, v in params.items()})
            ok = "code" in result
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            message = "Authorization received. You can close this tab." if ok else (
                f"Authorization failed: {result.get('error')}"
            )
            self.wfile.write(f"<html><body><h2>{message}</h2></body></html>".encode())

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("localhost", port), Handler)
    deadline = time.monotonic() + timeout_s
    try:
        # Keep serving until the OAuth redirect arrives (ignoring e.g. /favicon.ico)
        while not result and (remaining := deadline - time.monotonic()) > 0:
            server.timeout = remaining
            server.handle_request()
    finally:
        server.server_close()
    return result


def run_auth(env_path: Path, manual: bool = False) -> None:
    """Authorize with Strava and store the refresh token in the .env file."""
    env = {**read_env_file(env_path), **os.environ}
    client_id = env.get("STRAVA_CLIENT_ID")
    client_secret = env.get("STRAVA_CLIENT_SECRET")
    if _is_placeholder(client_id) or _is_placeholder(client_secret):
        sys.exit(
            f"Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in {env_path} first "
            "(from https://www.strava.com/settings/api)."
        )

    redirect_uri = "http://localhost" if manual else f"http://localhost:{CALLBACK_PORT}"
    url = f"{AUTHORIZE_URL}?" + urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "approval_prompt": "force",
        "scope": SCOPES,
    })

    print("Open this URL and click Authorize (keep all permission boxes checked):")
    print(f"\n  {url}\n")

    if manual:
        raw = input("Paste the full redirect URL (or just the code): ").strip()
        query = parse_qs(urlparse(raw).query)
        params = {k: v[0] for k, v in query.items()} if query else {"code": raw}
    else:
        webbrowser.open(url)
        print(f"Waiting for Strava to redirect to {redirect_uri} (5 min timeout)...")
        params = _wait_for_callback(CALLBACK_PORT)

    if "error" in params:
        sys.exit(f"Authorization denied: {params['error']}")
    if not params.get("code"):
        sys.exit("No authorization code received. Re-run, or use --manual.")

    granted = set(params.get("scope", "").split(","))
    if params.get("scope") and "activity:read_all" not in granted:
        sys.exit(
            f"Granted scopes are {sorted(granted)}; 'activity:read_all' is required. "
            "Re-run and keep the activity permission checked."
        )

    response = httpx.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": params["code"],
        "grant_type": "authorization_code",
    }, timeout=30)
    if response.status_code != 200:
        sys.exit(f"Token exchange failed (HTTP {response.status_code}): {response.text[:300]}")

    data = response.json()
    set_env_var(env_path, "STRAVA_REFRESH_TOKEN", data["refresh_token"])

    # Cached tokens from a previous authorization would take precedence over the new one
    tokens_path = StravaAuth._get_tokens_path()
    if tokens_path.exists():
        tokens_path.unlink()

    athlete = data.get("athlete", {})
    print(
        f"Authorized as {athlete.get('firstname', '?')} {athlete.get('lastname', '')}. "
        f"Refresh token saved to {env_path}."
    )
    if params.get("scope") and "profile:read_all" not in granted:
        print("Note: profile:read_all not granted; weight will not be calibrated.")


# --- calibrate -------------------------------------------------------------------


def _parse_start(activity: dict) -> datetime:
    return datetime.fromisoformat(str(activity["start_date"]).replace("Z", "+00:00"))


def estimate_threshold_pace(
    activities: list[dict], now: datetime | None = None
) -> tuple[float, dict] | None:
    """Estimate threshold pace (min/km) as the best 60-minute-equivalent run pace.

    Each qualifying run is projected to the distance sustainable for 60 minutes with
    Riegel's formula (T2 = T1 * (D2/D1)^1.06). Runs from the last year are preferred;
    older runs are used only if there are no recent ones.

    Returns:
        (pace_min_per_km, source_activity), or None if no run qualifies.
    """
    now = now or datetime.now(UTC)
    runs = [
        a for a in activities
        if "run" in str(a.get("sport_type", "")).lower()
        and a.get("moving_time", 0) >= MIN_RUN_SECONDS
        and a.get("distance", 0) >= MIN_RUN_METERS
    ]
    recent = [a for a in runs if _parse_start(a) >= now - timedelta(days=PACE_LOOKBACK_DAYS)]

    best: tuple[float, dict] | None = None
    for run in recent or runs:
        minutes = run["moving_time"] / 60
        km = run["distance"] / 1000
        km_in_60_min = km * (60 / minutes) ** (1 / RIEGEL_EXPONENT)
        pace = 60 / km_in_60_min
        if best is None or pace < best[0]:
            best = (pace, run)
    return best


def estimate_max_hr(activities: list[dict]) -> tuple[int, dict] | None:
    """Return the highest recorded max heart rate (a lower bound on true max HR)."""
    with_hr = [a for a in activities if a.get("max_heartrate")]
    if not with_hr:
        return None
    top = max(with_hr, key=lambda a: a["max_heartrate"])
    return round(top["max_heartrate"]), top


def _format_pace(pace: float) -> str:
    minutes, seconds = divmod(round(pace * 60), 60)
    return f"{minutes}:{seconds:02d}/km"


async def _fetch_for_calibration(env_path: Path) -> tuple[list[dict], dict]:
    for key, value in read_env_file(env_path).items():
        os.environ.setdefault(key, value)
    client = StravaClient(StravaAuth())
    activities = await client.get_all_activities()
    athlete = await client.get_athlete()
    return activities, athlete


def run_calibrate(env_path: Path, dry_run: bool = False) -> None:
    """Estimate settings from Strava data and update settings.json."""
    activities, athlete = asyncio.run(_fetch_for_calibration(env_path))
    config = UserConfig.load()
    runs = [a for a in activities if "run" in str(a.get("sport_type", "")).lower()]
    print(f"Fetched {len(activities)} activities ({len(runs)} runs).")

    pace = estimate_threshold_pace(activities)
    if pace:
        value, run = pace
        config.threshold_pace_min_per_km = round(value, 2)
        print(
            f"threshold pace: {_format_pace(value)} "
            f"(from {run['distance'] / 1000:.1f} km in {run['moving_time'] / 60:.0f} min "
            f"on {str(run['start_date'])[:10]}; training runs make this conservative)"
        )
    else:
        print(f"threshold pace: no qualifying run, kept {config.threshold_pace_min_per_km}")

    max_hr = estimate_max_hr(activities)
    if max_hr:
        hr, activity = max_hr
        config.max_hr = hr
        print(
            f"max HR: {hr} bpm (highest recorded, on {str(activity['start_date'])[:10]}; "
            "true max may be higher)"
        )
    else:
        print(f"max HR: no heart-rate data in activities, kept {config.max_hr}")

    weight = athlete.get("weight")
    if weight:
        config.weight_kg = round(float(weight), 1)
        print(f"weight: {config.weight_kg} kg (from Strava profile)")
    else:
        print(f"weight: not available (needs profile:read_all), kept {config.weight_kg}")

    if dry_run:
        print("\nDry run, settings not saved:")
        print(config.model_dump_json(indent=2))
        return
    config.save()
    print(f"\nSaved {UserConfig.config_path()}")


# --- entry point -----------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="strava-sport-science-setup",
        description="Authorize with Strava and calibrate sport-science settings.",
    )
    parser.add_argument(
        "--env-file", type=Path, default=Path(".env"),
        help="Path to the .env file holding Strava credentials (default: ./.env)",
    )
    sub = parser.add_subparsers(dest="command")
    auth_parser = sub.add_parser("auth", help="Authorize and store the refresh token")
    auth_parser.add_argument(
        "--manual", action="store_true",
        help="Paste the redirect URL instead of running a local callback server",
    )
    calibrate_parser = sub.add_parser("calibrate", help="Estimate settings from activities")
    calibrate_parser.add_argument(
        "--dry-run", action="store_true", help="Print estimates without saving"
    )
    args = parser.parse_args()

    if args.command in (None, "auth"):
        run_auth(args.env_file, manual=getattr(args, "manual", False))
    if args.command in (None, "calibrate"):
        run_calibrate(args.env_file, dry_run=getattr(args, "dry_run", False))


if __name__ == "__main__":
    main()
