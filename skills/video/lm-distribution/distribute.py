#!/usr/bin/env python3
"""Publish one exact Life Manager creative contract through Postiz."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone
from typing import Mapping


class DistributionError(RuntimeError):
    pass


class DistributionConfig:
    def __init__(
        self,
        *,
        creative_id: str,
        video: Path,
        caption: Path,
        ledger: Path,
        instagram_adapter: Path,
        tiktok_adapter: Path,
        instagram_handle: str,
        instagram_accounts: Path,
        instagram_settings: Path | None,
        instagram_credentials: Path | None,
        instagram_profile_state: Path | None,
        tiktok_integration: str,
        approvals: Path,
        env: Mapping[str, str] | None = None,
        format_id: str = "",
        form: str = "",
        locale: str = "",
        slot: str = "",
        instagram_integration: str = "",
        postiz_adapter: Path | None = None,
        youtube_adapter: Path | None = None,
        youtube_integration: str = "",
    ):
        self.creative_id = creative_id
        self.video = Path(video)
        self.caption = Path(caption)
        self.ledger = Path(ledger)
        self.instagram_adapter = Path(instagram_adapter)
        self.tiktok_adapter = Path(tiktok_adapter)
        self.youtube_adapter = Path(youtube_adapter) if youtube_adapter is not None else self.tiktok_adapter
        self.instagram_handle = instagram_handle
        self.instagram_accounts = Path(instagram_accounts)
        self.instagram_settings = (
            Path(instagram_settings) if instagram_settings is not None else None
        )
        self.instagram_credentials = (
            Path(instagram_credentials) if instagram_credentials is not None else None
        )
        self.instagram_profile_state = (
            Path(instagram_profile_state) if instagram_profile_state is not None else None
        )
        self.tiktok_integration = tiktok_integration
        self.instagram_integration = instagram_integration
        self.postiz_adapter = Path(postiz_adapter) if postiz_adapter is not None else Path(__file__).with_name("postiz_video.py")
        self.youtube_integration = youtube_integration
        self.approvals = Path(approvals)
        self.env = dict(env or os.environ)
        self.format_id = format_id
        self.form = form
        self.locale = locale
        self.slot = slot


def render_caption(bank: Path, creative_id: str, output: Path) -> Path:
    matches = []
    try:
        lines = Path(bank).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise DistributionError("creative bank is missing") from exc
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DistributionError("creative bank contains invalid JSON") from exc
        if isinstance(row, dict) and row.get("id") == creative_id:
            matches.append(row)
    if len(matches) != 1:
        raise DistributionError("creative id must match exactly one bank row")
    row = matches[0]
    fields = [row.get("pain"), row.get("moment"), row.get("punchline")]
    if any(not isinstance(value, str) or not value.strip() for value in fields):
        raise DistributionError("creative bank row is missing caption fields")
    caption = (
        f"{fields[0]}\n\n"
        f"{fields[1]}\n\n"
        f"{fields[2]}\n\n"
        "Life Manager が、予定に合わせて先回りします。\n"
        "aniccaai.com/life-manager\n\n"
        "#LifeManager #AIAssistant #CalendarAutomation\n"
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(caption, encoding="utf-8")
    os.chmod(output, 0o600)
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate(config: DistributionConfig, platform: str) -> tuple[str, str]:
    if not config.creative_id.strip():
        raise DistributionError("creative_id is required")
    for name, path in (("video", config.video), ("caption", config.caption)):
        if not path.is_file() or path.stat().st_size == 0:
            raise DistributionError(f"{name} must be a non-empty file")
    adapter = {
        "instagram": (
            "Instagram Postiz adapter" if config.instagram_integration.strip() else "instagram adapter",
            config.postiz_adapter if config.instagram_integration.strip() else config.instagram_adapter,
        ),
        "tiktok": ("tiktok adapter", config.tiktok_adapter),
        "youtube": ("youtube adapter", config.youtube_adapter),
    }.get(platform)
    if adapter is None or not adapter[1].is_file():
        raise DistributionError(f"{adapter[0] if adapter else platform + ' adapter'} is missing")
    caption_text = config.caption.read_text(encoding="utf-8").strip()
    if not caption_text:
        raise DistributionError("caption must contain text")
    return _sha256(config.video), _sha256(config.caption)


def _read_ledger(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    rows = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DistributionError("distribution ledger contains invalid JSON") from exc
        if not isinstance(row, dict):
            raise DistributionError("distribution ledger row must be an object")
        rows.append(row)
    return rows


def _approved(path: Path, creative_id: str, video_hash: str, caption_hash: str) -> dict | None:
    """Distribution is authorised by a receipt.

    Two shapes exist. A per-video receipt names one creative AND the digests of the exact video and
    caption that were shown for approval, so re-cutting the video or rewriting the caption silently
    invalidates it. A standing receipt (`scope: "standing"`) or the Life Manager approval object
    (`approval_mode: "standing_policy_no_additional_gate"`) records the 2026-07-26 Dais ruling that
    removed the preview gate: the daily pipeline's own renders are authorised from then on without a
    per-video receipt. Anything unreadable, unparseable or unmatched is not an approval.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    records = []
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        document = None
    if isinstance(document, dict):
        records.append(document)
    else:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                records.append(row)
    for row in records:
        if row.get("scope") == "standing":
            return row
        if (
            row.get("status") == "approved"
            and row.get("approval_mode") == "standing_policy_no_additional_gate"
            and row.get("creative_id") == creative_id
        ):
            return row
        if (
            row.get("creative_id") == creative_id
            and row.get("video_sha256") == video_hash
            and row.get("caption_sha256") == caption_hash
        ):
            return row
    return None


