#!/usr/bin/env python3
"""Immutable, product-isolated ebook script ledger."""
from __future__ import annotations

import hashlib
import json
import pathlib
import sqlite3
import re


PRODUCT_LANGUAGE = {"ebook-ja": "ja", "ebook-en": "en"}
PRODUCT_CTA = {"ebook-ja": "アニッチャ・リセットを読む", "ebook-en": "Read The Anicca Reset"}
COMPONENTS = ("hook", "pain_angle", "teaching", "action", "cta")
REQUIRED = {
    "schema_version", "product_id", "account_id", "language", "version",
    "parent_script_id", "source_mechanism_ids", "hook", "pain_angle", "teaching",
    "action", "cta", "hypothesis", "declared_mutation", "baseline", "campaign_id",
    "creative_id", "renderer_id", "primary_metric", "maturity_window", "stop_rule", "body",
}


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def canonical(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_signature(script: dict) -> str:
    value = {key: script[key] for key in (
        "product_id", "language", "renderer_id", *COMPONENTS, "body",
    )}
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def script_id(script: dict) -> str:
    value = {key: script[key] for key in sorted(REQUIRED)}
    return "script." + hashlib.sha256(canonical(value).encode()).hexdigest()[:24]


def validate_writer_contract(script: dict) -> None:
    body = script["body"].casefold() if script["language"] == "en" else script["body"]
    cursor = -1
    for key in ("hook", "pain_angle", "teaching", "action", "cta"):
        value = script[key].casefold() if script["language"] == "en" else script[key]
        next_cursor = body.find(value, cursor + 1)
        require(next_cursor >= 0, f"writer contract missing {key}")
        cursor = next_cursor
    if script["language"] == "ja":
        require(bool(re.search(r"[ぁ-んァ-ン一-龯]", body)), "Japanese writer contract required")
    else:
        require(bool(re.search(r"[A-Za-z]{3}", body)), "English writer contract required")


def preflight(script: dict) -> None:
    require(script["cta"] == PRODUCT_CTA[script["product_id"]], "product CTA mismatch")
    require(bool(script["campaign_id"].strip()) and bool(script["creative_id"].strip()), "campaign and creative required")
    mechanisms = script["source_mechanism_ids"]
    require(bool(mechanisms) and all(isinstance(item, str) and item.strip() for item in mechanisms), "source mechanism proof required")
    require(script["declared_mutation"] in COMPONENTS, "multiple or unknown mutation")
    banned = ("guaranteed cure", "治療を保証", "必ず治る", "diagnose", "診断します",
              "insomnia", "sleep better", "no more anxiety", "不眠を治", "不安をなく")
    require(not any(term in script["body"].casefold() for term in banned), "unsupported ebook claim")


def validate(script: dict, parent: dict | None = None) -> None:
    require(set(script) == REQUIRED, "script fields differ")
    require(script["schema_version"] == "marketing.ebook-script.v1", "script schema invalid")
    product = script["product_id"]
    require(PRODUCT_LANGUAGE.get(product) == script["language"], "product language mismatch")
    for key in REQUIRED - {"parent_script_id", "source_mechanism_ids", "baseline"}:
        require(isinstance(script[key], str) and script[key].strip(), f"script {key} required")
    require(isinstance(script["source_mechanism_ids"], list), "source mechanisms required")
    require(script["declared_mutation"] in COMPONENTS, "one declared component mutation required")
    require(isinstance(script["baseline"], bool), "baseline flag required")
    validate_writer_contract(script)
    preflight(script)
    if script["baseline"]:
        require(script["parent_script_id"] is None, "baseline cannot have parent")
    else:
        require(isinstance(script["parent_script_id"], str) and script["parent_script_id"], "child parent required")
        require(parent is not None and parent["product_id"] == product and parent["language"] == script["language"], "parent isolation mismatch")


class ScriptLedger:
    def __init__(self, path: pathlib.Path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS scripts (script_id TEXT PRIMARY KEY, product_id TEXT NOT NULL, language TEXT NOT NULL, semantic_signature TEXT NOT NULL, payload_json TEXT NOT NULL, UNIQUE(product_id, semantic_signature))")

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def get(self, value: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT payload_json FROM scripts WHERE script_id=?", (value,)).fetchone()
        require(row is not None, "script not found")
        return json.loads(row["payload_json"])

    def register(self, script: dict) -> dict:
        parent = self.get(script["parent_script_id"]) if script.get("parent_script_id") else None
        validate(script, parent)
        identifier, signature, payload = script_id(script), semantic_signature(script), canonical(script)
        with self.connect() as db:
            existing = db.execute("SELECT payload_json FROM scripts WHERE script_id=?", (identifier,)).fetchone()
            if existing:
                require(existing["payload_json"] == payload, "conflicting script replay")
                return {"created": False, "script_id": identifier, "semantic_signature": signature}
            duplicate = db.execute("SELECT script_id FROM scripts WHERE product_id=? AND semantic_signature=?", (script["product_id"], signature)).fetchone()
            require(duplicate is None, "semantic duplicate script")
            db.execute("INSERT INTO scripts(script_id,product_id,language,semantic_signature,payload_json) VALUES(?,?,?,?,?)", (identifier, script["product_id"], script["language"], signature, payload))
        return {"created": True, "script_id": identifier, "semantic_signature": signature}
