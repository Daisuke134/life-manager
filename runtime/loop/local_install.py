"""Install the existing local fleet using private host bindings and lm-loop."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from runtime.host.local_profile import host_environment, load_host_profile, prepare_host
from runtime.loop.local_fleet import build_fleet_manifest
from runtime.loop.lm_loop_apply import _loaded_arguments, _loaded_environment


ROOT = Path(__file__).resolve().parents[2]
MERCOR_BROWSER = {
    "id": "job-search-mercor-browser", "label": "ai.anicca.job-search-mercor-browser",
    "installer": "apps/job-search-loop/scripts/install-launchd.sh",
    "arguments": ["--mercor-browser-only"],
    "program": "apps/job-search-loop/scripts/run-browser.sh",
}


def installation_plan(repo_root: Path, *, home: Path | None = None) -> dict:
    fleet = build_fleet_manifest(repo_root)
    fleet["external_adapters"] = [MERCOR_BROWSER]
    profile = load_host_profile(home=home)
    fleet.update({"host_state": "prepared" if profile else "setup_required",
                  "business_outcomes_verified": False,
                  "external_owner_policy": "preserve_existing_owner",
                  "next_action": "local apply --release PATH" if profile else "local prepare"})
    for row in fleet["jobs"]:
        path = repo_root / row["entrypoint"]
        row["entrypoint_present"] = path.is_file() and os.access(path, os.X_OK)
    return fleet


def validate_release(release_root: Path, profile: dict) -> dict:
    manifest = json.loads((release_root / "RELEASE.json").read_text())
    if (not re.fullmatch(r"[0-9a-f]{40}", manifest.get("sha", ""))
            or manifest.get("provenance") != "ancestor-of-origin-main"
            or manifest.get("release_paths") != "ALL"):
        raise ValueError("local installation requires a complete main-derived immutable release")
    if manifest.get("runtime_python") != profile["runtime"]["python"]:
        raise ValueError("release runtime Python differs from this owner's host binding")
    if not (release_root / "bin/lm-loop").is_file():
        raise ValueError("release lm-loop is missing")
    return manifest


def apply_targets(release_root: Path, loop_ids: list[str], environment: dict[str, str],
                  *, runner=subprocess.run) -> list[dict]:
    """Use the existing safe control plane. Never turn a failed probe into absence."""
    registry = json.loads((release_root / "config/loop-registry.json").read_text())
    if len(set(loop_ids)) != len(loop_ids) or any(owner not in registry["loops"] for owner in loop_ids):
        raise ValueError("local apply target is unknown or duplicated")
    safe = str(release_root / "bin/launchctl-safe")
    env = {**os.environ, **environment, "LIFE_MANAGER_RELEASE_ROOT": str(release_root)}
    check = runner([safe, "preflight"], env=env, capture_output=True, text=True, timeout=30)
    if check.returncode:
        raise RuntimeError("launchctl-safe preflight failed; no owner applied")
    results = []
    for owner in loop_ids:
        label = registry["loops"][owner]["label"]
        probe = runner([safe, "print", f"gui/{os.getuid()}/{label}"], env=env,
                       capture_output=True, text=True, timeout=30)
        arguments = [str(release_root / "bin/lm-loop-run"), owner, str(release_root)]
        binding_matches = (not environment.get("LIFE_MANAGER_HOST_PROFILE") or all(
            _loaded_environment(probe.stdout).get(key) == value
            for key, value in environment.items()))
        if probe.returncode == 0 and _loaded_arguments(probe.stdout) == arguments and binding_matches:
            # Source identity is already installed. Running keep-alive owners
            # must not be restarted just to declare the installer successful.
            results.append({"ok": True, "loop_id": owner, "label": label,
                            "changed": False, "readback": "exact_release_loaded"})
            continue
        command = [str(release_root / "bin/lm-loop"), "apply"]
        if probe.returncode == 0:
            command.append("--loaded-idle-only")
        elif (probe.returncode == 75 or not re.search(
                r"could not find service|service not found|\babsent\b",
                probe.stdout + probe.stderr, re.IGNORECASE)):
            raise RuntimeError(f"{owner}: launchd label readback failed")
        completed = runner(command, env={**env, "LIFE_MANAGER_APPLY_TARGET": owner},
                           capture_output=True, text=True, timeout=180)
        try:
            rows = json.loads(completed.stdout)
        except (TypeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"{owner}: invalid owner apply result") from error
        if (completed.returncode or not isinstance(rows, list) or len(rows) != 1
                or not isinstance(rows[0], dict) or rows[0].get("ok") is not True
                or rows[0].get("label") != label):
            raise RuntimeError(f"{owner}: owner apply failed")
        results.extend({**row, "loop_id": owner} for row in rows)
    return results


def apply_host_owners(release_root: Path, owners: list[dict], environment: dict[str, str],
                      *, runner=subprocess.run) -> list[dict]:
    safe = str(release_root / "bin/launchctl-safe")
    env = {**os.environ, **environment, "JOB_SEARCH_LAUNCHCTL": safe,
           "JOB_SEARCH_PYTHON": environment["LIFE_MANAGER_RUNTIME_PYTHON"]}
    preflight = runner([safe, "preflight"], env=env, capture_output=True, text=True, timeout=30)
    if preflight.returncode:
        raise RuntimeError("host owner preflight failed")
    results = []
    for row in owners:
        label = row["label"]
        probe = runner([safe, "print", f"gui/{os.getuid()}/{label}"], env=env,
                       capture_output=True, text=True, timeout=30)
        if probe.returncode == 0:
            exact = _loaded_arguments(probe.stdout) == [str(release_root / row["program"])]
            results.append({"ok": True, "label": label, "changed": False,
                            **({"readback": "exact_release_loaded"} if exact else {"skipped": "existing_owner"})})
            continue
        if probe.returncode == 75 or not re.search(
                r"could not find service|service not found|\babsent\b",
                probe.stdout + probe.stderr, re.IGNORECASE):
            raise RuntimeError(f"{label}: host owner readback failed")
        command = ["zsh" if row["installer"].endswith("install-launchd.sh")
                   and row.get("arguments") else "bash", str(release_root / row["installer"]),
                   *row.get("arguments", [])]
        installed = runner(command, env=env, capture_output=True, text=True, timeout=180)
        if installed.returncode:
            raise RuntimeError(f"{label}: host owner installation failed")
        readback = runner([safe, "print", f"gui/{os.getuid()}/{label}"], env=env,
                          capture_output=True, text=True, timeout=30)
        if readback.returncode or _loaded_arguments(readback.stdout) != [str(release_root / row["program"])]:
            raise RuntimeError(f"{label}: installed program readback mismatch")
        results.append({"ok": True, "label": label, "changed": True, "readback": "exact_release_loaded"})
    return results


def cut_release(repo_root: Path, environment: dict[str, str], *, runner=subprocess.run) -> Path:
    completed = runner(["bash", str(repo_root / "bin/cut-loop-release.sh"), "HEAD"],
        env={**os.environ, **environment, "LIFE_MANAGER_SOURCE_REPO": str(repo_root),
             "LOOPS_ACTIVATE_CURRENT": "0", "LOOPS_RELEASE_PATHS": "",
             "LOOPS_RUNTIME_PYTHON": environment["LIFE_MANAGER_RUNTIME_PYTHON"]},
        capture_output=True, text=True, timeout=1800)
    if completed.returncode:
        raise RuntimeError("immutable release build failed: " + completed.stderr[-2000:])
    matches = re.findall(r"^release -> (.+)  \(ancestor-of-origin-main; current unchanged\)$",
                         completed.stdout, re.MULTILINE)
    if len(matches) != 1:
        raise RuntimeError("complete main release path was not returned")
    return Path(matches[0]).resolve(strict=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Life Manager全体のMac導入と状態確認")
    parser.add_argument("command", choices=("plan", "prepare", "install", "apply"), nargs="?", default="plan")
    parser.add_argument("--release", type=Path)
    parser.add_argument("--agent", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            print(json.dumps(installation_plan(ROOT), ensure_ascii=False, indent=2))
            return 0
        if platform.system() != "Darwin":
            raise ValueError("local host installation requires macOS")
        if args.command in {"prepare", "install"}:
            node = shutil.which("node")
            if not node:
                raise ValueError("Node.js is missing; run install.sh local prepare")
            codex = shutil.which("codex")
            prepare_host(ROOT, python=Path(sys.executable), node=Path(node),
                         codex=Path(codex) if codex else None)
            if args.command == "prepare":
                output = installation_plan(ROOT)
                output["next_action"] = "connect your own accounts, then local install"
                print(json.dumps(output, ensure_ascii=False, indent=2))
                return 0
        profile = load_host_profile()
        if profile is None:
            raise ValueError("host setup is missing; run install.sh local prepare")
        if args.release is None and args.command == "install":
            print("main由来のimmutable releaseを作成します。既存currentは維持します。", file=sys.stderr)
            args.release = cut_release(ROOT, host_environment())
        if args.release is None:
            parser.error("apply requires --release PATH")
        release = args.release.expanduser().resolve(strict=True)
        validate_release(release, profile)
        fleet = build_fleet_manifest(release)
        agents = {row["id"]: row for row in fleet["agents"]}
        if set(args.agent) - set(agents):
            raise ValueError("unknown agent selection")
        selected = ({owner for agent in args.agent for owner in agents[agent]["job_ids"]}
                    if args.agent else {row["loop_id"] for row in fleet["jobs"]})
        registry = json.loads((release / "config/loop-registry.json").read_text())
        # Browser processes precede their consumers; business scheduling remains
        # owned by the registry's cadence/admission, not by this installer.
        owners = sorted(selected, key=lambda owner: (not bool(registry["loops"][owner].get("browser_owner")), owner))
        print("本人のMacへ対象jobを登録します。既存の稼働中ownerは維持します。", file=sys.stderr)
        extras = []
        if not args.agent or "gig-mercor" in args.agent or "job-hunter" in args.agent:
            extras.append(MERCOR_BROWSER)
        if not args.agent or "host-steward" in args.agent:
            extras.extend({**row, "program": "bin/disk-watchdog.sh"} for row in fleet["host_owners"])
        host_results = apply_host_owners(release, extras, host_environment()) if extras else []
        result = apply_targets(release, owners, host_environment())
        pending = any(row.get("skipped") for row in [*result, *host_results])
        print(json.dumps({"status": "waiting" if pending else "installed",
                          "jobs": result, "business_outcomes_verified": False,
                          "external_labels": fleet["external_labels"],
                          "additional_host_owners": host_results}, ensure_ascii=False, indent=2))
        return 2 if pending else 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "setup_required", "error": str(error),
                          "business_outcomes_verified": False}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
