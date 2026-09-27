from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/ig_metrics.py"
SPEC = importlib.util.spec_from_file_location("ig_metrics", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_browser_fallback_is_repo_owned() -> None:
    repo = Path(__file__).resolve().parents[4]
    cdp = Path(MODULE.CDP).resolve()

    assert cdp.is_relative_to(repo)
    assert cdp.is_file()


def test_private_metrics_and_suspended_dom_do_not_fabricate_zero(tmp_path, monkeypatch):
    settings = tmp_path / "instagrapi-capafy.example.json"
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(MODULE.os.path, "expanduser", lambda _: str(settings))

    class Media:
        def model_dump(self):
            return {"play_count": 8, "view_count": 0, "like_count": 1, "comment_count": 2}

    class Client:
        def load_settings(self, _): pass
        def media_pk_from_code(self, code): return f"pk:{code}"
        def media_info_v1(self, pk):
            assert pk == "pk:DcWRx9ys7Cv"
            return Media()

    class Poster:
        @staticmethod
        def apply_proxy(client, handle, result, accounts):
            assert handle == "capafy.example"

    measured = MODULE._private_read(
        "https://www.instagram.com/reel/DcWRx9ys7Cv/",
        "capafy.example",
        client_factory=Client,
        poster_module=Poster,
    )
    assert measured == {
        "views": 8,
        "likes": 1,
        "comments": 2,
        "source": "instagrapi_private",
        "metric_status": "measured",
    }
    assert MODULE._browser_metrics({"available": False, "reason": "article_absent"}) is None

    metrics = tmp_path / "metrics.jsonl"
    marker = tmp_path / "reach.json"
    rows = [
        {"reel_url": "one", "handle": "current", "source": "instagrapi_private", "metric_status": "measured", "views": 1},
        {"reel_url": "two", "handle": "old", "source": "instagram_public_dom", "metric_status": "measured", "views": 99},
    ]
    metrics.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    assert MODULE._write_reach_marker(metrics, marker, "current") is False
    assert not marker.exists()

    rows[1]["source"] = "instagrapi_private"
    rows[1]["handle"] = "current"
    metrics.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    assert MODULE._write_reach_marker(metrics, marker, "current") is True
    assert json.loads(marker.read_text())["status"] == "reach_healthy"


def test_dead_session_self_heals_via_login_resilient(tmp_path, monkeypatch) -> None:
    """P-6 2026-09-27: a dead saved instagrapi session (LoginRequired) must not permanently stall
    metrics — _private_read should call the SAME login_resilient tier1/tier2/tier3 policy the
    poster uses, then retry the read, instead of returning None forever."""
    settings = tmp_path / "instagrapi-capafy.example.json"
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(MODULE.os.path, "expanduser", lambda _: str(settings))

    class Media:
        def model_dump(self):
            return {"play_count": 5, "view_count": 0, "like_count": 0, "comment_count": 0}

    class Client:
        def __init__(self):
            self.healed = False

        def load_settings(self, _):
            raise Exception("login_required")

        def media_pk_from_code(self, code):
            return f"pk:{code}"

        def media_info_v1(self, pk):
            if not self.healed:
                raise AssertionError("login_resilient must run before a retry")
            return Media()

    login_resilient_calls = []

    class Poster:
        @staticmethod
        def apply_proxy(client, handle, result, accounts):
            pass

        @staticmethod
        def login_resilient(client, handle, port, res, settings_path=None, accounts_path=None):
            login_resilient_calls.append((handle, port))
            client.healed = True
            return True

    measured = MODULE._private_read(
        "https://www.instagram.com/reel/DcWRx9ys7Cv/",
        "capafy.example",
        client_factory=Client,
        poster_module=Poster,
        port=49444,
    )
    assert login_resilient_calls == [("capafy.example", 49444)]
    assert measured == {
        "views": 5,
        "likes": 0,
        "comments": 0,
        "source": "instagrapi_private",
        "metric_status": "measured",
    }


def test_dead_session_without_port_gives_up_cleanly(tmp_path, monkeypatch) -> None:
    settings = tmp_path / "instagrapi-capafy.example.json"
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(MODULE.os.path, "expanduser", lambda _: str(settings))

    class Client:
        def load_settings(self, _):
            raise Exception("login_required")

        def media_pk_from_code(self, code):
            return f"pk:{code}"

    class Poster:
        @staticmethod
        def apply_proxy(client, handle, result, accounts):
            pass

    assert MODULE._private_read(
        "https://www.instagram.com/reel/DcWRx9ys7Cv/",
        "capafy.example",
        client_factory=Client,
        poster_module=Poster,
        port=None,
    ) is None
