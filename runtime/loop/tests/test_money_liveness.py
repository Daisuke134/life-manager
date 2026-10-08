import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from runtime.loop import money_liveness as ml  # noqa: E402

LANES = [{"id": "writer", "path": "w/articles.jsonl", "max_age_hours": 36,
          "meaning": "Writer published no article", "look_at": "launchd.err.log"}]


def _setup(tmp_path, age_hours):
    home = tmp_path / "home"
    (home / "w").mkdir(parents=True)
    f = home / "w" / "articles.jsonl"
    f.write_text("x")
    old = time.time() - age_hours * 3600
    os.utime(f, (old, old))
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"lanes": LANES}))
    return home, tmp_path / "state", cfg


def test_stale_lane_alerts_once_per_cooldown_then_recovers(tmp_path):
    home, state, cfg = _setup(tmp_path, age_hours=219)
    sent = []
    send = lambda t: sent.append(t) or True  # noqa: E731
    now = time.time()
    first = ml.run(home, state, send=send, now=now, config=cfg)
    assert first["stale"] == ["writer"] and len(sent) == 1 and "219h" in sent[0]
    ml.run(home, state, send=send, now=now + 3600, config=cfg)
    assert len(sent) == 1  # inside the 12h cooldown: no spam
    ml.run(home, state, send=send, now=now + 13 * 3600, config=cfg)
    assert len(sent) == 2  # still broken after the cooldown: remind
    f = home / "w" / "articles.jsonl"
    os.utime(f, (now + 14 * 3600, now + 14 * 3600))
    ml.run(home, state, send=send, now=now + 14 * 3600, config=cfg)
    assert len(sent) == 3 and sent[-1].startswith("RECOVERED")
    ml.run(home, state, send=send, now=now + 15 * 3600, config=cfg)
    assert len(sent) == 3  # recovery is announced once


def test_fresh_lane_is_silent(tmp_path):
    home, state, cfg = _setup(tmp_path, age_hours=1)
    sent = []
    result = ml.run(home, state, send=lambda t: sent.append(t) or True, config=cfg)
    assert result["stale"] == [] and sent == []


def test_missing_artifact_counts_as_stale(tmp_path):
    home, state, cfg = _setup(tmp_path, age_hours=1)
    (home / "w" / "articles.jsonl").unlink()
    sent = []
    ml.run(home, state, send=lambda t: sent.append(t) or True, config=cfg)
    assert len(sent) == 1 and "never" in sent[0]


def test_failed_delivery_is_retried_next_tick(tmp_path):
    home, state, cfg = _setup(tmp_path, age_hours=219)
    now = time.time()
    ml.run(home, state, send=lambda t: False, now=now, config=cfg)
    sent = []
    ml.run(home, state, send=lambda t: sent.append(t) or True, now=now + 300, config=cfg)
    assert len(sent) == 1


def test_real_config_lanes_are_well_formed():
    lanes = json.loads(ml.CONFIG.read_text())["lanes"]
    assert lanes and all({"id", "path", "max_age_hours", "meaning", "look_at"} <= set(l) for l in lanes)
