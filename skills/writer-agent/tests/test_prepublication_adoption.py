import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills/writer-agent/scripts"))

import article_generation_state as generation
import article_daily_start_control as start_control
import quality_repair_control as repair


class PrepublicationAdoptionTest(unittest.TestCase):
    def fixture(self, root: Path):
        run_id = "20260829-165022"
        run = root / "runs" / run_id
        gates = run / "gates"
        gates.mkdir(parents=True)
        prompt = run / "article-daily-prompt.txt"
        prompt.write_text("immutable prompt\n", encoding="utf-8")
        ledger = root / "articles.jsonl"
        ledger.write_text(
            "\n".join(
                json.dumps(
                    {
                        "run_id": run_id,
                        "platform": platform,
                        "lang": lang,
                        "published": False,
                        "live_url": None,
                        "state": "pending:media",
                        "reality_gate": None,
                    }
                )
                for platform, lang in (
                    ("note", "ja"),
                    ("substack", "ja"),
                    ("substack", "en"),
                    ("x-article", "ja"),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        state = generation.initialize(run, run_id, prompt, ledger)
        state["status"] = "provider-failed-ambiguous"
        state["attempts"] = [
            {
                "attempt": attempt,
                "status": "provider-failed-ambiguous",
                "return_code": 1,
                "boundary": "generated-or-staged-artifacts:article-ja.md",
            }
            for attempt in (1, 2, 3)
        ]
        (gates / "generation-state.json").write_text(
            json.dumps(state) + "\n", encoding="utf-8"
        )
        (run / "article-ja.md").write_text("日本語 draft\n", encoding="utf-8")
        (run / "article-en.md").write_text("English draft\n", encoding="utf-8")
        (gates / "editorial-ja.json").write_text('{"pass":false}\n', encoding="utf-8")
        (run / "headline-image.png").write_bytes(b"current image")
        return run, run_id, prompt, ledger

    def test_adopts_exact_exhausted_run_once_with_hash_bound_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, run_id, prompt, ledger = self.fixture(Path(tmp))
            state_path = run / "gates/generation-state.json"
            before = json.loads(state_path.read_text(encoding="utf-8"))

            result = generation.adopt_prepublication(run, run_id, prompt, ledger)

            state = json.loads(state_path.read_text(encoding="utf-8"))
            receipt_path = run / "gates/prepublication-adoption.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(result["action"], "adopted")
            self.assertEqual(state["status"], "quality-repair-ready")
            self.assertEqual(state["attempts"], before["attempts"])
            self.assertEqual(
                generation.resume_decision(run, run_id, prompt, ledger),
                {
                    "resumable": False,
                    "reason": "quality-repair-ready",
                    "status": "quality-repair-ready",
                },
            )
            self.assertEqual(receipt["from_status"], "provider-failed-ambiguous")
            self.assertEqual(receipt["to_status"], "quality-repair-ready")
            self.assertEqual(receipt["prompt_sha256"], generation.file_sha256(prompt))
            self.assertEqual(
                {item["path"] for item in receipt["draft_manifest"]},
                {"article-ja.md", "article-en.md"},
            )
            self.assertIn(
                "gates/editorial-ja.json",
                {item["path"] for item in receipt["artifact_manifest"]},
            )
            self.assertIn(
                "headline-image.png",
                {item["path"] for item in receipt["artifact_manifest"]},
            )
            state_bytes = state_path.read_bytes()
            receipt_bytes = receipt_path.read_bytes()

            replay = generation.adopt_prepublication(run, run_id, prompt, ledger)

            self.assertEqual(replay["action"], "unchanged")
            self.assertEqual(state_path.read_bytes(), state_bytes)
            self.assertEqual(receipt_path.read_bytes(), receipt_bytes)

            receipt["artifact_manifest_sha256"] = "0" * 64
            receipt["receipt_sha256"] = generation._adoption_receipt_hash(receipt)
            receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
            with self.assertRaises(generation.GenerationInvariant):
                generation.adopt_prepublication(run, run_id, prompt, ledger)

    def test_refreshes_prior_adoption_after_a_later_failed_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, run_id, prompt, ledger = self.fixture(Path(tmp))
            state_path = run / "gates/generation-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["attempts"] = state["attempts"][:2]
            state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

            generation.adopt_prepublication(run, run_id, prompt, ledger)
            prior = json.loads(
                (run / "gates/prepublication-adoption.json").read_text(encoding="utf-8")
            )
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["status"] = "provider-failed-ambiguous"
            state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
            (run / "article-ja.md").write_text("日本語 retry draft\n", encoding="utf-8")
            (run / "gates/quality-self-heal.json").write_text(
                "{\"status\":\"PENDING\"}\n", encoding="utf-8"
            )

            result = generation.adopt_prepublication(run, run_id, prompt, ledger)

            self.assertEqual(result["action"], "adopted-after-retry")
            history = run / "gates/prepublication-adoption-history" / f"{prior['receipt_sha256']}.json"
            self.assertTrue(history.is_file())
            current = json.loads(
                (run / "gates/prepublication-adoption.json").read_text(encoding="utf-8")
            )
            self.assertEqual(current["supersedes_receipt_sha256"], prior["receipt_sha256"])
            self.assertEqual(
                current["receipt_sha256"], generation._adoption_receipt_hash(current)
            )

    def test_staged_adoption_without_quality_receipt_can_resume_same_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, run_id, prompt, ledger = self.fixture(Path(tmp))
            state_path = run / "gates/generation-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["attempts"] = state["attempts"][:1]
            state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

            generation.adopt_prepublication(run, run_id, prompt, ledger)

            decision = generation.resume_decision(run, run_id, prompt, ledger)
            self.assertEqual(decision["resumable"], True)
            self.assertEqual(decision["reason"], "adopted-staged-prepublication")
            generation.begin(run, run_id, prompt, ledger, owner_pid=os.getpid())
            resumed = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(resumed["status"], "invoking")
            self.assertEqual(len(resumed["attempts"]), 2)

    def test_start_control_returns_generation_resume_for_staged_adoption(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, run_id, prompt, ledger = self.fixture(Path(tmp))
            state_path = run / "gates/generation-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["attempts"] = state["attempts"][:1]
            state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
            generation.adopt_prepublication(run, run_id, prompt, ledger)

            with patch.object(start_control, "proof", side_effect=start_control.QuarantineError("no proof")):
                decision = start_control.decide(Path(tmp), "2026-08-30")
            self.assertEqual(decision["action"], "resume-generation")
            self.assertEqual(decision["run_id"], run_id)
            self.assertEqual(decision["reason"], "same-jst-day-prepublication-provider-failure")

    def test_rebind_accepts_current_symlink_root_for_staged_adoption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "20260917-120000"
            run = root / "runs" / run_id
            gates = run / "gates"
            gates.mkdir(parents=True)
            current_link = root / "loops" / "current" / "skills" / "writer-agent"
            current_link.mkdir(parents=True)
            target_root = root / "loops" / "releases" / "next" / "skills" / "writer-agent"
            target_root.mkdir(parents=True)
            prompt = run / "article-daily-prompt.txt"
            prompt.write_text(f"writer_root={current_link}\n", encoding="utf-8")
            ledger = root / "articles.jsonl"
            ledger.write_text("", encoding="utf-8")
            state = generation.initialize(run, run_id, prompt, ledger)
            state["status"] = "provider-failed-ambiguous"
            state["attempts"] = [{
                "attempt": 1,
                "status": "provider-failed-ambiguous",
                "return_code": 1,
                "boundary": "generated-or-staged-artifacts:article-ja.md",
            }]
            (gates / "generation-state.json").write_text(
                json.dumps(state) + "\n", encoding="utf-8"
            )
            (run / "article-ja.md").write_text("日本語 draft\n", encoding="utf-8")
            (run / "article-en.md").write_text("English draft\n", encoding="utf-8")
            generation.adopt_prepublication(run, run_id, prompt, ledger)

            with patch.dict(os.environ, {"LOOPS_ROOT": str(root / "loops")}):
                result = generation.rebind_release(
                    run, run_id, prompt, ledger, target_root
                )

            self.assertEqual(result["action"], "rebound")
            self.assertIn(str(target_root), prompt.read_text(encoding="utf-8"))
            receipt = json.loads((gates / "prepublication-adoption.json").read_text())
            self.assertEqual(receipt["prompt_sha256"], generation.file_sha256(prompt))
            self.assertEqual(
                receipt["receipt_sha256"], generation._adoption_receipt_hash(receipt)
            )

    def test_rebind_accepts_exact_adoption_with_quality_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "20260917-120001"
            run = root / "runs" / run_id
            gates = run / "gates"
            gates.mkdir(parents=True)
            current_link = root / "loops" / "current" / "skills" / "writer-agent"
            current_link.mkdir(parents=True)
            target_root = root / "loops" / "releases" / "next" / "skills" / "writer-agent"
            target_root.mkdir(parents=True)
            prompt = run / "article-daily-prompt.txt"
            prompt.write_text(f"writer_root={current_link}\n", encoding="utf-8")
            ledger = root / "articles.jsonl"
            ledger.write_text("", encoding="utf-8")
            state = generation.initialize(run, run_id, prompt, ledger)
            state["status"] = "provider-failed-ambiguous"
            state["attempts"] = [{
                "attempt": 1,
                "status": "provider-failed-ambiguous",
                "return_code": 1,
                "boundary": "generated-or-staged-artifacts:article-ja.md",
            }]
            (gates / "generation-state.json").write_text(
                json.dumps(state) + "\n", encoding="utf-8"
            )
            (run / "article-ja.md").write_text("日本語 draft\n", encoding="utf-8")
            (run / "article-en.md").write_text("English draft\n", encoding="utf-8")
            (gates / "quality-self-heal.json").write_text(
                "{\"status\":\"PENDING\"}\n", encoding="utf-8"
            )
            generation.adopt_prepublication(run, run_id, prompt, ledger)

            with patch.dict(os.environ, {"LOOPS_ROOT": str(root / "loops")}):
                result = generation.rebind_release(
                    run, run_id, prompt, ledger, target_root
                )

            self.assertEqual(result["action"], "rebound")
            self.assertIn(str(target_root), prompt.read_text(encoding="utf-8"))
            receipt = json.loads((gates / "prepublication-adoption.json").read_text())
            self.assertEqual(receipt["prompt_sha256"], generation.file_sha256(prompt))
            self.assertEqual(
                receipt["receipt_sha256"], generation._adoption_receipt_hash(receipt)
            )

    def test_refuses_unsafe_evidence_before_mutation(self):
        cases = {
            "prompt hash drift": lambda run, prompt, ledger: prompt.write_text(
                "changed prompt\n", encoding="utf-8"
            ),
            "live row": lambda run, prompt, ledger: ledger.write_text(
                json.dumps({"run_id": run.name, "published": True}) + "\n",
                encoding="utf-8",
            ),
            "publication state": lambda run, prompt, ledger: (
                run / "gates/publication-state.json"
            ).write_text("{}\n", encoding="utf-8"),
            "symlink draft": self.replace_ja_with_symlink,
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                run, run_id, prompt, ledger = self.fixture(Path(tmp))
                before = (run / "gates/generation-state.json").read_bytes()
                mutate(run, prompt, ledger)

                with self.assertRaises(generation.GenerationInvariant):
                    generation.adopt_prepublication(run, run_id, prompt, ledger)

                self.assertEqual(
                    (run / "gates/generation-state.json").read_bytes(), before
                )
                self.assertFalse((run / "gates/prepublication-adoption.json").exists())

    def test_cli_adopts_non_resumable_attempt_before_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, run_id, prompt, ledger = self.fixture(Path(tmp))
            state_path = run / "gates/generation-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["attempts"] = state["attempts"][:2]
            state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "skills/writer-agent/scripts/article_generation_state.py"),
                    "--run-dir",
                    str(run),
                    "--run-id",
                    run_id,
                    "--prompt-file",
                    str(prompt),
                    "--ledger",
                    str(ledger),
                    "adopt-prepublication",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["action"], "adopted")
            self.assertEqual(
                json.loads(state_path.read_text(encoding="utf-8"))["status"],
                "quality-repair-ready",
            )

    def test_recovers_receipt_written_before_state_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, run_id, prompt, ledger = self.fixture(Path(tmp))
            state_path = run / "gates/generation-state.json"
            before = state_path.read_bytes()
            generation.adopt_prepublication(run, run_id, prompt, ledger)
            receipt_path = run / "gates/prepublication-adoption.json"
            receipt = receipt_path.read_bytes()
            state_path.write_bytes(before)

            result = generation.adopt_prepublication(run, run_id, prompt, ledger)

            self.assertEqual(result["action"], "recovered")
            self.assertEqual(receipt_path.read_bytes(), receipt)
            self.assertEqual(
                json.loads(state_path.read_text(encoding="utf-8"))["status"],
                "quality-repair-ready",
            )

    def test_quality_repair_plan_accepts_traceback_bound_adoption_and_begin_prepares_reader_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, run_id, prompt, ledger = self.fixture(Path(tmp))
            gates, traceback, quality_path = self.add_reader_traceback(run)
            generation.adopt_prepublication(run, run_id, prompt, ledger)
            adoption = json.loads(
                (gates / "prepublication-adoption.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                {
                    item["path"]: item["sha256"]
                    for item in adoption["artifact_manifest"]
                }["gates/quality-self-heal.json"],
                generation.file_sha256(quality_path),
            )

            decision = repair.plan(run, ledger)

            self.assertEqual(decision["status"], "READY")
            self.assertEqual(decision["run_id"], run_id)
            self.assertEqual(decision["source_defect"], "reader-terminal-receipt")
            self.assertEqual(
                decision["drafts"],
                {
                    "ja": generation.file_sha256(run / "article-ja.md"),
                    "en": generation.file_sha256(run / "article-en.md"),
                },
            )

            with patch.object(
                repair, "_quality_module", side_effect=AssertionError("must not assess")
            ):
                prepared = repair.begin(run, ledger)
            repair_state = json.loads(
                (gates / "quality-repair-state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                repair_state["qrr_lineage"], decision["qrr_lineage"]
            )

            self.assertEqual(prepared["status"], "prepared")
            self.assertEqual(prepared["quality_action"], "evaluate_reroute")
            prompt_text = Path(prepared["prompt_path"]).read_text(encoding="utf-8")
            self.assertIn("Run reader-testing-gate.sh for BOTH languages first", prompt_text)
            self.assertIn("editorial-gate.sh, identity-gate.sh, and reader-testing-gate.sh", prompt_text)
            self.assertIn("canonical media and CTA invariants", prompt_text)
            self.assertIn("quality_self_heal.py returns action=ready_to_freeze", prompt_text)
            archived = (
                run
                / "gates/quality-repair/epoch-1/original/quality-self-heal.json"
            )
            self.assertTrue(archived.is_file())
            self.assertEqual(archived.read_text(encoding="utf-8"), traceback)
            self.assertFalse((gates / "quality-self-heal.json").exists())
            self.assertFalse((run / "gates/publication-state.json").exists())
            self.assertFalse(generation.ledger_has_public_effect(ledger, run_id))

    def test_quality_repair_plan_refuses_missing_or_drifted_adoption_evidence(self):
        cases = {
            "missing receipt": lambda run, _prompt: (
                run / "gates/prepublication-adoption.json"
            ).unlink(),
            "traceback hash drift": lambda run, _prompt: (
                run / "gates/quality-self-heal.json"
            ).write_text(
                (run / "gates/quality-self-heal.json")
                .read_text(encoding="utf-8")
                .replace("line 132", "line 133"),
                encoding="utf-8",
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                run, run_id, prompt, ledger = self.fixture(Path(tmp))
                self.add_reader_traceback(run)
                generation.adopt_prepublication(run, run_id, prompt, ledger)
                mutate(run, prompt)

                decision = repair.plan(run, ledger)

                self.assertEqual(decision["status"], "REFUSED")
                self.assertEqual(decision["run_id"] if "run_id" in decision else None, None)
                self.assertFalse((run / "gates/quality-repair-state.json").exists())

    def test_provider_failed_plan_never_creates_adoption(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, run_id, prompt, ledger = self.fixture(Path(tmp))
            self.add_reader_traceback(run)
            with patch.object(
                repair.generation_state,
                "adopt_prepublication",
                side_effect=AssertionError("provider-failed state must not adopt"),
            ):
                decision = repair.plan(run, ledger)

            self.assertEqual(decision["status"], "REFUSED")
            self.assertFalse((run / "gates/prepublication-adoption.json").exists())

    def test_reader_receipt_defect_requires_exact_trace_and_missing_terminal(self):
        cases = {
            "normal JSON": lambda gates: (gates / "quality-self-heal.json").write_text(
                '{"version":2,"action":"block_freeze"}\n', encoding="utf-8"
            ),
            "different traceback": lambda gates: (gates / "quality-self-heal.json").write_text(
                "Traceback (most recent call last):\n"
                "QualitySelfHealError: another quality error\n",
                encoding="utf-8",
            ),
            "terminal exists": lambda gates: (
                gates / "reader-testing-gate-ja.terminal.json"
            ).write_text("{}\n", encoding="utf-8"),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                run, run_id, prompt, ledger = self.fixture(Path(tmp))
                gates, _traceback, _quality_path = self.add_reader_traceback(run)
                mutate(gates)
                generation.adopt_prepublication(run, run_id, prompt, ledger)

                decision = repair.plan(run, ledger)

                self.assertEqual(decision["status"], "REFUSED")
                self.assertNotEqual(
                    decision.get("reason"),
                    "tracked-reader-terminal-receipt-source-defect",
                )

    def test_production_recovery_owner_and_public_effect_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, run_id, prompt, ledger = self.fixture(root)
            gates, traceback, quality_path = self.add_reader_traceback(run)
            generation_state = json.loads((gates / "generation-state.json").read_text(encoding="utf-8"))
            generation_state["attempts"] = [
                {"attempt": 1, "status": "interrupted-safe", "return_code": 143, "boundary": "archived-prepublication-artifacts"},
                {"attempt": 2, "status": "interrupted-safe", "return_code": 143, "boundary": "archived-prepublication-artifacts"},
                {"attempt": 3, "status": "provider-failed-ambiguous", "return_code": 1, "boundary": "generated-or-staged-artifacts:article-en.md,article-ja.md,headline-image.png"},
            ]
            (gates / "generation-state.json").write_text(json.dumps(generation_state) + "\n", encoding="utf-8")
            ledger_rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            attempts = generation_state["attempts"]
            self.assertEqual([(a["attempt"], a["status"], a["return_code"], a["boundary"]) for a in attempts[:2]], [(1, "interrupted-safe", 143, "archived-prepublication-artifacts"), (2, "interrupted-safe", 143, "archived-prepublication-artifacts")])
            self.assertEqual((attempts[2]["attempt"], attempts[2]["status"], attempts[2]["return_code"]), (3, "provider-failed-ambiguous", 1))
            self.assertTrue(attempts[2]["boundary"].startswith("generated-or-staged-artifacts:"))
            self.assertTrue(all(name in attempts[2]["boundary"] for name in ("article-en.md", "article-ja.md", "headline-image.png")))
            self.assertEqual(len(ledger_rows), 4)
            self.assertEqual({(row["platform"], row["lang"]) for row in ledger_rows}, {("note", "ja"), ("substack", "ja"), ("substack", "en"), ("x-article", "ja")})
            self.assertTrue(all(row["published"] is False and row["live_url"] is None for row in ledger_rows))
            self.assertTrue(all((run / f"article-{lang}.md").is_file() for lang in ("ja", "en")))
            self.assertTrue((run / "headline-image.png").is_file())
            self.assertTrue(all(not (gates / f"reader-testing-gate-{lang}.terminal.json").exists() for lang in ("ja", "en")))
            self.assertEqual(quality_path.read_text(encoding="utf-8"), traceback)

            generation.adopt_prepublication(run, run_id, prompt, ledger)
            receipt = json.loads((gates / "prepublication-adoption.json").read_text(encoding="utf-8"))
            self.assertEqual({item["path"]: item["sha256"] for item in receipt["draft_manifest"]}, {"article-ja.md": generation.file_sha256(run / "article-ja.md"), "article-en.md": generation.file_sha256(run / "article-en.md")})
            self.assertEqual({item["path"]: item["sha256"] for item in receipt["artifact_manifest"] if item["path"] in {"headline-image.png", "gates/quality-self-heal.json"}}, {"headline-image.png": generation.file_sha256(run / "headline-image.png"), "gates/quality-self-heal.json": generation.file_sha256(quality_path)})
            with patch.object(start_control, "proof", side_effect=start_control.QuarantineError("no proof")):
                owner = start_control.decide(root, "2026-08-30")
            self.assertEqual(
                owner,
                {
                    "action": "skip-pending-worker",
                    "run_id": run_id,
                    "reason": "same-jst-day-owned-by-quality-repair",
                },
            )
            plan = repair.plan(run, ledger)
            self.assertEqual({key: plan[key] for key in ("status", "run_id", "source_defect", "reason")}, {"status": "READY", "run_id": run_id, "source_defect": "reader-terminal-receipt", "reason": "tracked-reader-terminal-receipt-source-defect"})
            self.assertEqual(plan["drafts"], {"ja": generation.file_sha256(run / "article-ja.md"), "en": generation.file_sha256(run / "article-en.md")})

            ledger.write_text(
                ledger.read_text(encoding="utf-8")
                + json.dumps(
                    {
                        "run_id": run_id,
                        "platform": "note",
                        "lang": "ja",
                        "published": True,
                        "live_url": "https://note.example/published",
                        "state": "live",
                        "reality_gate": "PASS",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with patch.object(start_control, "proof", side_effect=start_control.QuarantineError("no proof")):
                after_effect = start_control.decide(root, "2026-08-30")
            self.assertEqual(after_effect, {"action": "block-incomplete", "run_id": run_id, "reason": "same-jst-day-unclassified-run"})
            self.assertEqual(repair.plan(run, ledger), {"status": "REFUSED", "reason": "ledger-row-exists"})

    def test_prepared_quality_repair_refuses_post_begin_evidence_drift(self):
        cases = {
            "receipt deletion": lambda run: (
                run / "gates/prepublication-adoption.json"
            ).unlink(),
            "receipt tamper": lambda run: (
                run / "gates/prepublication-adoption.json"
            ).write_text("[]\n", encoding="utf-8"),
            "generation status": self.hand_edit_generation_status,
            "generation state symlink": self.make_generation_state_symlink,
            "original prompt drift": self.hand_edit_original_prompt,
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                run, run_id, prompt, ledger = self.fixture(Path(tmp))
                self.add_reader_traceback(run)
                generation.adopt_prepublication(run, run_id, prompt, ledger)
                repair.begin(run, ledger)
                mutate(run)

                decision = repair.plan(run, ledger)

                self.assertEqual(
                    decision,
                    {"status": "REFUSED", "reason": "quality-repair-evidence-invalid"},
                )

    def test_terminal_incomplete_rearms_same_attempt_once_from_editorial_source_defect(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, run_id, prompt, ledger = self.fixture(Path(tmp))
            self.add_reader_traceback(run)
            generation.adopt_prepublication(run, run_id, prompt, ledger)
            prepared = repair.begin(run, ledger)
            evidence = self.make_active_editorial_repair_evidence(run, prepared)

            decision = repair.plan(run, ledger)

            self.assertEqual(decision["status"], "READY")
            self.assertEqual(
                {
                    key: decision[key]
                    for key in (
                        "reason",
                        "run_id",
                        "run_dir",
                        "repair_epoch",
                        "attempts",
                        "prompt_path",
                        "prompt_sha256",
                    )
                },
                {
                    "reason": "tracked-active-editorial-repair-source-defect",
                    "run_id": run_id,
                    "run_dir": str(run.resolve()),
                    "repair_epoch": 1,
                    "attempts": 2,
                    "prompt_path": prepared["prompt_path"],
                    "prompt_sha256": prepared["prompt_sha256"],
                },
            )

            state_path = run / "gates/quality-repair-state.json"
            prior_state = state_path.read_bytes()
            invoking = repair.mark_invoking(run, ledger, owner_pid=os.getpid())
            self.assertEqual(invoking["attempts"], 2)
            self.assertEqual(invoking["status"], "invoking")
            recovery_path = run / "gates/quality-repair-source-recovery.json"
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            self.assertEqual(recovery["schema"], "writer.quality-repair-source-recovery")
            self.assertEqual(recovery["version"], 1)
            self.assertEqual(recovery["run_id"], run_id)
            self.assertEqual(
                recovery["reason"], "tracked-active-editorial-repair-source-defect"
            )
            self.assertEqual(recovery["recovery_attempt"], 1)
            self.assertEqual(
                recovery["prior_state_sha256"], hashlib.sha256(prior_state).hexdigest()
            )
            self.assertEqual(recovery["error_sha256"], evidence["error_sha256"])
            self.assertEqual(
                recovery["editorial_source_sha256"], evidence["editorial_source_sha256"]
            )
            self.assertEqual(recovery["drafts"], evidence["drafts"])
            self.assertEqual(recovery["owner_pid"], os.getpid())
            unsigned = {
                key: value
                for key, value in recovery.items()
                if key != "receipt_sha256"
            }
            self.assertEqual(
                recovery["receipt_sha256"],
                hashlib.sha256(
                    json.dumps(
                        unsigned,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
            )
            self.assertEqual(
                invoking["source_recovery_receipt_sha256"],
                hashlib.sha256(recovery_path.read_bytes()).hexdigest(),
            )
            recovery_bytes = recovery_path.read_bytes()

            result = repair.record_result(run, ledger, return_code=1)
            self.assertEqual(result["status"], "terminal-incomplete")
            self.assertEqual(
                repair.plan(run, ledger),
                {
                    "status": "REFUSED",
                    "reason": "quality-repair-source-recovery-already-recorded",
                },
            )
            with self.assertRaisesRegex(
                repair.QualityRepairError,
                "quality-repair-source-recovery-already-recorded",
            ):
                repair.mark_invoking(run, ledger, owner_pid=os.getpid())
            self.assertEqual(recovery_path.read_bytes(), recovery_bytes)

    def test_owner_prompt_recovery_evidence_fails_closed(self):
        cases = {
            "live prior owner": self.make_owner_recovery_live_owner,
            "missing first receipt": self.remove_first_source_recovery_receipt,
            "tampered first receipt": self.tamper_first_source_recovery_receipt,
            "missing orphan source authorization": self.disable_orphan_source_authorization,
            "alternate old prompt": self.make_owner_recovery_alternate_prompt,
            "existing owner receipt": self.make_existing_owner_recovery_receipt,
            "existing owner prompt": self.make_existing_owner_recovery_prompt,
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                run, run_id, prompt, ledger, _old_prompt = self.owner_recovery_fixture(
                    Path(tmp)
                )
                if name == "missing orphan source authorization":
                    with patch.object(
                        repair,
                        "_quality_self_heal_orphan_occurrence_source",
                        return_value=None,
                    ):
                        decision = repair.plan(run, ledger)
                else:
                    mutate(run)
                    decision = repair.plan(run, ledger)
                self.assertEqual(decision["status"], "REFUSED")
                self.assertNotEqual(
                    decision.get("reason"),
                    "tracked-repair-owner-prompt-source-defect",
                )

    def test_owner_prompt_recovery_crash_boundaries_resume_without_rewrite(self):
        for checkpoint in (
            "after-prompt-create",
            "after-receipt-create",
            "after-state-bind",
        ):
            with self.subTest(checkpoint=checkpoint), tempfile.TemporaryDirectory() as tmp:
                run, _run_id, _prompt, ledger, _old = self.owner_recovery_fixture(Path(tmp))
                state_path = run / "gates/quality-repair-state.json"
                prompt_path = run / "gates/quality-repair/epoch-1/prompts/owner-recovery-1.txt"
                receipt_path = run / "gates/quality-repair-owner-recovery.json"
                with patch.object(
                    repair,
                    "_owner_recovery_checkpoint",
                    side_effect=lambda phase: (
                        (_ for _ in ()).throw(RuntimeError(phase))
                        if phase == checkpoint else None
                    ),
                ):
                    with self.assertRaisesRegex(RuntimeError, checkpoint):
                        repair.mark_invoking(run, ledger, owner_pid=os.getpid())
                before = {
                    path: (path.read_bytes(), path.stat().st_ino)
                    for path in (prompt_path, receipt_path)
                    if path.exists()
                }
                resumed = repair.mark_invoking(run, ledger, owner_pid=os.getpid())
                self.assertEqual(resumed["status"], "invoking")
                self.assertEqual(resumed["attempts"], 2)
                for path, (bytes_before, inode_before) in before.items():
                    self.assertEqual(path.read_bytes(), bytes_before)
                    self.assertEqual(path.stat().st_ino, inode_before)

    def test_orphaned_owner_prompt_recovery_resumes_same_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _run_id, _prompt, ledger, _old = self.owner_recovery_fixture(Path(tmp))
            repair.mark_invoking(run, ledger, owner_pid=os.getpid())
            gates = run / "gates"
            state_path = gates / "quality-repair-state.json"
            owner_path = gates / "quality-repair-owner-recovery.json"
            owner = json.loads(owner_path.read_text(encoding="utf-8"))
            dead_pid = 999999
            owner["owner_pid"] = dead_pid
            owner["receipt_sha256"] = repair._receipt_hash(owner)
            owner_path.write_text(json.dumps(owner) + "\n", encoding="utf-8")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state.update({"status": "invoking", "owner_pid": dead_pid,
                          "started_at": "2026-08-31T00:00:00+00:00",
                          "owner_recovery_receipt_sha256": hashlib.sha256(owner_path.read_bytes()).hexdigest()})
            state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
            prompt = Path(state["prompt_path"])
            before = {path: (path.read_bytes(), path.stat().st_ino) for path in (
                gates / "quality-repair-source-recovery.json", owner_path, prompt)}
            decision = repair.plan(run, ledger)
            self.assertEqual(decision["reason"], "orphaned-owner-prompt-recovery")
            self.assertEqual(decision["attempts"], 2)
            self.assertEqual(decision["orphaned_owner_pid"], dead_pid)
            resumed = repair.mark_invoking(run, ledger, owner_pid=os.getpid())
            self.assertEqual(resumed["attempts"], 2)
            self.assertEqual(resumed["owner_pid"], os.getpid())
            for path, (body, inode) in before.items():
                self.assertEqual(path.read_bytes(), body)
                self.assertEqual(path.stat().st_ino, inode)
    def test_terminal_incomplete_editorial_repair_source_evidence_is_fail_closed(self):
        cases = {
            "wrong error": lambda run, evidence: (
                run / "gates/quality-self-heal-repair.err"
            ).write_text("QualitySelfHealError: another error\n", encoding="utf-8"),
            "current editorial hash": self.make_current_editorial_hash,
            "stale identity": self.make_stale_identity,
            "stale reader": self.make_stale_reader,
            "alternate repair prompt": self.make_alternate_repair_prompt,
            "symlink recovery receipt": self.make_symlink_recovery_receipt,
            "symlink repair error": self.make_symlink_repair_error,
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                run, run_id, prompt, ledger = self.fixture(Path(tmp))
                self.add_reader_traceback(run)
                generation.adopt_prepublication(run, run_id, prompt, ledger)
                prepared = repair.begin(run, ledger)
                evidence = self.make_active_editorial_repair_evidence(run, prepared)
                mutate(run, evidence)

                decision = repair.plan(run, ledger)

                self.assertEqual(decision["status"], "REFUSED")
                self.assertNotEqual(
                    decision.get("reason"),
                    "tracked-active-editorial-repair-source-defect",
                )

        with tempfile.TemporaryDirectory() as tmp:
            run, run_id, prompt, ledger = self.fixture(Path(tmp))
            self.add_reader_traceback(run)
            generation.adopt_prepublication(run, run_id, prompt, ledger)
            prepared = repair.begin(run, ledger)
            self.make_active_editorial_repair_evidence(run, prepared)
            with patch.object(
                repair,
                "_editorial_source_has_active_repair_authorization",
                return_value=False,
                create=True,
            ):
                decision = repair.plan(run, ledger)
            self.assertEqual(decision["status"], "REFUSED")

    def test_terminal_incomplete_owner_prompt_recovery_rearms_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, run_id, prompt, ledger = self.fixture(Path(tmp))
            self.add_reader_traceback(run)
            generation.adopt_prepublication(run, run_id, prompt, ledger)
            prepared = repair.begin(run, ledger)
            self.make_active_editorial_repair_evidence(run, prepared)
            first = repair.mark_invoking(run, ledger, owner_pid=999999)
            repair.record_result(run, ledger, return_code=1)

            old_prompt = Path(first["prompt_path"])
            old_prompt.write_text(
                old_prompt.read_text(encoding="utf-8").replace(
                    repair.OWNER_PROMPT_PROHIBITION + "\n", ""
                ),
                encoding="utf-8",
            )
            state_path = run / "gates/quality-repair-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["prompt_sha256"] = hashlib.sha256(old_prompt.read_bytes()).hexdigest()
            state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

            decision = repair.plan(run, ledger)
            self.assertEqual(decision["status"], "READY")
            self.assertEqual(decision["reason"], "tracked-repair-owner-prompt-source-defect")
            self.assertEqual(decision["attempts"], 2)
            self.assertEqual(decision["prompt_path"], str(old_prompt))
            old_prompt_bytes = old_prompt.read_bytes()
            prior_state = state_path.read_bytes()
            invoking = repair.mark_invoking(run, ledger, owner_pid=os.getpid())
            self.assertEqual(invoking["status"], "invoking")
            self.assertEqual(invoking["attempts"], 2)
            self.assertEqual(old_prompt.read_bytes(), old_prompt_bytes)
            new_prompt = run / "gates/quality-repair/epoch-1/prompts/owner-recovery-1.txt"
            self.assertEqual(
                new_prompt.read_bytes(),
                old_prompt_bytes.rstrip(b"\n") + b"\n\n"
                + repair.OWNER_PROMPT_PROHIBITION.encode("utf-8") + b"\n",
            )
            owner_receipt_path = run / "gates/quality-repair-owner-recovery.json"
            owner_receipt_bytes = owner_receipt_path.read_bytes()
            owner_receipt = json.loads(owner_receipt_bytes)
            self.assertEqual(owner_receipt["schema"], "writer.quality-repair-owner-recovery")
            self.assertEqual(owner_receipt["recovery_attempt"], 1)
            self.assertEqual(owner_receipt["prior_state_sha256"], hashlib.sha256(prior_state).hexdigest())
            self.assertEqual(owner_receipt["new_prompt_sha256"], hashlib.sha256(new_prompt.read_bytes()).hexdigest())
            self.assertEqual(owner_receipt["receipt_sha256"], repair._receipt_hash(owner_receipt))
            self.assertEqual(invoking["owner_recovery_receipt_sha256"], hashlib.sha256(owner_receipt_bytes).hexdigest())
            repair.record_result(run, ledger, return_code=1)
            self.assertEqual(repair.plan(run, ledger), {"status": "REFUSED", "reason": "quality-repair-owner-recovery-already-recorded"})
            with self.assertRaisesRegex(repair.QualityRepairError, "quality-repair-owner-recovery-already-recorded"):
                repair.mark_invoking(run, ledger, owner_pid=os.getpid())
            self.assertEqual(owner_receipt_path.read_bytes(), owner_receipt_bytes)

    @staticmethod
    def make_active_editorial_repair_evidence(run: Path, prepared: dict):
        gates = run / "gates"
        state_path = gates / "quality-repair-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update(
            {
                "status": "terminal-incomplete",
                "attempts": 2,
                "quality_action": "evaluate_reroute",
                "source_defect": "reader-terminal-receipt",
            }
        )
        state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
        error_path = gates / "quality-self-heal-repair.err"
        error_path.write_text(
            "Traceback (most recent call last):\n"
            "QualitySelfHealError: quality receipt snapshot hash binding failed\n",
            encoding="utf-8",
        )
        drafts = {}
        for lang in ("ja", "en"):
            article = run / f"article-{lang}.md"
            digest = hashlib.sha256(article.read_bytes()).hexdigest()
            drafts[lang] = digest
            (gates / f"identity-{lang}.json").write_text(
                json.dumps(
                    {"verdict": "PASS", "article_sha256": digest, "violations": []}
                )
                + "\n",
                encoding="utf-8",
            )
            (gates / f"editorial-{lang}.json").write_text(
                json.dumps(
                    {
                        "verdict": "FAIL",
                        "article_sha256": "0" * 64,
                        "requested_reasoning_effort": "high",
                        "fixes": ["revise the current draft"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        (gates / "reader-testing-gate-ja.terminal.json").write_text(
            json.dumps(
                {
                    "gate": "reader-testing-gate",
                    "lang": "ja",
                    "status": "revision-required",
                    "attempts": 2,
                    "exit_code": 75,
                    "article_sha256": drafts["ja"],
                    "payload": {
                        "verdict": "FAIL",
                        "unanswered_questions": ["q"],
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (gates / "reader-testing-gate-en.terminal.json").write_text(
            json.dumps(
                {
                    "gate": "reader-testing-gate",
                    "lang": "en",
                    "status": "advisory",
                    "attempts": 3,
                    "reason": "max-attempts-reached",
                    "article_sha256": drafts["en"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "drafts": drafts,
            "error_sha256": hashlib.sha256(error_path.read_bytes()).hexdigest(),
            "editorial_source_sha256": hashlib.sha256(
                (Path(__file__).resolve().parents[1] / "scripts/editorial-gate.sh").read_bytes()
            ).hexdigest(),
        }

    def owner_recovery_fixture(self, root: Path):
        run, run_id, prompt, ledger = self.fixture(root)
        self.add_reader_traceback(run)
        generation.adopt_prepublication(run, run_id, prompt, ledger)
        prepared = repair.begin(run, ledger)
        self.make_active_editorial_repair_evidence(run, prepared)
        first = repair.mark_invoking(run, ledger, owner_pid=999999)
        repair.record_result(run, ledger, return_code=1)
        old_prompt = Path(first["prompt_path"])
        old_prompt.write_text(
            old_prompt.read_text(encoding="utf-8").replace(
                repair.OWNER_PROMPT_PROHIBITION + "\n", ""
            ),
            encoding="utf-8",
        )
        state_path = run / "gates/quality-repair-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["prompt_sha256"] = hashlib.sha256(old_prompt.read_bytes()).hexdigest()
        state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
        return run, run_id, prompt, ledger, old_prompt

    @staticmethod
    def make_owner_recovery_live_owner(run: Path):
        state_path = run / "gates/quality-repair-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["owner_pid"] = os.getpid()
        state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

    @staticmethod
    def remove_first_source_recovery_receipt(run: Path):
        (run / "gates/quality-repair-source-recovery.json").unlink()

    @staticmethod
    def tamper_first_source_recovery_receipt(run: Path):
        path = run / "gates/quality-repair-source-recovery.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["owner_pid"] = 123
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    @staticmethod
    def disable_orphan_source_authorization(_run: Path):
        return None

    @staticmethod
    def make_owner_recovery_alternate_prompt(run: Path):
        state_path = run / "gates/quality-repair-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        alternate = run / "other-repair-prompt.txt"
        alternate.write_bytes(Path(state["prompt_path"]).read_bytes())
        state["prompt_path"] = str(alternate)
        state["prompt_sha256"] = hashlib.sha256(alternate.read_bytes()).hexdigest()
        state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

    @staticmethod
    def make_existing_owner_recovery_receipt(run: Path):
        (run / "gates/quality-repair-owner-recovery.json").write_text(
            "{}\n", encoding="utf-8"
        )

    @staticmethod
    def make_existing_owner_recovery_prompt(run: Path):
        path = run / "gates/quality-repair/epoch-1/prompts/owner-recovery-1.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("existing\n", encoding="utf-8")

    @staticmethod
    def make_current_editorial_hash(run: Path, evidence: dict):
        path = run / "gates/editorial-ja.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["article_sha256"] = evidence["drafts"]["ja"]
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    @staticmethod
    def make_stale_identity(run: Path, _evidence: dict):
        path = run / "gates/identity-ja.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["article_sha256"] = "0" * 64
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    @staticmethod
    def make_stale_reader(run: Path, _evidence: dict):
        path = run / "gates/reader-testing-gate-ja.terminal.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["article_sha256"] = "0" * 64
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    @staticmethod
    def make_alternate_repair_prompt(run: Path, _evidence: dict):
        state_path = run / "gates/quality-repair-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        original = Path(state["prompt_path"])
        alternate = run / "alternate-repair-prompt.txt"
        alternate.write_bytes(original.read_bytes())
        state["prompt_path"] = str(alternate)
        state["prompt_sha256"] = hashlib.sha256(alternate.read_bytes()).hexdigest()
        state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

    @staticmethod
    def make_symlink_recovery_receipt(run: Path, _evidence: dict):
        path = run / "gates/quality-repair-source-recovery.json"
        target = run.parent / "source-recovery-target.json"
        target.write_text("{}\n", encoding="utf-8")
        path.symlink_to(target)

    @staticmethod
    def make_symlink_repair_error(run: Path, evidence: dict):
        path = run / "gates/quality-self-heal-repair.err"
        target = run.parent / "repair-error-target.err"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)

    @staticmethod
    def hand_edit_generation_status(run: Path):
        state_path = run / "gates/generation-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["status"] = "provider-failed-ambiguous"
        state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

    @staticmethod
    def make_generation_state_symlink(run: Path):
        state_path = run / "gates/generation-state.json"
        target = run.parent / "generation-state-target.json"
        target.write_bytes(state_path.read_bytes())
        state_path.unlink()
        state_path.symlink_to(target)

    @staticmethod
    def hand_edit_original_prompt(run: Path):
        (run / "article-daily-prompt.txt").write_text(
            "changed original prompt\n", encoding="utf-8"
        )

    @staticmethod
    def add_reader_traceback(run: Path):
        gates = run / "gates"
        (gates / "topic-route.json").write_text(
            '{"topic_id":"writer-a4-reader-receipt","editorial_form":"explainer"}\n',
            encoding="utf-8",
        )
        traceback = (
            "Traceback (most recent call last):\n"
            "  File \"quality_self_heal.py\", line 132, in _snapshot_receipts\n"
            "    raise QualitySelfHealError(...)\n"
            "QualitySelfHealError: quality reader receipt is missing for ja\n"
        )
        quality_path = gates / "quality-self-heal.json"
        quality_path.write_text(traceback, encoding="utf-8")
        return gates, traceback, quality_path

    @staticmethod
    def replace_ja_with_symlink(run: Path, prompt: Path, ledger: Path):
        article = run / "article-ja.md"
        target = run.parent.parent / "outside-ja.md"
        target.write_text("outside\n", encoding="utf-8")
        article.unlink()
        article.symlink_to(target)


if __name__ == "__main__":
    unittest.main()
