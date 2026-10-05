from __future__ import annotations

import importlib.util
import json
import os
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


SEDO_PATH = Path(__file__).with_name("sedo.py")
SPEC = importlib.util.spec_from_file_location("domain_flip_sedo", SEDO_PATH)
assert SPEC is not None and SPEC.loader is not None
sedo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sedo)


def credential_file(tmp_path: Path) -> Path:
    os.chmod(tmp_path, 0o700)
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({
        "credentials": [{
            "service": "sedo",
            "partnerid": 1234,
            "signkey": "test-only-signkey",
            "username": "test-seller",
            "password": "test-pass-123",
        }],
    }), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def start_api(state: dict):
    categories = b"""<?xml version="1.0" encoding="UTF-8"?>
    <SEDODOMAINCATEGORIES ver="1.0">
      <maincategory id="50" name="Computers">
        <subcategory1 id="51" name="Artificial Intelligence" />
      </maincategory>
    </SEDODOMAINCATEGORIES>"""
    listing_ok = b"""<?xml version="1.0" encoding="UTF-8"?>
    <SEDOLIST><item><domain>novara.si</domain><status>Ok</status><message /></item></SEDOLIST>"""
    listing_fault = b"""<?xml version="1.0" encoding="UTF-8"?>
    <SEDOFAULT ver="1.0"><faultcode>E123</faultcode><faultstring>not accepted</faultstring></SEDOFAULT>"""
    status = b"""<?xml version="1.0" encoding="UTF-8"?>
    <SEDOLIST xmlns="https://api.sedo.com/api/v1/?wsdl">
      <item><domain>novara.si</domain><forsale>true</forsale><price>500.00</price>
      <currency>EUR</currency><domainstatus>1</domainstatus></item>
    </SEDOLIST>"""
    domain_list = b"""<?xml version="1.0" encoding="UTF-8"?>
    <SEDODOMAINLIST><item><domain>novara.si</domain><forsale>1</forsale>
    <price>500.00</price><minprice>300.00</minprice><fixedprice>0</fixedprice>
    <currency>0</currency><domainlanguage>en</domainlanguage></item></SEDODOMAINLIST>"""
    empty_list = b"""<?xml version="1.0" encoding="UTF-8"?>
    <SEDODOMAINLIST />"""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def reply(self, body: bytes, content_type: str = "text/xml"):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def record(self, body: bytes = b""):
            parsed = urlparse(self.path)
            state["requests"].append({
                "method": self.command,
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "body": parse_qs(body.decode("utf-8")),
            })

        def do_GET(self):
            self.record()
            path = urlparse(self.path).path
            if path.endswith("/DomainCategories"):
                self.reply(state.get("categories_xml", categories))
            else:
                self.reply(b"<SEDOFAULT ver='1.0'><faultcode>E404</faultcode></SEDOFAULT>")

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            self.record(body)
            path = urlparse(self.path).path
            if path.endswith("/DomainInsert"):
                state["insert_count"] += 1
                self.reply(state.get("insert_xml", listing_ok))
            elif path.endswith("/DomainStatus"):
                self.reply(state.get("status_xml", status))
            elif path.endswith("/DomainList"):
                self.reply(state.get("list_xml", domain_list))
            else:
                self.reply(b"<SEDOFAULT ver='1.0'><faultcode>E404</faultcode></SEDOFAULT>")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}/api/v1/"


