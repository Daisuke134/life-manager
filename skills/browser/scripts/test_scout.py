import asyncio
import json

import pytest

import scout


def test_browser_ws_uses_registered_identity_endpoint(monkeypatch):
    seen = []

    class Response:
        def read(self):
            return b'{"webSocketDebuggerUrl":"ws://127.0.0.1:9233/devtools/browser/test"}'

    def open_url(url, *, timeout):
        seen.append((url, timeout))
        return Response()

    monkeypatch.setenv("CLOAK_CDP_BASE_URL", "http://127.0.0.1:9233/")
    monkeypatch.setattr(scout.urllib.request, "urlopen", open_url)

    assert scout._browser_ws() == "ws://127.0.0.1:9233/devtools/browser/test"
    assert seen == [("http://127.0.0.1:9233/json/version", 8)]


def test_browser_attach_failure_closes_and_releases_target(monkeypatch):
    events = []

    class Socket:
        last = None

        async def send(self, payload):
            self.last = json.loads(payload)
            events.append(("send", self.last["method"]))

        async def recv(self):
            if self.last["method"] == "Target.createTarget":
                return json.dumps({"id": self.last["id"], "result": {"targetId": "scout-tab"}})
            if self.last["method"] == "Target.attachToTarget":
                return json.dumps({"id": self.last["id"], "error": {"message": "attach failed"}})
            return json.dumps({"id": self.last["id"], "result": {"success": True}})

    class Connection:
        async def __aenter__(self):
            return Socket()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(scout, "_browser_ws", lambda: "ws://browser")
    monkeypatch.setattr(scout.websockets, "connect", lambda *_a, **_k: Connection())
    monkeypatch.setattr(
        scout.target_ownership,
        "claim_target",
        lambda target, owner: events.append(("claim", target, owner)),
    )
    monkeypatch.setattr(
        scout.target_ownership,
        "release_target",
        lambda target, owner: events.append(("release", target, owner)),
    )

    with pytest.raises(RuntimeError):
        scout._browser("https://coconala.com")
    assert events == [
        ("send", "Target.createTarget"),
        ("claim", "scout-tab", "browser-scout"),
        ("send", "Target.attachToTarget"),
        ("send", "Target.closeTarget"),
        ("release", "scout-tab", "browser-scout"),
    ]
