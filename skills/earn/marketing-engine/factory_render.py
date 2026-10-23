"""Connect a validated Factory request to the existing HeyGen renderer."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

from ebook_distribute_daily import exclusive_lock
from ebook_runner import unresolved_heygen_effect
from factory_plan import build_plan
from render_eval.heygen_candidate import render, require


HERE = Path(__file__).resolve().parent


def _host_data_root() -> Path:
    host_root = os.environ.get("LM_DATA_DIR")
    require(host_root is None or (bool(host_root) and "\x00" not in host_root and Path(host_root).is_absolute()),
            "Factory host data root must be absolute")
    return (Path.home() / ".local/state/life-manager" if host_root is None
            else Path(os.path.normpath(host_root)))


def _host_disk_admission() -> bool:
    # Project overrides and loop exemptions must not weaken the ordinary producer gate.
    result = subprocess.run(
        [sys.executable, str(HERE.parents[2] / "runtime/host/disk_admission.py"),
         sys.executable, "-c", "pass"],
        env={"PATH": os.defpath}, capture_output=True, check=False,
    )
    return result.returncode == 0


def render_from_config(
    config: dict, script: str, run_id: str, *,
    environment: dict[str, str] | None = None, executor=subprocess.run,
) -> dict:
    plan = build_plan(config, script)
    require(isinstance(run_id, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", run_id) is not None,
            "Factory run ID invalid")
    data_root = _host_data_root()
    metadata = {"schema_version": "ai-monk-factory.render.v1", "project_id": plan["project_id"], "run_id": run_id}
    shared_root = data_root / "marketing/ebook"
    intent = shared_root / "runs" / f"factory.{plan['project_id']}.{run_id}.heygen-effect.json"
    output = Path(plan["state_root"]) / "renders" / f"{plan['project_id']}.{run_id}.mp4"
    env = os.environ if environment is None else environment
    renderer_environment = {key: env[key] for key in ("LIFE_MANAGER_HEYGEN", "LIFE_MANAGER_RESULT_HINT_PATH")
                            if env.get(key)}
    renderer_environment.update({
        "LM_EBOOK_EN_HEYGEN_AVATAR_ID": plan["render_request"]["avatar_id"],
        "LM_EBOOK_EN_HEYGEN_VOICE_ID": plan["render_request"]["voice_id"],
    })
    with exclusive_lock(shared_root / "locks/heygen-avatar-iv-account.lock"):
        pending = unresolved_heygen_effect(shared_root / "runs", intent)
        if pending:
            return {**metadata, "renderer_id": "heygen-avatar-iv", "state": "setup_required",
                    "reason": "prior_heygen_effect_unresolved", "pending_render": pending, "external_effects": []}
        if not _host_disk_admission():
            return {**metadata, "renderer_id": "heygen-avatar-iv", "state": "deferred",
                    "reason": "host_disk_admission_required", "external_effects": []}
        receipt = render(script=script, language=plan["language"], output=output, intent_path=intent,
                         environment=renderer_environment, executor=executor)
    return {**metadata, **receipt}
