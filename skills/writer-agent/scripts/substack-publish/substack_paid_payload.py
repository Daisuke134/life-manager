#!/usr/bin/env python3
"""Build the Writer loop's Substack ProseMirror payload for the publication's audience.

The audience follows the publication's live ``payments_state``: ``enabled`` builds
an ``only_paid`` post with one useful free preview before a single paywall node;
any other state builds a free ``everyone`` post with no paywall, whose closing CTA
(the publisher copy's lineage link) is readable by every visitor.  An unreadable
``payments_state`` is a blocker, never a guess.

The node shapes are a stdlib copy+tweak of python-substack 0.1.20's MIT-
licensed ``substack.post.Post`` output.  The paywall node follows the
Substack editor schema documented by printing-press-library's Apache-2.0
ProseMirror converter.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


_PAYWALL_LINE = re.compile(r"(?m)^\s*(?:\[paywall\]|\{\{paywall\}\})\s*$")
_IMAGE_LINE = re.compile(r"^!\[([^\]]*)\]\((https://[^)]+)\)$")
_LINK = re.compile(r"\[([^\]]+)\]\((https://[^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_CODE = re.compile(r"`([^`]+)`")
_PRELOADS = re.compile(
    r'<script[^>]*\bid="preloads-json"[^>]*>(.*?)</script>', re.DOTALL
)
AUDIENCES = ("only_paid", "everyone")
_AUDIENCE_BY_PAYMENTS_STATE = {"enabled": "only_paid", "disabled": "everyone"}


def audience_for_payments_state(state: object) -> str:
    """Map Substack's ``payments_state`` to the only audience it can sell to."""

    # Fail closed: an unknown Stripe state (paused, restricted, ...) on a paid publication
    # must block, never silently publish paid writing for free.
    audience = _AUDIENCE_BY_PAYMENTS_STATE.get(state) if isinstance(state, str) else None
    if audience is None:
        raise ValueError(f"Substack payments_state is unreadable or unknown: {state!r}")
    return audience


def payments_state_from_html(page: str, publication: str) -> str:
    """Read ``pub.payments_state`` from a public page of exactly this publication."""

    match = _PRELOADS.search(page)
    if match is None:
        raise ValueError("Substack preloads JSON is missing")
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise ValueError("Substack preloads JSON is malformed") from error
    pub = data.get("pub") if isinstance(data, dict) else None
    subdomain = publication.strip().lower().removesuffix(".substack.com")
    if not isinstance(pub, dict) or str(pub.get("subdomain", "")).lower() != subdomain:
        raise ValueError("Substack page does not belong to the publication")
    state = pub.get("payments_state")
    if not isinstance(state, str) or not state:
        raise ValueError("Substack payments_state is unreadable")
    return state


def read_publication_audience(publication: str) -> str:
    """Anonymous GET of the publication homepage -> the audience it allows."""

    from substack_http import text_request  # same-directory transport

    page, _ = text_request(
        f"https://{publication}/", {"User-Agent": "Mozilla/5.0"}
    )
    return audience_for_payments_state(
        payments_state_from_html(page, publication)
    )


def _text(value: str, marks: list[dict[str, Any]] | None = None) -> dict:
    node: dict[str, Any] = {"type": "text", "text": value}
    if marks:
        node["marks"] = marks
    return node


def _inline(value: str) -> list[dict[str, Any]]:
    matches: list[tuple[int, int, str, str, str | None]] = []
    for kind, pattern in (("code", _CODE), ("link", _LINK), ("bold", _BOLD)):
        for match in pattern.finditer(value):
            if any(start <= match.start() < end for start, end, *_ in matches):
                continue
            target = match.group(2) if kind == "link" else None
            matches.append(
                (match.start(), match.end(), kind, match.group(1), target)
            )
    matches.sort(key=lambda item: item[0])
    nodes: list[dict[str, Any]] = []
    position = 0
    for start, end, kind, content, target in matches:
        if start > position:
            nodes.append(_text(value[position:start]))
        if kind == "code":
            nodes.append(_text(content, [{"type": "code"}]))
        elif kind == "bold":
            nodes.append(_text(content, [{"type": "strong"}]))
        else:
            nodes.append(
                _text(
                    content,
                    [{"type": "link", "attrs": {"href": target}}],
                )
            )
        position = end
    if position < len(value):
        nodes.append(_text(value[position:]))
    return [node for node in nodes if node["text"]]


