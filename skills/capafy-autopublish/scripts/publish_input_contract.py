#!/usr/bin/env python3
"""Bind a prepared Capafy package and hosted model to one Agent ID."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


def snapshot(args: argparse.Namespace) -> dict:
    home = args.publisher_home.resolve()
    workspace = args.workspace.resolve()
    if workspace != home / ".openclaw/workspace":
        raise ValueError("workspace is not inside the Agent publisher home")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    model_id, max_tokens = config["model_id"], config["max_tokens"]
    if not isinstance(model_id, str) or not model_id or type(max_tokens) is not int:
        raise ValueError("invalid listing model contract")
    hosted = json.loads((home / ".openclaw/openclaw.json").read_text(encoding="utf-8"))
    provider = hosted["models"]["providers"]["openrouter"]
    if (provider.get("api") != "openai-responses"
            or provider.get("apiKey") != "${CAPAFY_HOST_OPENROUTER_KEY}"
            or provider.get("models") != [{"id": model_id, "name": model_id,
                                            "maxTokens": max_tokens}]
            or hosted["agents"]["defaults"]["model"]["primary"] != "openrouter/" + model_id):
        raise ValueError("hosted provider differs from the listing model contract")
    skill_dir = workspace / "skills" / args.skill_name
    manifest = json.loads((args.work_dir / "publish-work-state.json").read_text(encoding="utf-8"))
    extra = manifest["extra"]
    sources = [extra.get("explicit_skill"), *(extra.get("external_skill_bindings") or [])]
    if (manifest.get("agent_id") != args.agent_id
            or not manifest.get("agent_version_id")
            or Path(extra["runtime_dir"]).resolve() != workspace
            or not sources or not all(
                isinstance(source, dict) and source.get("source_path")
                and Path(source["source_path"]).resolve() == skill_dir
                for source in sources)):
        raise ValueError("Publisher manifest does not select this Agent and Skill")
    files = sorted(skill_dir.rglob("*"))
    if not (skill_dir / "SKILL.md").is_file() or any(path.is_symlink() for path in files):
        raise ValueError("prepared Skill is missing or contains a symlink")
    digest = hashlib.sha256()
    for value in (config, hosted, sources):
        digest.update(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    for path in files:
        if path.is_file():
            digest.update(str(path.relative_to(skill_dir)).encode("utf-8"))
            digest.update(path.read_bytes())
    icon = Path(config["icon"])
    digest.update(icon.read_bytes())
    return {"agent_id": args.agent_id, "skill_name": args.skill_name,
            "agent_version_id": manifest["agent_version_id"],
            "publisher_home": str(home), "workspace": str(workspace),
            "model_id": model_id, "max_tokens": max_tokens,
            "source_sha256": digest.hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("write", "verify"))
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--skill-name", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--publisher-home", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        expected = snapshot(args)
        target = args.work_dir / "publisher-inputs.json"
        if args.action == "verify":
            if json.loads(target.read_text(encoding="utf-8")) != expected:
                raise ValueError("publisher inputs changed after preparation")
            print(expected["model_id"], expected["max_tokens"])
            return 0
        args.work_dir.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".publisher-inputs.", dir=args.work_dir)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(expected, stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, target)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return 0
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"publish_input_contract: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
