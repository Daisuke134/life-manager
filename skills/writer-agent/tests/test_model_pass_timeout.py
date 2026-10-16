import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "article-daily.sh"


def test_model_pass_bound_covers_a_full_pass_through_publication():
    # 2026-10-17 run 20261016-230536: conscience ALLOW for both languages at 14.6 min, then the
    # 900 s bound killed the pass 27 s later, before STEP 4.9 init and the four destinations.
    # Every pass then ended before publication. The bound must leave room for publication and
    # still end before the next hourly calendar start.
    default = re.search(r'ARTICLE_MODEL_AGENT_TIMEOUT_SECONDS:-(\d+)', SCRIPT.read_text()).group(1)
    assert 1800 <= int(default) <= 3000
