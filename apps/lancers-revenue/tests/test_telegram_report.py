import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = REPO_ROOT / "skills/earn/lancers/scripts/telegram_report.py"

def _load_report():
    spec = importlib.util.spec_from_file_location("test_lancers_telegram_report", REPORT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("canonical_report_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def _snapshot(report, application, *, pending=0, verified=14, storefront=None, blocker=None):
    return report.build_snapshot(
        application=application,
        pending_count=pending,
        cumulative_verified=verified,
        storefront=storefront or {"published": 4, "paused": 0, "hidden": 0, "draft": 0},
        source_observed_at="2026-08-13T09:00:00Z",
        official_readback_observed_at="2026-08-13T08:59:00Z",
        provider_event_time=None,
        blocker=blocker,
    )


class _InventoryLocator:
    def __init__(self, values): self.values = list(values)
    def count(self): return len(self.values)
    def nth(self, index): return self.values[index]


class _InventoryNode:
    def __init__(self, text="", *, attrs=None, children=None, visible=True):
        self.text = text; self.attrs = attrs or {}; self.children = children or {}; self.visible = visible
    def inner_text(self): return self.text
    def get_attribute(self, name): return self.attrs.get(name)
    def is_visible(self): return self.visible
    def locator(self, selector): return _InventoryLocator(self.children.get(selector, ()))


class _InventoryResponse:
    def __init__(self, status=200): self.status = status


class _InventoryPage:
    def __init__(self, report, counts, rows, public, *, statuses=None, final_urls=None):
        self.report, self.counts, self.rows, self.public = report, counts, rows, public
        self.statuses, self.final_urls, self.url, self.closed = statuses or {}, final_urls or {}, "", False
    def goto(self, url, **_kwargs):
        self.url = self.final_urls.get(url, url)
        return _InventoryResponse(self.statuses.get(url, 200))
    def close(self): self.closed = True
    def locator(self, selector):
        parsed, page = urlsplit(self.url), None
        if parsed.query:
            page = int(parse_qs(parsed.query).get("page", ["0"])[0])
        if parsed.path.startswith("/menu/detail/"):
            listing_id = parsed.path.rsplit("/", 1)[-1]
            return _InventoryLocator(self.public.get(listing_id, {}).get(selector, ()))
        if selector == "a" and parsed.path == "/myplan" and page is None:
            anchors = [
                _InventoryNode(f"{label} ({self.counts[key]}件)", attrs={"href": href})
                for key, label, href in self.report._LABELS
            ]
            return _InventoryLocator(anchors + [_InventoryNode("更新ヒント", attrs={"href": "/menu/detail/999"})])
        if selector == self.report._INVENTORY_STORE_SELECTOR:
            return _InventoryLocator(self.rows.get((parsed.path, page), ()))
        return _InventoryLocator(())


class _InventoryBrowser:
    def __init__(self, page): self.contexts = [self]; self.page = page; self._anicca_playwright_runtime = None
    def new_page(self): return self.page


class _InventoryLock:
    def __enter__(self): return self
    def __exit__(self, *_args): return False


class _InventoryTick:
    CDP_URL = "http://inventory.test"
    def __init__(self): self.lock_path = None
    def account_lock(self, path): self.lock_path = path; return _InventoryLock()
    def _new_owned_page(self, browser): return browser.contexts[0].new_page()
    def _production_account_ready(self, _page): return True
    def _close_owned_page(self, page): page.close(); return True
    def _stop_playwright_runtime(self, _runtime): pass


def _inventory_store(report, listing_id, title="AI workflow package"):
    return _InventoryNode(children={
        report._INVENTORY_TITLE_SELECTOR: [_InventoryNode(title, attrs={"href": f"/menu/detail/{listing_id}"})],
    })


def _inventory_public(report, listing_id, *, canonical_id="101", canonical_url=None, og_url=None, complete=True):
    plan = _InventoryNode(children={
        "p.p-menu-browse-detail__sidebar-description": [_InventoryNode("private plan body")],
        "div.p-menu-browse-detail__sidebar-header-price": [_InventoryNode("10,000円")],
        "div.p-menu-browse-detail__sidebar-menu": [_InventoryNode("納期 3日")],
    }) if complete else _InventoryNode(children={
        "p.p-menu-browse-detail__sidebar-description": [_InventoryNode("private plan body")],
        "div.p-menu-browse-detail__sidebar-header-price": [_InventoryNode("price missing")],
        "div.p-menu-browse-detail__sidebar-menu": [_InventoryNode("納期 missing")],
    })
    public_url = f"https://www.lancers.jp/menu/detail/{listing_id}"
    return {
        "h1": [_InventoryNode("AI workflow package")],
        ".l-page-header__heading-description": [_InventoryNode("private subtitle")],
        "#body + .p-project-plan-markdown": [_InventoryNode("private business description")],
        "#notice_for_sale + .c-text": [_InventoryNode("private order notice")],
        'link[rel="canonical"]': [_InventoryNode(attrs={"href": canonical_url or f"https://www.lancers.jp/menu/detail/{canonical_id}"})],
        'meta[property="og:url"]': [_InventoryNode(attrs={"content": og_url or public_url})],
        "a.c-tag-list__item": [_InventoryNode("AI活用", attrs={"href": "/menu/tag/ai"})],
        "li.p-menu-browse-detail__sidebar-content.js-project-plan-tab-content": [plan, _InventoryNode()],
    }

class TelegramReportTests(unittest.TestCase):
    def test_acquisition_stages_pending_verified_and_blocker_are_separate(self):
        report = _load_report()
        message = report.render_snapshot(_snapshot(report, {
            "observed_count": 13, "eligible_count": 1, "submitted": False,
            "verified_count": 0, "error": "submission_uncertain",
        }, pending=1, blocker="submission_uncertain"))
        # The wake report is Japanese narrative now, but every stage must still be separately
        # readable -- observed is not qualified, qualified is not submitted, submitted is not
        # verified -- and the warning must name the blocker rather than just showing a triangle.
        for value in ("公開案件は13件", "適合候補は1件", "新しい応募は送信していません",
                      "公式確認は0件", "累計14件", "確認待ちは1件", "submission_uncertain"):
            self.assertIn(value, message)
    def test_no_eligible_does_not_turn_receipts_into_revenue(self):
        report = _load_report()
        message = report.render_snapshot(_snapshot(report, {
            "observed_count": 13, "eligible_count": 0, "submitted": False,
            "verified_count": 0, "reason": "no_eligible_project",
        }))
        # 14 official application receipts are not 14 of revenue. The report must say the revenue
        # was not computed, and must never render a receipt count where a yen amount belongs.
        self.assertIn("✅", message)
        self.assertIn("売上とAI処理費は集計していません", message)
        self.assertNotIn("売上: 14", message)
        self.assertNotIn("売上14", message)
    def test_reconciled_application_does_not_keep_stale_submission_blocker(self):
        report = _load_report()
        message = report.render_snapshot(_snapshot(report, {
            "observed_count": 2, "eligible_count": 2, "submitted": False,
            "verified_count": 0, "error": "submission_uncertain",
        }, pending=0, verified=15))
        # Nothing is pending any more, so submission_uncertain is resolved: the report must show a
        # clean wake, not carry yesterday's blocker forward.
        self.assertIn("累計15件", message)
        self.assertIn("確認待ちは0件", message)
        self.assertIn("✅", message)
        self.assertNotIn("submission_uncertain", message)
    def test_storefront_states_are_separate_and_mismatch_is_warning(self):
        report = _load_report()
        message = report.render_snapshot(_snapshot(report, {"observed_count": 1}, storefront={
            "published": 6, "paused": 0, "hidden": 0, "draft": 0,
            "error": "listing_readback_mismatch",
        }))
        self.assertIn("⚠️", message)
        for label in ("受付中", "受付休止中", "非表示", "下書き"):
            self.assertIn(label, message)
        self.assertNotIn("未処理", message)
        self.assertNotIn("✅", message)
    def test_timestamps_and_actual_cost_are_explicitly_unknown_or_labeled(self):
        report = _load_report()
        message = report.render_snapshot(_snapshot(report, {"observed_count": 1}))
        # Unknown must stay explicitly unknown rather than becoming a plausible number. The
        # snapshot is where these values live; the message must not invent one either.
        snapshot = _snapshot(report, {"observed_count": 1})
        # Known values stay exactly as observed; unknown ones stay None rather than becoming a
        # plausible number, and the cost carries its own explicit label.
        self.assertEqual(snapshot["source_observed_at"], "2026-08-13T09:00:00Z")
        self.assertEqual(snapshot["official_readback_observed_at"], "2026-08-13T08:59:00Z")
        self.assertIsNone(snapshot["provider_event_time"])
        self.assertEqual(snapshot["actual_ai_cost"], "unknown (meter未接続)")
        self.assertIn("売上とAI処理費は集計していません", message)
        self.assertNotIn("qualification cost", message)
        self.assertNotIn("file mtime", message)
    def test_semantic_dedupe_is_daily_and_state_change_sensitive(self):
        report = _load_report()
        first = _snapshot(report, {"observed_count": 13}, pending=0)
        changed = _snapshot(report, {"observed_count": 13}, pending=1, blocker="submission_uncertain")
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "telegram.sqlite3"
            day = datetime.fromisoformat("2026-08-13T09:00:00+09:00")
            self.assertTrue(report.enqueue_snapshot(database, first, day))
            self.assertFalse(report.enqueue_snapshot(database, first, day.replace(hour=10)))
            self.assertTrue(report.enqueue_snapshot(database, changed, day.replace(hour=11)))
            self.assertTrue(report.enqueue_snapshot(database, first, day.replace(day=14)))
    def test_delivery_requires_provider_id_and_quarantines_uncertain_send(self):
        report = _load_report()
        snapshot = _snapshot(report, {"observed_count": 1})
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "telegram.sqlite3"
            self.assertTrue(report.enqueue_snapshot(database, snapshot, "2026-08-13T00:00:00Z"))
            result = report.deliver_pending(database, lambda _message: report.SendResult(True, "77"), "2026-08-13T00:00:01Z")
            self.assertEqual(result.delivered, 1)
            self.assertTrue(report.enqueue_snapshot(database, _snapshot(report, {"observed_count": 2}), "2026-08-13T00:00:02Z"))
            uncertain = report.deliver_pending(database, lambda _message: report.SendResult(True, None), "2026-08-13T00:00:03Z")
            self.assertEqual(uncertain.delivery_uncertain, 1)
            self.assertEqual(report.deliver_pending(database, lambda _message: report.SendResult(True, "88"), "2026-08-13T00:00:04Z").attempted, 0)
    def test_official_reader_parses_only_four_myplan_anchors_under_injected_lock(self):
        report = _load_report()
        class Anchor:
            def __init__(self, text, href): self.text, self.href = text, href
            def is_visible(self): return True
            def inner_text(self): return self.text
            def get_attribute(self, name): return self.href if name == "href" else None
        class Anchors:
            def __init__(self, values): self.values = values
            def count(self): return len(self.values)
            def nth(self, index): return self.values[index]
        class Page:
            url = "https://www.lancers.jp/myplan"
            def goto(self, *_args, **_kwargs): pass
            def locator(self, selector):
                self.assert_selector = selector
                return Anchors([Anchor(f"{label} ({count}件)", href) for label, count, href in (("受付中", 6, "/myplan"), ("受付休止中", 0, "/myplan/paused"), ("非表示", 0, "/myplan/archived"), ("下書き", 0, "/myplan/draft"))])
        class Browser:
            def __init__(self): self.contexts = [self]
            def new_page(self): return Page()
        class Lock:
            def __enter__(self): self.entered = True
            def __exit__(self, *_args): self.exited = True
        lock = Lock()
        self.assertEqual(report.read_storefront(Path("/tmp/application.json"), browser_factory=lambda _url: Browser(), lock=lambda _path: lock), {"published": 6, "paused": 0, "hidden": 0, "draft": 0})
        self.assertTrue(lock.entered)

    def test_malformed_sources_are_unknown_warning_not_fabricated_zero(self):
        report = _load_report()
        message = report.render_snapshot(report.build_snapshot(
            application=None, pending_count=None, cumulative_verified=None,
            storefront=None, source_observed_at=None,
            official_readback_observed_at=None, provider_event_time=None,
        ))
        self.assertIn("⚠️", message)
        self.assertIn("unknown", message)
        self.assertNotIn("✅", message)
        self.assertNotIn("0件", message)
    def test_last_valid_json_ignores_malformed_trailing_lines(self):
        report = _load_report()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "application.log"
            path.write_text('{"observed_count":13}\nnot-json\n', encoding="utf-8")
            self.assertEqual(report.read_last_json(path), {"observed_count": 13})
    def test_application_false_ok_never_renders_success(self):
        report = _load_report()
        snapshot = _snapshot(report, {"ok": False, "observed_count": 13, "eligible_count": 0, "submitted": False, "verified_count": 0})
        self.assertFalse(snapshot["complete"])
        self.assertNotIn("✅", report.render_snapshot(snapshot))
    def test_now_is_not_source_timestamp_without_explicit_application_timestamp(self):
        report = _load_report()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "application.out.log"
            state = root / "application.json"
            log.write_text('{"ok":true,"observed_count":13,"eligible_count":0,"submitted":false,"verified_count":0,"reason":"no_eligible_project"}\n', encoding="utf-8")
            state.write_text('{"fingerprints":[],"pending":{}}\n', encoding="utf-8")
            snapshot = report.collect_snapshot(application_log=log, state_path=state, ledger_database=root / "ledger.sqlite3", storefront={"published": 0, "paused": 0, "hidden": 0, "draft": 0}, ledger_events=[], now="2099-01-01T00:00:00Z")
            message = report.render_snapshot(snapshot)
            # The invariant is that `now` is never passed off as the moment the source was
            # observed. The timestamps left the human message, so assert it where the value lives.
            self.assertIsNone(snapshot["source_observed_at"])
            self.assertNotIn("2099", message)
    def test_non_positive_or_non_numeric_provider_ids_are_uncertain(self):
        report = _load_report()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "telegram.sqlite3"
            for index in range(3):
                self.assertTrue(report.enqueue_snapshot(database, _snapshot(report, {"observed_count": index + 1}), f"2026-08-13T00:00:0{index}Z"))
            ids = iter(("0", "-1", "error"))
            result = report.deliver_pending(database, lambda _message: report.SendResult(True, next(ids)), "2026-08-13T00:01:00Z")
            self.assertEqual(result.delivered, 0)
            self.assertEqual(result.delivery_uncertain, 3)

    def _run_inventory(self, report, counts, rows, public, *, statuses=None, final_urls=None):
        page = _InventoryPage(report, counts, rows, public, statuses=statuses, final_urls=final_urls)
        tick = _InventoryTick()
        result = report.run_inventory(
            state_path=Path("/tmp/application.json"), browser_factory=lambda _url: _InventoryBrowser(page), tick_module=tick,
        )
        self.assertEqual(tick.lock_path, Path("/tmp/work-sync.json"))
        self.assertTrue(page.closed)
        return result

    def test_inventory_returns_six_sanitized_rows_and_one_deterministic_content_group(self):
        report = _load_report()
        ids = [str(101 + index) for index in range(6)]
        counts = {"published": 6, "paused": 0, "hidden": 0, "draft": 0}
        rows = {("/myplan", None): [_inventory_store(report, listing_id) for listing_id in ids]}
        public = {listing_id: _inventory_public(report, listing_id) for listing_id in ids}
        result = self._run_inventory(report, counts, rows, public)
        self.assertTrue(result["ok"] and result["logged_in"] and result["source_complete"])
        self.assertEqual(result["state_counts"], counts)
        self.assertEqual(result["listing_count"], 6)
        self.assertEqual([item["listing_external_id"] for item in result["listings"]], ids)
        self.assertEqual(len(result["content_groups"]), 1)
        self.assertEqual(result["content_groups"][0]["listing_ids"], ids)
        self.assertEqual(result["content_groups"][0]["canonical_listing_ids"], ["101"])
        rendered = json.dumps(result, ensure_ascii=False)
        for private in ("private subtitle", "private business description", "private order notice", "private plan body", "更新ヒント"):
            self.assertNotIn(private, rendered)

    def test_inventory_fails_closed_for_count_duplicate_public_and_page_limit_faults(self):
        report = _load_report()
        first = _inventory_store(report, "101")
        public = {"101": _inventory_public(report, "101")}
        count_overflow = self._run_inventory(
            report, {"published": 0, "paused": 0, "hidden": 0, "draft": 0}, {("/myplan", None): [first]}, public,
        )
        self.assertEqual(count_overflow["error"], "inventory_count_overflow")
        duplicate = self._run_inventory(
            report, {"published": 1, "paused": 1, "hidden": 0, "draft": 0},
            {("/myplan", None): [first], ("/myplan/paused", None): [_inventory_store(report, "101")]}, public,
        )
        self.assertEqual(duplicate["error"], "inventory_cross_state_duplicate")
        bad_og = self._run_inventory(
            report, {"published": 1, "paused": 0, "hidden": 0, "draft": 0}, {("/myplan", None): [first]},
            {"101": _inventory_public(report, "101", og_url="https://www.lancers.jp/menu/detail/999")},
        )
        self.assertEqual(bad_og["error"], "inventory_public_og_invalid")
        bad_plan = self._run_inventory(
            report, {"published": 1, "paused": 0, "hidden": 0, "draft": 0}, {("/myplan", None): [first]},
            {"101": _inventory_public(report, "101", complete=False)},
        )
        self.assertEqual(bad_plan["error"], "inventory_plan_invalid")
        with patch.object(report, "_INVENTORY_MAX_PAGES", 1):
            limited = self._run_inventory(
                report, {"published": 2, "paused": 0, "hidden": 0, "draft": 0}, {("/myplan", None): [first]}, public,
            )
        self.assertEqual(limited["error"], "inventory_page_limit_reached")
        self.assertFalse(any(value.get("ok") for value in (count_overflow, duplicate, bad_og, bad_plan, limited)))

    def test_inventory_worker_is_one_json_line_and_parent_uses_existing_watchdog(self):
        report = _load_report()
        payload = {"ok": True, "logged_in": True, "source_complete": True, "state_counts": {}, "listing_count": 0, "listings": [], "content_groups": []}
        output = io.StringIO()
        with patch.object(report, "run_inventory", return_value=payload):
            code = report.main(["--inventory-json", "--inventory-worker", "--state-path", "/tmp/application.json"], stdout=output)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue().count("\n"), 1)
        self.assertEqual(json.loads(output.getvalue()), payload)
        calls = []
        class WorkSync:
            TICK_TIMEOUT_SECONDS = 120
            @staticmethod
            def _watchdog(command, timeout):
                calls.append((command, timeout)); return payload
        original_load = report._load
        with patch.object(report, "_load", side_effect=lambda name, path: WorkSync if name == "lancers_inventory_work_sync" else original_load(name, path)):
            self.assertEqual(report._run_inventory_parent("/tmp/application.json"), payload)
        self.assertEqual(calls, [([
            sys.executable, str(REPORT_PATH.resolve()), "--inventory-json", "--inventory-worker", "--state-path", "/tmp/application.json",
        ], 120)])

    def test_scheduled_json_path_is_unchanged_and_never_enters_inventory_or_watchdog(self):
        report, output = _load_report(), io.StringIO()
        snapshot = {"complete": False}
        delivery = report.DeliveryResult(attempted=1, delivered=1)
        with (
            patch.object(report, "run_inventory", side_effect=AssertionError("inventory worker called")),
            patch.object(report, "_run_inventory_parent", side_effect=AssertionError("watchdog called")),
            patch.object(report, "collect_snapshot", return_value=snapshot) as collect,
            patch.object(report, "enqueue_snapshot", return_value=True) as enqueue,
            patch.object(report, "deliver_pending", return_value=delivery) as deliver,
        ):
            code = report.main(["--json", "--now", "2026-08-13T00:00:00Z"], stdout=output)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), {
            "ok": True, "enqueued": 1, "attempted": 1, "delivered": 1,
            "delivery_uncertain": 0, "pre_send_failed": 0, "provider_rejected": 0,
        })
        self.assertEqual(collect.call_count, enqueue.call_count)
        self.assertEqual(deliver.call_count, 1)

    def test_inventory_worker_fails_closed_for_each_required_public_boundary(self):
        report, listing_id = _load_report(), "101"
        counts = {"published": 1, "paused": 0, "hidden": 0, "draft": 0}
        rows = {("/myplan", None): [_inventory_store(report, listing_id)]}
        public_url = f"https://www.lancers.jp/menu/detail/{listing_id}"
        cases = {
            "http_non_200": {"statuses": {public_url: 503}},
            "public_route_drift": {"final_urls": {public_url: "https://www.lancers.jp/menu/detail/999"}},
            "missing_h1": {"remove": "h1"},
            "missing_subtitle": {"remove": ".l-page-header__heading-description"},
            "missing_canonical": {"remove": 'link[rel="canonical"]'},
            "invalid_canonical": {"canonical_url": "https://www.lancers.jp/menu/detail/not-a-number"},
            "missing_business": {"remove": "#body + .p-project-plan-markdown"},
            "missing_notice": {"remove": "#notice_for_sale + .c-text"},
        }
        for name, inject in cases.items():
            with self.subTest(name=name):
                public = _inventory_public(report, listing_id, canonical_url=inject.get("canonical_url"))
                if inject.get("remove"):
                    public.pop(inject["remove"])
                result = self._run_inventory(
                    report, counts, rows, {listing_id: public}, statuses=inject.get("statuses"), final_urls=inject.get("final_urls"),
                )
                self.assertFalse(result["ok"])
                self.assertFalse(result["source_complete"])
                self.assertIsInstance(result.get("error"), str)
                output = io.StringIO()
                with patch.object(report, "run_inventory", return_value=result):
                    code = report.main(["--inventory-json", "--inventory-worker"], stdout=output)
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(output.getvalue()), result)

    def test_inventory_reachable_boundary_has_no_mutation_or_report_side_effects(self):
        source = REPORT_PATH.read_text(encoding="utf-8")
        inventory = source[source.index("class InventoryFailure"):source.index("@dataclass")]
        for disallowed in (
            "POST", "PUT", "PATCH", "DELETE", ".evaluate(", ".fill(", ".press(", ".click(",
            "run_publish", "adopt_", "append_event", "enqueue_snapshot", "launchctl", "write_text(",
            "write_bytes(", "os.replace", "sqlite3", "INSERT ", "UPDATE ", "DELETE ",
        ):
            self.assertNotIn(disallowed, inventory)
        self.assertIsNone(re.search(r"(?:^|[^A-Za-z_])open\s*\([^\n]*[,=]\s*['\"]w", inventory))


