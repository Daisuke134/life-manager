from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
CHILD = ROOT / "skills/capafy-autopublish/scripts/daily_loop.sh"
PARENT = ROOT / "skills/self/capafy-loop/capafy-loop-daily.sh"


def _between(source: str, start: str, end: str) -> str:
    start_at = source.index(start)
    end_at = source.index(end, start_at)
    return source[start_at:end_at]


def _child_terminal_block() -> str:
    source = CHILD.read_text(encoding="utf-8")
    start = 'MAXTURNS_STREAK="$CAPAFY_STATE_DIR/.maxturns-streak"'
    return _between(source, start, "\nexit $RC") + "\nexit $RC"


def _parent_dispatch_block() -> tuple[str, str]:
    source = PARENT.read_text(encoding="utf-8")
    mark_start = "mark_healthy() {"
    mark_end = source.index("\n}\n", source.index(mark_start)) + len("\n}")
    dispatch_start = 'if [ "$VERDICT" = "PUBLISHABLE" ] && [ ! -f "$SELFHEAL_REQUEST" ]; then'
    dispatch_end = source.index("\nfi\n\nPROMPT=", source.index(dispatch_start)) + len("\nfi")
    return source[source.index(mark_start):mark_end], source[source.index(dispatch_start):dispatch_end]


def _run_parent_child(tmp_path: Path, *, post: str, rc: int, max_turns: bool = False) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    release = tmp_path / "release"
    child_path = release / "skills/capafy-autopublish/scripts/daily_loop.sh"
    child_state = tmp_path / "child-state"
    log = tmp_path / "loop.log"
    child_marker = child_state / ".capafy-healthy-pass"
    parent_last_pass = tmp_path / ".last-pass"
    parent_healthy = tmp_path / ".parent-healthy"
    child_state.mkdir(parents=True)
    if max_turns:
        (child_state / ".maxturns-streak").write_text("2\n", encoding="utf-8")
    child_path.parent.mkdir(parents=True)
    if max_turns:
        log.write_text("Reached max turns\n", encoding="utf-8")

    child_setup = "\n".join(
        (
            "set -uo pipefail",
            f"POST={shlex.quote(post)}",
            f"RC={rc}",
            f"MARK={shlex.quote(str(child_marker))}",
            f"CAPAFY_STATE_DIR={shlex.quote(str(child_state))}",
            f"LOG={shlex.quote(str(log))}",
            "TS=test",
            'PRE_ONLINE=""',
            'POST_ONLINE=""',
            _child_terminal_block(),
            "",
        )
    )
    child_path.write_text(child_setup, encoding="utf-8")

    mark_healthy, parent_dispatch = _parent_dispatch_block()
    parent_script = "\n".join(
        (
            "set -uo pipefail",
            f"export LIFE_MANAGER_RELEASE_ROOT={shlex.quote(str(release))}",
            f"export SELFHEAL_REQUEST={shlex.quote(str(tmp_path / 'no-selfheal-request'))}",
            f"export LOG={shlex.quote(str(log))}",
            f"export LAST_PASS_MARKER={shlex.quote(str(parent_last_pass))}",
            f"export HEALTHY_MARKER={shlex.quote(str(parent_healthy))}",
            "VERDICT=PUBLISHABLE",
            mark_healthy,
            parent_dispatch,
            "",
        )
    )
    result = subprocess.run(["bash", "-c", parent_script], capture_output=True, text=True, check=False)
    return result, child_marker, parent_last_pass, parent_healthy


@pytest.mark.parametrize("terminal", ["blocked", "max_turns_stuck"])
def test_failed_child_with_zero_runner_status_never_marks_parent_healthy(tmp_path: Path, terminal: str) -> None:
    result, child_marker, parent_last_pass, parent_healthy = _run_parent_child(
        tmp_path,
        post="PUBLISHABLE",
        rc=0,
        max_turns=terminal == "max_turns_stuck",
    )

    assert result.returncode == 1
    assert not child_marker.exists()
    assert not parent_last_pass.exists()
    assert not parent_healthy.exists()


