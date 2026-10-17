#!/usr/bin/env python3
"""Build one source-bound English affiliate article without exposing its link."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from local_loop import elevenlabs_link
from owned_publish import (  # noqa: F401  (ATTRIBUTION is part of this module's contract)
    ATTRIBUTION, TRACKED_HOST, render_affiliate_markdown,
)
from provider_cli import atomic_write


class ContentError(Exception):
    pass


REQUIRED = {
    "elevenlabs-affiliate": "Earn up to 22% in commissions over 12 months",
    "elevenlabs-pricing": "Free $0 (10,000 credits); Starter $6 (30,000 credits)",
    "elevenlabs-tts": "commercial usage rights are only available with paid plans",
    "elevenlabs-alec": "five-figure income stream",
    "elevenlabs-greg": "referring thousands of users each month",
}

FOUNDATION_REQUIRED = {
    "elevenlabs-pricing": "Credits are shared across every product",
    "elevenlabs-tts": "Output is nondeterministic",
}

AGENTS_REQUIRED = {
    "elevenagents-overview": "tools to monitor and evaluate agent performance at scale",
    "elevenagents-quickstart": "managed either through the",
    "elevenagents-integrations": "whether through web widgets, mobile apps, phone systems, or custom integrations",
    "elevenagents-cost": "There is no cost to create your agent.",
}

TTS_API_REQUIRED = {
    "elevenlabs-api-quickstart": "Store the key as a managed secret",
    "elevenlabs-api-reference": "character costs",
    "elevenlabs-tts-capability": (
        "The models are nondeterministic.",
        "Up to 2 free regenerations per generation",
    ),
    "elevenlabs-latency-guide": (
        "75ms refers to model inference time only.",
        "Actual end-to-end latency will vary",
    ),
    "elevenlabs-api-pricing": (
        "### v3\nText to Speech\n$0.10\nPrice per 1K characters",
        "v2 Multilingual\nText to Speech\n$0.10\nPrice per 1K characters",
        "Flash / Turbo\nText to Speech\n$0.05\nPrice per 1K characters",
    ),
}
TTS_API_SLUG = "elevenlabs-text-to-speech-api-for-developers"
TTS_API_LINK_FIELD = "TTS API affiliate link"
TTS_API_TITLE = "ElevenLabs Text-to-Speech API: What Developers Should Benchmark Before Paying"
TTS_API_URLS = (
    "https://elevenlabs.io/docs/eleven-api/quickstart",
    "https://elevenlabs.io/docs/api-reference/introduction",
    "https://elevenlabs.io/docs/overview/capabilities/text-to-speech",
    "https://elevenlabs.io/docs/eleven-api/guides/how-to/best-practices/latency-optimization",
    "https://elevenlabs.io/pricing/api",
)

DISCLOSURE = "Disclosure: This article contains an affiliate link."
FORBIDDEN_CLAIMS = ("guaranteed income", "guaranteed earnings", "risk-free income", "100% guaranteed")


def require_sources(state, required, now):
    source_hashes = {}
    for source_id, marker in required.items():
        directory = state / "sources" / source_id
        try:
            receipt = json.loads((directory / "latest.json").read_text(encoding="utf-8"))
            expires = datetime.fromisoformat(receipt["expires_at"])
            artifact = next(directory.glob(f"{receipt['raw_sha256']}.*"))
            raw = artifact.read_text(encoding="utf-8")
        except (OSError, ValueError, KeyError, StopIteration) as error:
            raise ContentError("required source capture is unavailable") from error
        markers = (marker,) if isinstance(marker, str) else tuple(marker)
        if expires <= now or not markers or any(value not in raw for value in markers):
            raise ContentError("required source is stale or does not support its claim")
        source_hashes[source_id] = receipt["raw_sha256"]
    return source_hashes


def build(root, state, private_markdown, link_field="Default affiliate link"):
    now = datetime.now(timezone.utc)
    source_hashes = require_sources(state, REQUIRED, now)
    link = elevenlabs_link(private_markdown, link_field)
    if not link:
        raise ContentError("executable ElevenLabs link is unavailable")
    template = (root / "config" / "content" / "elevenlabs-en-v1.md").read_text(encoding="utf-8")
    if template.count("{{AFFILIATE_LINK}}") != 1:
        raise ContentError("content template has an invalid link boundary")
    markdown = render_affiliate_markdown(template.replace("{{AFFILIATE_LINK}}", link), link)
    slug = "elevenlabs-plans-for-solo-creators"
    artifact = {
        "schema_version": 1,
        "artifact_id": "elevenlabs-en-v1",
        "slug": slug,
        "locale": "en",
        "title": "ElevenLabs for Solo Creators: Which Plan Actually Makes Sense?",
        "disclosure": "affiliate_link",
        "source_hashes": source_hashes,
        "content_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
        "markdown": markdown,
        "state": "READY_FOR_POLICY",
        "built_at": now.isoformat(),
    }
    target = state / "content" / f"{slug}.json"
    atomic_write(target, artifact)
    return {key: artifact[key] for key in ("artifact_id", "slug", "content_sha256", "state")}


def build_agents(root, state, private_markdown, link_field="ElevenAgents affiliate link"):
    now = datetime.now(timezone.utc)
    source_hashes = require_sources(state, AGENTS_REQUIRED, now)
    link = elevenlabs_link(private_markdown, link_field)
    if not link:
        raise ContentError("executable ElevenAgents link is unavailable")
    template = (root / "config" / "content" / "elevenagents-en-v1.md").read_text(encoding="utf-8")
    if template.count("{{AFFILIATE_LINK}}") != 1:
        raise ContentError("content template has an invalid link boundary")
    markdown = render_affiliate_markdown(template.replace("{{AFFILIATE_LINK}}", link), link)
    slug = "elevenagents-for-customer-support"
    artifact = {
        "schema_version": 1,
        "artifact_id": "elevenagents-en-v1",
        "slug": slug,
        "locale": "en",
        "title": "ElevenAgents for Customer Support: What to Test Before You Pay",
        "disclosure": "affiliate_link",
        "source_hashes": source_hashes,
        "content_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
        "markdown": markdown,
        "state": "READY_FOR_POLICY",
        "built_at": now.isoformat(),
    }
    atomic_write(state / "content" / f"{slug}.json", artifact)
    return {key: artifact[key] for key in ("artifact_id", "slug", "content_sha256", "state")}


def validate_tts_api_result(row):
    if row.get("title") != TTS_API_TITLE or not isinstance(row.get("markdown"), str):
        raise ContentError("generated TTS API article contract is invalid")
    markdown = row["markdown"]
    checks = (
        2500 <= len(markdown) <= 9000,
        markdown.startswith(f"# {TTS_API_TITLE}"),
        markdown.count("{{AFFILIATE_LINK}}") == 1,
        "try.elevenlabs.io" not in markdown,
        markdown.find(DISCLOSURE) < markdown.find("{{AFFILIATE_LINK}}"),
        "## A benchmark before you pay" in markdown,
        "Last evidence refresh" in markdown,
        all(url in markdown for url in TTS_API_URLS),
        not any(claim in markdown.lower() for claim in FORBIDDEN_CLAIMS),
    )
    if not all(checks):
        raise ContentError("generated TTS API article failed deterministic validation")
    return markdown


def build_tts_api(root, state, private_markdown):
    target = state / "content" / f"{TTS_API_SLUG}.json"
    link = elevenlabs_link(private_markdown, TTS_API_LINK_FIELD)
    if not link:
        raise ContentError("executable ElevenLabs link is unavailable")
    now = datetime.now(timezone.utc)
    source_hashes = require_sources(state, TTS_API_REQUIRED, now)
    if target.is_file():
        artifact = json.loads(target.read_text(encoding="utf-8"))
        if (
            artifact.get("readback_links") == [link]
            and artifact.get("source_hashes") == source_hashes
        ):
            return {key: artifact[key] for key in ("artifact_id", "slug", "content_sha256", "state")}
    template = (root / "config" / "content" / "elevenlabs-tts-api-en-v1.md").read_text(encoding="utf-8")
    markdown = render_affiliate_markdown(validate_tts_api_result({
        "title": TTS_API_TITLE, "markdown": template,
    }).replace("{{AFFILIATE_LINK}}", link), link)
    artifact = {
        "schema_version": 1, "artifact_id": "elevenlabs-tts-api-en-v1",
        "slug": TTS_API_SLUG, "locale": "en", "title": TTS_API_TITLE,
        "disclosure": "affiliate_link", "source_hashes": source_hashes,
        "content_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
        "markdown": markdown, "state": "READY_FOR_POLICY", "built_at": now.isoformat(),
    }
    atomic_write(target, artifact)
    return {key: artifact[key] for key in ("artifact_id", "slug", "content_sha256", "state")}


def build_foundation(root, state):
    now = datetime.now(timezone.utc)
    source_hashes = require_sources(state, FOUNDATION_REQUIRED, now)
    markdown = (root / "config" / "content" / "ai-voice-evaluation-en-v1.md").read_text(encoding="utf-8")
    if "affiliate link" not in markdown or "contains no affiliate links" not in markdown:
        raise ContentError("foundation disclosure is missing")
    slug = "how-to-test-ai-voice-tools-before-you-pay"
    artifact = {
        "schema_version": 1,
        "artifact_id": "ai-voice-evaluation-en-v1",
        "slug": slug,
        "locale": "en",
        "title": "How to Test an AI Voice Tool Before You Pay",
        "source_hashes": source_hashes,
        "content_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
        "markdown": markdown,
        "readback_markers": [
            "This article is independent editorial content.",
            "Score five things, not one",
            "Choose the lowest plan that clears the job",
        ],
        "state": "READY_FOR_PUBLICATION",
        "built_at": now.isoformat(),
    }
    atomic_write(state / "content" / f"{slug}.json", artifact)
    return {key: artifact[key] for key in ("artifact_id", "slug", "content_sha256", "state")}


def policy_checks(artifact, source_hashes, link):
    markdown = artifact.get("markdown", "")
    tracking = link if isinstance(link, str) else ""
    parsed = urlsplit(tracking)
    lowered = markdown.lower()
    return {
        "artifact_hash": hashlib.sha256(markdown.encode()).hexdigest() == artifact.get("content_sha256"),
        "disclosure_before_first_cta": bool(tracking) and DISCLOSURE in markdown and markdown.find(DISCLOSURE) < markdown.find(tracking),
        "fresh_sources_match_artifact": source_hashes == artifact.get("source_hashes"),
        # One distinct owned link; the rendered page repeats it at the top and end.
        "one_owned_tracking_link": bool(tracking) and parsed.scheme == "https" and parsed.hostname == TRACKED_HOST
        and set(re.findall(r"https://try\.elevenlabs\.io/[^\s)\]]*", markdown)) == {tracking},
        "forbidden_claims_absent": not any(claim in lowered for claim in FORBIDDEN_CLAIMS),
    }


def policy_campaign(state, private_markdown, slug, required, link_field, project, markers):
    path = state / "content" / f"{slug}.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ContentError("affiliate article artifact is unavailable") from error
    if artifact.get("state") not in ("READY_FOR_POLICY", "READY_FOR_PUBLICATION"):
        raise ContentError("affiliate article is not ready for policy")
    source_hashes = require_sources(state, required, datetime.now(timezone.utc))
    link = elevenlabs_link(private_markdown, link_field)
    checks = policy_checks(artifact, source_hashes, link)
    receipt = {
        "schema_version": 1,
        "receipt_type": "CONTENT_POLICY",
        "artifact_id": artifact.get("artifact_id"),
        "slug": slug,
        "content_sha256": artifact.get("content_sha256"),
        "source_hashes": source_hashes,
        "checks": checks,
        "decision": "PASS" if all(checks.values()) else "FAIL",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write(state / "policy" / f"{slug}.json", receipt)
    if receipt["decision"] != "PASS":
        raise ContentError("affiliate article policy failed")
    artifact.update({
        "project": project,
        "readback_markers": [DISCLOSURE, *markers, "Last evidence refresh"],
        "readback_links": [link],
        "state": "READY_FOR_PUBLICATION",
    })
    atomic_write(path, artifact)
    return {key: receipt[key] for key in ("artifact_id", "slug", "content_sha256", "decision")}


def policy(state, private_markdown, link_field="Default affiliate link"):
    return policy_campaign(
        state, private_markdown, "elevenlabs-plans-for-solo-creators", REQUIRED,
        link_field, "AI VOICE TOOLS", ["A simple buying checklist"],
    )


def policy_agents(state, private_markdown, link_field="ElevenAgents affiliate link"):
    return policy_campaign(
        state, private_markdown, "elevenagents-for-customer-support", AGENTS_REQUIRED,
        link_field, "AI CUSTOMER SUPPORT", ["The five-test evaluation"],
    )


def policy_tts_api(state, private_markdown):
    return policy_campaign(
        state, private_markdown, TTS_API_SLUG, TTS_API_REQUIRED,
        TTS_API_LINK_FIELD, "AI VOICE API", ["A benchmark before you pay"],
    )


def build_x(state):
    slug = "elevenlabs-plans-for-solo-creators"
    publication_path = state / "owned-publications" / f"{slug}.json"
    try:
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ContentError("live owned publication receipt is unavailable") from error
    url = f"https://aniccaai.com/blog/{slug}"
    if publication.get("state") != "LIVE" or publication.get("public_url") != url:
        raise ContentError("owned article is not live")
    text = (
        "Choosing an AI voice plan? Compare commercial rights, real monthly usage, "
        "cloning needs, and correction time before upgrading.\n\n"
        "Affiliate link: my evidence-based ElevenLabs plan guide:\n"
        f"{url}"
    )
    if len(text) > 280:
        raise ContentError("X artifact exceeds the platform limit")
    target = state / "x-content" / "elevenlabs-en-1.txt"
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text + "\n")
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)
    return {
        "artifact_id": "elevenlabs-x-en-1",
        "placement": "elevenlabs-en-1",
        "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "state": "READY_FOR_X_PUBLICATION",
    }


def build_x_agents(state):
    slug = "elevenagents-for-customer-support"
    publication_path = state / "owned-publications" / f"{slug}.json"
    try:
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ContentError("live owned publication receipt is unavailable") from error
    url = f"https://aniccaai.com/blog/{slug}"
    if publication.get("state") != "LIVE" or publication.get("public_url") != url:
        raise ContentError("owned article is not live")
    text = (
        "Before deploying a customer-support voice agent, test knowledge freshness, failure handling, "
        "latency, channel fit, and real call costs.\n\n"
        "Affiliate link disclosed in my ElevenAgents evaluation:\n"
        f"{url}"
    )
    if len(text) > 280:
        raise ContentError("X artifact exceeds the platform limit")
    target = state / "x-content" / "elevenagents-en-1.txt"
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text + "\n")
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)
    return {
        "artifact_id": "elevenagents-x-en-1",
        "placement": "elevenagents-en-1",
        "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "state": "READY_FOR_X_PUBLICATION",
    }


def build_x_tts_api(state):
    publication_path = state / "owned-publications" / f"{TTS_API_SLUG}.json"
    try:
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ContentError("live owned publication receipt is unavailable") from error
    url = f"https://aniccaai.com/blog/{TTS_API_SLUG}"
    if publication.get("state") != "LIVE" or publication.get("public_url") != url:
        raise ContentError("owned article is not live")
    text = (
        "Building with a TTS API? Benchmark secret handling, character costs, repeatability, "
        "and real end-to-end latency before paying.\n\n"
        "Affiliate link disclosed in my developer checklist:\n"
        f"{url}"
    )
    if len(text) > 280:
        raise ContentError("X artifact exceeds the platform limit")
    target = state / "x-content" / "elevenlabs-tts-api-en-1.txt"
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text + "\n")
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)
    return {
        "artifact_id": "elevenlabs-tts-api-x-en-1",
        "placement": "elevenlabs-tts-api-en-1",
        "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "state": "READY_FOR_X_PUBLICATION",
    }


def main():
    parser = argparse.ArgumentParser(prog="affiliate content")
    parser.add_argument("command", choices=("build", "build-agents", "build-tts-api", "build-foundation", "build-x", "build-x-agents", "build-x-tts-api", "policy", "policy-agents", "policy-tts-api"))
    parser.add_argument("--state", type=Path, default=Path("~/.local/state/life-manager/affiliate"))
    parser.add_argument("--private-markdown", type=Path, default=Path("~/.config/anicca/affiliate-credentials.md"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.command == "build-x":
        result = build_x(args.state.expanduser())
    elif args.command == "build-x-agents":
        result = build_x_agents(args.state.expanduser())
    elif args.command == "build-x-tts-api":
        result = build_x_tts_api(args.state.expanduser())
    elif args.command == "policy":
        result = policy(args.state.expanduser(), args.private_markdown.expanduser())
    elif args.command == "policy-agents":
        result = policy_agents(args.state.expanduser(), args.private_markdown.expanduser())
    elif args.command == "policy-tts-api":
        result = policy_tts_api(args.state.expanduser(), args.private_markdown.expanduser())
    elif args.command == "build-foundation":
        result = build_foundation(root, args.state.expanduser())
    elif args.command == "build-agents":
        result = build_agents(root, args.state.expanduser(), args.private_markdown.expanduser())
    elif args.command == "build-tts-api":
        result = build_tts_api(root, args.state.expanduser(), args.private_markdown.expanduser())
    else:
        result = build(root, args.state.expanduser(), args.private_markdown.expanduser())
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContentError, OSError, ValueError, KeyError):
        print("affiliate content: failed closed", file=sys.stderr)
        raise SystemExit(1)
