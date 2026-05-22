"""Shared dependencies for MCP tools."""

from strava_sport_science_mcp.auth import StravaAuth
from strava_sport_science_mcp.config import UserConfig
from strava_sport_science_mcp.strava_client import StravaClient

auth: StravaAuth | None = None
client: StravaClient | None = None
config: UserConfig | None = None


def initialize() -> None:
    """Initialize all dependencies.

    Called once at server startup.
    """
    global auth, client, config

    auth = StravaAuth()
    client = StravaClient(auth)
    config = UserConfig.load()