@pytest.mark.parametrize("terminal", ["blocked", "max_turns_stuck"])
def test_failed_child_preserves_existing_nonzero_runner_status(tmp_path: Path, terminal: str) -> None:
    result, child_marker, parent_last_pass, parent_healthy = _run_parent_child(
        tmp_path,
        post="PUBLISHABLE",
        rc=124,
        max_turns=terminal == "max_turns_stuck",
    )

    assert result.returncode == 124
    assert not child_marker.exists()
    assert not parent_last_pass.exists()
    assert not parent_healthy.exists()


@pytest.mark.parametrize("post", ["DRAINED", "CAP_FULL"])
def test_legitimate_noop_still_marks_child_and_parent_healthy(tmp_path: Path, post: str) -> None:
    result, child_marker, parent_last_pass, parent_healthy = _run_parent_child(
        tmp_path,
        post=post,
        rc=0,
    )

    assert result.returncode == 0
    assert child_marker.exists()
    assert parent_last_pass.exists()
    assert parent_healthy.exists()


def _retry_existing_stub_block() -> str:
    source = CHILD.read_text(encoding="utf-8")
    receipt = _between(source, "finish_receipt() {", "\n}\n") + "\n}"
    start = "retry_existing_stub_finish() {"
    return receipt + "\n" + _between(source, start, "\n}\n") + "\n}"