def _paragraph(lines: list[str]) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        content.extend(_inline(line))
        if index < len(lines) - 1:
            content.append({"type": "hardBreak"})
    return {"type": "paragraph", "content": content}


def _list_node(kind: str, rows: list[str]) -> dict[str, Any]:
    return {
        "type": kind,
        "content": [
            {
                "type": "list_item",
                "content": [
                    {"type": "paragraph", "content": _inline(row)}
                ],
            }
            for row in rows
        ],
    }


def _image_node(alt: str, source: str) -> dict[str, Any]:
    return {
        "type": "captionedImage",
        "content": [
            {
                "type": "image2",
                "attrs": {
                    "src": source,
                    "fullscreen": False,
                    "imageSize": "normal",
                    "height": 819,
                    "width": 1456,
                    # Keep portrait provider images below verify-preview's 950px
                    # height gate without changing the immutable asset bytes.
                    "resizeWidth": 600,
                    "bytes": None,
                    "alt": alt or None,
                    "title": None,
                    "type": None,
                    "href": None,
                    "belowTheFold": False,
                    "internalRedirect": None,
                },
            }
        ],
    }


def _markdown_nodes(markdown: str) -> list[dict[str, Any]]:
    lines = markdown.splitlines()
    nodes: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("```"):
            language = stripped[3:].strip()
            code: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(
                "```"
            ):
                code.append(lines[index])
                index += 1
            if index >= len(lines):
                raise ValueError("unclosed fenced code block")
            node: dict[str, Any] = {
                "type": "codeBlock",
                "content": [_text("\n".join(code))],
            }
            if language:
                node["attrs"] = {"language": language}
            nodes.append(node)
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            nodes.append(
                {
                    "type": "heading",
                    "attrs": {"level": len(heading.group(1))},
                    "content": _inline(heading.group(2)),
                }
            )
            index += 1
            continue
        image = _IMAGE_LINE.fullmatch(stripped)
        if image:
            nodes.append(_image_node(image.group(1), image.group(2)))
            index += 1
            continue
        if re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", stripped):
            nodes.append({"type": "horizontal_rule"})
            index += 1
            continue
        if stripped.startswith(("- ", "* ")):
            rows: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(
                ("- ", "* ")
            ):
                rows.append(lines[index].strip()[2:].strip())
                index += 1
            nodes.append(_list_node("bullet_list", rows))
            continue
        if re.match(r"^\d+\.\s+", stripped):
            rows = []
            while index < len(lines):
                ordered = re.match(r"^\d+\.\s+(.+)$", lines[index].strip())
                if ordered is None:
                    break
                rows.append(ordered.group(1))
                index += 1
            nodes.append(_list_node("ordered_list", rows))
            continue
        if stripped.startswith(">"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                rows.append(lines[index].strip().lstrip(">").strip())
                index += 1
            nodes.append(
                {
                    "type": "blockquote",
                    "content": [_paragraph(rows)],
                }
            )
            continue

        paragraph = [lines[index].strip()]
        index += 1
        while index < len(lines) and lines[index].strip():
            candidate = lines[index].strip()
            if (
                candidate.startswith(("```", "#", "- ", "* ", ">"))
                or _IMAGE_LINE.fullmatch(candidate)
                or re.match(r"^\d+\.\s+", candidate)
            ):
                break
            paragraph.append(candidate)
            index += 1
        nodes.append(_paragraph(paragraph))
    return nodes


def _visible_chars(node: Any) -> int:
    if isinstance(node, dict):
        own = len(node.get("text", "")) if isinstance(node.get("text"), str) else 0
        return own + sum(_visible_chars(value) for value in node.values())
    if isinstance(node, list):
        return sum(_visible_chars(value) for value in node)
    return 0


def build_paid_draft_payload(
    *,
    title: str,
    subtitle: str,
    markdown: str,
    byline_id: int,
    audience: str,
    after_chars: int = 1200,
    minimum_free_chars: int = 1000,
) -> dict[str, Any]:
    """Return one payload: ``only_paid`` with a single paywall, or free ``everyone``."""

    if audience not in AUDIENCES:
        raise ValueError(f"unsupported Substack audience: {audience!r}")
    if not title.strip() or byline_id <= 0:
        raise ValueError("title and positive byline_id are required")
    if _PAYWALL_LINE.search(markdown):
        raise ValueError("source already contains a paywall")
    nodes = _markdown_nodes(markdown)
    if len(nodes) < 2:
        raise ValueError("paid article requires multiple content blocks")

    paid = audience == "only_paid"
    if paid:
        free_chars = 0
        paywall_index: int | None = None
        for index, node in enumerate(nodes[:-1]):
            free_chars += _visible_chars(node)
            if free_chars >= after_chars:
                paywall_index = index + 1
                break
        if paywall_index is None or free_chars < minimum_free_chars:
            raise ValueError("free preview is shorter than money contract")
        nodes.insert(paywall_index, {"type": "paywall"})
    body = {"type": "doc", "content": nodes}
    return {
        "draft_title": title,
        "draft_subtitle": subtitle,
        "draft_body": json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "draft_bylines": [{"id": int(byline_id), "is_guest": False}],
        "type": "newsletter",
        "audience": audience,
        "draft_section_id": None,
        "section_chosen": True,
        "write_comment_permissions": audience,
        "should_send_email": False,
        "should_send_free_preview": paid,
    }


def verify_paid_draft_response(response: dict[str, Any], audience: str) -> int:
    """Verify authenticated readback still carries the expected audience contract."""

    if audience not in AUDIENCES:
        raise ValueError(f"unsupported Substack audience: {audience!r}")
    if response.get("audience") != audience:
        raise ValueError(f"authenticated draft audience is not {audience}")
    paid = audience == "only_paid"
    if paid and response.get("should_send_free_preview") is not True:
        raise ValueError("authenticated draft free preview is not enabled")
    body_value = response.get("draft_body")
    try:
        body = (
            json.loads(body_value)
            if isinstance(body_value, str)
            else body_value
        )
    except json.JSONDecodeError as error:
        raise ValueError("authenticated draft body is not valid JSON") from error

    def count_paywalls(value: Any) -> int:
        if isinstance(value, dict):
            return int(value.get("type") == "paywall") + sum(
                count_paywalls(child) for child in value.values()
            )
        if isinstance(value, list):
            return sum(count_paywalls(child) for child in value)
        return 0

    expected_paywalls = 1 if paid else 0
    if count_paywalls(body) != expected_paywalls:
        raise ValueError(
            f"authenticated draft must contain exactly {expected_paywalls} paywall"
        )
    draft_id = response.get("id")
    if not isinstance(draft_id, int) or draft_id <= 0:
        raise ValueError("authenticated draft id is missing")
    return draft_id


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the Writer loop's Substack draft payload for one audience."
    )
    parser.add_argument("--verify-response", action="store_true")
    parser.add_argument(
        "--read-audience",
        action="store_true",
        help="print the audience the live --publication payments_state allows",
    )
    parser.add_argument("--publication")
    parser.add_argument("--audience", choices=AUDIENCES)
    parser.add_argument("--title")
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--byline-id", type=int)
    parser.add_argument("--after-chars", type=int, default=1200)
    parser.add_argument("--minimum-free-chars", type=int, default=1000)
    args = parser.parse_args()
    try:
        if args.read_audience:
            if not args.publication:
                raise ValueError("--publication is required with --read-audience")
            print(read_publication_audience(args.publication))
            return 0
        if not args.audience:
            raise ValueError(
                "--audience is required; read it with --read-audience first"
            )
        if args.verify_response:
            response = json.load(sys.stdin)
            print(verify_paid_draft_response(response, args.audience))
            return 0
        if not args.title or args.byline_id is None:
            raise ValueError(
                "--title and --byline-id are required when building a payload"
            )
        payload = build_paid_draft_payload(
            title=args.title,
            subtitle=args.subtitle,
            markdown=sys.stdin.read(),
            byline_id=args.byline_id,
            audience=args.audience,
            after_chars=args.after_chars,
            minimum_free_chars=args.minimum_free_chars,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
