#!/usr/bin/env python3
"""Install the Coconala catalog through the shared immutable release/runtime.

Activation covers all catalog jobs, including Paid, Report, evidence GC and the
browser. It uses main-derived complete releases without moving shared current.
Existing busy owners and uncertain effects remain under the common runtime's
fences. Legacy rendering/GC helpers remain for historical release references;
the public installer does not activate that second manifest.

    gig_release.py build                 # prepare a complete main release
    gig_release.py activate              # install new jobs and reconcile idle jobs
    gig_release.py activate --jobs ai.anicca.hf-gig-browser
    gig_release.py status
    gig_release.py stop
    gig_release.py uninstall
"""

from __future__ import annotations

import argparse
import atexit
import fcntl
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
GIG_DIR = HERE.parent
REPO_ROOT = GIG_DIR.parents[2]
MANIFEST = GIG_DIR / "config" / "launchd-jobs.json"
OVERRIDES = Path(
    os.environ.get("GIG_INSTALL_OVERRIDES", Path.home() / ".config/anicca/gig/install.json")
)
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
RELEASE_ROOT = Path.home() / "gig" / "releases" / "life-manager"
CURRENT_RELEASE = RELEASE_ROOT / "current"
PIN_PATTERN = re.compile(r"(?P<pid>[1-9][0-9]*)-(?P<sha>[0-9a-f]{40})")
PUBLISH_LOCK = RELEASE_ROOT / ".publish.lock"
LAUNCHD_PREFLIGHT = REPO_ROOT / "skills" / "_shared" / "lib" / "launchd_preflight.py"
LAUNCHD_PREFLIGHT_RECEIPT = Path.home() / ".local/state/life-manager/launchd-control-plane-preflight.json"
# These legacy Upwork jobs are retired until account-bound authorization and a
# funded-contract readback open the managed Paid-owner gate. Keeping them in
# the historical manifest preserves source compatibility, but explicit release
# activation must fail closed rather than resurrecting a pre-gate loop.
RETIRED_PROVIDER_LABELS = frozenset({
    "ai.anicca.life-manager-upwork-browser",
    "ai.anicca.life-manager-upwork-free-loop",
})
# These long-lived owners are excluded from release garbage collection unless
# their loaded argv is inspected explicitly.
DEFAULT_EXCLUDED = {
    "ai.anicca.hf-gig-browser",
    "ai.anicca.life-manager-disk-cleanup",
}
# Negotiate is a durable supervisor rather than a periodic one-shot pass.  Waiting for
# ``is_running`` would therefore postpone every source release forever; its outbox is the
# restart boundary, so the watcher may reload it while periodic lanes wait for a gap.
CONTINUOUS_RELOADABLE = {"ai.anicca.hf-gig-reply-detector"}
PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
JOB_PROCESS_MARKERS = {
    "ai.anicca.life-manager-upwork-browser": "--remote-debugging-port=9233",
    "ai.anicca.hf-gig-browser": "--remote-debugging-port=9223",
    "ai.anicca.hf-gig-apply-direct": "application_direct.py",
    "ai.anicca.hf-gig-storefront-direct": "storefront_direct.py",
    "ai.anicca.hf-gig-reply-detector": "reply_detector.py",
    "ai.anicca.article-daily": "article-daily.sh",
    "ai.anicca.article-resume": "article-resume-pending.sh",
    "ai.anicca.article-zenn-retry": "zenn-deferred-worker.sh",
    "ai.anicca.article-healthcheck": "article-healthcheck.sh",
    "ai.anicca.writer-sales-measure": "writer-sales-measure-worker.sh",
    "ai.anicca.writer-craft-train": "craft-train.sh",
    "ai.anicca.article-self-improve": "self-improve.sh",
    "ai.anicca.article-audit-7day": "audit-7day.sh",
}


def activation_labels(requested_jobs: set[str] | None) -> set[str]:
    labels = set(requested_jobs) if requested_jobs is not None else set(coconala_jobs())
    retired = labels & RETIRED_PROVIDER_LABELS
    if retired:
        raise ValueError(
            "retired provider label cannot be activated before account-bound funded gate: "
            + ", ".join(sorted(retired))
        )
    return labels


