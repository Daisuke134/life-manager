#!/usr/bin/env python3
"""Deterministic pre-submit capability, contract-shape, and role checks."""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any


# Both marketplace contract shapes share the same Apply -> Reply -> Paid lifecycle.
# A retainer is not a policy exemption: the ordinary synchronous-presence and
# role checks below still reject a listing whose required deliverable needs a human.
APPLICABLE_BUCKETS: frozenset[str] = frozenset({"single", "retainer"})
REFUSED_BUCKETS: frozenset[str] = frozenset()
BUCKET_UNRECOGNIZED = "application_bucket_unrecognized"


# A5-③ (2026-07-31). Measured over the 37 closed 単発 jobs this loop applied to:
# 14 had someone hired (median 発注率 61%), 23 had 契約人数 0 (median 発注率 7%).
# So 62% of the losses were not lost to a rival -- the client hired nobody, and the
# bandit was being fed a reward of zero for an event that never had a winner.
# Filtering on 発注率 > 40 moves P(anyone is hired at all) from 0.14 [0.04, 0.33] to
# 0.69 [0.44, 0.87]: Fisher exact OR=13.2, p=0.0016. No model, no bandit, no
# exploration. Production evidence later showed that the hard gate also excludes
# every new client (Coconala renders no history as 0%) and can close the money entrance.
# Keep the measurement as a ranking signal, but never confuse commercial preference
# with an inability to fulfill digital work. Capability and evidence failures remain
# fail-closed in this single gate.
#
# 40 is where n=37 puts the knee, not a law. The env var exists so the next 37 closed
# jobs can move it without a code change; a value that does not parse falls back to
# the measured default rather than to "no gate".
MIN_CLIENT_ORDER_RATE_ENV = "GIG_MIN_CLIENT_ORDER_RATE"
DEFAULT_MIN_CLIENT_ORDER_RATE = 40.0
CLIENT_ORDER_RATE_BELOW_THRESHOLD = "client_order_rate_below_threshold"
CLIENT_ORDER_RATE_MISSING = "client_order_rate_missing"
MARKET_SNAPSHOT_MISSING = "market_snapshot_missing"


def min_client_order_rate() -> float:
    """The ranking threshold, read per call so a running loop can be retuned."""
    try:
        return float(os.environ.get(MIN_CLIENT_ORDER_RATE_ENV, "").strip())
    except ValueError:
        return DEFAULT_MIN_CLIENT_ORDER_RATE


SYNCHRONOUS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "video_meeting",
        re.compile(
            r"(?:Google\s*Meet|Zoom|Microsoft\s*Teams|Webex|"
            r"ビデオ(?:通話|会議|面談)|オンライン(?:面談|ヒアリング|面接)|"
            r"Web(?:面談|会議|面接))",
            re.IGNORECASE,
        ),
    ),
    (
        "scheduled_interview",
        re.compile(
            r"(?:クライアント|採用|オンライン)?面談.{0,45}"
            r"(?:日時|日程|時刻|対応(?:は)?可能|ご対応|候補日)|"
            r"(?:日時|日程|時刻|候補日).{0,45}(?:面談|面接|ヒアリング)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "live_participation",
        re.compile(
            r"(?:オンライン)?(?:ヒアリング|インタビュー|面接).{0,35}"
            r"(?:参加|ご協力|お話|実施)|"
            r"(?:参加|ご協力).{0,35}(?:ヒアリング|インタビュー|面接)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "phone_or_voice",
        re.compile(
            r"(?:電話|通話|音声通話|本人音声|音声収録|ナレーション収録)",
            re.IGNORECASE,
        ),
    ),
    (
        "live_or_face",
        re.compile(
            r"(?:ライブ講義|生配信への出演|顔出し|顔を出して|対面(?:作業|面談|打合せ|打ち合わせ))",
            re.IGNORECASE,
        ),
    ),
)

PARTICIPANT_BUYER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:ヒアリング|インタビュー|アンケート|モニター)"
        r".{0,40}(?:ご協力|参加|回答(?:して|いただ|ください)|お話を伺)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(?:ご協力|参加|回答(?:して|いただ|ください)).{0,40}"
        r"(?:ヒアリング|インタビュー|アンケート|モニター)",
        re.IGNORECASE | re.DOTALL,
    ),
)

SERVICE_PROVIDER_PROPOSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:支援|サポート).{0,20}(?:提案|提供|いたします|します)"),
    re.compile(r"(?:納品|お渡し|作成|制作|構築|改善案)"),
)

ASYNCHRONOUS_NEGATION = re.compile(
    r"(?:チャット|トークルーム|テキスト).{0,25}"
    r"(?:非同期|隙間時間|完結)|"
    r"(?:非同期|隙間時間).{0,25}(?:チャット|テキスト)",
    re.IGNORECASE | re.DOTALL,
)