def _existing(rows: list[dict], platform: str, creative_id: str, video_hash: str, caption_hash: str, slot: str = ""):
    url_owners: dict[str, tuple] = {}
    provider_owners: dict[str, tuple] = {}
    matches = []
    expected = (creative_id, video_hash, caption_hash, slot)
    for row in rows:
        if (
            row.get("platform") != platform
            or row.get("status") != "published"
            or not _valid_public_url(platform, row.get("public_url"))
        ):
            continue
        lineage = (row.get("creative_id"), row.get("video_sha256"), row.get("caption_sha256"), row.get("slot", ""))
        public_url = row["public_url"]
        provider_id = row.get("provider_id")
        url_owners.setdefault(public_url, lineage)
        if isinstance(provider_id, str) and provider_id:
            provider_owners.setdefault(provider_id, lineage)
        owns_url = url_owners[public_url] == lineage
        owns_provider = not provider_id or provider_owners[provider_id] == lineage
        if lineage == expected and owns_url and owns_provider:
            matches.append(row)
    return matches[-1] if matches else None


def _valid_public_url(platform: str, value) -> bool:
    if not isinstance(value, str):
        return False
    if platform == "instagram":
        return bool(re.fullmatch(r"https://www\.instagram\.com/(?:reel|p)/[A-Za-z0-9_-]+/?", value))
    if platform == "tiktok":
        return bool(re.fullmatch(r"https://www\.tiktok\.com/@[^/]+/video/[0-9]+/?", value))
    if platform == "youtube":
        return bool(re.fullmatch(
            r"https://www\.youtube\.com/(?:shorts/[A-Za-z0-9_-]+|watch\?v=[A-Za-z0-9_-]+(?:&[^#]+)?)/?",
            value,
        ))
    return False