def coconala_jobs(repo_root: Path | None = None) -> dict[str, str]:
    root = repo_root or REPO_ROOT
    catalog = json.loads((root / "apps/life-manager/config/product-loop-catalog.json").read_text())
    registry = json.loads((root / "config/loop-registry.json").read_text())["loops"]
    product = next(row for row in catalog["loops"] if row["id"] == "gig-coconala")
    return {registry[owner]["label"]: owner for owner in product["job_ids"]}


def _runtime_environment() -> dict[str, str]:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from runtime.host.local_profile import host_environment
    return host_environment()


def _complete_main_release(path: Path, sha: str, python: str) -> bool:
    try:
        receipt = json.loads((path / "RELEASE.json").read_text())
        return (receipt.get("sha") == sha
                and receipt.get("provenance") == "ancestor-of-origin-main"
                and receipt.get("release_paths") == "ALL"
                and receipt.get("runtime_python") == python
                and Path(python).is_file() and os.access(python, os.X_OK))
    except (OSError, ValueError):
        return False


def managed_release(sha: str) -> Path:
    """Reuse or cut the canonical complete release, leaving shared current alone."""
    git("merge-base", "--is-ancestor", sha, "origin/main")
    python = _runtime_environment().get("LIFE_MANAGER_RUNTIME_PYTHON", sys.executable)
    releases = Path(os.environ.get("LOOPS_ROOT", "~/loops")).expanduser() / "releases"
    for candidate in sorted(releases.glob("*"), reverse=True):
        if candidate.is_dir() and not candidate.is_symlink() and _complete_main_release(candidate, sha, python):
            return candidate.resolve()
    result = subprocess.run(
        ["/bin/bash", str(REPO_ROOT / "bin/cut-loop-release.sh"), sha],
        env={**os.environ, "LIFE_MANAGER_SOURCE_REPO": str(REPO_ROOT),
             "LOOPS_ACTIVATE_CURRENT": "0", "LOOPS_RELEASE_PATHS": "",
             "LOOPS_RUNTIME_PYTHON": python},
        capture_output=True, text=True, check=True,
    )
    match = re.search(r"^release -> (.+)  \([^\n]+; current unchanged\)$", result.stdout, re.MULTILINE)
    if not match:
        raise ValueError("canonical release path was not acknowledged")
    release = Path(match.group(1)).resolve()
    if release.parent != releases.resolve() or not _complete_main_release(release, sha, python):
        raise ValueError("Coconala requires a complete immutable main release")
    return release


def activate_managed_jobs(release: Path, wanted: set[str], dry_run: bool) -> int:
    jobs = coconala_jobs(release)
    if wanted - jobs.keys():
        raise ValueError("requested job is outside the Coconala catalog")
    owners = [jobs[label] for label in sorted(wanted, key=lambda label: (not label.endswith("hf-gig-browser"), label))]
    if dry_run:
        print(json.dumps({"status": "planned", "jobs": owners, "release": str(release)}))
        return 0
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from runtime.loop.local_install import apply_targets

    try:
        results = apply_targets(release, owners, {
            "LIFE_MANAGER_RUNTIME_PYTHON": sys.executable,
            "LIFE_MANAGER_SOURCE_REPO": str(REPO_ROOT),
            "LIFE_MANAGER_APPLY_REQUIRE_CURRENT": "0",
            **_runtime_environment(),
        }, runner=subprocess.run)
    except RuntimeError as error:
        print(json.dumps({"status": "blocked", "error": str(error)}))
        return 75
    if {row.get("label") for row in results} != wanted or any(row.get("ok") is not True for row in results):
        raise ValueError("Coconala owner readback does not match the requested jobs")
    waiting = any(row.get("skipped") for row in results)
    print(json.dumps({"status": "waiting" if waiting else "ready", "jobs": len(results), "results": results}))
    return 2 if waiting else 0


