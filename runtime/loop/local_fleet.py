"""Read-only source inventory for a complete local Life Manager installation."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from runtime.loop.macos_loop_registry import SYSTEM_ROLES, validate_registry


HOST_STEWARD_JOB_IDS = (
    "life-manager-disk-cleanup",
    "life-manager-disk-cleanup-15d",
    "lm-fence-reconciler",
    "life-manager-release-reconciler",
)
DISK_WATCHDOG = {
    "id": "disk-watchdog",
    "label": "com.anicca.disk-watchdog",
    "installer": "skills/self/disk-cleanup/install-launchd.sh",
    "template": "skills/self/disk-cleanup/launchd/com.anicca.disk-watchdog.plist",
}


def build_fleet_manifest(repo_root: Path) -> dict:
    """Join committed source metadata without reading private state or starting jobs."""
    registry = json.loads((repo_root / "config/loop-registry.json").read_text())
    catalog = json.loads((repo_root / "apps/life-manager/config/product-loop-catalog.json").read_text())
    loops = registry["loops"]
    diagnostics = []

    def diagnose(code: str, owner_id: str, target: str, **details) -> None:
        diagnostics.append({"code": code, "owner_id": owner_id, "target": target, **details})

    try:
        validate_registry(registry)
    except ValueError as error:
        diagnose("registry_invalid", "loop-registry", "config/loop-registry.json", message=str(error))

    products_by_job = {}
    agents = []
    for product in catalog["loops"]:
        product_id = product["id"]
        agents.append({
            "id": product_id,
            "name": product["name"],
            "job_ids": product["job_ids"],
            "requirements": product.get("requirements", []),
            "hosts": product.get("hosts", {}),
        })
        for loop_id in product["job_ids"]:
            products_by_job.setdefault(loop_id, []).append(product_id)
            if loop_id not in loops:
                diagnose("catalog_job_missing", product_id, loop_id)

    jobs = []
    for loop_id, row in sorted(loops.items()):
        product_ids = products_by_job.get(loop_id, [])
        system_role = row.get("system_role")
        if system_role is not None and system_role not in SYSTEM_ROLES:
            diagnose("unknown_system_role", loop_id, system_role)
        elif not product_ids and system_role is None:
            diagnose("system_role_missing", loop_id, loop_id)
        browser_target = row.get("browser_target_owner")
        if browser_target is not None and browser_target not in loops:
            # A browser target can name a logical lease owner, not a managed service.
            diagnose("browser_target_not_managed", loop_id, browser_target,
                     severity="informational", runtime_validity="unverified")
        jobs.append({
            "loop_id": loop_id,
            "label": row.get("label"),
            "entrypoint": row.get("entrypoint"),
            "product_ids": product_ids,
            "system_role": system_role,
            "browser_target_owner": browser_target,
            "browser_identity": row.get("browser_identity"),
            "resource_class": row.get("resource_class"),
        })

    agents.append({
        "id": "host-steward",
        "name": "Host Steward",
        "job_ids": [loop_id for loop_id in HOST_STEWARD_JOB_IDS if loop_id in loops],
        "requirements": [],
        "hosts": {},
    })
    for loop_id in HOST_STEWARD_JOB_IDS:
        if loop_id not in loops:
            diagnose("host_steward_job_missing", "host-steward", loop_id)
    for field in ("installer", "template"):
        if not (repo_root / DISK_WATCHDOG[field]).is_file():
            diagnose("host_owner_source_missing", "disk-watchdog", DISK_WATCHDOG[field])

    names = {agent["name"].casefold() for agent in agents}
    names.add("host steward (cleanup) — system agent")
    for readme_name in ("README.md", "README.ja.md"):
        readme_path = repo_root / readme_name
        if not readme_path.is_file():
            diagnose("readme_source_missing", readme_name, readme_name)
            continue
        for line in readme_path.read_text().splitlines():
            match = re.match(r"^\|\s*\d+\s*\|\s*([^|]+)\|", line)
            if match:
                name = match.group(1).strip().strip("*")
                if name.casefold() not in names:
                    diagnose("readme_agent_unmapped", readme_name, name)

    catalog_jobs = set(products_by_job) & set(loops)
    external_labels = registry.get("external_labels", [])
    return {
        "schema_version": "local.fleet.v1",
        "agents": agents,
        "jobs": jobs,
        "external_labels": external_labels,
        "host_owners": [dict(DISK_WATCHDOG)],
        "coverage": {
            "registered_jobs": len(loops),
            "catalog_jobs": len(catalog_jobs),
            "system_jobs": len(set(loops) - catalog_jobs),
            "external_labels": len(external_labels),
            "additional_host_owners": 1,
        },
        "diagnostics": diagnostics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Life Managerの全agentとjobをJSONで一覧化します。")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2],
                        help="Life Managerのソースディレクトリ")
    parser.add_argument("--output", type=Path, help="JSONを追加保存するファイル")
    args = parser.parse_args(argv)
    output = json.dumps(build_fleet_manifest(args.repo_root), ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
