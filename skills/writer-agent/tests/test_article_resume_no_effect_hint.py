"""article-resume reports a verified no-effect result only when no publisher was dispatched.

2026-10-18: every pass that published nothing still ended effect unknown, so a lost admission
release fenced article-resume:18df6fc53500b510-26567 and stopped all Writer publication.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OCC = "article-resume:no-effect-test"
MARKER = '{"effect":0,"status":"pre_effect_failure"}\n'


def _write(path: Path, body: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def _harness(tmp_path: Path) -> tuple[list[str], dict, Path, Path]:
    fake_root = tmp_path / "writer-agent"
    scripts = fake_root / "scripts"
    state = tmp_path / "state"
    (state / "runs").mkdir(parents=True)
    repo = tmp_path / "life-manager"
    _write(repo / "apps/life-manager/scripts/lib/load-env-file.sh", "lm_load_env_file() { :; }\n")
    (repo / "runtime/host").mkdir(parents=True)
    shutil.copy(ROOT.parents[1] / "runtime/host/disk_admission.py", repo / "runtime/host")
    home = tmp_path / "home"
    (home / ".local/state/life-manager/state").mkdir(parents=True)
    _write(scripts / "article-resume-pending.sh",
           (ROOT / "scripts/article-resume-pending.sh").read_text(encoding="utf-8"))
    shutil.copy(ROOT / "scripts/writer-runtime-env.sh", scripts)
    _write(scripts / "article_daily_start_control.py",
           "import os\nprint(os.environ.get('START', '{\"action\":\"block-incomplete\",\"reason\":\"t\"}'))\n")
    _write(scripts / "article_adoption_selection.py", "")
    _write(scripts / "quality_feedback_recovery.py",
           "def plan(*_a): return {'status':'NONE'}\nif __name__ == '__main__': print('{\"status\":\"NONE\"}')\n")
    _write(scripts / "quality_repair_control.py", "print('{\"status\":\"NONE\"}')\n")
    _write(scripts / "recover-known-unavailable.py", "")
    _write(scripts / "writer_unavailable_incident_bridge.py", "")
    _write(scripts / "article_pending.py",
           "import json, os\n"
           "if os.environ.get('PLAN') == 'READY':\n"
           f" print(json.dumps({{'status':'READY','run_id':'20261017-223414','run_dir':{str(state / 'runs/x')!r},"
           "'state_path':'/nonexistent','ledger_path':'/nonexistent',"
           "'initialization_pairs':[],'eligible_pairs':['note/ja'],'recovery_pairs':[]}))\n"
           "else:\n print('{\"status\":\"WAIT\"}')\n")
    # The self-heal dispatcher may run a model; it records what it inherited and can forge a hint.
    _write(scripts / "writer_repair_dispatch.py",
           "import json, os\n"
           "open(os.environ['SEEN'], 'a').write(json.dumps({k: os.environ.get(k) for k in "
           "('LIFE_MANAGER_RESULT_HINT_PATH', 'LIFE_MANAGER_OCCURRENCE_ID')}) + '\\n')\n"
           "if os.environ.get('FORGE') == '1':\n"
           " fd = os.open('entrypoint-result.json', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)\n"
           " os.write(fd, json.dumps({'schema_version':1,'kind':'life_manager_no_effect_result',"
           "'status':'verified_no_effect','effect':0,'owner_id':'article-resume',"
           f"'occurrence_id':{OCC!r},'reason':'no_pending_publication'}}).encode())\n"
           " os.close(fd)\n"
           "print(json.dumps({'status': os.environ.get('REPAIR_STATUS', 'NO_ACTIONABLE_INCIDENT')}))\n")
    _write(scripts / "publication_contract_resolver.py", "raise SystemExit(9)\n")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    hint = scratch / "entrypoint-result.json"
    env = {
        **os.environ,
        "ARTICLE_ROOT": str(fake_root), "HOME": str(home), "LIFE_MANAGER_REPO": str(repo),
        "ARTICLE_STATE_DIR": str(state), "ARTICLE_OWNER_FENCE_ACTIVE": "1",
        "ARTICLE_LOCAL_DATE": "2026-10-18", "ARTICLE_LOCAL_HOUR": "07",
        "ARTICLE_RESUME_LOG": str(tmp_path / "resume.log"),
        "LIFE_MANAGER_RESULT_HINT_PATH": str(hint), "LIFE_MANAGER_OCCURRENCE_ID": OCC,
        "SEEN": str(tmp_path / "seen.jsonl"),
    }
    return ["bash", str(scripts / "article-resume-pending.sh")], env, hint, state


def _run(command, env, hint: Path, **extra) -> subprocess.CompletedProcess:
    hint.write_text(MARKER, encoding="utf-8")   # lm-loop-run's pre-spawn marker
    hint.chmod(0o600)
    return subprocess.run(command, env={**env, **extra}, cwd=hint.parent,
                          capture_output=True, text=True, check=False)


def _no_effect_reason(hint: Path) -> str | None:
    if not hint.exists():
        return None
    info = hint.lstat()
    value = json.loads(hint.read_text(encoding="utf-8"))
    if value.get("kind") != "life_manager_no_effect_result":
        return None
    assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
    assert set(value) == {"schema_version", "kind", "status", "effect", "owner_id",
                          "occurrence_id", "reason"}
    assert (value["schema_version"], value["status"], value["effect"], value["owner_id"],
            value["occurrence_id"]) == (1, "verified_no_effect", 0, "article-resume", OCC)
    return value["reason"]


def test_publication_free_branches_write_a_bounded_no_effect_hint(tmp_path):
    command, env, hint, state = _harness(tmp_path)

    result = _run(command, env, hint)
    assert result.returncode == 0, result.stderr
    assert _no_effect_reason(hint) == "no_pending_publication"
    # The spawned self-heal process never sees the hint path or the occurrence.
    seen = [json.loads(line) for line in (tmp_path / "seen.jsonl").read_text().splitlines()]
    assert seen == [{"LIFE_MANAGER_RESULT_HINT_PATH": None, "LIFE_MANAGER_OCCURRENCE_ID": None}]

    result = _run(command, env, hint, START='{"action":"new","reason":"no-same-jst-day-run"}',
                  ARTICLE_LOCAL_HOUR="03")
    assert result.returncode == 0, result.stderr
    assert _no_effect_reason(hint) == "daily_schedule_not_due"

    (state / ".article-daily.lockdir").mkdir()
    _write(state / ".article-daily.lockdir/foreign", "x")
    result = _run(command, env, hint)
    assert result.returncode == 0, result.stderr
    assert _no_effect_reason(hint) == "lock_held"
    shutil.rmtree(state / ".article-daily.lockdir")

    _write(state / ".publication-paused", "")
    result = _run(command, env, hint)
    assert result.returncode == 0, result.stderr
    assert _no_effect_reason(hint) == "publication_paused"


def test_a_model_routed_self_heal_or_a_forged_hint_never_reports_no_effect(tmp_path):
    command, env, hint, _state = _harness(tmp_path)
    # A dispatcher that routed an incident to a model is not a provable no-publication pass.
    result = _run(command, env, hint, REPAIR_STATUS="ROUTED")
    assert result.returncode == 0, result.stderr
    assert _no_effect_reason(hint) is None
    # A child forging the guessable hint path is removed before exit.
    result = _run(command, env, hint, REPAIR_STATUS="ROUTED", FORGE="1")
    assert result.returncode == 0, result.stderr
    assert _no_effect_reason(hint) is None


def test_a_dispatched_publication_pass_leaves_no_no_effect_hint(tmp_path):
    command, env, hint, _state = _harness(tmp_path)
    result = _run(command, env, hint, PLAN="READY", FORGE="1")
    assert result.returncode == 1   # the stub contract resolver fails after dispatch began
    assert _no_effect_reason(hint) is None
    records = [json.loads(line.split("article-resume: pass ", 1)[1])
               for line in (tmp_path / "resume.log").read_text().splitlines()
               if line.startswith("article-resume: pass ")]
    assert [r["branch"] for r in records] == ["start", "publication"]
