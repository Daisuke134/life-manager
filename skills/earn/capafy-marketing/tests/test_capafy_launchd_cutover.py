import plistlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MARKETING_LAUNCHD = ROOT / "skills/earn/capafy-marketing/launchd"
LOOP_LAUNCHD = ROOT / "skills/self/capafy-loop/launchd"
RENDER = MARKETING_LAUNCHD / "render-launchd.sh"
EXPECTED = {
    "ai.anicca.capafy-goal-monitor": "skills/earn/capafy-marketing/capafy-goal-monitor.sh",
    "ai.anicca.capafy-goal-monitor-hourly": "skills/earn/capafy-marketing/capafy-goal-monitor.sh",
    "ai.anicca.capafy-goal-monitor-daily-close": "skills/earn/capafy-marketing/capafy-goal-monitor.sh",
    "ai.anicca.capafy-ig-account-manager": "skills/earn/capafy-marketing/capafy-ig-account-manager.sh",
    "ai.anicca.capafy-ig-marketing-daily": "skills/earn/capafy-marketing/capafy-ig-marketing-daily.sh",
    "ai.anicca.capafy-outcome-monitor": "skills/earn/capafy-marketing/capafy-outcome-monitor.sh",
    "ai.anicca.capafy-loop-daily": "skills/self/capafy-loop/capafy-loop-daily.sh",
    "ai.anicca.capafy-loop-healthcheck": "skills/self/capafy-loop/capafy-loop-healthcheck.sh",
}


def test_all_capafy_launchd_templates_resolve_to_existing_life_manager_sources(tmp_path):
    state_home = tmp_path / "state"
    subprocess.run(
        [
            "bash",
            str(RENDER),
            "--output-dir",
            str(tmp_path),
            "--repo-root",
            str(ROOT),
            "--life-manager-home",
            str(state_home),
        ],
        check=True,
    )
    for label, relative_script in EXPECTED.items():
        plist_path = tmp_path / f"{label}.plist"
        data = plistlib.loads(plist_path.read_bytes())
        expected_script = str(ROOT / relative_script)

        assert data["Label"] == label
        assert data["ProgramArguments"] == ["/bin/bash", expected_script]
        assert data["WorkingDirectory"] == str(ROOT)
        assert Path(expected_script).is_file()
        assert "/Users/anicca/anicca" not in plist_path.read_text()

    ig = plistlib.loads((tmp_path / "ai.anicca.capafy-ig-marketing-daily.plist").read_bytes())
    assert ig["StartInterval"] == 3600
    assert "StartCalendarInterval" not in ig


def test_ig_goal_monitor_generator_uses_hourly_interval() -> None:
    text = (ROOT / "skills/earn/capafy-marketing/capafy-goal-monitor.sh").read_text()
    assert "<key>StartInterval</key><integer>3600</integer>" in text
    start = text.index("write_ig_plist() {")
    assert "StartCalendarInterval" not in text[start:text.index("\n}\n", start)]
