"""Async Strava API v3 client."""

import httpx

from strava_sport_science_mcp.auth import StravaAuth
from strava_sport_science_mcp.models.activity import Activity, ActivityStream


class StravaClient:
    """Async Strava API v3 client."""

    BASE_URL = "https://www.strava.com/api/v3"
    RATE_LIMIT_PER_CYCLE = 100  # 100 req per 15 min
    RATE_LIMIT_DAILY = 1000  # 1000 req per day

    def __init__(self, auth: StravaAuth) -> None:
        """Initialize the client.

        Args:
            auth: StravaAuth instance for token management.
        """
        self.auth = auth

    async def _get(self, endpoint: str, params: dict | None = None) -> dict:
        """Make an authenticated GET request.

        Args:
            endpoint: API endpoint (e.g., "/athlete")
            params: Query parameters.

        Returns:
            Response JSON as dict.

        Raises:
            RuntimeError: For API errors.
        """
        token = await self.auth.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}{endpoint}", headers=headers, params=params
            )

        if response.status_code == 429:
            raise RuntimeError(
                "Strava API rate limit exceeded. Try again in 15 minutes."
            )

        if response.status_code == 401:
            raise RuntimeError(
                "Strava authentication failed. Your refresh token may be revoked. "
                "Please re-authorize."
            )

        if response.status_code >= 400:
            try:
                error_data = response.json()
                error_msg = error_data.get("message", response.text)
            except Exception:
                error_msg = response.text

            raise RuntimeError(
                f"Strava API error (HTTP {response.status_code}): {error_msg}"
            )

        return response.json()

    async def get_athlete(self) -> dict:
        """Get authenticated athlete's profile.

        Returns:
            Athlete profile dict.
        """
        return await self._get("/athlete")

    async def get_activities(
        self,
        after: int | None = None,
        before: int | None = None,
        per_page: int = 100,
        page: int = 1,
    ) -> list[dict]:
        """Get athlete's activities with pagination.

        Args:
            after: UNIX timestamp to get activities after.
            before: UNIX timestamp to get activities before.
            per_page: Items per page (capped at 200).
            page: Page number (1-indexed).

        Returns:
            List of activity dicts.
        """
        per_page = min(per_page, 200)
        params = {"per_page": per_page, "page": page}

        if after is not None:
            params["after"] = after

        if before is not None:
            params["before"] = before

        return await self._get("/athlete/activities", params=params)

    async def get_all_activities(
        self, after: int | None = None, before: int | None = None
    ) -> list[dict]:
        """Get all activities in a period, auto-paginating.

        Args:
            after: UNIX timestamp to get activities after.
            before: UNIX timestamp to get activities before.

        Returns:
            List of all activity dicts.
        """
        all_activities: list[dict] = []
        page = 1
        max_pages = 10

        while page <= max_pages:
            activities = await self.get_activities(after=after, before=before, page=page)

            if not activities:
                break

            all_activities.extend(activities)

            if len(activities) < 100:
                break

            page += 1

        return all_activities

    async def get_activity(self, activity_id: int) -> dict:
        """Get detailed info for a specific activity.

        Args:
            activity_id: The activity ID.

        Returns:
            Activity detail dict.
        """
        return await self._get(f"/activities/{activity_id}")

    async def get_activity_streams(
        self, activity_id: int, keys: list[str]
    ) -> dict:
        """Get time-series stream data for an activity.

        Args:
            activity_id: The activity ID.
            keys: Stream types to fetch (e.g., ["time", "heartrate", "altitude"]).

        Returns:
            Dict keyed by stream type, each with "data" list.
            Missing stream types are not included.
        """
        params = {
            "keys": ",".join(keys),
            "key_by_type": "true",
        }

        return await self._get(f"/activities/{activity_id}/streams", params=params)
