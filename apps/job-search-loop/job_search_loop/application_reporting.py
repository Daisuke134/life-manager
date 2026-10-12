from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .ledger import Ledger
from .connector_preflight import _application_email
from .browser_agent.contracts import QueueRowReceiptV1
from .browser_agent.outcome_reporting import build_hourly_outcome_message
from .outbox import DeliveryUncertain
from .telegram import is_configured as telegram_is_configured
from .telegram import send_daily_report, send_document_once, send_once
from .email_reporting import send_email_once


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_email_reporting_since(
    path: Path,
    *,
    now: datetime | None = None,
) -> str:
    if path.is_symlink():
        raise ValueError("email reporting cursor must not be a symlink")
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            enabled_at = value.get("enabled_at") if isinstance(value, dict) else None
            parsed = datetime.fromisoformat(str(enabled_at).replace("Z", "+00:00"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            raise ValueError("email reporting cursor is invalid") from None
        if value.get("version") != 1 or parsed.tzinfo is None:
            raise ValueError("email reporting cursor is invalid")
        return parsed.astimezone(timezone.utc).isoformat()

    enabled_at = now or datetime.now(timezone.utc)
    if enabled_at.tzinfo is None:
        raise ValueError("email reporting cursor time has no timezone")
    normalized = enabled_at.astimezone(timezone.utc).isoformat()
    _write_private_json(path, {"version": 1, "enabled_at": normalized})
    return normalized


def _received_after_activation(received_at: str, email_since: str) -> bool:
    try:
        receipt_time = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
        activation_time = datetime.fromisoformat(email_since.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return False
    if receipt_time.tzinfo is None or activation_time.tzinfo is None:
        return False
    return receipt_time.astimezone(timezone.utc) >= activation_time.astimezone(timezone.utc)


def _candidate_application_email() -> str:
    profile_path = Path(
        os.environ.get(
            "JOB_SEARCH_PROFILE",
            str(Path.home() / ".config" / "anicca" / "job-search" / "profile.json"),
        )
    ).expanduser()
    return _application_email(profile_path)


def deliver_wake_report(
    *,
    ledger_path: Path,
    outbox_path: Path,
    run_id: str,
    japan_day: str,
    runner_summary_path: Path,
    discovery_path: Path,
    output_path: Path,
    sender: Callable[..., dict[str, str | None]] | None = send_daily_report,
    email_sender: Callable[..., dict[str, str | None]] | None = None,
    email_outbox_path: Path | None = None,
    email_recipient: str | None = None,
) -> dict[str, Any]:
    if email_sender is not None and not all((email_outbox_path, email_recipient)):
        raise ValueError("daily email requires an outbox and recipient")
    summary = _read_object(runner_summary_path)
    discovery = _read_object(discovery_path)
    result: dict[str, Any] = {}
    result_path = Path(str(summary.get("result_path") or ""))
    if result_path.parent == runner_summary_path.parent:
        result = _read_object(result_path)
    semantic = _read_object(runner_summary_path.parent / "semantic-validation.json")
    attempt: dict[str, Any] = {}
    attempts_path = Path(str(summary.get("attempts_path") or ""))
    if attempts_path.parent == runner_summary_path.parent and attempts_path.is_file():
        lines = attempts_path.read_text(encoding="utf-8").splitlines()
        if lines:
            try:
                value = json.loads(lines[-1])
                attempt = value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                pass

    queued = discovery.get("queued_application_ids")
    application_id = str(queued[0]) if isinstance(queued, list) and queued else ""
    company, role = "none", "none"
    ledger = Ledger(ledger_path)
    try:
        row = ledger.connection.execute(
            "SELECT company,title FROM applications WHERE id=?",
            (application_id,),
        ).fetchone()
        if row is not None:
            company, role = str(row["company"]), str(row["title"])
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        metrics = ledger.connection.execute(
            "SELECT COUNT(DISTINCT c.intent_id), COUNT(DISTINCT a.company), COUNT(*), "
            "(SELECT COUNT(DISTINCT application_id) FROM funnel_outcomes "
            "WHERE funnel_stage='interview' AND disposition='positive') "
            "FROM submission_confirmations c JOIN submit_intents i ON i.intent_id=c.intent_id "
            "JOIN applications a ON a.id=i.application_id "
            "WHERE datetime(c.received_at)>=datetime(?)",
            (cutoff,),
        ).fetchone()
    finally:
        ledger.close()
    human_blockers = result.get("human_only_blockers")
    human_blockers = len(human_blockers) if isinstance(human_blockers, list) else int(human_blockers or 0)
    duplicate_effects = max(0, int(result.get("duplicate_effects") or 0))
    submitted = result.get("submitted")
    submitted_count = len(submitted) if isinstance(submitted, list) else 0
    submit_unknown = result.get("submit_unknown")
    submit_unknown_count = len(submit_unknown) if isinstance(submit_unknown, list) else 0
    blocked = result.get("blocked")
    blocked_count = len(blocked) if isinstance(blocked, list) else 0

    semantic_reason = semantic.get("reason") if semantic.get("status") == "failed" else None
    result_status = str(result.get("status") or "")
    partial_reason = (
        result_status if result_status == "blocked_before_queue_complete"
        else "submit_unknown" if submit_unknown_count
        else "row_blocked" if blocked_count
        else None
    )
    outcome = (
        "failed"
        if semantic_reason or result_status == "transport_failed"
        else "partial" if partial_reason
        else "success" if summary.get("status") == "success" else "failed"
    )
    reason = str(
        semantic_reason
        or (result_status if result_status == "transport_failed" else partial_reason)
        or attempt.get("error_class")
        or attempt.get("adapter_error")
        or summary.get("status")
        or discovery.get("status")
        or "unknown"
    )
    if outcome == "success":
        next_action = "continue_next_eligible_workday"
    elif submit_unknown_count:
        next_action = "reconcile_submission_receipts"
    elif reason == "transient_quota":
        next_action = "retry_with_available_provider_capacity"
    elif discovery.get("status") == "no_work":
        next_action = "discover_next_eligible_workday"
    else:
        next_action = "resume_same_row_next_wake"
    checked = len(discovery.get("shortlist") or discovery.get("discovered") or [])
    if outcome == "partial":
        heading = "⚠️ 今回の応募処理は一部未完了です"
        result_text = (
            f"応募完了: {submitted_count}件\n"
            f"送信結果不明: {submit_unknown_count}件\n"
            f"未完了/保留: {blocked_count}件"
        )
    elif outcome == "success" and submitted_count == 0:
        heading = "🔎 今回の処理は完了しましたが、応募完了は0件です"
        result_text = (
            f"送信結果不明: {submit_unknown_count}件\n"
            f"未完了/保留: {blocked_count}件"
        )
    elif outcome == "success" and company != "none":
        heading = "✅ 今回の処理を完了しました"
        result_text = f"会社: {company}\n求人: {role}"
    elif outcome == "success":
        heading = "🔎 新しい応募対象を確認しました"
        result_text = "今回は新しい応募の完了には至りませんでした。"
    else:
        heading = "⚠️ 今回の処理を完了できませんでした"
        result_text = (
            f"会社: {company}\n求人: {role}"
            if company != "none"
            else "応募対象を確定する前に処理が止まりました。"
        )
    next_text = {
        "continue_next_eligible_workday": "次の新しい適合求人の確認を続けます。",
        "reconcile_submission_receipts": "応募結果が不明な求人は再送せず、受領メールとの照合を続けます。",
        "retry_with_available_provider_capacity": "安全な処理を次回の空き時間に再開します。",
        "discover_next_eligible_workday": "登録済みsourceと新しい公式Workday会社の探索を続けます。",
        "resume_same_row_next_wake": "同じ求人の保存済みcheckpointから安全に再開します。",
    }.get(next_action, "30分後に次の安全な処理を続けます。")
    visible_reason = "処理を完了しました。" if outcome == "success" else "次回に安全に再開します。"
    message = (
        "[Job Hunting] 24時間レポート\n\n"
        "直近24時間の実績\n"
        f"応募完了: {metrics[0] or 0}件\n"
        f"新しい会社: {metrics[1] or 0}社\n"
        f"確認メール取得: {metrics[2] or 0}件\n"
        f"面接案内: {metrics[3] or 0}件\n"
        f"人間の対応待ち: {human_blockers}件\n"
        f"重複外部作用: {duplicate_effects}件\n\n"
        "今回の処理\n"
        f"公式求人候補を{checked}件確認しました。\n"
        f"{heading}\n"
        f"{result_text}\n"
        f"状態: {visible_reason}\n\n"
        "次に自動で行うこと\n"
        f"{next_text}\nユーザーの操作は必要ありません。"
    )
    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
    if sender is None:
        delivery = {"status": "suppressed", "message_id": None, "event_key": None}
    else:
        try:
            delivery = sender(
                database=outbox_path,
                japan_day=japan_day,
                message=message,
                material_digest=digest,
            )
        except Exception as error:
            delivery = {
                "status": "failed",
                "message_id": None,
                "event_key": None,
                "error_class": type(error).__name__,
            }
    email_delivery: dict[str, str | None] | None = None
    if email_sender is not None:
        try:
            email_delivery = email_sender(
                database=email_outbox_path,
                event_key=f"job-search-daily-email:{japan_day}",
                recipient=email_recipient,
                account=email_recipient,
                subject=f"[Job Hunting] Daily briefing — {japan_day}",
                message=message,
            )
        except (DeliveryUncertain, OSError, RuntimeError, ValueError) as error:
            email_delivery = {
                "status": "send_unknown"
                if isinstance(error, DeliveryUncertain)
                else "failed",
                "message_id": None,
                "error_class": type(error).__name__,
            }
    receipt: dict[str, Any] = {
        "status": delivery.get("status"),
        "message_id": delivery.get("message_id"),
        "event_key": delivery.get("event_key"),
        "application_id": application_id or None,
        "company": company,
        "role": role,
        "outcome": outcome,
        "reason": reason,
        "next_action": next_action,
    }
    if email_delivery is not None:
        receipt["email_status"] = str(email_delivery.get("status") or "failed")
        receipt["email_message_id"] = email_delivery.get("message_id")
        if email_delivery.get("error_class"):
            receipt["email_error_class"] = str(email_delivery["error_class"])
    _write_private_json(output_path, receipt)
    return receipt


def deliver_reconciled_outcomes(
    *,
    ledger_path: Path,
    outbox_path: Path,
    sender: Callable[..., dict[str, str | None]] | None = send_once,
    email_sender: Callable[..., dict[str, str | None]] | None = None,
    email_outbox_path: Path | None = None,
    email_recipient: str | None = None,
    email_since: str | None = None,
) -> list[dict[str, str | None]]:
    if email_sender is not None and not all(
        (email_outbox_path, email_recipient, email_since)
    ):
        raise ValueError("email reporting requires an outbox, recipient, and activation time")
    ledger = Ledger(ledger_path)
    try:
        rows = ledger.connection.execute(
            """
            SELECT
              applications.id AS application_id,
              applications.company,
              applications.title,
              submission_confirmations.message_id,
              submission_confirmations.received_at
            FROM submission_confirmations
            JOIN submit_intents
              ON submit_intents.intent_id = submission_confirmations.intent_id
            JOIN applications
              ON applications.id = submit_intents.application_id
            WHERE applications.current_state = 'submitted'
            ORDER BY submission_confirmations.received_at,
                     submission_confirmations.message_id
            """
        ).fetchall()
    finally:
        ledger.close()

    deliveries = []
    for row in rows:
        application_id = str(row["application_id"])
        message_id = str(row["message_id"])
        message = build_hourly_outcome_message(
            (
                QueueRowReceiptV1(
                    application_id,
                    str(row["company"]),
                    str(row["title"]),
                    "submitted",
                ),
            ),
            {application_id: "authoritative_receipt_email"},
        )
        event_key = f"application-submitted:{application_id}:{message_id}"
        if sender is None:
            telegram = {"status": "suppressed", "message_id": None}
        else:
            try:
                telegram = sender(database=outbox_path, event_key=event_key, message=message)
            except Exception as error:
                telegram = {"status": "failed", "message_id": None, "error_class": type(error).__name__}
        delivery: dict[str, str | None] = {
            "application_id": application_id,
            "receipt_message_id": message_id,
            "status": telegram["status"],
            "message_id": telegram["message_id"],
        }
        if email_sender is not None:
            if _received_after_activation(str(row["received_at"]), str(email_since)):
                try:
                    email = email_sender(
                        database=email_outbox_path,
                        event_key=event_key,
                        recipient=email_recipient,
                        account=email_recipient,
                        subject=(
                            f"[Job Hunting] 応募完了: {row['company']} — {row['title']}"
                        ),
                        message=message,
                    )
                except (DeliveryUncertain, OSError, RuntimeError, ValueError) as error:
                    email = {
                        "status": "send_unknown"
                        if isinstance(error, DeliveryUncertain)
                        else "failed",
                        "message_id": None,
                        "error_class": type(error).__name__,
                    }
            else:
                email = {"status": "suppressed_before_activation", "message_id": None}
            delivery["email_status"] = str(email.get("status") or "failed")
            delivery["email_message_id"] = email.get("message_id")
            if email.get("error_class"):
                delivery["email_error_class"] = str(email["error_class"])
        deliveries.append(delivery)
    return deliveries


def deliver_fit_decision(
    *,
    decision: dict[str, Any],
    outbox_path: Path,
    sender: Callable[..., dict[str, str | None]] = send_once,
) -> dict[str, str | None]:
    event_key = (
        f"workday-fit:{decision.get('application_id')}:"
        f"{decision.get('evidence_sha256')}"
    )
    return {"status": "suppressed", "message_id": None, "event_key": event_key}


def deliver_application_progress(
    *,
    ledger_path: Path,
    outbox_path: Path,
    application_id: str,
    run_id: str,
    sender: Callable[..., dict[str, str | None]] = send_once,
) -> dict[str, str | None]:
    event_key = f"workday-application-progress:{application_id}:{run_id}"
    return {"status": "suppressed", "message_id": None, "event_key": event_key}


def deliver_submitted_resumes(
    *,
    ledger_path: Path,
    outbox_path: Path,
    media_root: Path,
    sender: Callable[..., dict[str, str | None]] = send_document_once,
) -> list[dict[str, str | None]]:
    ledger = Ledger(ledger_path)
    try:
        reports = ledger.submitted_resume_reports()
    finally:
        ledger.close()

    deliveries = []
    for report in reports:
        message = (
            "[Job Hunting] 応募書類\n"
            "📎 応募に使用した履歴書\n"
            f"{report['company']} — {report['title']}\n"
            f"{report['canonical_url']}"
        )
        try:
            delivery = sender(
                database=outbox_path,
                event_key=(
                    f"application-resume:{report['application_id']}:"
                    f"{report['resume_sha256']}"
                ),
                message=message,
                document=Path(report["resume_path"]),
                media_root=media_root,
            )
        except Exception as error:
            delivery = {"status": "failed", "message_id": None, "error_class": type(error).__name__}
        deliveries.append(
            {
                "application_id": report["application_id"],
                "status": delivery["status"],
                "message_id": delivery["message_id"],
            }
        )
    return deliveries


def deliver_terminal_report(
    *,
    outbox_path: Path,
    run_id: str,
    outcome: str,
    reason: str,
    output_path: Path,
    sender: Callable[..., dict[str, str | None]] = send_once,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "delivery": "suppressed",
        "event_key": f"job-search-inbox:{run_id}",
        "message_id": None,
        "outcome": outcome,
        "reason": reason,
    }
    _write_private_json(output_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("deliver", "wake", "progress", "terminal"))
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--outbox", type=Path, required=True)
    parser.add_argument("--media-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--day")
    parser.add_argument("--runner-summary", type=Path)
    parser.add_argument("--discovery", type=Path)
    parser.add_argument("--application-id")
    parser.add_argument("--outcome")
    parser.add_argument("--reason")
    args = parser.parse_args()

    if args.command == "terminal":
        if not all((args.run_id, args.outcome, args.reason)):
            parser.error("terminal requires --run-id, --outcome and --reason")
        receipt = deliver_terminal_report(
            outbox_path=args.outbox,
            run_id=args.run_id,
            outcome=args.outcome,
            reason=args.reason,
            output_path=args.output,
        )
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "progress":
        if not args.application_id or not args.run_id:
            parser.error("progress requires --application-id and --run-id")
        receipt = deliver_application_progress(
            ledger_path=args.ledger,
            outbox_path=args.outbox,
            application_id=args.application_id,
            run_id=args.run_id,
        )
        _write_private_json(args.output, receipt)
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 0 if receipt.get("message_id") or receipt.get("status") == "suppressed" else 1

    if args.command == "wake":
        if not all((args.run_id, args.day, args.runner_summary, args.discovery)):
            parser.error("wake requires --run-id, --day, --runner-summary and --discovery")
        receipt = deliver_wake_report(
            ledger_path=args.ledger,
            outbox_path=args.outbox,
            run_id=args.run_id,
            japan_day=args.day,
            runner_summary_path=args.runner_summary,
            discovery_path=args.discovery,
            output_path=args.output,
            sender=send_daily_report if telegram_is_configured() else None,
            email_sender=send_email_once,
            email_outbox_path=args.outbox,
            email_recipient=_candidate_application_email(),
        )
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 0 if receipt.get("email_status") == "sent" else 1

    if args.media_root is None:
        parser.error("deliver requires --media-root")

    email_recipient = _candidate_application_email()
    email_since = ensure_email_reporting_since(
        args.outbox.parent / "email-reporting-enabled.json"
    )
    telegram_sender = send_once if telegram_is_configured() else None
    deliveries = (
        deliver_submitted_resumes(
            ledger_path=args.ledger,
            outbox_path=args.outbox,
            media_root=args.media_root,
        )
        if telegram_sender is not None
        else []
    )
    outcomes = deliver_reconciled_outcomes(
        ledger_path=args.ledger,
        outbox_path=args.outbox,
        sender=telegram_sender,
        email_sender=send_email_once,
        email_outbox_path=args.outbox,
        email_recipient=email_recipient,
        email_since=email_since,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(
        json.dumps(
            {"deliveries": deliveries, "outcomes": outcomes},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0
    os.chmod(args.output, 0o600)


if __name__ == "__main__":
    raise SystemExit(main())