class ReportChatTests(unittest.TestCase):
    """The chat id is not in the repo, so a placeholder here means silent blindness.

    A wrong id does not raise: the outbox records delivery_uncertain and the
    owner simply stops hearing from the loop, which is how four days passed
    before anyone noticed.
    """

    def test_chat_is_never_the_placeholder(self):
        report = _load_report()

        self.assertNotEqual(report.TARGET, "0000000000")

    def test_environment_wins_over_the_private_config(self):
        report = _load_report()

        with patch.dict(os.environ, {"LANCERS_REPORT_CHAT": "111"}, clear=False):
            self.assertEqual(report._report_chat(), "111")

    def test_falls_back_to_the_private_config_when_launchd_carries_no_chat(self):
        report = _load_report()
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "telegram.env"
            config.write_text("LANCERS_REPORT_CHAT=222\n", encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k not in ("LANCERS_REPORT_CHAT", "GIG_REPORT_CHAT")}
            with patch.dict(os.environ, env, clear=True), patch.object(report, "CHAT_CONFIG", config):
                self.assertEqual(report._report_chat(), "222")

    def test_returns_empty_rather_than_a_guess_when_nothing_is_configured(self):
        report = _load_report()
        with tempfile.TemporaryDirectory() as directory:
            env = {k: v for k, v in os.environ.items() if k not in ("LANCERS_REPORT_CHAT", "GIG_REPORT_CHAT")}
            missing = Path(directory) / "absent.env"
            with patch.dict(os.environ, env, clear=True), patch.object(report, "CHAT_CONFIG", missing):
                self.assertEqual(report._report_chat(), "")


if __name__ == "__main__":
    unittest.main()