def stop_managed_jobs(uninstall: bool) -> int:
    safe = str(REPO_ROOT / "bin/launchctl-safe")
    check = subprocess.run([safe, "preflight"], capture_output=True, text=True)
    if check.returncode:
        return 75
    jobs = coconala_jobs()
    environment = {**os.environ, "LIFE_MANAGER_RUNTIME_PYTHON": sys.executable}
    for label in sorted(jobs, key=lambda label: (label.endswith("hf-gig-browser"), label)):
        result = subprocess.run([str(REPO_ROOT / "bin/lm-loop"), "stop", jobs[label]],
                                env=environment, capture_output=True, text=True)
        rows = json.loads(result.stdout)
        if (not isinstance(rows, list) or len(rows) != 1
                or rows[0].get("label") != label
                or (rows[0].get("return_code") != 0 and not re.search(
                    r"could not find service|service not found|\babsent\b",
                    rows[0].get("detail", ""), re.IGNORECASE))):
            raise ValueError(f"Coconala stop readback failed: {label}")
        if uninstall:
            (LAUNCH_AGENTS / f"{label}.plist").unlink(missing_ok=True)
    print(json.dumps({"status": "uninstall" if uninstall else "stop", "jobs": len(jobs), "private_state": "preserved"}))
    return 0


