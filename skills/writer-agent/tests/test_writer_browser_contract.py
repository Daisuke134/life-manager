import json
from pathlib import Path


ROOT = Path(__file__).parents[3]
MANIFEST = ROOT / "skills" / "earn" / "gig" / "config" / "launchd-jobs.json"
DAILY = ROOT / "skills" / "writer-agent" / "article-daily.sh"
RESUME = ROOT / "skills" / "writer-agent" / "scripts" / "article-resume-pending.sh"


def test_writer_uses_authenticated_x_driver_not_coconala_driver():
    writer_env = json.loads(MANIFEST.read_text())['writer_env']
    assert writer_env['WRITER_CDP_URL'] == 'http://127.0.0.1:9222'
    assert writer_env['WRITER_CDP_PORT'] == '9222'
    assert writer_env['WRITER_CDP_PROFILE'].endswith('/.cloak/profiles/daily-driver')
    assert writer_env['CLOAK_BROWSER_LAUNCHD_LABEL'] == 'ai.anicca.life-manager-daily-driver'
    assert 'BROWSER_GUARD=' in DAILY.read_text()
    assert 'WRITER_CDP_URL' in RESUME.read_text()
