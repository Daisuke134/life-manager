"""2026-10-10/11: drive_checkpoint2.py gave up when the review page hydrated slowly
(display-model combobox count 0), and publish_finish died on the first
is_confirmed_config_keys miss. A plain rerun of the same driver then verified at once
(8822853032, 17:40 -> 18:0x). One more driver pass must run before the die."""
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_finish.sh"


def test_cp2_driver_reruns_once_before_giving_up() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    loop = text.index("for CP2_ATTEMPT in 1 2")
    driver = text.index('"$AUTO/scripts/drive_checkpoint2.py" "$CP2"', loop)
    poll = text.index("poll is_confirmed_config_keys 1", driver)
    die = text.index("CP2 key host NOT confirmed", poll)
    assert loop < driver < poll < die