def stop_api(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


def test_insert_uses_post_eur_price_and_live_category_ids(tmp_path):
    state = {"requests": [], "insert_count": 0}
    server, thread, base_url = start_api(state)
    try:
        client = sedo.SedoClient(credentials_file=credential_file(tmp_path), base_url=base_url)
        result = client.insert_for_sale("novara.si", Decimal("500.00"), Decimal("300.00"))

        insert = next(row for row in state["requests"] if row["path"].endswith("/DomainInsert"))
        assert insert["method"] == "POST"
        assert insert["query"] == {}
        assert insert["body"]["domainentry[0][domain]"] == ["novara.si"]
        assert insert["body"]["domainentry[0][category][0]"] == ["50"]
        assert insert["body"]["domainentry[0][category][1]"] == ["51"]
        assert insert["body"]["domainentry[0][forsale]"] == ["1"]
        assert insert["body"]["domainentry[0][price]"] == ["500.00"]
        assert insert["body"]["domainentry[0][minprice]"] == ["300.00"]
        assert insert["body"]["domainentry[0][currency]"] == ["0"]
        assert insert["body"]["domainentry[0][fixedprice]"] == ["0"]
        assert insert["body"]["password"] == ["test-pass-123"]
        assert result["status"] == "listing-pending"
        assert result["listed"] is False
        assert result["provider_receipt_id"] is None
    finally:
        stop_api(server, thread)


def test_missing_ai_category_prevents_insert(tmp_path):
    state = {
        "requests": [],
        "insert_count": 0,
        "categories_xml": b"<SEDODOMAINCATEGORIES><maincategory id='50' name='Computers'><subcategory1 id='51' name='General'/></maincategory></SEDODOMAINCATEGORIES>",
    }
    server, thread, base_url = start_api(state)
    try:
        client = sedo.SedoClient(credentials_file=credential_file(tmp_path), base_url=base_url)

        with pytest.raises(sedo.SedoError) as error:
            client.insert_for_sale("novara.si", Decimal("500"), Decimal("300"))

        assert error.value.code == "ai_category_unavailable"
        assert state["insert_count"] == 0
    finally:
        stop_api(server, thread)


def test_ok_submission_does_not_mark_listed(tmp_path):
    state = {"requests": [], "insert_count": 0}
    server, thread, base_url = start_api(state)
    try:
        client = sedo.SedoClient(credentials_file=credential_file(tmp_path), base_url=base_url)

        result = client.insert_for_sale("novara.si", Decimal("500"), Decimal("300"))

        assert result["status"] == "listing-pending"
        assert result["listed"] is False
    finally:
        stop_api(server, thread)


def test_domain_status_confirms_exact_price(tmp_path):
    state = {"requests": [], "insert_count": 0}
    server, thread, base_url = start_api(state)
    try:
        client = sedo.SedoClient(credentials_file=credential_file(tmp_path), base_url=base_url)

        result = client.domain_status("novara.si")

        assert result["domain"] == "novara.si"
        assert result["listed"] is True
        assert result["price"] == Decimal("500.00")
        assert result["currency"] == "EUR"
        request = next(row for row in state["requests"] if row["path"].endswith("/DomainStatus"))
        assert request["method"] == "POST"
        assert request["query"] == {}
        assert request["body"]["domainlist[0]"] == ["novara.si"]
    finally:
        stop_api(server, thread)


def test_domain_not_in_sedo_is_not_listed(tmp_path):
    state = {"requests": [], "insert_count": 0, "list_xml": b"<SEDODOMAINLIST />"}
    server, thread, base_url = start_api(state)
    try:
        client = sedo.SedoClient(credentials_file=credential_file(tmp_path), base_url=base_url)

        result = client.domain_list(["novara.si"])

        assert result == []
        request = next(row for row in state["requests"] if row["path"].endswith("/DomainList"))
        assert request["body"]["domain[0]"] == ["novara.si"]
    finally:
        stop_api(server, thread)


def test_sedo_fault_stays_unverified(tmp_path):
    state = {
        "requests": [],
        "insert_count": 0,
        "insert_xml": b"<SEDOFAULT ver='1.0'><faultcode>E123</faultcode><faultstring>not accepted</faultstring></SEDOFAULT>",
    }
    server, thread, base_url = start_api(state)
    try:
        client = sedo.SedoClient(credentials_file=credential_file(tmp_path), base_url=base_url)

        with pytest.raises(sedo.SedoError):
            client.insert_for_sale("novara.si", Decimal("500"), Decimal("300"))

        assert state["insert_count"] == 1
    finally:
        stop_api(server, thread)
