from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import owner_report
import owner_report_reconcile as reconcile


BOT = 111
OTHER_BOT = 222
URL = "https://www.tiktok.com/@anicca/video/7697791291253361936"


def _event(kind: str = "action", native_url: str = URL, age: int = 24, measured: bool = True) -> dict:
    facts = {"native_url": native_url}
    if kind == "checkpoint":
        facts.update({"platform": "tiktok", "target_age_hours": age})
        facts.update({"checkpoint_status": "measured", "views": 5} if measured else {"checkpoint_status": "missed", "reason": "metric_unavailable"})
    suffix = f"postiz:post-{int(measured)}:{age}" if kind == "checkpoint" else "7697791291253361936"
    return owner_report._event(
        kind=kind,
        product_id="anicca-ios",
        as_of=dt.datetime(2026, 10, 18, 0, 0, tzinfo=dt.timezone.utc),
        message_key=f"{kind}:anicca-ios:{suffix}",
        facts=facts,
        evidence_refs=["post-metrics.jsonl#1"],
    )


def _timeout(_text: str) -> dict:
    raise TimeoutError("transport timeout")


class OwnerReportReconcileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = owner_report.OwnerReportStore(
            self.root / "owner-reports.jsonl", self.root / "owner-report-deliveries.jsonl"
        )
        self.reads: list[tuple[int, dt.datetime, dt.datetime]] = []

    def tearDown(self) -> None:
        self.temp.cleanup()

    def unknown(self, event: dict) -> dt.datetime:
        self.assertEqual(owner_report.deliver(event, self.store, _timeout)["status"], "delivery_unknown")
        return self.claimed_at(event)

    def claimed_at(self, event: dict) -> dt.datetime:
        rows = owner_report.load_jsonl(self.store.delivery_path)
        claims = [row for row in rows if row["message_key"] == event["message_key"] and row["status"] == "sending"]
        return owner_report._parse_time(claims[-1]["claimed_at"])

    def reader(self, history: dict[int, dict]):
        def read(bot_id: int, start: dt.datetime, end: dt.datetime) -> dict:
            self.reads.append((bot_id, start, end))
            return history[bot_id]

        return read

    @staticmethod
    def message(message_id: int, sender: int, when: dt.datetime, text: str) -> dict:
        return {"id": message_id, "sender_id": sender, "out": False, "date": when.isoformat(), "text": text}

    def run_reconcile(self, history: dict[int, dict], now: dt.datetime) -> list[dict]:
        return reconcile.reconcile_open_deliveries(
            self.root, bot_ids=[BOT, OTHER_BOT], read_window=self.reader(history), now=now
        )

    def test_exact_identity_in_history_closes_unknown_as_delivered_without_resend(self):
        event = _event()
        claimed = self.unknown(event)
        sent = owner_report.render_japanese(event)
        history = {
            BOT: {"complete": True, "messages": [self.message(9001, BOT, claimed + dt.timedelta(seconds=20), sent)]},
            OTHER_BOT: {"complete": True, "messages": []},
        }
        results = self.run_reconcile(history, claimed + dt.timedelta(hours=2))

        self.assertEqual([r["status"] for r in results], ["delivered"])
        row = self.store.delivery_for(event["message_key"])
        self.assertEqual(row["status"], "delivered")
        self.assertEqual(row["message_ids"], [9001])
        self.assertEqual(row["receipt"]["provider_readback"]["matched_by"], "immutable_event_identity")
        calls = []
        replay = owner_report.deliver(event, self.store, lambda _text: calls.append(1))
        self.assertEqual(replay["message_ids"], [9001])
        self.assertEqual(calls, [])

    def test_complete_window_without_identity_confirms_absence_and_normal_path_resends(self):
        event = _event()
        claimed = self.unknown(event)
        unrelated = "📣 Aniccaの公開を確認しました。\n次に確認するリンク: https://www.tiktok.com/@anicca/video/1"
        history = {
            BOT: {"complete": True, "messages": [self.message(9002, BOT, claimed + dt.timedelta(seconds=5), unrelated)]},
            OTHER_BOT: {"complete": True, "messages": []},
        }
        results = self.run_reconcile(history, claimed + dt.timedelta(hours=2))

        self.assertEqual([r["status"] for r in results], ["not_delivered_confirmed"])
        row = self.store.delivery_for(event["message_key"])
        self.assertEqual(row["status"], "not_delivered_confirmed")
        self.assertEqual(row["message_ids"], [])
        readback = row["receipt"]["provider_readback"]
        self.assertEqual(readback["matched_by"], "complete_window_absence")
        self.assertEqual(sorted(readback["bot_ids"]), [BOT, OTHER_BOT])
        self.assertEqual({bot for bot, _start, _end in self.reads}, {BOT, OTHER_BOT})
        for _bot, start, end in self.reads:
            self.assertEqual(claimed - start, dt.timedelta(seconds=300))
            self.assertGreaterEqual(end, claimed + dt.timedelta(seconds=reconcile.READBACK_WINDOW_SECONDS))

        calls = []
        resent = owner_report.deliver(event, self.store, lambda _text: calls.append(1) or {"status": "delivered", "message_ids": [9100]})
        self.assertEqual(resent["status"], "delivered")
        self.assertEqual(len(calls), 1)

    def test_incomplete_history_keeps_delivery_unknown(self):
        event = _event()
        claimed = self.unknown(event)
        history = {
            BOT: {"complete": True, "messages": []},
            OTHER_BOT: {"complete": False, "messages": []},
        }
        results = self.run_reconcile(history, claimed + dt.timedelta(hours=2))

        self.assertEqual(results[0]["status"], "unknown")
        self.assertEqual(results[0]["reason"], "telegram_history_incomplete")
        self.assertEqual(self.store.delivery_for(event["message_key"])["status"], "delivery_unknown")

    def test_stuck_sending_claim_is_reconciled_from_history(self):
        event = _event()
        self.store.record(event)
        claimed_ok, _claim = self.store.claim_delivery(event["message_key"])
        self.assertTrue(claimed_ok)
        claimed = self.claimed_at(event)
        sent = owner_report.render_japanese(event)
        history = {
            BOT: {"complete": True, "messages": []},
            OTHER_BOT: {"complete": True, "messages": [self.message(77, OTHER_BOT, claimed + dt.timedelta(seconds=3), sent)]},
        }
        results = self.run_reconcile(history, claimed + dt.timedelta(days=9))

        self.assertEqual([r["status"] for r in results], ["delivered"])
        row = self.store.delivery_for(event["message_key"])
        self.assertEqual(row["receipt"]["reconciled_from"], "sending")
        self.assertEqual(row["receipt"]["provider_readback"]["sender_bot_id"], OTHER_BOT)

    def test_same_kind_message_without_link_is_ambiguous_not_absence(self):
        event = _event("checkpoint")
        claimed = self.unknown(event)
        old_renderer = "📊 anicca-iosのTikTokチェックポイント（24時間）。\n閲覧数 5、表示回数 None。"
        history = {
            BOT: {"complete": True, "messages": [self.message(9003, BOT, claimed + dt.timedelta(seconds=4), old_renderer)]},
            OTHER_BOT: {"complete": True, "messages": []},
        }
        results = self.run_reconcile(history, claimed + dt.timedelta(hours=2))

        self.assertEqual(results[0]["status"], "unknown")
        self.assertEqual(results[0]["reason"], "same_kind_message_without_identity")
        self.assertEqual(self.store.delivery_for(event["message_key"])["status"], "delivery_unknown")

    def test_same_url_in_other_kind_message_is_not_delivery(self):
        event = _event("checkpoint")
        claimed = self.unknown(event)
        action_text = f"📣 Aniccaの公開を確認しました。\n次に確認するリンク: {URL}"
        history = {
            BOT: {"complete": True, "messages": [self.message(9004, BOT, claimed + dt.timedelta(seconds=4), action_text)]},
            OTHER_BOT: {"complete": True, "messages": []},
        }
        results = self.run_reconcile(history, claimed + dt.timedelta(hours=2))

        self.assertEqual(results[0]["status"], "not_delivered_confirmed")

    def test_other_age_checkpoint_of_same_post_does_not_close_key(self):
        for measured in (True, False):
            with self.subTest(measured=measured):
                six = _event("checkpoint", age=6, measured=measured)
                day = _event("checkpoint", age=24, measured=measured)
                claimed = self.unknown(day)
                history = {
                    BOT: {"complete": True, "messages": [
                        self.message(9005, BOT, claimed + dt.timedelta(seconds=4), owner_report.render_japanese(six))]},
                    OTHER_BOT: {"complete": True, "messages": []},
                }
                results = self.run_reconcile(history, claimed + dt.timedelta(hours=2))

                status = {r["message_key"]: r for r in results}[day["message_key"]]
                self.assertEqual(status["status"], "unknown")
                self.assertEqual(self.store.delivery_for(day["message_key"])["status"], "delivery_unknown")

    def test_stale_ambiguous_checkpoint_expires_without_resend(self):
        event = _event("checkpoint", age=72)
        claimed = self.unknown(event)
        old_renderer = "📊 anicca-iosのTikTokチェックポイント（72時間）。\n閲覧数 5、表示回数 None。"
        history = {
            BOT: {"complete": True, "messages": [self.message(9006, BOT, claimed + dt.timedelta(seconds=4), old_renderer)]},
            OTHER_BOT: {"complete": True, "messages": []},
        }
        results = self.run_reconcile(history, claimed + dt.timedelta(days=10))

        self.assertEqual([r["status"] for r in results], ["expired_unknown"])
        row = self.store.delivery_for(event["message_key"])
        self.assertEqual(row["status"], "expired_unknown")
        self.assertEqual(row["message_ids"], [])
        self.assertEqual(row["receipt"]["reason"], "stale_checkpoint_identity_unprovable")
        readback = row["receipt"]["provider_readback"]
        self.assertTrue(readback["complete"])
        self.assertEqual(readback["ambiguity"], "same_kind_message_without_identity")
        self.assertGreaterEqual(readback["claim_age_seconds"], 7 * 86400)
        calls = []
        replay = owner_report.deliver(event, self.store, lambda _text: calls.append(1))
        self.assertEqual(replay["status"], "expired_unknown")
        self.assertEqual(calls, [])

    def test_stale_ambiguous_action_stays_open(self):
        event = _event()
        claimed = self.unknown(event)
        linkless = "📣 Aniccaの公開を確認しました。"
        history = {
            BOT: {"complete": True, "messages": [self.message(9007, BOT, claimed + dt.timedelta(seconds=4), linkless)]},
            OTHER_BOT: {"complete": True, "messages": []},
        }
        results = self.run_reconcile(history, claimed + dt.timedelta(days=10))

        self.assertEqual(results[0]["status"], "unknown")
        self.assertEqual(self.store.delivery_for(event["message_key"])["status"], "delivery_unknown")

    def test_cli_counts_expired_unknown_as_resolved_not_open(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from unittest import mock
        import owner_report_cli

        event = _event("checkpoint", age=72)
        claimed = self.unknown(event)
        self.store.expire_unknown(event["message_key"], "stale_checkpoint_identity_unprovable", {
            "source": "telegram_mtproto_history", "matched_by": "complete_window_ambiguous", "complete": True,
            "observed_at": "2026-10-18T01:00:00Z", "claim_age_seconds": 10 * 86400,
        })

        def build(_root, _kind, *, product_id, as_of, skip_message_keys):
            return [] if event["message_key"] in skip_message_keys else [event]

        stdout = io.StringIO()
        with (
            mock.patch.object(owner_report, "build_events", side_effect=build),
            mock.patch.object(owner_report_cli, "_send_text") as send,
            redirect_stdout(stdout),
            redirect_stderr(io.StringIO()),
        ):
            rc = owner_report_cli.main(["sweep", "--kind", "checkpoint", "--state-root", str(self.root)])

        self.assertEqual(rc, 0)
        send.assert_not_called()
        self.assertIn("owner_report_resolved_unknown=1", stdout.getvalue())

    def test_open_readback_window_is_not_read(self):
        event = _event()
        claimed = self.unknown(event)
        results = self.run_reconcile({}, claimed + dt.timedelta(seconds=60))

        self.assertEqual(results[0]["reason"], "readback_window_open")
        self.assertEqual(self.reads, [])
        self.assertEqual(self.store.delivery_for(event["message_key"])["status"], "delivery_unknown")

    def test_absence_requires_complete_history_readback(self):
        event = _event()
        self.unknown(event)
        with self.assertRaises(owner_report.DeliveryError):
            self.store.confirm_not_delivered(
                event["message_key"],
                {"source": "telegram_mtproto_history", "matched_by": "complete_window_absence", "complete": False,
                 "observed_at": "2026-10-18T01:00:00Z"},
            )


if __name__ == "__main__":
    unittest.main()
