"""Minimal SSE response helper.

Event dicts are emitted as `data: {json}\n\n`; `None` yields a heartbeat
comment (`: ping\n\n`) that keeps proxies and clients alive during slow
local-LLM turns.
"""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse


def sse_response(source: AsyncIterator[dict | None], heartbeat_seconds: float = 15):
    async def _with_heartbeats() -> AsyncIterator[str]:
        # The heartbeat wait must NOT cancel the pending __anext__: a
        # cancellation is thrown into the source generator and kills it at
        # its current await (slow snapshot / LLM first token), so the next
        # __anext__ raises StopAsyncIteration and the stream ends silently
        # without a `complete` or `error` event. Shield the task instead and
        # keep awaiting it across heartbeats.
        source_iter = source.__aiter__()
        task = asyncio.ensure_future(source_iter.__anext__())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        asyncio.shield(task), timeout=heartbeat_seconds
                    )
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                except StopAsyncIteration:
                    return
                except Exception as exc:  # noqa: BLE001 — surfaced as an SSE error event
                    # A mid-stream failure must not surface as a raw network
                    # error — clients know how to render an error event.
                    yield f"data: {json.dumps({'stage': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
                    return
                task = asyncio.ensure_future(source_iter.__anext__())
                if event is None:
                    yield ": ping\n\n"
                else:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(
        _with_heartbeats(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
