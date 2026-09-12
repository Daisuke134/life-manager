from pathlib import Path


def test_bounded_live_meeting_handoff_does_not_conflict_with_human_deliverable_refusal():
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "application_loop.py"
    ).read_text(encoding="utf-8")

    assert "Zoom・電話・video meetingが明示的に必須でも拒否せず" in source
    assert "同期参加そのものが成果物ならmandatory_human_presence" in source
    assert "shared Telegram human-handoff" in source
    assert "必須ならhard_prohibitedにする" not in source
    assert "SKIP_CACHE_VERSION = 3" in source
