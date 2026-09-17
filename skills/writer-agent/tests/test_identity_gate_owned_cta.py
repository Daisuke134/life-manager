import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
IDENTITY_GATE = ROOT / "scripts" / "identity-gate.sh"


def test_identity_gate_hides_query_only_owned_cta_from_context_judge(tmp_path: Path) -> None:
    article = tmp_path / "article-ja.md"
    article.write_text(
        "この記事は読者の次の一歩を整理します。\n\n"
        "[手順を確認する](https://aniccaai.com?product_id=anicca&run_id=run-1&"
        "artifact_id=article-ja&variant_id=workflow&click_id=run-1-article-ja)\n",
        encoding="utf-8",
    )
    runner = tmp_path / "judge.sh"
    runner.write_text(
        "#!/bin/sh\n"
        "if grep -q 'https://aniccaai.com?product_id='; then\n"
        "  printf '%s\\n' '{\"verdict\":\"FAIL\",\"violations\":[\"C: owned CTA leaked\"]}'\n"
        "else\n"
        "  printf '%s\\n' '{\"verdict\":\"PASS\",\"violations\":[]}'\n"
        "fi\n",
        encoding="utf-8",
    )
    runner.chmod(0o700)
    env = {
        **os.environ,
        "ARTICLE_ROOT": str(ROOT),
        "ARTICLE_SKILL_DIR": str(ROOT),
        "LIFE_MANAGER_REPO": str(ROOT.parent.parent),
        "ARTICLE_MODEL_RUNNER": str(runner),
        "ARTICLE_RUN_DIR": str(tmp_path / "run"),
        "ARTICLE_GATES_LOG": str(tmp_path / "gates.log"),
        "LIFE_MANAGER_ENV_FILE": str(tmp_path / "missing.env"),
    }

    result = subprocess.run(
        ["bash", str(IDENTITY_GATE), str(article), "--lang", "ja"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert '"verdict":"PASS"' in result.stdout
