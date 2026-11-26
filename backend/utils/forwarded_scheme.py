"""Trust nginx's X-Forwarded-Proto on the unix socket only nginx can reach."""

_SCHEMES = {
    "http": {"http", "https"},
    "websocket": {"ws", "wss"},
}


class UnixSocketForwardedSchemeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in _SCHEMES and not scope.get("client"):
            for name, value in scope["headers"]:
                if name == b"x-forwarded-proto":
                    scheme = value.decode("latin1").strip().lower()
                    if scope["type"] == "websocket":
                        scheme = scheme.replace("http", "ws")
                    if scheme in _SCHEMES[scope["type"]]:
                        scope = {**scope, "scheme": scheme}
                    break
        await self.app(scope, receive, send)
