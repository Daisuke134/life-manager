"""Codex/OpenAI structured output rejects a schema whose `required` omits any property
(live 2026-10-08: 400 invalid_json_schema "Missing 'beat_texts'" made every caption fail)."""
import json
import unittest
from pathlib import Path

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def _objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            yield node
        for value in node.values():
            yield from _objects(value)
    elif isinstance(node, list):
        for value in node:
            yield from _objects(value)


class StrictSchemas(unittest.TestCase):
    def test_every_property_is_required(self) -> None:
        for path in sorted(SCHEMAS.glob("*.json")):
            for obj in _objects(json.loads(path.read_text())):
                self.assertEqual(set(obj.get("required", [])), set(obj["properties"]), path.name)


if __name__ == "__main__":
    unittest.main()