def _run_retry_existing(
    tmp_path: Path,
    *,
    finish_rc: int = 0,
    manifest_agent_id: str = "7393298474",
    manifest_version: str = "2110426515594047488",
    remote_status: int = 0,
    remote_version: str = "2110426515594047488",
    post_remote_status: int = 1,
    post_remote_version: str | None = None,
    remote_ok: bool = True,
    post_remote_ok: bool = True,
    confirmed_skills: bool = True,
    confirmed_config_keys: bool = True,
    package_uploaded: bool = True,
    post_confirmed_skills: bool = True,
    post_confirmed_config_keys: bool = True,
    post_package_uploaded: bool = True,
    model_result: str = "MODEL_MATCH deepseek/deepseek-v4.1-flash",
    model_result_second: str | None = None,
    missing_raw_field: str = "",
    retry_reason: str = "retry Capafy AI-generator stub draft on the same agent_id",
    run_resume_branch: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path, Path]:
    release = tmp_path / "release"
    auto = release / "skills/capafy-autopublish"
    scripts = auto / "scripts"
    scripts.mkdir(parents=True)
    publisher = auto / "vendor/capafy-publisher"
    publisher.mkdir(parents=True)
    state_home = tmp_path / "state"
    capafy_state = state_home / "state/capafy-autopublish"
    capafy_state.mkdir(parents=True)
    publisher_state = state_home / "runtime/capafy-publisher"
    agent_id = "7393298474"
    version_id = "2110426515594047488"
    remote_version = remote_version or version_id
    post_remote_version = post_remote_version or remote_version
    skill_dir = tmp_path / "catalog/tiktok-comment-reply-script-pack"
    skill_dir.mkdir(parents=True)
    skill = skill_dir / "SKILL.md"
    listing = skill_dir / "LISTING.md"
    icon = skill_dir / "icon.png"
    skill.write_text("skill", encoding="utf-8")
    listing.write_text("listing", encoding="utf-8")
    icon.write_bytes(b"png")
    manifest = publisher_state / "work" / "agents" / agent_id / "publish-work-state.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"agent_id": manifest_agent_id, "agent_version_id": manifest_version}),
        encoding="utf-8",
    )

    (scripts / "check_hosted_model.py").write_text(
        'import os\nfrom pathlib import Path\n'
        'p=Path(os.environ["MODEL_STATUS_CALLS"])\n'
        'n=int(p.read_text()) if p.exists() else 0\np.write_text(str(n+1))\n'
        'print(os.environ["MODEL_RESULT"] if n == 0 else os.environ["MODEL_RESULT_SECOND"])\n',
        encoding="utf-8")
    (publisher / "packager.py").write_text(
        "import json,os,sys\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(ROOT / 'skills/capafy-autopublish/vendor/capafy-publisher')!r})\n"
        "from packaging.publish.platform.runtime_mapping import LatestVersion\n"
        "agent_id=sys.argv[sys.argv.index('--agent-id')+1]\n"
        "calls_path=Path(os.environ['REMOTE_STATUS_CALLS'])\n"
        "calls=int(calls_path.read_text()) if calls_path.exists() else 0\n"
        "calls_path.write_text(str(calls+1))\n"
        f"status={remote_status}\n"
        f"version='{remote_version}'\n"
        f"skills={confirmed_skills}\n"
        f"config={confirmed_config_keys}\n"
        f"package={package_uploaded}\n"
        f"ok={remote_ok}\n"
        "if calls > 0:\n"
        f" status={post_remote_status}\n"
        f" version='{post_remote_version}'\n"
        f" skills={post_confirmed_skills}\n"
        f" config={post_confirmed_config_keys}\n"
        f" package={post_package_uploaded}\n"
        f" ok={post_remote_ok}\n"
        "raw={'agentId':agent_id,'agentVersionId':version,'status':status,"
        "'auditStatus':0,'agentType':'run_online','isConfirmedSkills':skills,"
        "'isConfirmedConfigKeys':config,'packageUrl':"
        "('https://example.test/package.zip' if package else '' if package is not None else None)}\n"
        "if os.environ.get('MISSING_RAW_FIELD'): raw.pop(os.environ['MISSING_RAW_FIELD'],None)\n"
        "latest=LatestVersion.from_response(agent_id,raw).public_payload()\n"
        "print(json.dumps({'ok':ok,'agent_id':agent_id,'latest_version':latest}))\n",
        encoding="utf-8",
    )
    finish_log = tmp_path / "finish.log"
    finish = scripts / "publish_finish.sh"
    finish.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$FINISH_LOG"\n'
        'if [ "$FINISH_RC" -eq 0 ]; then\n'
        '  echo "CP3 submit attempt 1"\n'
        '  echo "platform_status=1 skills=1 cfg=1 package_uploaded=1 audit=1 title=Test Agent"\n'
        'fi\n'
        'exit "$FINISH_RC"\n',
        encoding="utf-8",
    )
    finish.chmod(0o755)

    inventory = {
        "verdict": "PUBLISHABLE",
        "action": "retry_existing",
        "reason": retry_reason,
        "item": {
            "agent_id": agent_id, "skill": str(skill), "listing": str(listing),
            "icon": str(icon), "title": "TikTok Comment Reply Script Pack",
        },
    }
    log = tmp_path / "daily_loop.log"
    marker = capafy_state / ".capafy-healthy-pass"
    script = "\n".join((
        "set -uo pipefail",
        f"export AUTO={shlex.quote(str(auto))}",
        f"export LIFE_MANAGER_STATE_HOME={shlex.quote(str(state_home))}",
        f"export CAPAFY_PUBLISHER_STATE_HOME={shlex.quote(str(publisher_state))}",
        f"export CAPAFY_STATE_DIR={shlex.quote(str(capafy_state))}",
        f"export MODEL_RESULT={shlex.quote(model_result)}",
        f"export MODEL_RESULT_SECOND={shlex.quote(model_result_second or model_result)}",
        f"export MODEL_STATUS_CALLS={shlex.quote(str(tmp_path / 'model-status-calls'))}",
        f"export MISSING_RAW_FIELD={shlex.quote(missing_raw_field)}",
        f"export REMOTE_STATUS_CALLS={shlex.quote(str(tmp_path / 'remote-status-calls'))}",
        "export LIFE_MANAGER_RUN_ID=test-run-123",
        "export LIFE_MANAGER_OCCURRENCE_ID=capafy-loop-daily:test-run-123",
        "export LIFE_MANAGER_RELEASE_SHA=" + ("a" * 40),
        f"export FINISH_LOG={shlex.quote(str(finish_log))}",
        f"export FINISH_RC={finish_rc}",
        f"LOG={shlex.quote(str(log))}",
        f"MARK={shlex.quote(str(marker))}",
        "TS=test",
        f"INV={shlex.quote(json.dumps(inventory))}",
        f"RESUME={shlex.quote(chr(9).join((agent_id, skill_dir.name, str(listing), str(skill_dir), str(icon))))}",
        "RETRY_EXISTING_STUB=1",
        'REUSE_PREPARE_ID=""',
        'FRESH=""',
        _retry_existing_stub_block(),
        "retry_existing_stub_finish",
        (_between(CHILD.read_text(), 'if [ -n "$RESUME" ]', "\n# PUBLISHABLE")
         + '\nprintf "REUSE_PREPARE_ID=%s\\n" "$REUSE_PREPARE_ID"\n'
         if run_resume_branch else "echo SHOULD_NOT_REACH_DETERMINISTIC_FINISH"),
        "",
    ))

    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    return result, finish_log, marker, capafy_state, log


