"""SSE heartbeat regressions.

The heartbeat wait must not cancel the pending ``__anext__``: cancelling it
throws ``CancelledError`` into the source generator, which dies at its
current await (slow snapshot / LLM first token) and the stream then ends
silently — no ``complete``, no ``error`` — which the client renders as
"Report stream ended without a report.".
"""

import json

from app.core.sse import sse_response


async def _collect(response, *, expect_pings: bool = False) -> list[dict]:
    events: list[dict] = []
    pings = 0
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        for line in text.splitlines():
            if line.startswith(": ping"):
                pings += 1
            elif line.startswith("data:"):
                events.append(json.loads(line[len("data:") :]))
    if expect_pings:
        assert pings > 0, "expected at least one heartbeat ping"
    return events


async def test_heartbeat_does_not_kill_slow_source():
    """A source that stalls past the heartbeat still delivers every event."""

    async def source():
        yield {"stage": "stats"}
        # Longer than the heartbeat timeout — under the old wait_for-based
        # implementation the pending __anext__ was cancelled here and the
        # rest of the stream was lost.
        import asyncio

        await asyncio.sleep(0.3)
        yield {"stage": "complete", "report": {"id": "r1"}}

    events = await _collect(
        sse_response(source(), heartbeat_seconds=0.05),
        expect_pings=True,
    )
    assert events == [
        {"stage": "stats"},
        {"stage": "complete", "report": {"id": "r1"}},
    ]


async def test_mid_stream_failure_surfaces_as_error_event():
    """An exception in the source becomes an SSE error event, not silence."""

    async def source():
        yield {"stage": "stats"}
        raise RuntimeError("provider exploded")

    events = await _collect(
        sse_response(source(), heartbeat_seconds=0.05),
    )
    assert events[0] == {"stage": "stats"}
    assert events[-1] == {"stage": "error", "message": "provider exploded"}


async def test_none_yields_ping():
    """None events remain heartbeat comments, not data frames."""

    async def source():
        yield None
        yield {"stage": "complete"}

    events: list[dict] = []
    async for chunk in sse_response(source(), heartbeat_seconds=0.05).body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        for line in text.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:") :]))
    assert events == [{"stage": "complete"}]
