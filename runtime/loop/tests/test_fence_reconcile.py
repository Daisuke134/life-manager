"""T5-G-2/T5-G-3: the generic fence self-reconciler never retries an effect.

These tests use fake ``run_call``/``read_fenced`` callables so no real owner
script, browser, or admission database is touched.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from runtime.loop.fence_reconcile import (
    build_argv,
    plan_targets,
    reconcile,
    round_robin,
)


def _registry(loops: dict) -> dict:
    return {"schema_version": 2, "loops": loops}


class BuildArgvTest(unittest.TestCase):
    def test_builds_interpreter_prefixed_argv_with_occurrence_and_resolve(self):
        cfg = {
            "argv": ["skills/x/reconcile.py", "--state-root", "~/x"],
            "occurrence_flag": "--occurrence", "resolve_flag": "--resolve",
        }
        argv = build_argv(cfg, Path("/release"), "owner-a:1")
        self.assertEqual(argv[0], sys.executable)
        self.assertEqual(
            argv[1:],
            ["/release/skills/x/reconcile.py", "--state-root", "~/x",
             "--occurrence", "owner-a:1", "--resolve"],
        )

    def test_null_occurrence_flag_omits_occurrence_args(self):
        cfg = {"argv": ["skills/x/reconcile.py"], "occurrence_flag": None,
               "resolve_flag": "--resolve"}
        argv = build_argv(cfg, Path("/release"), None)
        self.assertNotIn("--occurrence", argv)
        self.assertIn("--resolve", argv)

    def test_null_resolve_flag_never_appends_a_flag(self):
        cfg = {"argv": ["skills/x/reconcile.py"], "occurrence_flag": "--occurrence-id",
               "resolve_flag": None}
        argv = build_argv(cfg, Path("/release"), "owner-a:1")
        self.assertEqual(argv[-2:], ["--occurrence-id", "owner-a:1"])

    def test_occurrence_flag_without_target_raises(self):
        cfg = {"argv": ["x.py"], "occurrence_flag": "--occurrence"}
        with self.assertRaises(ValueError):
            build_argv(cfg, Path("/r"), None)

    def test_empty_argv_raises(self):
        with self.assertRaises(ValueError):
            build_argv({"argv": []}, Path("/r"), None)

    def test_ebook_postiz_reconcile_entries_pass_each_exact_occurrence(self):
        root = Path(__file__).resolve().parents[3]
        registry = json.loads((root / "config/loop-registry.json").read_text())
        owners = (
            "ebook-en-tiktok-daily",
            "ebook-ja-tiktok-daily",
            "ebook-ja-instagram-daily",
        )
        for owner_id in owners:
            with self.subTest(owner_id=owner_id):
                config = registry["loops"][owner_id]["effect_reconcile"]
                self.assertEqual(config["occurrence_flag"], "--occurrence-id")
                occurrence_id = f"{owner_id}:claim-1"
                argv = build_argv(config, Path("/release"), occurrence_id)
                self.assertEqual(argv[-3:], ["--occurrence-id", occurrence_id, "--resolve"])


class PlanTargetsTest(unittest.TestCase):
    def test_owner_without_effect_reconcile_needs_adapter(self):
        fenced = {"owner-a": ("owner-a:1",)}
        targets, needs_adapter = plan_targets(fenced, {"owner-a": {}})
        self.assertEqual(targets, {})
        self.assertEqual(needs_adapter, ["owner-a"])

    def test_owner_missing_from_registry_needs_adapter(self):
        fenced = {"owner-ghost": ("owner-ghost:1",)}
        targets, needs_adapter = plan_targets(fenced, {})
        self.assertEqual(targets, {})
        self.assertEqual(needs_adapter, ["owner-ghost"])

    def test_owner_with_null_occurrence_flag_gets_single_none_target(self):
        fenced = {"owner-b": ("owner-b:1", "owner-b:2")}
        loops = {"owner-b": {"effect_reconcile": {"argv": ["x.py"], "occurrence_flag": None}}}
        targets, needs_adapter = plan_targets(fenced, loops)
        self.assertEqual(targets, {"owner-b": [None]})
        self.assertEqual(needs_adapter, [])

    def test_owner_with_occurrence_flag_gets_one_target_per_occurrence(self):
        fenced = {"owner-c": ("owner-c:1", "owner-c:2")}
        loops = {"owner-c": {"effect_reconcile": {
            "argv": ["x.py"], "occurrence_flag": "--occurrence"}}}
        targets, _ = plan_targets(fenced, loops)
        self.assertEqual(targets, {"owner-c": ["owner-c:1", "owner-c:2"]})


class RoundRobinTest(unittest.TestCase):
    def test_interleaves_owners_before_exhausting_one(self):
        targets = {"a": ["a1", "a2", "a3"], "b": ["b1"]}
        calls = round_robin(targets, cap=10)
        self.assertEqual(calls, [("a", "a1"), ("b", "b1"), ("a", "a2"), ("a", "a3")])

    def test_cap_limits_total_calls_and_keeps_fairness(self):
        targets = {"a": ["a1", "a2"], "b": ["b1", "b2"]}
        calls = round_robin(targets, cap=2)
        self.assertEqual(calls, [("a", "a1"), ("b", "b1")])

    def test_prioritizes_investment_readback_owner_before_other_adapters(self):
        targets = {
            "crowdworks-revenue-application": ["crowdworks-revenue-application:1"],
            "investment-cross-venue-report": ["investment-cross-venue-report:1"],
        }
        calls = round_robin(
            targets, cap=1, priority_owners={"investment-cross-venue-report"},
        )
        self.assertEqual(
            calls,
            [("investment-cross-venue-report", "investment-cross-venue-report:1")],
        )


class ReconcileTest(unittest.TestCase):
    def test_owner_with_reconcile_script_that_closes_the_row(self):
        state = {"owner-a": ["owner-a:1"]}

        def read_fenced():
            return {k: tuple(v) for k, v in state.items() if v}

        def run_call(argv, **_k):
            occ = argv[argv.index("--occurrence") + 1]
            state["owner-a"] = [o for o in state["owner-a"] if o != occ]
            return 0, "resolved"

        loops = {"owner-a": {"effect_reconcile": {
            "argv": ["skills/x/reconcile.py"], "occurrence_flag": "--occurrence",
            "resolve_flag": "--resolve"}}}
        summary = reconcile(
            registry=_registry(loops), root=Path("/release"),
            run_call=run_call, read_fenced=read_fenced, log_path=None,
        )
        self.assertEqual(summary, {
            "checked": 1, "closed": 1, "still_fenced": 0, "deferred_calls": 0, "needs_readback_adapter": [],
        })

    def test_owner_script_nonzero_exit_leaves_it_fenced_and_is_never_retried(self):
        state = {"owner-b": ["owner-b:1"]}
        calls = []

        def read_fenced():
            return {k: tuple(v) for k, v in state.items() if v}

        def run_call(argv, **_k):
            calls.append(argv)
            return 1, "held"

        loops = {"owner-b": {"effect_reconcile": {
            "argv": ["skills/x/reconcile.py"], "occurrence_flag": "--occurrence",
            "resolve_flag": "--resolve"}}}
        summary = reconcile(
            registry=_registry(loops), root=Path("/release"),
            run_call=run_call, read_fenced=read_fenced, log_path=None,
        )
        self.assertEqual(summary["closed"], 0)
        self.assertEqual(summary["still_fenced"], 1)
        self.assertEqual(len(calls), 1)

    def test_owner_without_effect_reconcile_reported_as_needs_adapter(self):
        def read_fenced():
            return {"owner-c": ("owner-c:1",)}

        summary = reconcile(
            registry=_registry({"owner-c": {}}), root=Path("/release"),
            run_call=lambda argv: (0, ""), read_fenced=read_fenced, log_path=None,
        )
        self.assertEqual(summary, {
            "checked": 1, "closed": 0, "still_fenced": 1, "deferred_calls": 0,
            "needs_readback_adapter": ["owner-c"],
        })

    def test_null_occurrence_flag_owner_is_called_once_for_all_its_fences(self):
        state = {"owner-d": ["owner-d:1", "owner-d:2"]}
        calls = []

        def read_fenced():
            return {k: tuple(v) for k, v in state.items() if v}

        def run_call(argv, **_k):
            calls.append(argv)
            state["owner-d"] = []  # the script's own internal enumeration closed both
            return 0, "resolved"

        loops = {"owner-d": {"effect_reconcile": {
            "argv": ["skills/x/self_enumerate.py"], "occurrence_flag": None,
            "resolve_flag": "--resolve"}}}
        summary = reconcile(
            registry=_registry(loops), root=Path("/release"),
            run_call=run_call, read_fenced=read_fenced, log_path=None,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(summary["closed"], 2)
        self.assertEqual(summary["still_fenced"], 0)

    def test_cap_and_round_robin_respected_across_owners(self):
        state = {
            "owner-a": [f"owner-a:{i}" for i in range(3)],
            "owner-b": [f"owner-b:{i}" for i in range(3)],
        }
        calls = []

        def read_fenced():
            return {k: tuple(v) for k, v in state.items() if v}

        def run_call(argv, **_k):
            calls.append(argv)
            occ = argv[argv.index("--occurrence") + 1]
            owner = occ.split(":")[0]
            state[owner] = [o for o in state[owner] if o != occ]
            return 0, "resolved"

        loops = {owner: {"effect_reconcile": {
            "argv": ["skills/x/reconcile.py"], "occurrence_flag": "--occurrence",
            "resolve_flag": "--resolve"}} for owner in ("owner-a", "owner-b")}
        summary = reconcile(
            registry=_registry(loops), root=Path("/release"), cap=3,
            run_call=run_call, read_fenced=read_fenced, log_path=None,
        )
        self.assertEqual(summary["checked"], 6)
        self.assertEqual(len(calls), 3)
        self.assertEqual(summary["closed"], 3)
        owners_called = [argv[argv.index("--occurrence") + 1].split(":")[0] for argv in calls]
        self.assertEqual(owners_called, ["owner-a", "owner-b", "owner-a"])

    def test_reconcile_prioritizes_financial_adapter_when_wake_is_capped(self):
        state = {
            "crowdworks-revenue-application": ["crowdworks-revenue-application:1"],
            "investment-cross-venue-report": ["investment-cross-venue-report:1"],
        }
        calls = []

        def read_fenced():
            return {k: tuple(v) for k, v in state.items() if v}

        def run_call(argv, **_k):
            calls.append(argv[1])
            return 1, "held"

        loops = {
            "crowdworks-revenue-application": {
                "domain": "growth",
                "effect_reconcile": {
                    "argv": ["skills/crowdworks/reconcile.py"],
                    "occurrence_flag": "--occurrence",
                },
            },
            "investment-cross-venue-report": {
                "domain": "financial",
                "effect_reconcile": {
                    "argv": ["apps/life-manager/investment-core/reconcile.py"],
                    "occurrence_flag": "--occurrence",
                },
            },
        }
        reconcile(
            registry=_registry(loops), root=Path("/release"), cap=1,
            run_call=run_call, read_fenced=read_fenced, log_path=None,
        )
        self.assertEqual(
            calls,
            ["/release/apps/life-manager/investment-core/reconcile.py"],
        )

    def test_writes_one_jsonl_record_per_occurrence(self):
        import json

        state = {"owner-a": ["owner-a:1"]}

        def read_fenced():
            return {k: tuple(v) for k, v in state.items() if v}

        def run_call(argv, **_k):
            state["owner-a"] = []
            return 0, "resolved output"

        loops = {"owner-a": {"effect_reconcile": {
            "argv": ["skills/x/reconcile.py"], "occurrence_flag": "--occurrence",
            "resolve_flag": "--resolve"}}}
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "reconcile-calls.jsonl"
            reconcile(
                registry=_registry(loops), root=Path("/release"),
                run_call=run_call, read_fenced=read_fenced, log_path=log_path,
            )
            rows = [json.loads(line) for line in log_path.read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["owner_id"], "owner-a")
        self.assertEqual(rows[0]["occurrence_id"], "owner-a:1")
        self.assertTrue(rows[0]["closed"])
        self.assertEqual(rows[0]["exit_code"], 0)
        self.assertLessEqual(len(rows[0]["stdout_tail"]), 300)




class WakeBudgetTest(unittest.TestCase):
    def test_per_owner_timeout_is_passed_and_overrunning_calls_are_deferred(self):
        state = {"slow": ["slow:1"], "fast": ["fast:1", "fast:2"]}
        calls = []
        now = [0.0]

        def read_fenced():
            return {k: tuple(v) for k, v in state.items() if v}

        def run_call(argv, timeout):
            calls.append((argv[1], timeout))
            now[0] += timeout
            return 1, "inconclusive"

        loops = {
            "slow": {"effect_reconcile": {"argv": ["skills/slow.py"], "occurrence_flag": None,
                                          "resolve_flag": "--resolve", "timeout_seconds": 900}},
            "fast": {"effect_reconcile": {"argv": ["skills/fast.py"], "occurrence_flag": "--occurrence",
                                          "resolve_flag": "--resolve"}},
        }
        summary = reconcile(
            registry=_registry(loops), root=Path("/release"), budget_seconds=1000,
            clock=lambda: now[0], run_call=run_call, read_fenced=read_fenced, log_path=None,
        )
        # fast (60s default) runs first, then slow (900s) fits (60+900<=1000); the second
        # fast call would overrun the budget and is deferred, never killed mid-proof.
        self.assertEqual(calls, [("/release/skills/fast.py", 60), ("/release/skills/slow.py", 900)])
        self.assertEqual(summary["deferred_calls"], 1)
        self.assertEqual(summary["closed"], 0)


if __name__ == "__main__":
    unittest.main()


class RotatingStartTest(unittest.TestCase):
    def test_start_rotates_the_non_priority_owners_so_a_late_owner_gets_a_turn(self):
        targets = {name: [f"{name}:1"] for name in ("a", "b", "c", "d", "e", "f")}
        first = [o for o, _ in round_robin(targets, cap=2)]
        later = [o for o, _ in round_robin(targets, cap=2, start=4)]
        self.assertEqual(first, ["a", "b"])
        self.assertEqual(later, ["e", "f"])

    def test_priority_owners_are_always_first_regardless_of_the_rotation(self):
        targets = {name: [f"{name}:1"] for name in ("a", "b", "c", "fin")}
        calls = [o for o, _ in round_robin(targets, cap=2, priority_owners={"fin"}, start=2)]
        self.assertEqual(calls[0], "fin")
        self.assertEqual(calls[1], "c")

    def test_every_owner_is_served_over_consecutive_wakes(self):
        targets = {f"o{n:02d}": [f"o{n:02d}:1"] for n in range(41)}
        served = set()
        for wake in range(3):
            served |= {o for o, _ in round_robin(targets, cap=20, start=wake * 20)}
        self.assertEqual(served, set(targets))

    def test_reconcile_derives_a_different_start_per_wake_from_the_clock(self):
        seen = []
        loops = {f"o{n:02d}": {"effect_reconcile": {"argv": ["x.py"], "occurrence_flag": "--occurrence"}}
                 for n in range(6)}
        fenced = {k: (f"{k}:1",) for k in loops}
        for tick in (0.0, 600.0, 1200.0):
            reconcile(registry=_registry(loops), root=Path("/r"), cap=1, budget_seconds=100,
                      clock=lambda: tick, run_call=lambda argv, timeout=60: (seen.append(argv[argv.index("--occurrence") + 1]) or (0, "")),
                      read_fenced=lambda f=fenced: f, log_path=None, wake_epoch=tick)
        self.assertEqual(len(set(seen)), 3, seen)