def git(*args: str, cwd: Path = REPO_ROOT) -> str:
    command = ("git", *args)
    try:
        return subprocess.run(command, cwd=cwd, check=True,
                              capture_output=True, text=True).stdout.strip()
    except subprocess.CalledProcessError:
        # The release watcher is itself a launchd job. On this Mac the system resolver can
        # answer GitHub while libcurl's resolver intermittently cannot, which otherwise leaves
        # the watcher on an old immutable release forever. Retry fetches through the resolved
        # IPv4 address while retaining the TLS host name via curl's resolve option.
        if not args or args[0] != "fetch":
            raise
        remote = subprocess.run(
            ("git", "config", "--get", "remote.origin.url"), cwd=cwd,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        host = urlparse(remote).hostname or ""
        if not host:
            raise
        resolved = subprocess.run(
            ("nslookup", "-type=A", host), capture_output=True, text=True, check=False,
        )
        addresses = re.findall(r"^Address:\s+(\d{1,3}(?:\.\d{1,3}){3})$",
                               resolved.stdout, flags=re.MULTILINE)
        if not addresses:
            raise
        fallback = ("git", "-c", f"http.curloptResolve={host}:443:{addresses[-1]}", *args)
        return subprocess.run(fallback, cwd=cwd, check=True,
                              capture_output=True, text=True).stdout.strip()


def resolve(values: dict[str, str]) -> dict[str, str]:
    """Expand {{NAME}} against the same table until it stops changing."""
    out = dict(values)
    for _ in range(10):
        changed = False
        for key, value in out.items():
            if not isinstance(value, str):
                continue
            new = PLACEHOLDER.sub(lambda m: out.get(m.group(1), m.group(0)), value)
            if new != value:
                out[key], changed = new, True
        if not changed:
            return out
    raise SystemExit("launchd-jobs.json: placeholders do not settle -- check for a cycle")


def render(value, table: dict[str, str]):
    if isinstance(value, str):
        return PLACEHOLDER.sub(lambda m: table.get(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [render(item, table) for item in value]
    if isinstance(value, dict):
        return {key: render(item, table) for key, item in value.items()}
    return value


def settings(release: Path) -> tuple[dict, dict[str, str]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    table = dict(manifest["defaults"])
    table["HOME"] = str(Path.home())
    if OVERRIDES.is_file():
        machine = json.loads(OVERRIDES.read_text(encoding="utf-8"))
        if not isinstance(machine, dict):
            raise SystemExit(f"{OVERRIDES}: expected a flat object of overrides")
        table.update({k: str(v) for k, v in machine.items()})
    table["RELEASE"] = str(release)
    # The watcher is the one job that runs from the checkout: it has to fetch.
    table["CHECKOUT"] = str(REPO_ROOT)
    return manifest, resolve(table)


def release_dir(sha: str) -> Path:
    return RELEASE_ROOT / sha


def current_sha() -> str:
    """Return the published immutable SHA, or empty when no valid pointer exists."""
    try:
        resolved = CURRENT_RELEASE.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return ""
    if resolved.parent != RELEASE_ROOT.resolve() or not re.fullmatch(r"[0-9a-f]{40}", resolved.name):
        return ""
    return resolved.name


def publish(release: Path) -> None:
    """Atomically make a validated immutable release current, with one writer."""
    release = release.resolve(strict=True)
    if release.parent != RELEASE_ROOT.resolve() or not re.fullmatch(r"[0-9a-f]{40}", release.name):
        raise SystemExit(f"refusing release outside {RELEASE_ROOT}: {release}")
    marker = release / "skills" / "earn" / "gig" / "scripts" / "gig_paths.py"
    if not marker.is_file():
        raise SystemExit(f"incomplete release: {release}")
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    with PUBLISH_LOCK.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        temporary = RELEASE_ROOT / f".current.{os.getpid()}"
        try:
            temporary.unlink(missing_ok=True)
            temporary.symlink_to(release.name)
            os.replace(temporary, CURRENT_RELEASE)
        finally:
            temporary.unlink(missing_ok=True)


def build(sha: str) -> Path:
    """Extract the tracked tree at `sha` and freeze it read-only."""
    target = release_dir(sha)
    if (target / "skills" / "earn" / "gig" / "scripts" / "gig_paths.py").is_file():
        return target
    if target.exists():                       # a half-written tree from an aborted run
        subprocess.run(["chmod", "-R", "u+w", str(target)], check=False)
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=target.parent, prefix=f".{sha[:12]}-"))
    try:
        archive = staging / "tree.tar"
        with archive.open("wb") as handle:
            subprocess.run(["git", "archive", "--format=tar", sha], cwd=REPO_ROOT,
                           check=True, stdout=handle)
        tree = staging / "tree"
        tree.mkdir()
        with tarfile.open(archive) as tar:
            tar.extractall(tree)              # noqa: S202 - our own git archive
        archive.unlink()
        tree.rename(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    # Read-only so a lane, or an agent a lane spawns, cannot edit the code it runs.
    subprocess.run(["chmod", "-R", "a-w", str(target)], check=True)
    return target


def pin_release_for_process(path: Path) -> Path | None:
    """Keep an immutable release alive while this wrapper may reuse it."""
    release = next(
        (parent for parent in path.resolve().parents if re.fullmatch(r"[0-9a-f]{40}", parent.name)),
        None,
    )
    if release is None:
        return None
    pin_dir = release.parent / ".pins"
    pin_dir.mkdir(exist_ok=True)
    marker = pin_dir / f"{os.getpid()}-{release.name}"
    marker.touch(exist_ok=True)
    atexit.register(marker.unlink, missing_ok=True)
    return marker


def collect_old_releases() -> list[str]:
    """Remove reproducible releases except current, live, and one rollback copy."""
    if not RELEASE_ROOT.is_dir():
        return []
    releases = sorted(
        (path for path in RELEASE_ROOT.iterdir()
         if path.is_dir() and not path.is_symlink()
         and re.fullmatch(r"[0-9a-f]{40}", path.name)),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    protected = {CURRENT_RELEASE.resolve(strict=False)}
    pin_dir = RELEASE_ROOT / ".pins"
    if pin_dir.is_dir():
        for marker in pin_dir.iterdir():
            match = PIN_PATTERN.fullmatch(marker.name)
            if match is None:
                continue
            try:
                os.kill(int(match.group("pid")), 0)
            except ProcessLookupError:
                marker.unlink(missing_ok=True)
            except PermissionError:
                protected.add(RELEASE_ROOT / match.group("sha"))
            else:
                protected.add(RELEASE_ROOT / match.group("sha"))
    processes = subprocess.run(
        ["ps", "-axo", "command="], capture_output=True, text=True, check=False,
    )
    if processes.returncode != 0:
        return []
    loaded_excluded_argv = [
        arg for label in DEFAULT_EXCLUDED for arg in loaded_program(label)
    ]
    for release in releases:
        if str(release) in processes.stdout or any(
            str(release) in arg for arg in loaded_excluded_argv
        ):
            protected.add(release)
    rollback = next((path for path in releases if path not in protected), None)
    if rollback:
        protected.add(rollback)
    removed = []
    for release in releases:
        if release in protected:
            continue
        subprocess.run(["chmod", "-R", "u+w", str(release)], check=False)
        shutil.rmtree(release)
        removed.append(release.name)
    return removed


def plist_for(job: dict, table: dict[str, str]) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_env = manifest["shared_env"]
    env = render(dict(manifest_env), table)
    if job.get("env_profile") == "writer":
        env |= render(dict(manifest.get("writer_env", {})), table)
    env |= render(dict(job.get("env", {})), table)
    log_dir = table["GIG_LOG_DIR"]
    out = {
        "Label": job["label"],
        "ProgramArguments": render(job["program"], table),
        "EnvironmentVariables": {k: v for k, v in env.items() if v != ""},
        "WorkingDirectory": str(Path.home()),
        "StandardOutPath": f"{log_dir}/{job['log_basename']}.out.log",
        "StandardErrorPath": f"{log_dir}/{job['log_basename']}.err.log",
    }
    for key in (
        "StartInterval", "StartCalendarInterval", "ThrottleInterval",
        "RunAtLoad", "KeepAlive", "ProcessType",
    ):
        if key in job:
            out[key] = job[key]
    return out


def loaded_program(label: str) -> list[str]:
    """The argv launchd is actually holding, not the argv on disk."""
    printed = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
        capture_output=True, text=True,
    )
    if printed.returncode != 0:
        return []
    argv, inside = [], False
    for line in printed.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("arguments = {"):
            inside = True
            continue
        if inside:
            if stripped == "}":
                break
            argv.append(stripped)
    return argv


def loaded_environment(label: str) -> dict[str, str]:
    """Return the explicit environment launchd is actually holding."""
    printed = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
        capture_output=True, text=True,
    )
    if printed.returncode != 0:
        return {}
    environment, inside = {}, False
    for line in printed.stdout.splitlines():
        stripped = line.strip()
        if stripped == "environment = {":
            inside = True
            continue
        if inside:
            if stripped == "}":
                break
            key, separator, value = stripped.partition(" => ")
            if separator:
                environment[key] = value
    return environment


def job_needs_activation(job: dict, table: dict[str, str]) -> bool:
    """Detect both stale program paths and stale launchd-held configuration."""
    desired = plist_for(job, table)
    if loaded_program(job["label"]) != desired["ProgramArguments"]:
        return True
    loaded_env = loaded_environment(job["label"])
    return any(loaded_env.get(key) != str(value)
               for key, value in desired["EnvironmentVariables"].items())


def skip_busy_for_requested_activation(
    label: str, requested_jobs: set[str] | None,
) -> bool:
    """Only an explicit continuous-lane request may interrupt its supervisor."""
    return requested_jobs is None or label not in CONTINUOUS_RELOADABLE


def control_plane_available() -> bool:
    """Whether this context can read the user's launchd domain."""
    return subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}"],
        capture_output=True,
    ).returncode == 0


