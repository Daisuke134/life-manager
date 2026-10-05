from __future__ import annotations

import importlib.util
import json
import os
import threading
import time
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


OPENPROVIDER_PATH = Path(__file__).with_name("openprovider.py")
SPEC = importlib.util.spec_from_file_location("domain_flip_openprovider", OPENPROVIDER_PATH)
assert SPEC is not None and SPEC.loader is not None
openprovider = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(openprovider)


def credential_file(tmp_path: Path) -> Path:
    os.chmod(tmp_path, 0o700)
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({
        "credentials": [{
            "service": "openprovider",
            "username": "test-reseller",
            "password": "test-only-password",
        }],
    }), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def start_api(state: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def reply(self, payload: dict, status: int = 200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def request_body(self):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8"))

        def record(self, body=None):
            state["requests"].append({
                "method": self.command,
                "path": urlparse(self.path).path,
                "query": parse_qs(urlparse(self.path).query),
                "body": body,
                "authorization": self.headers.get("Authorization"),
            })

        def do_POST(self):
            body = self.request_body()
            self.record(body)
            path = urlparse(self.path).path
            if path in state.get("nonzero_paths", set()):
                self.reply({"code": 42, "data": {}, "desc": "provider-error"})
                return
            if path == "/v1/auth/login":
                self.reply({"code": 0, "data": {"token": "test-token"}, "desc": ""})
            elif path == "/v1/domains/check":
                self.reply({"code": 0, "data": {"results": [{
                    "domain": "novara.si",
                    "status": "free",
                    "reason": "Domain is free",
                }]}, "desc": ""})
            elif path == "/v1/domains":
                state["create_count"] += 1
                if state.get("delay_create"):
                    time.sleep(state["delay_create"])
                self.reply({"code": 0, "data": {"id": 123, "status": "PRE"}, "desc": ""})
            else:
                self.reply({"code": 404, "data": {}, "desc": "not-found"}, status=404)

        def do_GET(self):
            self.record()
            parsed = urlparse(self.path)
            if parsed.path in state.get("nonzero_paths", set()):
                self.reply({"code": 42, "data": {}, "desc": "provider-error"})
            elif parsed.path == "/v1/domains/prices":
                query = parse_qs(parsed.query)
                operation = query.get("operation", ["create"])[0]
                amount = "9.99" if operation == "create" else "10.99"
                self.reply({"code": 0, "data": {
                    "price": {"reseller": {"price": float(amount), "currency": "USD"}},
                    "is_premium": False,
                }, "desc": ""})
            elif parsed.path == "/v1/domains/123":
                self.reply({"code": 0, "data": {
                    "id": 123,
                    "domain": {"name": "novara", "extension": "si"},
                    "status": "ACT",
                    "owner_handle": "OWNER-1",
                    "owner": {
                        "full_name": "Private Fixture Name",
                        "email": "private-fixture@example.test",
                        "address": "private-fixture-address",
                    },
                    "expiration_date": "2027-10-05",
                }, "desc": ""})
            elif parsed.path == "/v1/domains":
                self.reply({"code": 0, "data": {"results": [{
                    "id": 123,
                    "domain": "novara.si",
                    "status": "ACT",
                    "owner_handle": "OWNER-1",
                    "owner": {
                        "full_name": "Private Fixture Name",
                        "email": "private-fixture@example.test",
                        "address": "private-fixture-address",
                    },
                }], "total": state.get("list_total", 1)}, "desc": ""})
            else:
                self.reply({"code": 404, "data": {}, "desc": "not-found"}, status=404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}/v1"


def stop_api(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


def test_check_and_quote_use_official_si_fields(tmp_path):
    state = {"requests": [], "create_count": 0}
    server, thread, base_url = start_api(state)
    try:
        client = openprovider.OpenProviderClient(
            credentials_file=credential_file(tmp_path),
            base_url=base_url,
        )

        availability = client.check_domain("novara.si")
        quote = client.quote_create("novara.si")

        assert availability["available"] is True
        assert availability["domain"] == "novara.si"
        assert quote["currency"] == "USD"
        assert quote["registration_amount"] == Decimal("9.99")
        assert quote["renewal_amount"] == Decimal("10.99")
        assert quote["registration_cost_eur"] is None
        assert quote["provider_receipt_id"] is None
        assert quote["readback_verified"] is True

        check = next(row for row in state["requests"] if row["path"] == "/v1/domains/check")
        assert check["method"] == "POST"
        assert check["body"]["domains"] == [{"name": "novara", "extension": "si"}]
        assert check["body"]["with_price"] is True
        assert check["authorization"] == "Bearer test-token"

        price_requests = [row for row in state["requests"] if row["path"] == "/v1/domains/prices"]
        assert [row["query"]["operation"][0] for row in price_requests] == ["create", "renew"]
        assert price_requests[0]["query"]["domain.name"] == ["novara"]
        assert price_requests[0]["query"]["domain.extension"] == ["si"]
        assert price_requests[0]["query"]["period"] == ["1"]
        assert "period" not in price_requests[1]["query"]
    finally:
        stop_api(server, thread)


def test_quote_does_not_fabricate_provider_receipt_id(tmp_path):
    state = {"requests": [], "create_count": 0}
    server, thread, base_url = start_api(state)
    try:
        client = openprovider.OpenProviderClient(
            credentials_file=credential_file(tmp_path),
            base_url=base_url,
        )
        quote = client.quote_create("novara.si")

        assert quote["provider_receipt_id"] is None
        assert quote["readback_verified"] is True
        assert quote["readback_payloads"]["create"]["code"] == 0
    finally:
        stop_api(server, thread)


def test_fx_requires_matching_funding_receipt(tmp_path):
    state = {"requests": [], "create_count": 0}
    server, thread, base_url = start_api(state)
    try:
        client = openprovider.OpenProviderClient(
            credentials_file=credential_file(tmp_path),
            base_url=base_url,
        )
        basis = {
            "verified": True,
            "funding_receipt_id": "funding-1",
            "account_currency": "EUR",
            "eur_per_account_unit": "1.00",
            "evidence_refs": ["lm-domain-flip://funding/funding-1/fx"],
        }
        mismatched = client.quote_create("novara.si", funding_fx_basis=basis)
        assert mismatched["registration_cost_eur"] is None
        assert mismatched["fx_verified"] is False

        basis["account_currency"] = "USD"
        normalized = client.quote_create("novara.si", funding_fx_basis=basis)
        assert normalized["fx_verified"] is True
        assert normalized["fx_basis_receipt_id"] == "funding-1"
        assert normalized["registration_cost_eur"] == Decimal("9.9900")
        assert normalized["renewal_cost_eur"] == Decimal("10.9900")
    finally:
        stop_api(server, thread)


def test_register_sends_owner_and_autorenew_off(tmp_path):
    state = {"requests": [], "create_count": 0}
    server, thread, base_url = start_api(state)
    try:
        client = openprovider.OpenProviderClient(
            credentials_file=credential_file(tmp_path),
            base_url=base_url,
        )
        submitted = client.register("novara.si", "OWNER-1", "occurrence-1")
        domain = client.get_domain(submitted["domain_id"])
        portfolio = client.list_domains()

        assert submitted["status"] == "submitted"
        assert submitted["provider_receipt_id"] == "123"
        assert domain["status"] == "ACT"
        assert domain["owner_contact_fingerprint"]
        assert "owner_handle" not in domain
        assert portfolio[0]["domain"] == "novara.si"
        assert "owner_handle" not in portfolio[0]
        request = next(row for row in state["requests"] if row["method"] == "POST" and row["path"] == "/v1/domains")
        assert request["body"]["domain"] == {"name": "novara", "extension": "si"}
        assert request["body"]["owner_handle"] == "OWNER-1"
        assert request["body"]["autorenew"] == "off"
        assert request["body"]["period"] == 1
        assert request["body"]["unit"] == "y"
        assert request["body"]["is_private_whois_enabled"] is False
        assert "idempotency_key" not in request["body"]
    finally:
        stop_api(server, thread)


def test_domain_readback_filters_personal_contact_fields(tmp_path):
    state = {"requests": [], "create_count": 0}
    server, thread, base_url = start_api(state)
    try:
        client = openprovider.OpenProviderClient(
            credentials_file=credential_file(tmp_path),
            base_url=base_url,
        )
        domain = client.get_domain("123")
        portfolio = client.list_domains()
        sanitized = json.dumps([domain, *portfolio])

        assert "Private Fixture Name" not in sanitized
        assert "private-fixture@example.test" not in sanitized
        assert "private-fixture-address" not in sanitized
        assert domain["owner_contact_fingerprint"]
        assert portfolio[0]["owner_contact_fingerprint"]
    finally:
        stop_api(server, thread)


def test_list_truncation_is_not_complete_readback(tmp_path):
    state = {"requests": [], "create_count": 0, "list_total": 101}
    server, thread, base_url = start_api(state)
    try:
        client = openprovider.OpenProviderClient(
            credentials_file=credential_file(tmp_path),
            base_url=base_url,
        )

        with pytest.raises(openprovider.ProviderError) as error:
            client.list_domains()

        assert error.value.code == "domain_list_incomplete"
    finally:
        stop_api(server, thread)


def test_missing_credentials_prevent_mutation(tmp_path):
    state = {"requests": [], "create_count": 0}
    server, thread, base_url = start_api(state)
    try:
        client = openprovider.OpenProviderClient(
            credentials_file=tmp_path / "missing.json",
            base_url=base_url,
        )

        with pytest.raises(openprovider.CredentialMissing):
            client.register("novara.si", "OWNER-1", "occurrence-1")

        assert state["requests"] == []
    finally:
        stop_api(server, thread)


def test_nonzero_provider_code_is_not_success(tmp_path):
    state = {"requests": [], "create_count": 0, "nonzero_paths": {"/v1/domains/check"}}
    server, thread, base_url = start_api(state)
    try:
        client = openprovider.OpenProviderClient(
            credentials_file=credential_file(tmp_path),
            base_url=base_url,
        )

        with pytest.raises(openprovider.ProviderError):
            client.check_domain("novara.si")
    finally:
        stop_api(server, thread)


def test_timeout_is_effect_unknown_without_retry(tmp_path):
    state = {"requests": [], "create_count": 0, "delay_create": 0.2}
    server, thread, base_url = start_api(state)
    try:
        client = openprovider.OpenProviderClient(
            credentials_file=credential_file(tmp_path),
            base_url=base_url,
            timeout=0.05,
        )

        with pytest.raises(openprovider.EffectUnknown):
            client.register("novara.si", "OWNER-1", "occurrence-1")

        assert state["create_count"] == 1
        assert sum(
            row["method"] == "POST" and row["path"] == "/v1/domains"
            for row in state["requests"]
        ) == 1
    finally:
        stop_api(server, thread)