def test_retry_existing_finishes_the_exact_existing_agent_version(tmp_path: Path) -> None:
    result, finish_log, marker, capafy_state, log = _run_retry_existing(tmp_path)

    assert result.returncode == 0
    assert not result.stdout.strip()
    assert finish_log.read_text(encoding="utf-8").strip() == (
        f"7393298474 tiktok-comment-reply-script-pack "
        f"{tmp_path / 'catalog/tiktok-comment-reply-script-pack/LISTING.md'} 2110426515594047488"
    )
    assert marker.is_file()
    assert (capafy_state / ".maxturns-streak").read_text(encoding="utf-8").strip() == "0"
    loop_log = log.read_text(encoding="utf-8")
    assert "AGENT_ID=7393298474" in loop_log
    assert "AGENT_VERSION_ID=2110426515594047488" in loop_log
    assert "SUBMITTED — 7393298474 finished CP2/CP3 after prepare" in loop_log
    assert "RETRY_EXISTING version=2110426515594047488" in loop_log
    receipt_lines = [line.split("=", 1)[1] for line in loop_log.splitlines()
                     if line.startswith("CAPAFY_RETRY_FINISH_RECEIPT=")]
    assert len(receipt_lines) == 1
    receipt = json.loads(receipt_lines[0])
    assert receipt["owner_id"] == "capafy-loop-daily"
    assert receipt["run_id"] == "test-run-123"
    assert receipt["occurrence_id"] == "capafy-loop-daily:test-run-123"
    assert receipt["release_sha"] == "a" * 40
    assert receipt["agent_id"] == "7393298474"
    assert receipt["agent_version_id"] == "2110426515594047488"
    assert receipt["platform_status"] == 1
    assert receipt["action_key"] == "retry:7393298474"
    assert receipt["cp3_attempt"] == 1
    assert receipt["is_confirmed_skills"] is True
    assert receipt["is_confirmed_config_keys"] is True
    assert receipt["package_uploaded"] is True
    assert receipt["provider_receipt_id"] == (
        "capafy:agent/7393298474/version/2110426515594047488:platform_status=1"
    )
    assert receipt["verified_at"].endswith("Z")


