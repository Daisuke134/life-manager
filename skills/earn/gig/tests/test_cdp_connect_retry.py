"""The browser refusing to talk is weather, not an answer about the page.

Four lanes share one browser. Under that contention the CDP endpoint answers the websocket
upgrade with HTTP 500, or drops the socket before the first frame. Every one of those ended
a whole wake: measured, `server rejected WebSocket connection: HTTP 500` appeared repeatedly
across the storefront log, including immediately after a browser restart, so uptime was not
the cause -- contention was.

A refusal that survives every attempt is raised unchanged, so the wake still reports what it
actually saw rather than a summary.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
import websockets

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import listing_inventory  # noqa: E402


class _Socket:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _CleanupDisconnectSocket(_Socket):
    async def __aexit__(self, *exc):
        raise OSError("no close frame received or sent")


class _EventOnlySocket:
    async def send(self, _message):
        return None

    async def recv(self):
        await asyncio.sleep(0.02)
        return '{"method":"Page.lifecycleEvent"}'


@pytest.fixture
def connect(monkeypatch):
    calls, sleeps = [], []

    async def _sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(listing_inventory.asyncio, "sleep", _sleep)

    def install(outcomes):
        queue = list(outcomes)

        async def fake(*args, **kwargs):
            calls.append(1)
            outcome = queue.pop(0) if queue else outcomes[-1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(websockets, "connect", fake)
    return install, calls, sleeps


REFUSED = websockets.exceptions.InvalidStatus.__new__(
    websockets.exceptions.InvalidStatus)


def test_a_refusal_that_clears_is_not_fatal(connect):
    install, calls, sleeps = connect
    socket = _Socket()
    install([REFUSED, REFUSED, socket])
    assert asyncio.run(listing_inventory._cdp_connect("ws://x")) is socket
    assert len(calls) == 3
    assert sleeps == [5, 5]


def test_the_window_outlasts_one_sibling_browser_step(connect):
    install, calls, sleeps = connect
    install([REFUSED])
    with pytest.raises(type(REFUSED)):
        asyncio.run(listing_inventory._cdp_connect("ws://x"))
    assert len(calls) == 8
    assert sleeps == [5, 5, 5, 5, 5, 5, 5]


def test_a_socket_that_opens_first_time_costs_nothing(connect):
    install, calls, sleeps = connect
    socket = _Socket()
    install([socket])
    assert asyncio.run(listing_inventory._cdp_connect("ws://x")) is socket
    assert len(calls) == 1
    assert sleeps == []


def test_a_dropped_connection_is_retried_too(connect):
    install, calls, _ = connect
    socket = _Socket()
    install([OSError("no close frame received or sent"), socket])
    assert asyncio.run(listing_inventory._cdp_connect("ws://x")) is socket
    assert len(calls) == 2


def test_read_only_session_ignores_disconnect_during_cleanup(monkeypatch):
    socket = _CleanupDisconnectSocket()

    async def connect_once(_url):
        return socket

    monkeypatch.setattr(listing_inventory, "_cdp_connect", connect_once)

    async def read_page():
        async with listing_inventory._cdp_session("ws://x") as entered:
            return entered

    assert asyncio.run(read_page()) is socket


def test_read_only_session_preserves_page_error_when_cleanup_disconnects(monkeypatch):
    socket = _CleanupDisconnectSocket()

    async def connect_once(_url):
        return socket

    monkeypatch.setattr(listing_inventory, "_cdp_connect", connect_once)

    async def read_page():
        async with listing_inventory._cdp_session("ws://x"):
            raise ValueError("page read failed")

    with pytest.raises(ValueError, match="page read failed"):
        asyncio.run(read_page())


def test_cdp_call_has_one_deadline_even_when_unrelated_events_continue(monkeypatch):
    monkeypatch.setattr(listing_inventory, "CDP_CALL_TIMEOUT_SECONDS", 0.01)

    async def call():
        return await listing_inventory._call(_EventOnlySocket(), "Runtime.evaluate", {}, 7)

    with pytest.raises(asyncio.TimeoutError, match="CDP call timed out"):
        asyncio.run(call())


def test_the_last_refusal_is_raised_unchanged(connect):
    install, _, _ = connect
    specific = OSError("server rejected WebSocket connection: HTTP 500")
    install([specific])
    with pytest.raises(OSError) as caught:
        asyncio.run(listing_inventory._cdp_connect("ws://x"))
    assert "HTTP 500" in str(caught.value)


def test_eval_json_goes_through_the_retrying_connect():
    source = (SCRIPTS / "listing_inventory.py").read_text(encoding="utf-8")
    block = source[source.index("async def _eval_json"):][:300]
    assert "_cdp_session" in block
    assert "websockets.connect(" not in block


def test_apply_parent_reuses_the_retrying_connect():
    source = (SCRIPTS / "application_parent.py").read_text(encoding="utf-8")
    # The pre-submit authenticated-identity readback adds one more guarded
    # session; it must use the same retrying connector as every other CDP path.
    assert source.count("async with await _cdp_connect(self.ws_url)") == 10
    assert "async with websockets.connect(" not in source
