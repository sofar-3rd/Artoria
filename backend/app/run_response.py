import asyncio
from contextlib import aclosing
from typing import Mapping

from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from app.chat_stream import ChatRun


async def _watch_disconnect(receive: Receive, run: ChatRun) -> None:
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            run.cancel()
            return


class RunResponse(Response):
    """SSE response that owns the receive/send loop of a `ChatRun`.

    Unlike `StreamingResponse` it never cancels the generator from outside. A
    disconnect is turned into a `cancel` item on the run's queue, so the run
    stops itself and can still await its wrap-up.
    """

    media_type = "text/event-stream"

    def __init__(self, run: ChatRun, headers: Mapping[str, str] | None = None) -> None:
        self.run = run
        self.status_code = 200
        self.background = None
        self.init_headers(headers)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        run = self.run
        run.start()
        watcher = asyncio.create_task(_watch_disconnect(receive, run))
        connected = True

        async def emit(message: dict) -> None:
            nonlocal connected
            if not connected:
                return
            try:
                await send(message)
            except OSError:  # ASGI >= 2.4 servers report a dead client this way
                connected = False
                run.cancel()

        try:
            await emit({
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self.raw_headers,
            })
            async with aclosing(run.stream()) as events:
                async for chunk in events:
                    await emit({
                        "type": "http.response.body",
                        "body": chunk.encode(self.charset),
                        "more_body": True,
                    })
            await emit({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            watcher.cancel()
        if self.background is not None:
            await self.background()
