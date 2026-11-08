"""Tests for the HTTP transport: bearer-token auth, host protection and CLI guard."""

import json

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from strava_sport_science_mcp import server
from strava_sport_science_mcp.http_app import (
    BearerTokenMiddleware,
    build_app,
    transport_security,
    validate_token,
)

TOKEN = "t" * 32
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _first_json(response) -> dict:  # type: ignore[no-untyped-def]
    """Decode a JSON or single-event SSE response body."""
    if "text/event-stream" in response.headers["content-type"]:
        data = next(line for line in response.text.splitlines() if line.startswith("data:"))
        return json.loads(data.removeprefix("data:"))
    return response.json()


# --- middleware in isolation -------------------------------------------------------


@pytest.fixture
def protected() -> TestClient:
    app = Starlette(routes=[Route("/", lambda request: PlainTextResponse("secret"))])
    app.add_middleware(BearerTokenMiddleware, token=TOKEN)
    return TestClient(app)


def test_rejects_missing_wrong_and_non_bearer_credentials(protected: TestClient) -> None:
    for headers in ({}, _bearer("wrong"), _bearer(TOKEN[:-1]), {"Authorization": f"Basic {TOKEN}"}):
        response = protected.get("/", headers=headers)
        assert response.status_code == 401, headers
        assert response.headers["www-authenticate"].startswith("Bearer")
        assert "secret" not in response.text


def test_accepts_correct_token_case_insensitive_scheme(protected: TestClient) -> None:
    assert protected.get("/", headers=_bearer(TOKEN)).text == "secret"
    assert protected.get("/", headers={"Authorization": f"bearer {TOKEN}"}).status_code == 200


# --- configuration guards ----------------------------------------------------------


def test_validate_token_requires_a_strong_token() -> None:
    assert validate_token(TOKEN) == TOKEN
    for weak in (None, "", "short"):
        with pytest.raises(ValueError, match="STRAVA_MCP_AUTH_TOKEN"):
            validate_token(weak)


def test_transport_security_adds_public_hosts_to_loopback() -> None:
    settings = transport_security(["mcp.example.com"])
    assert settings.enable_dns_rebinding_protection
    assert {"localhost:*", "mcp.example.com", "mcp.example.com:*"} <= set(settings.allowed_hosts)
    assert "https://mcp.example.com" in settings.allowed_origins


def test_http_mode_refuses_to_start_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STRAVA_MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(server.deps, "initialize", lambda: pytest.fail("must fail before init"))
    with pytest.raises(SystemExit, match="STRAVA_MCP_AUTH_TOKEN"):
        server.main(["--transport", "http"])


# --- the real MCP app --------------------------------------------------------------


@pytest.fixture(scope="module")
def mcp_client() -> TestClient:
    """The real server app. Module-scoped: a session manager can only run once."""
    app = build_app(server.mcp, TOKEN, allowed_hosts=["mcp.example.com"])
    with TestClient(app, base_url="http://localhost:8000") as client:
        yield client


def test_mcp_endpoint_requires_token(mcp_client: TestClient) -> None:
    response = mcp_client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS)
    assert response.status_code == 401


def test_mcp_initialize_with_token(mcp_client: TestClient) -> None:
    response = mcp_client.post(
        "/mcp", json=INITIALIZE, headers={**MCP_HEADERS, **_bearer(TOKEN)}
    )
    assert response.status_code == 200
    assert _first_json(response)["result"]["serverInfo"]["name"] == "strava-sport-science"


def test_mcp_rejects_unknown_host_even_with_token(mcp_client: TestClient) -> None:
    """DNS-rebinding protection: a Host that isn't loopback or allowed is refused."""
    headers = {**MCP_HEADERS, **_bearer(TOKEN), "Host": "evil.example.net"}
    assert mcp_client.post("/mcp", json=INITIALIZE, headers=headers).status_code == 421


def test_mcp_accepts_allowed_public_host(mcp_client: TestClient) -> None:
    headers = {**MCP_HEADERS, **_bearer(TOKEN), "Host": "mcp.example.com"}
    assert mcp_client.post("/mcp", json=INITIALIZE, headers=headers).status_code == 200
