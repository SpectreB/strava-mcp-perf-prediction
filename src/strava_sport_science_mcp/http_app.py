"""HTTP transport for personal remote use, protected by a static bearer token.

Single-user by design: the server still acts for the one athlete whose Strava
credentials it holds. The token only keeps strangers out of that athlete's data
when the endpoint is reachable beyond localhost (e.g. through a tunnel).
"""

import hmac
import json

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MIN_TOKEN_LENGTH = 24
LOOPBACK_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
LOOPBACK_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


class BearerTokenMiddleware:
    """Reject HTTP requests that don't carry the expected `Authorization: Bearer` token.

    Pure ASGI (not BaseHTTPMiddleware) so streamed MCP responses are not buffered.
    Non-HTTP scopes (lifespan) pass through untouched.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        header = dict(scope["headers"]).get(b"authorization", b"")
        scheme, _, presented = header.partition(b" ")
        # Constant-time comparison so the token can't be guessed byte by byte
        if scheme.lower() == b"bearer" and hmac.compare_digest(presented.strip(), self._token):
            await self.app(scope, receive, send)
            return

        body = json.dumps({"error": "unauthorized"}).encode()
        start: Message = {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", b'Bearer realm="strava-sport-science"'),
            ],
        }
        await send(start)
        await send({"type": "http.response.body", "body": body})


def transport_security(allowed_hosts: list[str]) -> TransportSecuritySettings:
    """DNS-rebinding protection allowing loopback plus the given public hostnames.

    Args:
        allowed_hosts: Public hostnames the server is reached through (e.g. a tunnel's
            "mcp.example.com"), without scheme.
    """
    hosts = list(LOOPBACK_HOSTS)
    origins = list(LOOPBACK_ORIGINS)
    for host in allowed_hosts:
        hosts += [host, f"{host}:*"]
        origins += [f"https://{host}", f"http://{host}"]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )


def validate_token(token: str | None) -> str:
    """Return the token, or raise ValueError if it is missing or too weak to expose."""
    if not token or len(token) < MIN_TOKEN_LENGTH:
        raise ValueError(
            "HTTP mode needs STRAVA_MCP_AUTH_TOKEN of at least "
            f"{MIN_TOKEN_LENGTH} characters. Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
    return token


def build_app(mcp: FastMCP, token: str, allowed_hosts: list[str]) -> Starlette:
    """Streamable-HTTP ASGI app for `mcp`, protected by the bearer token.

    Note: a FastMCP instance's session manager can only run once, so call this once
    per instance.
    """
    mcp.settings.transport_security = transport_security(allowed_hosts)
    app = mcp.streamable_http_app()
    app.add_middleware(BearerTokenMiddleware, token=validate_token(token))
    return app


def run_http(
    mcp: FastMCP, host: str, port: int, token: str, allowed_hosts: list[str]
) -> None:
    """Serve `mcp` over streamable HTTP at http://host:port/mcp."""
    app = build_app(mcp, token, allowed_hosts)
    uvicorn.run(app, host=host, port=port, log_level="info")
