import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from job_search_loop.agent_runner import AgentRunner, PassAlreadyRunning, TASK_CLASSES
from job_search_loop.mercor_pass import (
    _host_capabilities,
    _blocked_for_evidence_violation,
    build_context,
    deny_mercor_media_permissions,
    main,
    record_inspections,
    record_profile_sync,
    record_verified_submissions,
    validate_bounded_scan,
    validate_evidence_paths,
    validate_priority_scan,
    validate_submission_fit,
)


ROOT = Path(__file__).resolve().parents[1]


class MercorPassContractTests(unittest.TestCase):
    def test_media_permissions_are_denied_before_model_browser_work(self):
        class FakeWebSocket:
            def __init__(self):
                self.sent = []
                self.closed = False

            def send(self, value):
                self.sent.append(json.loads(value))

            def recv(self):
                return json.dumps({"id": len(self.sent), "result": {}})

            def close(self):
                self.closed = True

        connection = FakeWebSocket()
        deny_mercor_media_permissions(
            "ws://127.0.0.1:9222/devtools/page/owned",
            websocket_factory=lambda *_args, **_kwargs: connection,
        )
        self.assertEqual(
            [item["params"]["permission"]["name"] for item in connection.sent],
            ["microphone", "camera", "display-capture"],
        )
        self.assertTrue(all(
            item["method"] == "Browser.setPermission"
            and item["params"]["setting"] == "denied"
            and item["params"]["origin"] == "https://work.mercor.com"
            for item in connection.sent
        ))
        self.assertTrue(connection.closed)

    @staticmethod
    def _profile(path: Path) -> Path:
        path.write_text(json.dumps({
            "candidate": {"base": "Japan", "application_email": "operator@example.invalid"},
            "facts": [{"id": "education", "claim": "Bachelor studies", "evidence": "resume"}],
        }), encoding="utf-8")
        return path

    def test_inspections_become_a_durable_next_wake_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            record_inspections(state, {
                "inspected_listings": [{"listing_id": "list-seen", "decision": "not_fit"}]
            }, run_id="run-1")
            context = build_context(
                state_root=state,
                profile_path=self._profile(state / "profile.json"),
                resume_path=state / "resume.pdf",
                cdp_url="http://127.0.0.1:9222",
            )
            self.assertEqual(context["recently_inspected_listing_ids"], ["list-seen"])

    @patch("job_search_loop.mercor_pass._sysctl")
    @patch("job_search_loop.mercor_pass.platform.mac_ver", return_value=("15.6", ("", "", ""), ""))
    @patch("job_search_loop.mercor_pass.platform.machine", return_value="arm64")
    def test_context_proves_local_mac_eligibility(self, _machine, _mac_ver, sysctl):
        sysctl.side_effect = lambda key: {
            "machdep.cpu.brand_string": "Apple M4",
            "hw.model": "Mac16,10",
        }[key]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            context = build_context(
                state_root=state,
                profile_path=self._profile(state / "profile.json"),
                resume_path=state / "resume.pdf",
                cdp_url="http://127.0.0.1:9222",
            )
            self.assertEqual(context["host_capabilities"], {
                "architecture": "arm64", "macos_version": "15.6",
                "apple_silicon": True, "macos_sequoia_or_newer": True,
                "chip": "Apple M4", "machine_model": "Mac16,10",
            })
            self.assertEqual(context["mercor_auth_context"], {
                "login_method": "email",
                "account_email": "operator@example.invalid",
            })

    def test_context_binds_private_profile_and_resume_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            profile = self._profile(state / "profile.json")
            resume = state / "resume.pdf"
            resume.write_bytes(b"resume")
            context = build_context(
                state_root=state,
                profile_path=profile,
                resume_path=resume,
                cdp_url="http://127.0.0.1:9222",
            )
            self.assertEqual(context["profile_material"]["profile_sha256"],
                             hashlib.sha256(profile.read_bytes()).hexdigest())
            self.assertEqual(context["profile_material"]["resume_sha256"],
                             hashlib.sha256(resume.read_bytes()).hexdigest())
            self.assertEqual(context["profile_material"]["verified_fact_ids"], ["education"])

    def test_context_exposes_only_private_profile_proposal_path_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            profile = self._profile(state / "profile.json")
            proposal = state / "profile-proposal.json"
            proposal.write_text('{"profile_version":"v1"}\n', encoding="utf-8")
            context = build_context(
                state_root=state,
                profile_path=profile,
                resume_path=state / "resume.pdf",
                cdp_url="http://127.0.0.1:9222",
            )
            self.assertEqual(context["profile_proposal_path"], str(proposal.resolve()))

    def test_profile_sync_readback_is_recorded_without_private_field_values(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "profile-proposal.json").write_text(json.dumps({
                "profile_version": "profile-v1",
                "field_hashes": {"summary": "hash"},
                "resume_sha256": "resume-hash",
            }), encoding="utf-8")
            evidence_root = state / "evidence"
            evidence_root.mkdir()
            (evidence_root / "profile-readback.json").write_text("{}\n", encoding="utf-8")
            record_profile_sync(state, {
                "profile_sync": {
                    "status": "synced",
                    "authenticated": True,
                    "resume_visible": True,
                    "parser_reviewed": True,
                    "profile_version": "profile-v1",
                    "field_hashes": {"summary": "hash"},
                    "resume_sha256": "resume-hash",
                    "evidence_ref": "profile-readback.json",
                }
            }, run_id="run-profile", evidence_root=evidence_root)
            row = json.loads((state / "profile-sync.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(row["status"], "synced")
            self.assertEqual(row["profile_version"], "profile-v1")
            self.assertTrue(row["authenticated"])
            self.assertEqual(row["field_hashes"], {"summary": "hash"})
            self.assertNotIn("summary", row)
            self.assertEqual((state / "profile-sync.jsonl").stat().st_mode & 0o777, 0o600)

    def test_profile_sync_cannot_be_marked_synced_without_authentication(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            record_profile_sync(state, {
                "profile_sync": {
                    "status": "synced",
                    "authenticated": False,
                    "resume_visible": True,
                    "parser_reviewed": True,
                    "profile_version": "profile-v1",
                    "field_hashes": {"summary": "hash"},
                    "resume_sha256": "resume-hash",
                    "evidence_ref": "profile-readback.json",
                }
            }, run_id="run-profile")
            row = json.loads((state / "profile-sync.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(row["status"], "unknown")

    def test_profile_sync_cannot_bind_a_different_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            record_profile_sync(state, {
                "profile_sync": {
                    "status": "synced",
                    "authenticated": True,
                    "resume_visible": True,
                    "parser_reviewed": True,
                    "profile_version": "profile-v1",
                    "field_hashes": {"summary": "hash"},
                    "resume_sha256": "stale-resume",
                    "evidence_ref": "profile-readback.json",
                }
            }, run_id="run-profile", expected_resume_sha256="current-resume")
            row = json.loads((state / "profile-sync.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(row["status"], "unknown")

    def test_profile_sync_requires_current_pass_evidence_file(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "profile-proposal.json").write_text(json.dumps({
                "profile_version": "profile-v1",
                "field_hashes": {"summary": "hash"},
                "resume_sha256": "resume-hash",
            }), encoding="utf-8")
            evidence_root = state / "evidence"
            evidence_root.mkdir()
            record_profile_sync(state, {
                "profile_sync": {
                    "status": "synced",
                    "authenticated": True,
                    "resume_visible": True,
                    "parser_reviewed": True,
                    "profile_version": "profile-v1",
                    "field_hashes": {"summary": "hash"},
                    "resume_sha256": "resume-hash",
                    "evidence_ref": "missing.json",
                }
            }, run_id="run-profile", evidence_root=evidence_root)
            row = json.loads((state / "profile-sync.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(row["status"], "unknown")

    def test_profile_sync_promotes_unknown_when_exact_readback_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "profile-proposal.json").write_text(json.dumps({
                "profile_version": "profile-v1",
                "field_hashes": {"claims": "hash"},
                "resume_sha256": "resume-hash",
            }), encoding="utf-8")
            evidence_root = state / "evidence"
            evidence_root.mkdir()
            (evidence_root / "profile-readback.json").write_text("{}\n", encoding="utf-8")
            record_profile_sync(state, {
                "profile_sync": {
                    "status": "unknown",
                    "authenticated": True,
                    "resume_visible": True,
                    "parser_reviewed": True,
                    "profile_version": "profile-v1",
                    "field_hashes": {"claims": "hash"},
                    "resume_sha256": "resume-hash",
                    "evidence_ref": "profile-readback.json",
                }
            }, run_id="run-profile", evidence_root=evidence_root)
            row = json.loads((state / "profile-sync.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(row["status"], "unchanged")

    @patch("job_search_loop.mercor_pass.subprocess.run")
    def test_host_capabilities_keep_unknown_sysctl_values_explicit(self, run):
        run.return_value.returncode = 1
        run.return_value.stdout = ""
        facts = _host_capabilities()
        self.assertEqual(facts["chip"], "")
        self.assertEqual(facts["machine_model"], "")

    def test_mercor_is_retired_locally_but_keeps_portable_thirty_minute_cadence(self):
        registry = json.loads((ROOT.parents[1] / "config" / "loop-registry.json").read_text())
        self.assertNotIn("job-search-mercor", registry["loops"])
        self.assertIn("ai.anicca.job-search-mercor", registry["retired_labels"])
        provider_registry = (ROOT.parents[1] / "loops" / "job-hunter" / "registry.yaml").read_text()
        mercor = provider_registry.split("  - id: mercor\n", 1)[1]
        self.assertIn("interval_seconds: 1800", mercor)

    def _run_shell_with_pass_rc(self, *, pass_rc: int, pass_stderr: str):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        calls = root / "reporting-call.json"
        fake_python = root / "python"
        fake_python.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "argv = sys.argv[1:]\n"
            "if argv[:2] == ['-m', 'job_search_loop.browser_owner']:\n"
            "    pathlib.Path(argv[argv.index('--output') + 1]).write_text('{}\\n')\n"
            "    raise SystemExit(0)\n"
            "if argv[:2] == ['-m', 'job_search_loop.mercor_pass']:\n"
            "    print(os.environ['MERCOR_TEST_PASS_STDERR'], file=sys.stderr, end='')\n"
            "    raise SystemExit(int(os.environ['MERCOR_TEST_PASS_RC']))\n"
            "if argv[:2] == ['-m', 'job_search_loop.mercor_reporting']:\n"
            "    pathlib.Path(os.environ['MERCOR_TEST_REPORTING_CALL']).write_text(json.dumps(argv))\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit(0)\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o700)
        result = subprocess.run(
            ["/bin/zsh", str(ROOT / "scripts" / "run-mercor.sh")],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(root / "home"),
                "XDG_DATA_HOME": str(root / "data"),
                "JOB_SEARCH_STATE_ROOT": str(root / "state"),
                "JOB_SEARCH_PYTHON": str(fake_python),
                "MERCOR_TEST_PASS_RC": str(pass_rc),
                "MERCOR_TEST_PASS_STDERR": pass_stderr,
                "MERCOR_TEST_REPORTING_CALL": str(calls),
            },
        )
        reporting_call = json.loads(calls.read_text(encoding="utf-8"))
        return result, reporting_call

    def test_task_class_is_modelled_browser_lane(self):
        self.assertEqual(TASK_CLASSES["mercor_pass"], "browser-lane-agent")

    def test_prompt_contains_model_led_submit_guard_and_human_stop(self):
        prompt = " ".join(
            (ROOT / "prompts" / "mercor-pass.md").read_text(encoding="utf-8").split()
        )
        for required in (
            "model-led",
            "`N of N` and `100%`",
            "Submit application",
            "continue to the next distinct listing",
            "Apply maximally among reasonable-shot roles",
            "never retry",
            "needs_human",
            "Never click `Google`, `Okta`, or",
            "Never write evidence",
            "only the current `evidence_dir`",
            "exact `evidence_dir` supplied",
            "never inspect or reuse an older `model-pass-*` directory",
            "visible pagination controls",
            "button titled `Page N` or `Next`",
            "remaining pages up to page 4",
            "bounded maximum of four total Explore pages",
            "twelve candidate detail pages per wake",
            "detail pages per wake",
            "Never stop after the first Explore page",
            "Start every wake at Explore page 1 when pagination is visible",
            "Collect the distinct listing cards from the current page before opening detail",
            "Do not spend detail slots in DOM order",
            "inspect pages 1 through 4 in order",
            "Submit every ready distinct listing",
            "immediately return a",
            "do not spend the current wake's terminal budget after an accepted provider effect",
            "current-pass submitted set",
            "python3 -m job_search_loop.mercor_submit_guard",
            "--provider-fit-status",
            "--ranking-band",
            "--application-state",
            '"claimed": true',
            '"claimed": false',
            "capability_catalog_path",
            "Japan-eligible Japanese-language",
            "host_capabilities",
            "job_search_loop.mercor_human_gate_notify",
            "Never open or enter a person-bound step",
            "Inspect an existing incomplete application only through its application card",
            "Continue application when the next step is reversible",
            "Do not click the person-bound control or enter its flow",
            "a `Continue application` navigation is allowed solely to reach earlier reversible steps",
            "go directly to Explore while preserving the listing's resumable state",
            "Prefer a visible `1-click apply` candidate",
            "resume the same application",
            "Never invent a credential, experience, language level, or legal answer",
            "camera, microphone, or screen-sharing permission",
            "Do not click an interview or assessment step",
            "Do not call browser media-device or permission APIs",
            "application summary is sufficient evidence",
            "skip that candidate for the rest of this wake without waiting",
            "The first two shell/browser commands",
            "at most 120 lines",
            "Live browser progress comes before repository research",
            "submit it immediately after the guard and official readback",
            "One broken card must not block the whole pass",
            "invoke `.click()` once on that",
            "ranking signals rather",
            "Missing years, degrees, or experience evidence is medium",
            "unless Mercor explicitly marks the condition as required or blocked",
            "shared_apply_context.policy.ranking.band_definitions",
            "overlap alone never makes a senior/specialist role high",
            "low_fit_person_bound_skipped",
            "candidate is not submission-eligible",
            "no_reasonable_shot",
            "owned by the deterministic email-auth adapter",
            "Never submit or retry login from this model pass",
            "do not use Job Hunter policy",
            "profile_material",
            "2–4 representative",
            "copy the exact profile_version and field hashes from the supplied profile proposal",
            "save a fresh local Profile/Résumé readback JSON",
            "a provider URL alone is not evidence",
            "highest-priority card by visible title",
            "use the visible Filter/Search controls",
            "Japan, Japanese, Developer, automation, AI agent, Coding",
            "Do not open existing incomplete application cards before the target search queue",
            "human_gate_store",
            "application_report_outbox",
            "application_report_telegram_env",
            "--gate-store",
            "--outbox",
            "Do not pass `state_root` as `--gate-store`",
            "profile_sync",
            "field hashes",
        ):
            self.assertIn(required, prompt)
        self.assertNotIn("Choose at most one new listing", prompt)
        self.assertNotIn("Never click an existing incomplete application", prompt)
        self.assertNotIn("Do not click `Continue application` when a person-bound step remains", prompt)
        self.assertNotIn("Do not resume an already-incomplete application", prompt)

    def test_legacy_job_hunter_reference_only_points_to_mercor_canon(self):
        reference = (
            ROOT.parents[1] / "skills" / "job-hunter" / "references" / "mercor.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(reference.strip(), "Mercor policy → `skills/mercor/SKILL.md`")

    def test_result_contract_allows_every_bounded_candidate_to_be_submitted(self):
        schema = json.loads(
            (ROOT / "schemas" / "mercor-pass-result.v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["submitted"]["maxItems"], 12)

    def test_result_contract_requires_provider_fit_evidence(self):
        schema = json.loads(
            (ROOT / "schemas" / "mercor-pass-result.v1.schema.json").read_text(encoding="utf-8")
        )
        inspected = schema["properties"]["inspected_listings"]["items"]
        self.assertIn("provider_fit_status", inspected["required"])
        self.assertIn("requirement_evidence", inspected["required"])
        self.assertIn("strategy_version", inspected["required"])
        self.assertEqual(
            inspected["properties"]["provider_fit_status"]["enum"],
            ["allowed", "warning", "blocked", "not_shown", "unknown"],
        )

    def test_result_contract_requires_profile_sync_for_strict_provider_schema(self):
        schema = json.loads(
            (ROOT / "schemas" / "mercor-pass-result.v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertIn("profile_sync", schema["required"])
        profile_sync = schema["properties"]["profile_sync"]
        self.assertEqual(
            set(profile_sync["required"]),
            set(profile_sync["properties"]),
        )
        field_hashes = profile_sync["properties"]["field_hashes"]
        self.assertFalse(field_hashes.get("additionalProperties", True))
        self.assertEqual(field_hashes["required"], ["claims"])

    def test_missing_requirement_evidence_accepts_null_fact_id(self):
        schema = json.loads(
            (ROOT / "schemas" / "mercor-pass-result.v1.schema.json").read_text(encoding="utf-8")
        )
        result = {
            "status": "observed_no_action",
            "profile_sync": {
                "status": "unchanged",
                "authenticated": True,
                "resume_visible": True,
                "parser_reviewed": True,
                "profile_version": "profile-v1",
                "field_hashes": {"claims": "a" * 64},
                "resume_sha256": "b" * 64,
                "evidence_ref": "profile-readback.json",
            },
            "inspected_listings": [{
                "listing_id": "list-missing-proof",
                "url": "https://work.mercor.com/explore?listingId=list-missing-proof",
                "title": "Finance Evaluator",
                "application_state": "ready",
                "submit_visible": True,
                "decision": "rank_medium",
                "ranking_band": "medium",
                "ranking_evidence": ["Related finance-services work; years evidence missing"],
                "provider_fit_status": "warning",
                "requirement_evidence": [{
                    "requirement": "3+ years hands-on finance",
                    "fact_id": None,
                    "disposition": "missing_preferred",
                }],
                "strategy_version": "mercor-fit-evidence-v1",
            }],
            "submitted": [], "needs_human": [], "blocked": [],
            "evidence": {"page_url": "https://work.mercor.com/explore", "screenshot_path": "", "dom_path": ""},
        }
        AgentRunner.validate(result, schema)

    def test_blocked_fit_cannot_be_submitted(self):
        with self.assertRaisesRegex(ValueError, "blocked_fit_submitted"):
            validate_submission_fit({
                "submitted": [{"listing_id": "list-blocked"}],
                "inspected_listings": [{
                    "listing_id": "list-blocked",
                    "provider_fit_status": "blocked",
                    "ranking_band": "medium",
                }],
            })

    def test_low_fit_cannot_be_submitted(self):
        with self.assertRaisesRegex(ValueError, "low_fit_submitted"):
            validate_submission_fit({
                "submitted": [{"listing_id": "list-low"}],
                "inspected_listings": [{
                    "listing_id": "list-low",
                    "provider_fit_status": "unknown",
                    "ranking_band": "low",
                }],
            })

    def test_nonblocked_pass_cannot_quit_after_two_of_twelve_visible_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dom = root / "page.html"
            dom.write_text("\n".join(
                f'<a href="/explore?listingId=list_{index}">Role</a>'
                for index in range(12)
            ), encoding="utf-8")
            result = {
                "status": "observed_no_action",
                "inspected_listings": [
                    {"listing_id": "list_0"}, {"listing_id": "list_1"}
                ],
                "evidence": {"dom_path": str(dom)},
            }
            with self.assertRaisesRegex(ValueError, "bounded_scan_incomplete:2_of_12"):
                validate_bounded_scan(result)

    def test_transient_blocker_may_end_a_partial_scan(self):
        validate_bounded_scan({
            "status": "blocked",
            "inspected_listings": [],
            "evidence": {"dom_path": "/not/read"},
        })

    def test_nonblocked_pass_must_inspect_observed_japanese_and_pending_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "page.json").write_text(
                '<a href="/explore?listingId=list_jp"><h2 data-test="listing-title">'
                'Bilingual Writer - Japanese (Japan)</h2></a>',
                encoding="utf-8",
            )
            result = {"status": "observed_no_action", "inspected_listings": []}
            with self.assertRaisesRegex(ValueError, "priority_scan_incomplete"):
                validate_priority_scan(result, root)
            result["inspected_listings"] = [
                {"listing_id": "list_jp"}
            ]
            validate_priority_scan(result, root)

    def test_current_skill_and_spec_match_continuous_application_policy(self):
        skill = (ROOT.parents[1] / "skills" / "mercor" / "SKILL.md").read_text()
        self.assertIn("30-minute", skill)
        self.assertIn("every ready listing", skill)
        self.assertIn("material required language, location, domain, or seniority contradiction", skill)
        self.assertIn("Missing or preferred evidence remains eligible medium", skill)
        self.assertNotIn("existing hourly Job Hunter loop", skill)
        self.assertNotIn("submit exactly one new listing", skill)
        spec = (
            ROOT.parents[1]
            / "docs"
            / "superpowers"
            / "specs"
            / "2026-08-22-mercor-life-manager-consolidation.md"
        ).read_text()
        self.assertIn("30-minute `mercor-revenue-application` owner", spec)
        self.assertIn("submit every grounded ready listing", spec)

    def test_success_result_contract_validates(self):
        schema = json.loads(
            (ROOT / "schemas" / "mercor-pass-result.v1.schema.json").read_text(encoding="utf-8")
        )
        result = {
            "status": "submitted",
            "profile_sync": {
                "status": "synced",
                "authenticated": True,
                "resume_visible": True,
                "parser_reviewed": True,
                "profile_version": "profile-v1",
                "field_hashes": {"claims": "a" * 64},
                "resume_sha256": "b" * 64,
                "evidence_ref": "profile-readback.json",
            },
            "inspected_listings": [{
                "listing_id": "list-test",
                "url": "https://work.mercor.com/jobs/test",
                "title": "Software Evaluator",
                "application_state": "3/3",
                "submit_visible": True,
                "decision": "submitted",
                "ranking_band": "high",
                "ranking_evidence": ["verified resume overlap"],
                "provider_fit_status": "allowed",
                "requirement_evidence": [{
                    "requirement": "Relevant AI experience",
                    "fact_id": "verified-ai",
                    "disposition": "verified",
                }],
                "strategy_version": "mercor-fit-evidence-v1",
            }],
            "submitted": [{
                "listing_id": "list-test",
                "title": "Software Evaluator",
                "url": "https://work.mercor.com/jobs/test",
                "status": "submitted_pending_review",
                "evidence_url": "https://work.mercor.com/jobs/apply/test",
                "evidence_path": "/tmp/evidence.json",
            }],
            "needs_human": [],
            "blocked": [],
            "evidence": {
                "page_url": "https://work.mercor.com/jobs/apply/test",
                "screenshot_path": "/tmp/screenshot.png",
                "dom_path": "/tmp/dom.json",
            },
        }
        AgentRunner.validate(result, schema)

    def test_evidence_violation_fallback_keeps_strict_profile_sync_shape(self):
        schema = json.loads(
            (ROOT / "schemas" / "mercor-pass-result.v1.schema.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            fallback = _blocked_for_evidence_violation(
                {"status": "submitted", "inspected_listings": [], "submitted": [],
                 "needs_human": [], "blocked": [], "evidence": {}},
                Path(directory),
                ValueError("stale evidence"),
            )
        AgentRunner.validate(fallback, schema)
        self.assertEqual(fallback["profile_sync"]["status"], "blocked")
        self.assertEqual(fallback["profile_sync"]["field_hashes"], {"claims": "unavailable"})

    def test_runner_snapshots_prompt_and_schema_into_private_pass_evidence(self):
        script = (ROOT / "scripts" / "run-mercor.sh").read_text(encoding="utf-8")
        for required in (
            'PASS_PROMPT="$EVIDENCE/mercor-pass.md"',
            'PASS_SCHEMA="$EVIDENCE/mercor-pass-result.v1.schema.json"',
            'cp "$JOB_SEARCH_APP_ROOT/schemas/mercor-pass-result.v1.schema.json" "$PASS_SCHEMA"',
            '--prompt "$PASS_PROMPT"',
            '--schema "$PASS_SCHEMA"',
        ):
            self.assertIn(required, script)

    def test_runner_normalizes_model_evidence_modes_after_the_pass(self):
        script = (ROOT / "scripts" / "run-mercor.sh").read_text(encoding="utf-8")
        self.assertIn('find "$EVIDENCE" -type d -exec chmod 700 {} +', script)
        self.assertIn('find "$EVIDENCE" -type f -exec chmod 600 {} +', script)

    def test_busy_runner_returns_75_without_a_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence" / "agent"
            profile = self._profile(root / "profile.json")
            with patch(
                "job_search_loop.mercor_pass.run_pass",
                side_effect=PassAlreadyRunning(),
            ), patch("job_search_loop.mercor_pass.deny_mercor_media_permissions"):
                self.assertEqual(main([
                    "--state-root", str(root / "state"),
                    "--profile", str(profile),
                    "--resume", str(root / "resume.pdf"),
                    "--cdp-url", "http://127.0.0.1:9334",
                    "--cdp-page-ws", "ws://127.0.0.1:9334/devtools/page/owned",
                    "--prompt", str(root / "prompt.md"),
                    "--schema", str(root / "schema.json"),
                    "--evidence-dir", str(evidence),
                    "--workdir", str(root),
                    "--run-id", "busy",
                ]), 75)
            self.assertFalse((evidence / "mercor-pass-summary.json").exists())

    def test_shell_maps_only_identified_busy_to_already_running(self):
        busy, busy_call = self._run_shell_with_pass_rc(
            pass_rc=75,
            pass_stderr="LIFE_MANAGER_PROVIDER_LEASE_BUSY\n",
        )
        self.assertEqual(busy.returncode, 0, busy.stderr)
        self.assertEqual(
            busy_call[busy_call.index("--reason") + 1],
            "mercor_pass_already_running",
        )
        budget, budget_call = self._run_shell_with_pass_rc(
            pass_rc=75,
            pass_stderr="budget blocked\n",
        )
        self.assertEqual(budget.returncode, 75, budget.stderr)
        self.assertEqual(
            budget_call[budget_call.index("--reason") + 1],
            "mercor_runner_failed",
        )

    def test_evidence_paths_must_stay_inside_current_private_pass(self):
        with self.subTest("stale evidence path is rejected"):
            with self.assertRaises(ValueError):
                validate_evidence_paths(
                    {
                        "status": "needs_human",
                        "evidence": {
                            "page_url": "https://work.mercor.com/explore",
                            "screenshot_path": "/tmp/old-pass/screenshot.png",
                            "dom_path": "/tmp/old-pass/dom.json",
                        },
                        "submitted": [],
                    },
                    Path("/tmp/current-pass"),
                )

    def test_evidence_paths_accept_existing_files_inside_current_private_pass(self):
        with self.subTest("current evidence is accepted"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                screenshot = root / "screenshot.png"
                dom = root / "dom.json"
                screenshot.write_bytes(b"png")
                dom.write_text("{}", encoding="utf-8")
                validate_evidence_paths(
                    {
                        "status": "needs_human",
                        "evidence": {
                            "page_url": "https://work.mercor.com/explore",
                            "screenshot_path": str(screenshot),
                            "dom_path": str(dom),
                        },
                        "submitted": [],
                    },
                    root,
                )

    def test_context_binds_the_current_evidence_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            state.mkdir()
            context = build_context(
                state_root=state,
                profile_path=self._profile(root / "profile.json"),
                resume_path=root / "resume.pdf",
                cdp_url="http://127.0.0.1:9334",
                evidence_dir=root / "evidence" / "current-pass",
            )
            self.assertEqual(
                context["evidence_dir"],
                str((root / "evidence" / "current-pass").resolve()),
            )

    def test_context_exposes_file_paths_for_human_gate_notification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "mercor" / "application"
            state.mkdir(parents=True)
            job_search_state = root / "job-search"
            profile = self._profile(root / "profile.json")
            with patch.dict(
                os.environ,
                {"JOB_SEARCH_STATE_ROOT": str(job_search_state)},
                clear=False,
            ):
                context = build_context(
                    state_root=state,
                    profile_path=profile,
                    resume_path=root / "resume.pdf",
                    cdp_url="http://127.0.0.1:9222",
                )
            self.assertEqual(
                context["human_gate_store"],
                str((state / "human-gates.jsonl").resolve()),
            )
            self.assertEqual(
                context["application_report_outbox"],
                str((job_search_state / "telegram-outbox.sqlite3").resolve()),
            )
            self.assertNotEqual(context["human_gate_store"], str(state.resolve()))
            self.assertNotEqual(context["application_report_outbox"], str(state.resolve()))

    def test_context_deduplicates_persistent_pre_effect_claim_after_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            state.mkdir()
            (state / "submission-fences.jsonl").write_text(
                '{"listing_id":"list-claimed","status":"submit_claimed"}\n',
                encoding="utf-8",
            )
            context = build_context(
                state_root=state,
                profile_path=self._profile(root / "profile.json"),
                resume_path=root / "resume.pdf",
                cdp_url="http://127.0.0.1:9334",
            )
            self.assertIn("list-claimed", context["submitted_listing_ids"])
            self.assertEqual(
                context["submission_fence_ledger"],
                str((state / "submission-fences.jsonl").resolve()),
            )

    def test_verified_submissions_are_recorded_once_for_next_wake(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            result = {
                "status": "submitted",
                "submitted": [
                    {
                        "listing_id": "list-one",
                        "title": "Software Evaluator",
                        "url": "https://work.mercor.com/jobs/list-one/software-evaluator",
                        "status": "submitted_pending_review",
                        "evidence_url": "https://work.mercor.com/jobs/apply/candidate-one",
                        "evidence_path": "/tmp/evidence-one.json",
                    },
                    {
                        "listing_id": "list-two",
                        "title": "Data Evaluator",
                        "url": "https://work.mercor.com/jobs/list-two/data-evaluator",
                        "status": "submitted_pending_review",
                        "evidence_url": "https://work.mercor.com/jobs/apply/candidate-two",
                        "evidence_path": "/tmp/evidence-two.json",
                    },
                ],
            }
            record_verified_submissions(state, result, run_id="run-1")
            record_verified_submissions(state, result, run_id="run-replay")
            ledger = state / "applications.jsonl"
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual([row["listing_id"] for row in rows], ["list-one", "list-two"])


if __name__ == "__main__":
    unittest.main()
