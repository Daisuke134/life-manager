import copy
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "runtime/agent-runner/context_capsule.schema.json"
PACKET_PATH = ROOT / "runtime/agent-runner/context_packet.py"
PACKET_SPEC = importlib.util.spec_from_file_location("life_manager_context_packet", PACKET_PATH)
PACKET = importlib.util.module_from_spec(PACKET_SPEC)
assert PACKET_SPEC and PACKET_SPEC.loader
sys.modules[PACKET_SPEC.name] = PACKET
PACKET_SPEC.loader.exec_module(PACKET)


def validate(value, schema):
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
        key=lambda error: list(error.path),
    )
    if errors:
        raise AssertionError(errors[0].message)


class ContextCapsuleSchemaTest(unittest.TestCase):
    def test_capsule_requires_bounded_hash_bound_context(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        capsule = {
            "schema_version": 1,
            "capsule_id": "capsule-1",
            "tenant_id": "tenant-1",
            "owner_id": "ai.anicca.hf-gig-apply-direct",
            "product_loop_id": "gig-coconala",
            "job_id": "hf-gig-apply-direct",
            "wake_id": "wake-1",
            "goal": {
                "text": "Find one eligible application",
                "success_condition": "Official provider receipt or typed wait",
                "revision": 1,
            },
            "sources": [{
                "ref": "ledger://gig-coconala/wake-1",
                "observed_at": "2026-09-15T06:00:00Z",
                "content_sha256": "a" * 64,
                "freshness": "fresh",
                "excerpt": "eligible opportunity count: 1",
            }],
            "decisions": [{
                "id": "decision-1",
                "summary": "Use the provider adapter",
                "source_refs": ["ledger://gig-coconala/wake-1"],
            }],
            "open_questions": [],
            "budget": {"max_bytes": 8192, "max_tokens": 2048},
            "freshness": {
                "compiled_at": "2026-09-15T06:00:00Z",
                "max_age_seconds": 300,
                "stale_source_count": 0,
            },
            "content_sha256": "b" * 64,
            "privacy": {"redaction": "secret_free", "payload_mode": "references_only"},
        }
        validate(capsule, schema)

        for missing in ("budget", "content_sha256"):
            invalid = copy.deepcopy(capsule)
            del invalid[missing]
            with self.assertRaises(AssertionError):
                validate(invalid, schema)

        invalid = copy.deepcopy(capsule)
        invalid["budget"]["max_bytes"] = 0
        with self.assertRaises(AssertionError):
            validate(invalid, schema)

    def test_compiler_is_deterministic_freshness_aware_and_secret_free(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        arguments = {
            "tenant_id": "tenant-1",
            "owner_id": "ai.anicca.hf-gig-apply-direct",
            "product_loop_id": "gig-coconala",
            "job_id": "hf-gig-apply-direct",
            "wake_id": "wake-1",
            "goal": {
                "text": "Find one eligible application",
                "success_condition": "Official provider receipt or typed wait",
                "revision": 1,
            },
            "sources": [
                {
                    "ref": "ledger://gig-coconala/wake-1",
                    "observed_at": "2026-09-15T05:59:00Z",
                    "content_sha256": "a" * 64,
                    "freshness": "fresh",
                    "excerpt": "eligible opportunity count: 1",
                },
                {
                    "ref": "provider://coconala/account",
                    "observed_at": "2026-09-14T05:00:00Z",
                    "content_sha256": "c" * 64,
                    "freshness": "stale",
                    "excerpt": "old account status",
                },
            ],
            "decisions": [{
                "id": "decision-1",
                "summary": "Use the provider adapter",
                "source_refs": ["ledger://gig-coconala/wake-1"],
            }],
            "open_questions": ["Is an interview required?"],
            "max_bytes": 8192,
            "max_tokens": 2048,
            "max_age_seconds": 300,
            "compiled_at": "2026-09-15T06:00:00Z",
        }
        capsule = PACKET.build_context_capsule(**arguments)
        replay = PACKET.build_context_capsule(**arguments)
        validate(capsule, schema)
        self.assertEqual(capsule, replay)
        self.assertEqual(capsule["freshness"]["stale_source_count"], 1)
        body = {key: value for key, value in capsule.items()
                if key not in {"capsule_id", "content_sha256"}}
        canonical = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        self.assertEqual(capsule["content_sha256"], hashlib.sha256(canonical.encode()).hexdigest())

        secret = copy.deepcopy(arguments)
        secret["sources"] = [{**secret["sources"][0], "excerpt": "token=do-not-store"}]
        with self.assertRaises(PACKET.ContextPacketError):
            PACKET.build_context_capsule(**secret)


if __name__ == "__main__":
    unittest.main()
