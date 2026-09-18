#!/usr/bin/env python3
"""Restore the paid contract on one persisted, unpublished Substack ID."""
import argparse, importlib.util, json, os, subprocess, sys
from pathlib import Path
from urllib.parse import urlparse

P=Path(__file__).with_name("substack_inplace_repair.py")
S=importlib.util.spec_from_file_location("substack_repair",P); m=importlib.util.module_from_spec(S); S.loader.exec_module(m)

def _publication_host(value):
    if isinstance(value, dict):
        for key in ("subdomain", "host", "domain", "url"):
            host = _publication_host(value.get(key))
            if host:
                return host
        return ""
    if not isinstance(value, str):
        return ""
    value=value.strip().lower()
    if not value:
        return ""
    if "://" in value:
        value=urlparse(value).hostname or ""
    value=value.rstrip("/")
    if value and "." not in value:
        value=f"{value}.substack.com"
    return value if value.endswith(".substack.com") else ""


def _publication_for_pair(pair):
    """Resolve the publication host from the pair, never from the JA default."""
    if pair not in {"substack/ja", "substack/en"}:
        return ""
    lang = pair.rsplit("/", 1)[1].upper()
    specific = _publication_host(
        os.environ.get(f"SUBSTACK_PUBLICATION_{lang}", "")
    )
    if specific:
        return specific
    # The generic variable predates separate JA/EN publications and is safe
    # only for JA. EN must never silently target the JA publication.
    return (
        _publication_host(os.environ.get("SUBSTACK_PUBLICATION", ""))
        if lang == "JA"
        else ""
    )

def _draft_publication_host(draft):
    for key in ("publication", "draft_publication", "publication_host", "publication_subdomain", "subdomain"):
        host=_publication_host(draft.get(key))
        if host:
            return host
    return ""

def _authenticated_draft_publication_host(draft):
    direct = _draft_publication_host(draft)
    if direct:
        return direct
    publication_id = draft.get("publication_id")
    if not str(publication_id).isdigit():
        return ""
    try:
        profile = m._request("GET", "/api/v1/publication")
    except (OSError, ValueError, m.SubstackRepairRefused):
        return ""
    if not isinstance(profile, dict) or str(profile.get("id")) != str(publication_id):
        return ""
    return _publication_host(profile)


def _owned_byline_ids(draft):
    def parse(value, key, label):
        if value is None:
            return None
        if not isinstance(value, list):
            raise m.SubstackRepairRefused(f"{label} readback shape is invalid")
        ids=set()
        for item in value:
            if not isinstance(item, dict) or not str(item.get(key, "")).isdigit():
                raise m.SubstackRepairRefused(f"{label} contains an unidentified byline")
            ids.add(int(item[key]))
        return ids or None

    draft_ids=parse(draft.get("draft_bylines"), "id", "draft_bylines")
    post_ids=parse(draft.get("postBylines"), "user_id", "postBylines")
    if draft_ids and post_ids and draft_ids != post_ids:
        raise m.SubstackRepairRefused("Substack byline readbacks disagree")
    return draft_ids or post_ids or set()


def _build_embedded_markdown(state, lang):
    """Rebuild same-draft media so cached tall Mermaid URLs cannot survive a refresh."""
    descriptor = state.get("drafts", {}).get(lang, {})
    source = Path(str(descriptor.get("path", "")))
    media = state.get("media", {})
    headline = media.get("headline_image", {})
    bodies = media.get("body_assets", [])
    if not source.is_file() or not headline.get("path") or not bodies:
        raise m.SubstackRepairRefused("immutable Substack media inputs are incomplete")
    run_dir = Path(str(state.get("run_dir", "")))
    out = run_dir / "gates" / "substack-refresh" / f"article-{lang}-embedded.md"
    command = [
        sys.executable,
        str(Path(__file__).parents[1] / "_shared" / "embed-mermaid-substack.py"),
        "--markdown-file", str(source),
        "--out", str(out),
        "--headline-image", str(headline["path"]),
    ]
    for body in bodies:
        command.extend(("--body-image", str(body["path"])))
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not out.is_file():
        raise m.SubstackRepairRefused("same-ID media rebuild failed")
    return out.read_text(encoding="utf-8")

def refresh(pair):
    state=m._state(); entry=state["pairs"][pair]; target=str(entry.get("target",""))
    if entry.get("status")!="intent" or not target.isdigit(): raise m.SubstackRepairRefused("persisted intent missing")
    old=m._request("GET",f"/api/v1/drafts/{target}")
    if not isinstance(old, dict) or str(old.get("id", "")) != target:
        raise m.SubstackRepairRefused("draft identity readback missing")
    # Refresh uploads media and PUTs the same draft ID.  The managed publisher
    # may call this before its live-publish guard, so the readback here is an
    # independent no-mutation boundary: a missing receipt must never turn an
    # already-live (or ambiguous) draft into an overwrite target.
    if old.get("is_published") is not False or old.get("post_date"):
        raise m.SubstackRepairRefused(
            "exact Substack draft is live or ambiguous; refresh refused"
        )
    draft_publication=_authenticated_draft_publication_host(old)
    if not draft_publication:
        raise m.SubstackRepairRefused("draft publication identity readback missing")
    if draft_publication != m._publication():
        raise m.SubstackRepairRefused("draft publication identity does not match configured publication")
    title=str(old.get("draft_title") or old.get("title") or "").strip()
    byline_ids=_owned_byline_ids(old)
    if not byline_ids:
        raise m.SubstackRepairRefused("draft byline identity readback missing")
    if not title or byline_ids!={m._identity()}: raise m.SubstackRepairRefused("owned title/byline missing")
    media=state["media"]; headline=media["headline_image"]; bodies=media["body_assets"]
    for x in [headline,*bodies]:
        p=Path(x["path"])
        if not p.is_file() or m.sha256(p)!=x["sha256"]: raise m.SubstackRepairRefused("immutable media changed")
    embedded_markdown = _build_embedded_markdown(state, pair.split("/", 1)[1])
    payload=m._paid_payload_builder()(title=title,subtitle=str(old.get("draft_subtitle") or old.get("subtitle") or ""),markdown=embedded_markdown,byline_id=m._identity())
    updated=m._request("PUT",f"/api/v1/drafts/{target}",payload=payload)
    if str(updated.get("id",""))!=target: raise m.SubstackRepairRefused("same-ID refresh failed")
    return {"pair":pair,"target":target,"refreshed":True}
def main():
    p=argparse.ArgumentParser();p.add_argument("--pair",required=True,choices=("substack/ja","substack/en"));a=p.parse_args()
    publication = _publication_for_pair(a.pair)
    if not publication:
        raise SystemExit(f"SUBSTACK publication host is required for {a.pair}")
    os.environ["SUBSTACK_PUBLICATION"] = publication
    lang=a.pair.rsplit("/", 1)[1]
    cookie=os.environ.get(f"SUBSTACK_SESSION_COOKIE_{lang.upper()}", "").strip()
    if not cookie and lang == "ja":
        cookie=os.environ.get("SUBSTACK_SESSION_COOKIE", "").strip()
    if not cookie:
        raise SystemExit(f"SUBSTACK_SESSION_COOKIE_{lang.upper()} is required for managed Substack publication")
    os.environ["SUBSTACK_SESSION_COOKIE"] = cookie
    print(json.dumps(refresh(a.pair),separators=(",",":")));return 0
if __name__=="__main__": raise SystemExit(main())
