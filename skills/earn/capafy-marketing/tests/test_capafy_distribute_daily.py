"""Dry-run, no-network smoke tests for capafy-distribute-daily.sh.

Exercises the real script (ledger check, skill selection, run-dir setup,
dry-run receipt) with everything redirected into tmp_path so no production
state under ~/.local/state/life-manager is touched and no model/network call
is ever made (CAPAFY_DISTRIBUTE_DRY_RUN=1 short-circuits before the model
dispatch).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3].parent  # .../life-manager-main worktree root
SCRIPT = REPO_ROOT / "skills" / "earn" / "capafy-marketing" / "capafy-distribute-daily.sh"

PRODUCTS_JSON = {
    "products": {
        "anicca": {"landing_url": "https://aniccaai.com/lm"},
        "capafy-skills": {
            "skills": {
                "hook-lab": {"agent_id": "111", "buyer_problem": "hook problem"},
                "slide-maker": {"agent_id": "222", "buyer_problem": "slide problem"},
            }
        },
    }
}


def run(tmp_path: Path, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    products_config = tmp_path / "products.json"
    products_config.write_text(json.dumps(PRODUCTS_JSON))
    env_file = tmp_path / "empty.env"
    env_file.write_text("")
    state_dir = tmp_path / "capafy-distribute-state"
    fence_dir = tmp_path / "owner-fence"
    env = dict(os.environ)
    env.update(
        {
            "CAPAFY_DISTRIBUTE_DRY_RUN": "1",
            "CAPAFY_DISTRIBUTE_PRODUCTS_CONFIG": str(products_config),
            "CAPAFY_DISTRIBUTE_ANALYTICS_FILE": str(tmp_path / "does-not-exist.json"),
            "CAPAFY_DISTRIBUTE_STATE_DIR": str(state_dir),
            "CAPAFY_DISTRIBUTE_OWNER_FENCE_DIR": str(fence_dir),
            "LIFE_MANAGER_ENV_FILE": str(env_file),
            "LIFE_MANAGER_LOOP_ID": "capafy-distribute-daily",
            "LIFE_MANAGER_RUN_ID": "test-run-1",
            "LIFE_MANAGER_OCCURRENCE_ID": "capafy-distribute-daily:test-run-1",
            "POSTIZ_API_KEY": "test-no-network",
            "LM_POSTIZ_API_KEY": "",
            "WRITER_STATE_DIR": str(state_dir),
        }
    )
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, check=False, env=env, timeout=60,
    )


def test_dry_run_exits_zero_and_writes_ledger(tmp_path: Path) -> None:
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    ledger_path = tmp_path / "capafy-distribute-state" / "ledger.json"
    assert ledger_path.exists()
    ledger = json.loads(ledger_path.read_text())
    assert len(ledger) == 1
    (entry,) = ledger.values()
    assert entry["status"] == "dry_run"
    assert entry["capafy_skill"] in {"hook-lab", "slide-maker"}
    # Capafy only attributes ct values registered as promotion links in the
    # console (2026-10-07); these are the ones issued for the sellers.
    assert entry["cta_url"].endswith(("ct=hooklab_blog", "ct=slides_blog"))
    occurrence_files = list((tmp_path / "capafy-distribute-state" / "occurrences").glob("*.json"))
    assert len(occurrence_files) == 1
    occurrence = json.loads(occurrence_files[0].read_text())
    assert occurrence["owner_id"] == "capafy-distribute-daily"
    assert occurrence["run_id"] == "test-run-1"
    assert occurrence["occurrence_id"] == "capafy-distribute-daily:test-run-1"
    keyword_slugs = {k["slug"] for f in (Path(__file__).resolve().parents[1] / "seo").glob("*-keywords.json")
                     for k in json.loads(f.read_text())}
    assert occurrence["slot"] in occurrence["article_slug"] or occurrence["article_slug"] in keyword_slugs
    assert not list((tmp_path / "capafy-distribute-state" / "runs").rglob("occurrence.json"))


def test_mismatched_runtime_occurrence_identity_stops_before_receipt(tmp_path: Path) -> None:
    result = run(tmp_path, {"LIFE_MANAGER_OCCURRENCE_ID": "line-sticker:other-run"})
    assert result.returncode != 0
    assert not (tmp_path / "capafy-distribute-state" / "ledger.json").exists()


def test_second_dry_run_same_day_is_a_no_op_and_does_not_rewrite_the_pick(tmp_path: Path) -> None:
    first = run(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    ledger_path = tmp_path / "capafy-distribute-state" / "ledger.json"
    first_ledger = json.loads(ledger_path.read_text())

    second = run(tmp_path, {
        "LIFE_MANAGER_RUN_ID": "test-run-2",
        "LIFE_MANAGER_OCCURRENCE_ID": "capafy-distribute-daily:test-run-2",
    })
    assert second.returncode == 0, second.stdout + second.stderr
    second_ledger = json.loads(ledger_path.read_text())

    assert first_ledger == second_ledger  # idempotent: no duplicate publish, same receipt


def test_already_published_slot_writes_occurrence_bound_no_effect_hint(tmp_path: Path) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    slot = f"{now:%Y-%m-%d}-h{now.hour:02d}m{(now.minute // 30) * 30:02d}"
    home = tmp_path / "home"
    writer_state = home / ".local/state/life-manager/writer"
    state_dir = writer_state / "capafy-distribute/capafy-distribute"
    state_dir.mkdir(parents=True)
    (state_dir / "ledger.json").write_text(json.dumps({slot: {"status": "published"}}))
    occurrence = "capafy-distribute-daily:test-run-1"
    events = writer_state / "capafy-distribute/events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    events.write_text(json.dumps({
        "owner_id": "capafy-distribute-daily",
        "run_id": "test-run-1",
        "occurrence_id": occurrence,
        "phase": "execute",
        "status": "running",
        "timestamp": now.isoformat(),
    }) + "\n")
    hint = tmp_path / "entrypoint-result.json"

    result = run(tmp_path, {
        "HOME": str(home),
        "WRITER_STATE_DIR": str(writer_state / "capafy-distribute"),
        "CAPAFY_DISTRIBUTE_STATE_DIR": str(state_dir),
        "LIFE_MANAGER_RESULT_HINT_PATH": str(hint),
    })

    assert result.returncode == 0, result.stdout + result.stderr
    value = json.loads(hint.read_text())
    assert value == {
        "schema_version": 1,
        "kind": "life_manager_no_effect_result",
        "status": "verified_no_effect",
        "effect": 0,
        "owner_id": "capafy-distribute-daily",
        "occurrence_id": "capafy-distribute-daily:test-run-1",
        "reason": "daily_limit_reached",
    }
    assert hint.stat().st_mode & 0o777 == 0o600


def test_wrapper_publish_keeps_a_multiword_query_as_one_argument() -> None:
    text = SCRIPT.read_text()
    start = text.index("SEO_PUBLISH_ARGS=()")
    end = text.index("\nFREE_ARTICLE_URL=", start)
    arguments = text[start:end]
    assert 'SEO_PUBLISH_ARGS+=(--title-must-contain "$SEO_QUERY" --indexnow-key "$INDEXNOW_KEY")' in arguments
    assert '"${SEO_PUBLISH_ARGS[@]}"' in text
    out = subprocess.run(
        ["bash", "-c", f'SEO_QUERY="hook script template"; INDEXNOW_KEY=k\n{arguments}\nprintf "%s\\n" "${{SEO_PUBLISH_ARGS[@]}}"'],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    assert out == ["--title-must-contain", "hook script template", "--indexnow-key", "k"]


def test_model_runner_does_not_inherit_loop_owned_result_hint_path() -> None:
    text = SCRIPT.read_text()
    dispatch = text.index('python3 "$LIFE_MANAGER_REPO/runtime/loop/bounded-exec.py"')
    sanitization = text.rfind(
        "env -u LIFE_MANAGER_RESULT_HINT_PATH -u CAPAFY_DISTRIBUTE_STATE_DIR", 0, dispatch)
    assert sanitization >= 0
    for variable in (
        "CAPAFY_DISTRIBUTE_EVENTS_PATH", "CAPAFY_DISTRIBUTE_RUNS_ROOT",
        "LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", "LIFE_MANAGER_LOOP_ID",
        "LIFE_MANAGER_RUN_ID", "LIFE_MANAGER_OCCURRENCE_ID", "POSTIZ_API_KEY",
        "LM_POSTIZ_API_KEY", "LIFE_MANAGER_MARKETING_ENV_FILE",
    ):
        assert f"-u {variable}" in text[sanitization:dispatch]


def test_model_prompt_only_writes_draft_and_caption_for_wrapper() -> None:
    text = SCRIPT.read_text()
    prompt = text.split('cat >"$PROMPT_FILE" <<PROMPT_EOF\n', 1)[1].split(
        "\nPROMPT_EOF", 1)[0]
    assert "Do not publish" in prompt
    assert "validates the JSON" in prompt
    assert "writes the draft and caption" in prompt
    assert '"article_markdown"' in prompt and '"x_caption"' in prompt
    assert "or write files" in prompt
    assert "capafy_free_article.py publish" not in prompt
    assert "Do not publish, push commits, call Postiz, run capafy_x_post.py" in prompt
    assert "capafy_distribute_ledger.py record" not in prompt
    assert '"$ARTICLE_MODEL_RUNNER" agent-workspace --prompt-file "$PROMPT_FILE"' in text
    assert 'ARTICLE_CODEX_NO_TOOLS=1' in text
    assert "write_capafy_pii_gate_attestation" in text
    assert "--no-effect-reason pii_gate_blocked" in text
    assert 'TG_MARK="$CAPAFY_DISTRIBUTE_STATE_DIR/notifications/$LIFE_MANAGER_RUN_ID.telegram-sent"' in text


def test_wrapper_runs_pii_gate_before_external_article_publish() -> None:
    text = SCRIPT.read_text()
    model = text.index('"$ARTICLE_MODEL_RUNNER" agent-workspace --prompt-file "$PROMPT_FILE"')
    materialize = text.index('python3 "$SELF_DIR/capafy_draft_output.py" materialize')
    gate = text.index('"$ARTICLE_ROOT/scripts/pii-gate.py" --stage capafy-distribute-publish')
    attest = text.index("write_capafy_pii_gate_attestation")
    no_effect = text.index("--no-effect-reason pii_gate_blocked")
    publish = text.index('python3 "$SELF_DIR/capafy_free_article.py" publish')
    assert model < materialize < gate
    assert gate < attest < no_effect < publish


def test_prompt_guidance_is_loaded_before_unquoted_prompt_heredoc() -> None:
    text = SCRIPT.read_text()
    craft = text.index('CRAFT_GUIDANCE="$(cat "$ARTICLE_ROOT/reference/CRAFT.md")"')
    identity = text.index('IDENTITY_GUIDANCE="$(awk')
    prompt = text.index('cat >"$PROMPT_FILE" <<PROMPT_EOF')
    assert craft < prompt
    assert identity < prompt


def test_x_post_requires_wrapper_verified_published_article() -> None:
    text = SCRIPT.read_text()
    x_post = text.index('python3 "$SELF_DIR/capafy_x_post.py" --caption')
    guard = text.rfind('if [ "$X_CHECK_RC" -eq 10 ]', 0, x_post)
    ledger_check = text.rfind('capafy_distribute_ledger.py" check --ledger "$LEDGER" --date "$SLOT"',
                              0, x_post)
    assert ledger_check >= 0
    assert guard > ledger_check


def test_seo_brief_renders_under_launchd_python39() -> None:
    # launchd resolves python3 to /usr/bin/python3 (3.9); a backslash inside an f-string
    # expression is a SyntaxError there, which left SEO_BRIEF empty in every production run.
    import shutil

    py = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else shutil.which("python3")
    text = SCRIPT.read_text()
    start = text.index('SEO_BRIEF="$(printf')
    end = text.index("')\"", start)
    code = text[text.index("python3 -c '", start) + len("python3 -c '"):end]
    out = subprocess.run(
        [py, "-c", code], input='{"query": "hook script template", "lang": "en"}',
        capture_output=True, text=True, check=True,
    ).stdout
    assert 'search query "hook script template" in language "en"' in out


def test_publish_flags_preserve_utf8_and_one_shell_argument_across_locales() -> None:
    text = SCRIPT.read_text()
    start = text.index("SEO_PUBLISH_ARGS=()")
    end = text.index("\nFREE_ARTICLE_URL=", start)
    arguments = text[start:end]
    for locale in ('en_US.UTF-8', 'C'):
        for query in ('リール 冒頭 文言', 'ganchos para vídeos',
                      "creator's hook; $(echo must-stay-literal)"):
            result = subprocess.run(
                ['/bin/bash', '-c', arguments + '\nprintf \'%s\\0\' "${SEO_PUBLISH_ARGS[@]}"'],
                env=os.environ | {'SEO_QUERY': query, 'INDEXNOW_KEY': 'test',
                                  'LC_ALL': locale}, capture_output=True, check=True)
            flags = result.stdout.decode('utf-8').split('\0')[:-1]
            assert flags == ['--title-must-contain', query,
                             '--indexnow-key', 'test']


def test_every_distributable_seller_has_issued_blog_and_x_promotion_links() -> None:
    # Capafy counts a ?ct= visit only when that token was created in the seller console, and it
    # rewrites the name (hyphens -> underscores). A skill without an issued pair is measured as zero.
    import re

    text = SCRIPT.read_text()
    block = text[text.index('case "$CAPAFY_SKILL_SLUG" in'):text.index("esac", text.index('case "$CAPAFY_SKILL_SLUG" in'))]
    mapped = dict(re.findall(r"^\s{2}([a-z-]+)\) CAPAFY_CT=(\w+); X_CT=\w+ ;;", block, re.M))
    assert mapped["tiktok-series-continuity-planner"] == "tiktok_series_blog"
    assert "X_CT=tiktok_series_x" in block


def test_allowlisted_agent_links_go_through_click_counter(tmp_path: Path, monkeypatch) -> None:
    # 8123079349 / 8828622062 are in site/netlify/functions/allowed-agents.json, so the
    # article and X links route via /go/<agent>/<platform>/<post> and keep the ct token.
    monkeypatch.setitem(PRODUCTS_JSON["products"]["capafy-skills"]["skills"]["hook-lab"], "agent_id", "8123079349")
    monkeypatch.setitem(PRODUCTS_JSON["products"]["capafy-skills"]["skills"]["slide-maker"], "agent_id", "8828622062")
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    (entry,) = json.loads((tmp_path / "capafy-distribute-state" / "ledger.json").read_text()).values()
    go = "https://capafy-skills-daily.netlify.app/go/"
    assert entry["cta_url"].startswith(go) and "/article/" in entry["cta_url"]
    assert entry["cta_url"].endswith(("?ct=hooklab_blog", "?ct=slides_blog"))
    assert entry["x_cta_url"].startswith(go) and "/x/x-" in entry["x_cta_url"]
    assert entry["x_cta_url"].endswith(("?ct=hooklab_x", "?ct=slides_x"))
