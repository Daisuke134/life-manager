#!/usr/bin/env python3
"""Validate the dedicated Railway mount, then run the finite tick as `manager`."""
import json
import os
from pathlib import Path
import pwd
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager_core.owned_platform_host import (
    RuntimeConfigurationError,
    read_railway_runtime_identity,
)


SOURCE_ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = Path("/data/manager")


def main():
    env = dict(os.environ)
    try:
        if os.geteuid() != 0:
            raise RuntimeConfigurationError("root entrypoint required to prepare the private mount")
        if STATE_ROOT.is_symlink():
            raise RuntimeConfigurationError("state mount cannot be a symlink")
        identity = read_railway_runtime_identity(
            env,
            expected_project_id=env.get("MANAGER_EXPECTED_RAILWAY_PROJECT_ID"),
            expected_environment_id=env.get("MANAGER_EXPECTED_RAILWAY_ENVIRONMENT_ID"),
            expected_service_id=env.get("MANAGER_EXPECTED_RAILWAY_SERVICE_ID"),
            expected_volume_name=env.get("MANAGER_EXPECTED_RAILWAY_VOLUME_NAME"),
            source_root=SOURCE_ROOT,
            state_root=STATE_ROOT,
        )
        manager = pwd.getpwnam("manager")
        # The volume root may initially be root-owned. Change only that inode;
        # the worker runs without root and owns every file it creates itself.
        os.chown(STATE_ROOT, manager.pw_uid, manager.pw_gid)
        os.setgroups([])
        os.setgid(manager.pw_gid)
        os.setuid(manager.pw_uid)
        executable = SOURCE_ROOT / "scripts" / "run_owned_digital_cycle.py"
        argv = [sys.executable, str(executable), "--state-store", str(STATE_ROOT)]
        os.execve(sys.executable, argv, env)
    except (RuntimeConfigurationError, OSError, KeyError, ValueError):
        # Do not print exception contents: configuration errors can include paths
        # or values supplied by the hosting environment.
        print(json.dumps({"status": "DEPLOYMENT_HOST_REQUIRED", "writes": 0,
                          "reason": "RAILWAY_OWNER_ENTRYPOINT_PREFLIGHT_FAILED"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