SYNC_SIGNAL_WORD = re.compile(
    r"(?:Google\s*Meet|Zoom|Microsoft\s*Teams|Webex|電話|通話|"
    r"面談|面接|ヒアリング|インタビュー|ライブ講義|顔出し|対面)",
    re.IGNORECASE,
)

OPTIONAL_OR_ABSENT = re.compile(
    r"(?:ありません|不要|必要(?:は)?ありません|必須ではありません|"
    r"必須ではない|任意|求めません|できなくても(?:可|可能)|歓迎条件)",
    re.IGNORECASE,
)


def _normalize(value: str | None) -> str:
    return unicodedata.normalize("NFKC", value or "").strip()


def _matching_signals(
    text: str,
    patterns: tuple[tuple[str, re.Pattern[str]], ...],
) -> list[str]:
    return [name for name, pattern in patterns if pattern.search(text)]


def _required_synchronous_text(text: str) -> str:
    segments = re.split(r"(?<=[。\n！？])|(?=ただし|一方で)", text)
    return "\n".join(
        segment
        for segment in segments
        if not (
            SYNC_SIGNAL_WORD.search(segment)
            and OPTIONAL_OR_ABSENT.search(segment)
        )
    )


def _client_order_rate_codes(
    market: dict[str, Any] | None,
    threshold: float,
) -> tuple[list[str], list[str], float | None]:
    """Separate observation failures from a commercial ranking signal.

    FAIL-CLOSED on a missing rate, and the reason is in the data rather than in
    caution: Coconala prints a client who has never ordered as `0%`, not as nothing
    (observed on tyogvii, Mooty, kiki_1115, pdnob_jp). "No history" is therefore
    already representable. A page with NO stat card
    at all is a page we failed to read -- and every such card in this loop's logs
    (34 of 310 complete ones) is the two-name 会社名+担当者名 card that belongs to
    the 継続 side A3 already refuses. So fail-closed costs approximately zero real
    単発 opportunities, while fail-open would silently restore the pre-A5 loop the
    first time a selector drifts, and leave no way to tell that it had.
    """
    if market is None:
        return [MARKET_SNAPSHOT_MISSING], [], None
    raw = market.get("client_order_rate")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return [CLIENT_ORDER_RATE_MISSING], [], None
    rate = float(raw)
    if rate <= threshold:
        return [], [CLIENT_ORDER_RATE_BELOW_THRESHOLD], rate
    return [], [], rate


def evaluate_application(
    brief_text: str,
    proposal_text: str,
    *,
    form_text: str = "",
    bucket: str = "single",
    market: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a stable fail-closed verdict for explicit unsupported work.

    `market` is keyword-only and has NO default on purpose. A default would mean the
    market gate could be bypassed by writing less code, and writing less code is
    exactly how `bid_jpy` came to be on 0 of 311 ledger rows. A caller that forgets
    it gets a TypeError before the browser is ever connected; a caller that has
    nothing to pass says so with an explicit None and is refused.
    """
    bucket = str(bucket or "").strip()
    brief = _normalize(brief_text)
    proposal = _normalize(proposal_text)
    form = _normalize(form_text)
    combined = "\n".join(part for part in (brief, form) if part)

    synchronous_signals = _matching_signals(
        _required_synchronous_text(combined),
        SYNCHRONOUS_PATTERNS,
    )
    buyer_expects_participant = any(
        pattern.search(brief) for pattern in PARTICIPANT_BUYER_PATTERNS
    )
    proposal_sells_service = any(
        pattern.search(proposal)
        for pattern in SERVICE_PROVIDER_PROPOSAL_PATTERNS
    )

    reason_codes: list[str] = []
    if bucket not in APPLICABLE_BUCKETS:
        reason_codes.append(BUCKET_UNRECOGNIZED)
    if synchronous_signals:
        reason_codes.append("synchronous_live_presence_required")
    if buyer_expects_participant and proposal_sells_service:
        reason_codes.append(
            "buyer_participant_seller_provider_role_mismatch"
        )
    threshold = min_client_order_rate()
    if bucket == "retainer":
        # Coconala Assist listings do not render the single-request client order-rate
        # card. Its absence is the official retainer shape, not a failed observation.
        market_codes, ranking_codes, client_order_rate = [], [], None
    else:
        market_codes, ranking_codes, client_order_rate = _client_order_rate_codes(
            market, threshold
        )
    reason_codes.extend(market_codes)

    return {
        "version": 1,
        "allowed": not reason_codes,
        "reason_codes": reason_codes,
        "ranking_codes": ranking_codes,
        "signals": {
            "bucket": bucket,
            "client_order_rate": client_order_rate,
            "min_client_order_rate": threshold,
            "synchronous": synchronous_signals,
            "buyer_expects_participant": buyer_expects_participant,
            "proposal_sells_service": proposal_sells_service,
            "asynchronous_text_explicit": (
                ASYNCHRONOUS_NEGATION.search(combined) is not None
            ),
        },
    }
