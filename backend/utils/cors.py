"""CORS setup: credentialed access only for exactly listed origins."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.config import Settings


class PatternOriginsWithoutCredentials:
    """Drop ``Access-Control-Allow-Credentials`` for regex-admitted origins.

    ``PWC_EXTRA_ALLOWED_ORIGIN_REGEX`` lets any Hugging Face Space read the
    public API. Anyone can create a Space, so those origins must not make
    credentialed requests; only the exact origin list keeps that right.
    """

    def __init__(self, app: ASGIApp, exact_origins: list[str]) -> None:
        self.app = app
        self.exact_origins = frozenset(exact_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        origin = Headers(scope=scope).get("origin")
        if origin is None or origin in self.exact_origins:
            await self.app(scope, receive, send)
            return

        async def send_without_credentials(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if "access-control-allow-credentials" in headers:
                    del headers["access-control-allow-credentials"]
            await send(message)

        await self.app(scope, receive, send_without_credentials)


def install_cors(app: FastAPI, settings: Settings) -> None:
    """Add CORS middleware for the configured origins.

    ``allow_origin_regex`` permits the Hugging Face Space mirror (e.g.
    ``https://<owner>-<name>.hf.space``) without hardcoding every subdomain,
    but such origins get CORS without credentials.
    """
    exact_origins = settings.cors_allowed_origins
    cors_kwargs = dict(
        allow_origins=exact_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    if settings.extra_allowed_origin_regex:
        cors_kwargs["allow_origin_regex"] = settings.extra_allowed_origin_regex
    app.add_middleware(CORSMiddleware, **cors_kwargs)
    if settings.extra_allowed_origin_regex:
        # Added after CORSMiddleware, so it wraps it and sees its headers.
        app.add_middleware(
            PatternOriginsWithoutCredentials, exact_origins=exact_origins
        )
