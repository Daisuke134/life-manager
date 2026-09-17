"""Pure money-safety cap logic for the claude-p -> Franklin funding pipeline. No I/O, no
network -- every function here takes plain data in and returns plain data out, so it is fully
unit-testable (see tests/test_caps.py).

Source of the rails this encodes: the repository funding design record §3
("MUST per-transfer cap / daily cap / cumulative cap ... 超えたら halt", "MUST reserve 保護").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class CapDecision:
    allowed: bool
    reason: str
    amount_usd: float


# Status precedence for dedup-by-tx_hash below: higher wins. 'pending' = broadcast happened,
# confirmation not yet resolved (may already have moved real money -- see Finding A). 'sent' =
# on-chain confirmed (status 0x1). Anything else ('failed'/'skipped'/'dry') never moved money
# and is excluded entirely.
_SPEND_STATUS_PRIORITY = {"pending": 1, "sent": 2}


def _outflow_rows(history: Iterable[Mapping]) -> list[Mapping]:
    """Rows that represent REAL (or possibly-real) capital leaving claude-p's own Polymarket
    capital base, counted exactly once per broadcast tx.

    Two adversary-review findings (money-safety review, 2026-07-08) are encoded here:

    Finding C (cap over-consumption): `run.py` chains three hops -- withdraw (deposit wallet
    -> owner EOA), bridge (owner EOA -> founder Solana wallet), send_to_franklin (founder
    Solana wallet -> Franklin) -- for ONE logical "$X funded to Franklin" decision. An earlier
    version of this function summed 'sent' rows across all three steps from the shared ledger,
    so one $X seed consumed ~3x $X of cap headroom. The withdraw hop is the ONE point where
    money actually leaves claude-p's capital base (the 0x904B... deposit wallet); bridge and
    send_to_franklin only move that SAME already-withdrawn money onward across claude-p's/
    Franklin's own custody chain (0x810f -> BF9v -> Franklin), so they are not a second or
    third real outflow from claude-p capital. Filtering to `step == "withdraw"` is the
    simplest fix that makes the cap match its documented meaning ("actual outflow from
    claude-p capital, once per seed") without weakening protection: all three scripts share
    this same function and the same ledger file, so bridge.py/send_to_franklin.py's own
    `check_caps` calls see the identical withdraw-only total as withdraw.py's.

    Finding A (crash-before-confirm): a tx that was broadcast but crashed before its
    confirmation could be recorded may already have moved real money, so a 'pending' row
    (written immediately after broadcast, before waiting for confirmation) must still consume
    cap headroom -- otherwise a subsequent run would not see money that already moved and
    could permit a further real transfer that, combined with the untracked one, exceeds the
    intended caps. When the same tx_hash later gets a terminal 'sent' row (confirmation
    succeeded), only the single most-terminal row for that tx_hash is counted, so one real
    transfer is never double-counted. Rows with no tx_hash (e.g. legacy rows, or any future
    status-only bookkeeping) are each counted individually, matching the original behavior.
    """
    candidates = [
        r
        for r in history
        if r.get("step") == "withdraw"
        and r.get("status") in _SPEND_STATUS_PRIORITY
        # `--include-pusd` broadcasts TWO txs for one logical withdraw: an internal
        # pUSD->USDC.e unwrap (phase="unwrap", stays inside the deposit wallet, NOT an
        # outflow of claude-p capital) then the real transfer to the owner EOA
        # (phase="transfer"/absent). Only the transfer moves money out, so exclude the
        # unwrap phase — otherwise one $X seed is counted as $2X (money-safety cap bug).
        and r.get("phase") != "unwrap"
    ]
    best_by_hash: dict = {}
    untracked: list[Mapping] = []
    for r in candidates:
        tx_hash = r.get("tx_hash")
        if not tx_hash:
            untracked.append(r)
            continue
        prev = best_by_hash.get(tx_hash)
        if prev is None or _SPEND_STATUS_PRIORITY[r["status"]] > _SPEND_STATUS_PRIORITY[prev["status"]]:
            best_by_hash[tx_hash] = r
    return untracked + list(best_by_hash.values())


def check_caps(
    *,
    amount_usd: float,
    history: Sequence[Mapping],
    config: Mapping,
    now_ts: float,
    counts_as_outflow: bool = True,
) -> CapDecision:
    """Evaluate `amount_usd` against per-transfer / daily / cumulative caps in `config`.

    `history` is the parsed funding-ledger.jsonl (list of row dicts with at least
    `ts` (epoch seconds), `amount_usd`, `status`). `config` has `per_transfer_usd_cap`,
    `daily_usd_cap`, `cumulative_usd_cap` (any of these may be None/absent to mean "no cap").

    `counts_as_outflow`: True only for the WITHDRAW step, the single point where money
    leaves claude-p's capital. Bridge/send move that ALREADY-withdrawn (already-counted)
    money downstream, so they pass `False`: their amount is NOT re-added to the daily/
    cumulative running total (otherwise one $X seed would burn 2-3x the cap). The
    per-transfer ceiling is still enforced for every step as a defense-in-depth bound.
    """
    if not isinstance(amount_usd, (int, float)) or isinstance(amount_usd, bool) or amount_usd <= 0:
        return CapDecision(False, "amount_usd must be a positive number", amount_usd)

    per_cap = config.get("per_transfer_usd_cap")
    if per_cap is not None and amount_usd > per_cap:
        return CapDecision(
            False, f"amount ${amount_usd} exceeds per-transfer cap ${per_cap}", amount_usd
        )

    outflow = _outflow_rows(history)

    day_ago = now_ts - 86400
    daily_spent = sum(
        float(r.get("amount_usd", 0)) for r in outflow if float(r.get("ts", 0)) >= day_ago
    )
    daily_cap = config.get("daily_usd_cap")
    if daily_cap is not None and daily_spent + (amount_usd if counts_as_outflow else 0.0) > daily_cap:
        return CapDecision(
            False,
            f"amount ${amount_usd} would exceed daily cap ${daily_cap} "
            f"(already spent ${daily_spent} in the last 24h)",
            amount_usd,
        )

    cumulative_spent = sum(float(r.get("amount_usd", 0)) for r in outflow)
    cumulative_cap = config.get("cumulative_usd_cap")
    if cumulative_cap is not None and cumulative_spent + (amount_usd if counts_as_outflow else 0.0) > cumulative_cap:
        return CapDecision(
            False,
            f"amount ${amount_usd} would exceed cumulative cap ${cumulative_cap} "
            f"(already spent ${cumulative_spent} total)",
            amount_usd,
        )

    return CapDecision(True, "within all caps", amount_usd)


def reserve_protected_amount(*, available_usd: float, reserve_usd: float) -> float:
    """How much of `available_usd` may safely be moved while never dipping the source below
    `reserve_usd` (pm-earner's own working capital). Fails closed to 0.0, never negative."""
    if not isinstance(available_usd, (int, float)) or isinstance(available_usd, bool):
        return 0.0
    if not isinstance(reserve_usd, (int, float)) or isinstance(reserve_usd, bool):
        reserve_usd = 0.0
    return max(0.0, available_usd - reserve_usd)