def _run_json(argv: list[str], env: Mapping[str, str]) -> dict:
    proc = subprocess.run(argv, text=True, capture_output=True, env=dict(env), timeout=900)
    if proc.returncode != 0:
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        detail = None
        if lines:
            try:
                payload = json.loads(lines[-1])
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                detail = payload.get("error") or payload.get("message")
        suffix = f": {detail}" if isinstance(detail, str) and detail else ""
        raise DistributionError(f"adapter failed with exit {proc.returncode}{suffix}")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise DistributionError("adapter returned no JSON")
    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise DistributionError("adapter returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise DistributionError("adapter JSON must be an object")
    return result


def _append_success(
    config: DistributionConfig,
    *,
    platform: str,
    public_url: str,
    video_hash: str,
    caption_hash: str,
    provider_id: str | None,
    adapter_result: dict | None = None,
) -> dict:
    adapter_result = adapter_result or {}
    route = adapter_result.get("route")
    provider_cost = adapter_result.get("provider_cost_usd")
    logged_out = adapter_result.get("logged_out_readback")
    migration_date = adapter_result.get("migration_date")
    provider_reconciled = adapter_result.get("reconciled") is True
    public_readback_verified = platform != "tiktok" or provider_reconciled
    if platform == "tiktok" and not public_readback_verified:
        raise DistributionError("TikTok adapter did not provide public readback")
    if route == "direct_browser" and not (
        provider_cost == 0
        and logged_out is True
        and isinstance(migration_date, str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", migration_date)
    ):
        raise DistributionError("direct TikTok result lacks zero-cost logged-out provenance")
    row = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "platform": platform,
        "status": "published",
        "creative_id": config.creative_id,
        "video_path": str(config.video),
        "video_sha256": video_hash,
        "caption_path": str(config.caption),
        "caption_sha256": caption_hash,
        "public_url": public_url,
        "provider_id": provider_id,
        "route": route or ("instagram_file_script" if platform == "instagram" else "postiz"),
        "provider_cost_usd": provider_cost,
        "logged_out_readback": logged_out,
        "migration_date": migration_date,
        "provider_reconciled": provider_reconciled,
        "public_readback_verified": public_readback_verified,
        # Publication lineage: without these fields a ledger-reconciled receipt cannot
        # pass the adapter's own verification (FIX 1).
        "format_id": config.format_id,
        "form": config.form,
        "locale": config.locale,
        "slot": config.slot,
    }
    config.ledger.parent.mkdir(parents=True, exist_ok=True)
    with config.ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.chmod(config.ledger, 0o600)
    return row


def distribute_platform(config: DistributionConfig, platform: str) -> dict:
    if platform not in {"instagram", "tiktok", "youtube"}:
        raise DistributionError("platform must be instagram, tiktok, or youtube")
    if platform == "youtube" and not config.youtube_integration.strip():
        raise DistributionError("YouTube integration is required")
    video_hash, caption_hash = _validate(config, platform)
    # Fail closed BEFORE any adapter runs: without an approval for these exact bytes nothing is posted.
    approval = _approved(config.approvals, config.creative_id, video_hash, caption_hash)
    if approval is None:
        raise DistributionError(
            f"no approval receipt for creative {config.creative_id} with this exact video and caption"
        )
    rows = _read_ledger(config.ledger)

    existing = _existing(rows, platform, config.creative_id, video_hash, caption_hash, config.slot)
    if existing:
        if platform == "tiktok" and existing.get("public_readback_verified") is not True:
            raise DistributionError("existing TikTok receipt lacks public readback")
        return {
            "creative_id": config.creative_id,
            "video_sha256": video_hash,
            "caption_sha256": caption_hash,
            "platform": platform,
            "public_url": existing["public_url"],
            "provider_post_id": existing.get("provider_id"),
            "provider_route": existing.get("route"),
            # Provenance, not fabrication: the short-circuit reports whether the EXISTING
            # ledger row was provider-reconciled, exactly as recorded.
            "provider_reconciled": existing.get("provider_reconciled") is True,
        }

    if platform == "instagram":
        if config.instagram_integration.strip():
            result = _run_json(
                [
                    str(config.postiz_adapter),
                    "--video",
                    str(config.video),
                    "--caption-file",
                    str(config.caption),
                    "--integration",
                    config.instagram_integration,
                    "--platform",
                    "instagram",
                ],
                config.env,
            )
            instagram_url = result.get("post_url")
            if result.get("state") != "PUBLISHED" or not _valid_public_url("instagram", instagram_url):
                raise DistributionError("Instagram Postiz did not return a PUBLISHED direct public URL")
            published = _append_success(
                config,
                platform="instagram",
                public_url=instagram_url,
                video_hash=video_hash,
                caption_hash=caption_hash,
                provider_id=result.get("post_id"),
                adapter_result=result,
            )
        else:
            instagram_argv = [
                    str(config.instagram_adapter),
                    "--video",
                    str(config.video),
                    "--caption-file",
                    str(config.caption),
                    "--handle",
                    config.instagram_handle,
                    "--accounts-path",
                    str(config.instagram_accounts),
            ]
            if config.instagram_settings is not None:
                instagram_argv.extend(["--settings-path", str(config.instagram_settings)])
            if config.instagram_credentials is not None:
                instagram_argv.extend(["--credentials-path", str(config.instagram_credentials)])
            if config.instagram_profile_state is not None:
                instagram_argv.extend(["--profile-state-dir", str(config.instagram_profile_state)])
            instagram_argv.append("--live")
            result = _run_json(instagram_argv, config.env)
        instagram_url = result.get("post_url")
        if not config.instagram_integration.strip():
            if result.get("outcome") != "published" or not _valid_public_url("instagram", instagram_url):
                raise DistributionError("Instagram did not return a published public URL")
            published = _append_success(
                config,
                platform="instagram",
                public_url=instagram_url,
                video_hash=video_hash,
                caption_hash=caption_hash,
                provider_id=result.get("code"),
                adapter_result=result,
            )
    elif platform == "tiktok":
        result = _run_json(
            [
                str(config.tiktok_adapter),
                "--video",
                str(config.video),
                "--caption-file",
                str(config.caption),
                "--integration",
                config.tiktok_integration,
            ],
            config.env,
        )
        tiktok_url = result.get("post_url")
        if result.get("state") != "PUBLISHED" or not _valid_public_url("tiktok", tiktok_url):
            raise DistributionError("TikTok did not return a PUBLISHED public URL")
        published = _append_success(
            config,
            platform="tiktok",
            public_url=tiktok_url,
            video_hash=video_hash,
            caption_hash=caption_hash,
            provider_id=result.get("post_id"),
            adapter_result=result,
        )
    else:
        result = _run_json(
            [
                str(config.youtube_adapter),
                "--video",
                str(config.video),
                "--caption-file",
                str(config.caption),
                "--integration",
                config.youtube_integration,
                "--platform",
                "youtube",
            ],
            config.env,
        )
        youtube_url = result.get("post_url")
        if result.get("state") != "PUBLISHED" or not _valid_public_url("youtube", youtube_url):
            raise DistributionError("YouTube did not return a PUBLISHED direct public URL")
        published = _append_success(
            config,
            platform="youtube",
            public_url=youtube_url,
            video_hash=video_hash,
            caption_hash=caption_hash,
            provider_id=result.get("post_id"),
            adapter_result=result,
        )

    return {
        "creative_id": config.creative_id,
        "video_sha256": video_hash,
        "caption_sha256": caption_hash,
        "platform": platform,
        "public_url": published["public_url"],
        "provider_post_id": published.get("provider_id"),
        "provider_route": published.get("route"),
        "provider_reconciled": published.get("provider_reconciled") is True,
    }


def distribute(config: DistributionConfig) -> dict:
    instagram = distribute_platform(config, "instagram")
    tiktok = distribute_platform(config, "tiktok")

    return {
        "creative_id": config.creative_id,
        "video_sha256": instagram["video_sha256"],
        "caption_sha256": instagram["caption_sha256"],
        "instagram_url": instagram["public_url"],
        "tiktok_url": tiktok["public_url"],
    }


def _lm_video_state_root() -> Path:
    """Portable lm-video state root: LM_DATA_DIR when set (absolute only,
    mirroring resolveDataRoot in apps/life-manager/lib/runtime-paths.js and
    default_video_root in skills/video/daily-lm-video/generate.py), else
    <home>/.local/state/life-manager."""
    override = os.environ.get("LM_DATA_DIR", "").strip()
    if override:
        if not Path(override).is_absolute():
            raise SystemExit("LM_DATA_DIR must be an absolute path")
        data_root = Path(override)
    else:
        data_root = Path.home() / ".local/state/life-manager"
    return data_root / "state" / "lm-video"


def default_tiktok_adapter(here: Path, env: Mapping[str, str]) -> Path:
    if env.get("LM_TIKTOK_DIRECT_MIGRATION") == "1":
        return Path(here) / "tiktok_direct.mjs"
    return Path(here) / "postiz_video.py"


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--creative-id", required=True)
    parser.add_argument("--platform", choices=("instagram", "tiktok", "youtube", "both"), default="both")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--caption-file", type=Path)
    parser.add_argument(
        "--bank",
        type=Path,
        default=here.parent / "daily-lm-video" / "creative-bank.jsonl",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=(
            Path(os.environ["LM_DISTRIBUTION_LEDGER"]).expanduser()
            if os.environ.get("LM_DISTRIBUTION_LEDGER")
            else _lm_video_state_root() / "distribution.jsonl"
        ),
    )
    parser.add_argument(
        "--instagram-adapter",
        type=Path,
        default=here / "instagram_video.sh",
    )
    parser.add_argument(
        "--tiktok-adapter",
        type=Path,
        default=default_tiktok_adapter(here, os.environ),
    )
    parser.add_argument(
        "--youtube-adapter",
        type=Path,
        default=here / "postiz_video.py",
    )
    parser.add_argument(
        "--postiz-adapter",
        type=Path,
        default=here / "postiz_video.py",
    )
    parser.add_argument("--instagram-handle", default=os.environ.get("LM_INSTAGRAM_HANDLE", "anicca.affirms2"))
    parser.add_argument(
        "--instagram-accounts",
        type=Path,
        default=Path(
            os.environ.get(
                "LM_INSTAGRAM_ACCOUNTS",
                "~/.cloak/life-manager-instagram-accounts.json",
            )
        ).expanduser(),
    )
    parser.add_argument("--instagram-settings", type=Path)
    parser.add_argument("--instagram-credentials", type=Path)
    parser.add_argument("--instagram-profile-state", type=Path)
    parser.add_argument("--instagram-integration", default=os.environ.get("LM_INSTAGRAM_INTEGRATION", ""))
    parser.add_argument(
        "--approvals",
        type=Path,
        default=(
            Path(os.environ["LM_DISTRIBUTION_APPROVALS"]).expanduser()
            if os.environ.get("LM_DISTRIBUTION_APPROVALS")
            else _lm_video_state_root() / "distribution-approvals.jsonl"
        ),
    )
    parser.add_argument(
        "--tiktok-integration",
        default=os.environ.get("LM_TIKTOK_INTEGRATION", "cmpc6cr6g00d8lg0yfythzz9f"),
    )
    parser.add_argument(
        "--youtube-integration",
        default=os.environ.get("LM_YOUTUBE_INTEGRATION", ""),
    )
    parser.add_argument("--format-id", default="")
    parser.add_argument("--form", default="")
    parser.add_argument("--locale", default="")
    parser.add_argument("--slot", default="")
    args = parser.parse_args()

    caption = args.caption_file
    if caption is None:
        caption = _lm_video_state_root() / "captions" / f"{args.creative_id}.txt"
        render_caption(args.bank, args.creative_id, caption)
    config = DistributionConfig(
            creative_id=args.creative_id,
            video=args.video,
            caption=caption,
            ledger=args.ledger,
            instagram_adapter=args.instagram_adapter,
            tiktok_adapter=args.tiktok_adapter,
            youtube_adapter=args.youtube_adapter,
            instagram_handle=args.instagram_handle,
            instagram_accounts=args.instagram_accounts,
            instagram_settings=args.instagram_settings,
            instagram_credentials=args.instagram_credentials,
            instagram_profile_state=args.instagram_profile_state,
            tiktok_integration=args.tiktok_integration,
            youtube_integration=args.youtube_integration,
            approvals=args.approvals,
            format_id=args.format_id,
            form=args.form,
            locale=args.locale,
            slot=args.slot,
            instagram_integration=args.instagram_integration,
            postiz_adapter=args.postiz_adapter,
        )
    result = (
        distribute(config)
        if args.platform == "both"
        else distribute_platform(config, args.platform)
    )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DistributionError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, separators=(",", ":")))
        raise SystemExit(1)