def require_control_plane() -> bool:
    """Write a durable diagnosis and allow no launchd mutation on failure."""
    result = subprocess.run(
        [sys.executable, str(LAUNCHD_PREFLIGHT)], capture_output=True, text=True, check=False,
    )
    if result.returncode == 0:
        return True
    detail = (result.stderr or result.stdout).strip()
    print(f"launchd mutation blocked by control-plane preflight (rc={result.returncode}): {detail[-500:]}")
    return False


def is_running(label: str) -> bool:
    printed = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"],
                             capture_output=True, text=True)
    if printed.returncode == 0:
        return "state = running" in printed.stdout
    # ``launchctl print`` can fail transiently with macOS' Reentrancy avoided
    # response while the process itself is healthy. Treating that as idle lets
    # the watcher bootout a live browser pass. The process table is read-only
    # and is used only as a conservative busy fence; a missing or unreadable
    # table still fails closed (busy) rather than reloading.
    marker = JOB_PROCESS_MARKERS.get(label)
    if not marker:
        return True
    try:
        processes = subprocess.run(
            ["ps", "-axo", "command="], capture_output=True, text=True,
            timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    if processes.returncode != 0:
        return True
    return any(marker in line for line in processes.stdout.splitlines())


def is_brake_only_process(label: str, table: dict[str, str]) -> bool:
    """True only when the current Apply PID has durably refused work on the brake."""
    if label != "ai.anicca.hf-gig-apply-direct":
        return False
    processes = subprocess.run(
        ["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=False,
    )
    if processes.returncode != 0:
        return False
    pids = []
    for line in processes.stdout.splitlines():
        if JOB_PROCESS_MARKERS[label] not in line:
            continue
        fields = line.strip().split(None, 1)
        if fields and fields[0].isdigit():
            pids.append(fields[0])
    if len(pids) != 1:
        return False
    wakes = Path(table["GIG_STATE_DIR"]) / "apply-direct" / "wakes.jsonl"
    try:
        with wakes.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            start = max(0, end - 2_000_000)
            handle.seek(start)
            lines = handle.read().splitlines()
        receipt = json.loads(lines[-1])
    except (OSError, IndexError, json.JSONDecodeError):
        return False
    return (
        receipt.get("status") == "operator_brake"
        and receipt.get("effect") == 0
        and str(receipt.get("pass_id") or "").endswith(f"-{pids[0]}")
    )


def activate(job: dict, table: dict[str, str], release: Path, dry_run: bool,
             skip_busy: bool = False) -> bool:
    label = job["label"]
    path = LAUNCH_AGENTS / f"{label}.plist"
    body = plist_for(job, table)
    if dry_run:
        print(json.dumps(body, indent=1))
        return True
    # Persist the desired immutable release before the busy fence. The loaded
    # launchd definition is unchanged while a pass is live, but the next natural
    # gap must already have the new plist waiting on disk.
    Path(table["GIG_LOG_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(table["GIG_BRAKE_DIR"]).mkdir(parents=True, exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(body, handle)
    if skip_busy:
        # Booting out mid-pass kills the browser lease and leaves locks behind.  A
        # The next watcher tick can activate the new immutable release after a
        # natural gap, while this tick never creates a second owner. Continuous
        # lanes are deliberately reloadable because their durable outbox is the
        # restart boundary and they otherwise have no natural idle gap.
        running = is_running(label)
        brake_only = is_brake_only_process(label, table) if running else False
        if running and not brake_only:
            print(f"  {label}: still mid-pass, leaving it for the next tick")
            return True
        if brake_only:
            print(f"  {label}: brake-only receipt confirmed; migrating stable definition")

    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], capture_output=True)
    # bootout returns before launchd has finished unloading; bootstrapping into
    # the gap fails with "Input/output error" and leaves the lane down.
    for _ in range(50):
        if subprocess.run(["launchctl", "print", f"{domain}/{label}"],
                          capture_output=True).returncode != 0:
            break
        time.sleep(0.2)
    else:
        print(f"  {label}: still loaded after bootout, not bootstrapping")
        return False
    loaded = subprocess.run(["launchctl", "bootstrap", domain, str(path)],
                            capture_output=True, text=True)
    if loaded.returncode != 0:
        print(f"  {label}: bootstrap failed: {loaded.stderr.strip()}")
        return False

    # launchd runs the definition it loaded, so the file we just wrote proves
    # nothing. Compare what launchd hands back with what we meant to install.
    argv = loaded_program(label)
    if argv != body["ProgramArguments"]:
        print(f"  {label}: readback disagrees -> {argv or '(no program)'}")
        return False
    script = next((a for a in argv if a.endswith((".py", ".sh"))), "")
    print(f"  {label}: running {script}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("build", "activate", "status", "stop", "uninstall"))
    parser.add_argument("--sha", help="release this commit instead of HEAD")
    parser.add_argument("--jobs", help="comma-separated labels; default is the complete Coconala catalog")
    parser.add_argument("--dry-run", action="store_true", help="print target jobs, build/load nothing")
    args = parser.parse_args()

    requested_jobs = (
        {label.strip() for label in args.jobs.split(",")} if args.jobs else None
    )
    try:
        wanted = activation_labels(requested_jobs)
        if wanted - coconala_jobs().keys():
            raise ValueError("requested job is outside the Coconala catalog")
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        if args.command in {"stop", "uninstall"}:
            return stop_managed_jobs(args.command == "uninstall")
        if args.command == "status":
            if not require_control_plane():
                return 75
            for owner in coconala_jobs().values():
                result = subprocess.run([str(REPO_ROOT / "bin/lm-loop"), "status", owner],
                                        env={**os.environ, "LIFE_MANAGER_RUNTIME_PYTHON": sys.executable},
                                        capture_output=True, text=True)
                print(result.stdout, end="")
                if result.returncode:
                    return result.returncode
            return 0
        if args.command == "activate" and args.dry_run:
            return activate_managed_jobs(REPO_ROOT, wanted, True)
        sha = git("rev-parse", args.sha or "HEAD")
        release = managed_release(sha)
        if args.command == "build":
            print(json.dumps({"release": str(release), "sha": sha}))
            return 0
        return activate_managed_jobs(release, wanted, False)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
