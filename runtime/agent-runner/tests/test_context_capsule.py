import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "runtime/agent-runner/context_capsule.schema.json"


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


if __name__ == "__main__":
    unittest.main()