@pytest.mark.parametrize("second_result", [None, "MODEL_UNKNOWN detail-fetch-failed:TimeoutError"])
def test_unstarted_stub_reaches_existing_same_agent_prepare_without_finishing(
    tmp_path: Path, second_result: str | None,
) -> None:
    result, finish_log, marker, _, _ = _run_retry_existing(
        tmp_path, confirmed_skills=False, confirmed_config_keys=False, package_uploaded=False,
        model_result="MODEL_UNKNOWN no-confirmed-model-yet", model_result_second=second_result,
        finish_rc=1, run_resume_branch=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "REUSE_PREPARE_ID=7393298474"
    assert not finish_log.exists()
    assert not marker.exists()
    assert (tmp_path / "model-status-calls").read_text() == "1"


@pytest.mark.parametrize("overrides", [
    {"remote_ok": False},
    {"remote_version": "different-version"},
    {"remote_status": 1},
    {"model_result": "MODEL_MATCH deepseek/deepseek-v4.1-flash"},
    {"model_result": "MODEL_UNKNOWN detail-fetch-failed:TimeoutError"},
    {"confirmed_skills": None},
    {"confirmed_config_keys": None},
    {"package_uploaded": None},
    {"package_uploaded": True},
])
def test_unstarted_stub_does_not_resume_uncertain_or_changed_state(tmp_path: Path, overrides: dict) -> None:
    options = dict(confirmed_skills=False, confirmed_config_keys=False, package_uploaded=False,
                   model_result="MODEL_UNKNOWN no-confirmed-model-yet", run_resume_branch=True)
    options.update(overrides)
    result, finish_log, marker, _, _ = _run_retry_existing(tmp_path, **options)

    assert result.returncode == 1
    assert not result.stdout.strip()
    assert not finish_log.exists()
    assert not marker.exists()


@pytest.mark.parametrize("field", [
    "agentId", "agentType", "isConfirmedSkills", "isConfirmedConfigKeys", "packageUrl",
])
def test_unstarted_stub_rejects_raw_fields_missing_before_normalization(tmp_path: Path, field: str) -> None:
    result, finish_log, marker, _, _ = _run_retry_existing(
        tmp_path, confirmed_skills=False, confirmed_config_keys=False, package_uploaded=False,
        model_result="MODEL_UNKNOWN no-confirmed-model-yet", missing_raw_field=field,
        run_resume_branch=True,
    )

    assert result.returncode == 1
    assert not result.stdout.strip()
    assert not finish_log.exists()
    assert not marker.exists()


@pytest.mark.parametrize(
    ("post_remote_status", "post_remote_version", "post_package_uploaded"),
    [(0, "2110426515594047488", True),
     (1, "different-version", True),
     (1, "2110426515594047488", False)],
)
def test_retry_existing_needs_exact_final_official_receipt_before_healthy_marker(
    tmp_path: Path,
    post_remote_status: int,
    post_remote_version: str,
    post_package_uploaded: bool,
) -> None:
    result, finish_log, marker, _, log = _run_retry_existing(
        tmp_path,
        post_remote_status=post_remote_status,
        post_remote_version=post_remote_version,
        post_package_uploaded=post_package_uploaded,
    )

    assert result.returncode == 1
    assert finish_log.read_text(encoding="utf-8").count("7393298474 tiktok-comment-reply-script-pack") == 1
    assert not marker.exists()
    assert "CAPAFY_RETRY_FINISH_RECEIPT=" not in log.read_text(encoding="utf-8")
    assert "SHOULD_NOT_REACH_DETERMINISTIC_FINISH" not in result.stdout


def test_retry_existing_rejects_failed_preflight_readback(tmp_path: Path) -> None:
    result, finish_log, marker, _, log = _run_retry_existing(tmp_path, remote_ok=False)

    assert result.returncode == 1
    assert not finish_log.exists()
    assert not marker.exists()
    assert "CAPAFY_RETRY_FINISH_RECEIPT=" not in log.read_text(encoding="utf-8")
    assert "SHOULD_NOT_REACH_DETERMINISTIC_FINISH" not in result.stdout


def test_retry_existing_rejects_failed_final_readback(tmp_path: Path) -> None:
    result, finish_log, marker, _, log = _run_retry_existing(tmp_path, post_remote_ok=False)

    assert result.returncode == 1
    assert finish_log.read_text(encoding="utf-8").count("7393298474 tiktok-comment-reply-script-pack") == 1
    assert not marker.exists()
    assert "CAPAFY_RETRY_FINISH_RECEIPT=" not in log.read_text(encoding="utf-8")
    assert "SHOULD_NOT_REACH_DETERMINISTIC_FINISH" not in result.stdout


def test_retry_existing_finish_failure_does_not_fall_back_to_agentic_submit(
    tmp_path: Path,
) -> None:
    result, finish_log, marker, _, _ = _run_retry_existing(tmp_path, finish_rc=1)

    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert finish_log.read_text(encoding="utf-8").splitlines() == [
        f"7393298474 tiktok-comment-reply-script-pack "
        f"{tmp_path / 'catalog/tiktok-comment-reply-script-pack/LISTING.md'} 2110426515594047488"
    ]
    assert not marker.exists()


@pytest.mark.parametrize(
    ("manifest_agent_id", "remote_version"),
    [("different-agent", "2110426515594047488"),
     ("7393298474", "different-version")],
)
def test_retry_existing_manifest_and_official_version_must_match(
    tmp_path: Path, manifest_agent_id: str, remote_version: str,
) -> None:
    result, finish_log, marker, _, _ = _run_retry_existing(
        tmp_path, manifest_agent_id=manifest_agent_id, remote_version=remote_version,
    )

    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert not finish_log.exists()
    assert not marker.exists()


@pytest.mark.parametrize(
    "overrides",
    [
        {"confirmed_skills": False},
        {"confirmed_config_keys": False},
        {"package_uploaded": False},
        {"model_result": "MODEL_MISMATCH old new"},
        {"model_result": "MODEL_UNKNOWN detail-fetch-failed:TimeoutError"},
    ],
)
def test_retry_existing_stops_when_cp1_or_model_confirmation_is_missing(
    tmp_path: Path, overrides: dict[str, object],
) -> None:
    result, finish_log, marker, _, _ = _run_retry_existing(tmp_path, **overrides)

    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert not finish_log.exists()
    assert not marker.exists()


def test_rejected_retry_existing_falls_back_without_deterministic_finish(tmp_path: Path) -> None:
    result, finish_log, marker, _, _ = _run_retry_existing(
        tmp_path, remote_status=2, retry_reason="review_rejected retry",
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "SHOULD_NOT_REACH_DETERMINISTIC_FINISH"
    assert not finish_log.exists()
    assert not marker.exists()


def test_resume_draft_finish_writes_a_bound_resume_receipt(tmp_path: Path) -> None:
    # 2026-10-15: a resume_draft submission left no receipt, so every successful
    # resume fenced the factory until a human proved the effect.
    _, _, _, _, log = _run_retry_existing(tmp_path, retry_reason="resume exact-title repository draft")
    log.write_text("", encoding="utf-8")
    calls = tmp_path / "remote-status-calls"
    calls.write_text("1", encoding="utf-8")
    script = "\n".join((
        "set -uo pipefail",
        f"export AUTO={shlex.quote(str(tmp_path / 'release/skills/capafy-autopublish'))}",
        f"export LIFE_MANAGER_STATE_HOME={shlex.quote(str(tmp_path / 'state'))}",
        f"export CAPAFY_PUBLISHER_STATE_HOME={shlex.quote(str(tmp_path / 'state/runtime/capafy-publisher'))}",
        f"export REMOTE_STATUS_CALLS={shlex.quote(str(calls))}",
        "export LIFE_MANAGER_RUN_ID=test-run-123",
        "export LIFE_MANAGER_OCCURRENCE_ID=capafy-loop-daily:test-run-123",
        "export LIFE_MANAGER_RELEASE_SHA=" + ("a" * 40),
        f"LOG={shlex.quote(str(log))}",
        _retry_existing_stub_block(),
        "finish_receipt 7393298474 2110426515594047488 capafy_resume_draft_finish resume",
        "",
    ))
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    lines = [line.split("=", 1)[1] for line in log.read_text(encoding="utf-8").splitlines()
             if line.startswith("CAPAFY_RETRY_FINISH_RECEIPT=")]
    assert len(lines) == 1
    receipt = json.loads(lines[0])
    assert receipt["event"] == "capafy_resume_draft_finish"
    assert receipt["action_key"] == "resume:7393298474"
    assert receipt["platform_status"] == 1


def _submitted_block() -> str:
    source = CHILD.read_text(encoding="utf-8")
    return _between(source, "# SUBMITTED-SELECTED-BEGIN", "# SUBMITTED-SELECTED-END")


def _run_submitted(tmp_path: Path, *, rc: int, lifecycle: str) -> tuple[int, Path]:
    marker = tmp_path / ".healthy"
    state = tmp_path / "state"
    state.mkdir()
    post_json = json.dumps({"agents": [{"agent_id": "111", "lifecycle": lifecycle}]})
    script = "\n".join((
        "set -uo pipefail",
        f"RC={rc}",
        'SELECTED_ID="111"',
        f"POST_JSON={shlex.quote(post_json)}",
        f"MARK={shlex.quote(str(marker))}",
        f"CAPAFY_STATE_DIR={shlex.quote(str(state))}",
        f"LOG={shlex.quote(str(tmp_path / 'loop.log'))}",
        "TS=test",
        "POST=PUBLISHABLE",
        _submitted_block(),
        "exit 9",
    ))
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    return result.returncode, marker


def test_selected_agent_now_under_review_is_a_healthy_pass_even_if_queue_stays_publishable(tmp_path: Path) -> None:
    code, marker = _run_submitted(tmp_path, rc=0, lifecycle="occupied")
    assert code == 0 and marker.exists()


@pytest.mark.parametrize("rc,lifecycle", [(0, "retry"), (1, "occupied")])
def test_selected_agent_not_submitted_or_runner_failed_falls_through(tmp_path: Path, rc: int, lifecycle: str) -> None:
    code, marker = _run_submitted(tmp_path, rc=rc, lifecycle=lifecycle)
    assert code == 9 and not marker.exists()


def test_drainer_prompts_say_a_sonnet_5_5_listing_hosts_on_the_sonnet_5_id():
    """2026-10-25: the drainer agent stopped three times because publish_prepare printed
    'model: Claude Sonnet 5' for a 'Claude Sonnet 5.5' listing; build_config.py maps one to the other by design."""
    source = CHILD.read_text(encoding="utf-8")
    sentence = "A LISTING Primary Model of Claude Sonnet 5.5 is hosted on the Claude Sonnet 5 id by design"
    assert source.count(sentence) == 2
    assert "not a stop condition" in source


def test_drainer_prompts_give_the_status_command_path_and_the_only_lease_stop():
    """2026-10-25: the agent ran `vendor/capafy-publisher/packager.py` from the repo root (rc 127, no such
    file), never ran with-browser.sh, then reported the browser lease as unavailable (status 10)."""
    source = CHILD.read_text(encoding="utf-8")
    command = "python3 skills/capafy-autopublish/vendor/capafy-publisher/packager.py publish-remote-status --agent-id"
    assert source.count(command) == 2
    assert source.count("only a with-browser.sh exit of 75 or 10") == 2


def test_drainer_prompts_retry_a_transient_with_browser_exit_10_before_stopping():
    """2026-10-25 05:13Z: with-browser.sh exited 10 for the agent while the same call from a shell and from a
    plain codex exec succeeded on the loaded host (load 6-13), so one 10 is not proof the browser is down."""
    source = CHILD.read_text(encoding="utf-8")
    assert source.count("If with-browser.sh exits 10, wait 30 seconds and retry up to 3 times") == 2
