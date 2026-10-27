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


def get_client() -> StravaClient:
    """Return the initialized Strava client.

    Tools must call this at request time rather than importing `client` directly,
    since a `from ... import client` binding would keep the pre-initialization None.

    Raises:
        RuntimeError: If initialize() has not been called.
    """
    if client is None:
        raise RuntimeError("Dependencies not initialized")
    return client


def get_config() -> UserConfig:
    """Return the loaded user config.

    Raises:
        RuntimeError: If initialize() has not been called.
    """
    if config is None:
        raise RuntimeError("Dependencies not initialized")
    return config
