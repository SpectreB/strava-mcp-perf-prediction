"""OAuth2 token management for Strava API."""

import json
import os
import time
from pathlib import Path

import httpx


class StravaAuth:
    """Manages Strava OAuth2 tokens with automatic refresh."""

    STRAVA_AUTH_URL = "https://www.strava.com/api/v3/oauth/token"

    def __init__(self) -> None:
        """Initialize auth with credentials from environment variables.

        Raises:
            ValueError: If required environment variables are not set.
        """
        self.client_id = os.getenv("STRAVA_CLIENT_ID")
        self.client_secret = os.getenv("STRAVA_CLIENT_SECRET")
        self.refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")

        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise ValueError(
                "Missing required environment variables: "
                "STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN"
            )

        self.access_token: str | None = None
        self.expires_at: int | None = None
        self._tokens_path = self._get_tokens_path()

        self._load_tokens()

    @staticmethod
    def _get_tokens_path() -> Path:
        """Get the path to the tokens file.

        Returns:
            Path to ~/.config/strava-sport-science-mcp/tokens.json
        """
        tokens_dir = Path.home() / ".config" / "strava-sport-science-mcp"
        return tokens_dir / "tokens.json"

    def _load_tokens(self) -> None:
        """Load tokens from file if they exist."""
        if self._tokens_path.exists():
            with open(self._tokens_path) as f:
                data = json.load(f)
            self.access_token = data.get("access_token")
            self.refresh_token = data.get("refresh_token", self.refresh_token)
            self.expires_at = data.get("expires_at")

    def _save_tokens(self) -> None:
        """Save tokens to file."""
        self._tokens_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self._tokens_path, "w") as f:
            json.dump(
                {
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "expires_at": self.expires_at,
                },
                f,
            )

    async def _refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token.

        Raises:
            RuntimeError: If token refresh fails.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.STRAVA_AUTH_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                },
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to refresh Strava token. Status: {response.status_code}. "
                "Your refresh token may be revoked. Please re-authorize."
            )

        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        self.expires_at = data["expires_at"]

        self._save_tokens()

    async def get_access_token(self) -> str:
        """Get a valid access token, refreshing if needed.

        Returns:
            A valid Strava access token.

        Raises:
            RuntimeError: If token refresh fails.
        """
        # Check if token is expired or expiring soon (60-second buffer)
        if self.expires_at is None or (self.expires_at - time.time()) < 60:
            await self._refresh_access_token()

        if self.access_token is None:
            raise RuntimeError("Failed to obtain access token")

        return self.access_token
