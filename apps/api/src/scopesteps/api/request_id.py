from uuid import UUID

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from scopesteps.kernel.ids import new_id

HEADER = "X-Request-ID"


class RequestIdMiddleware:
    """Assigns every request an ID, honouring a valid UUID supplied by the client."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or str(new_id())
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(
                    (HEADER.lower().encode(), request_id.encode())
                )
            await send(message)

        await self.app(scope, receive, send_with_header)


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == HEADER.lower().encode():
            try:
                return str(UUID(value.decode()))
            except ValueError:
                return None
    return None
