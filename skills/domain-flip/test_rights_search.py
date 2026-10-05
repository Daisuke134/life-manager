from __future__ import annotations

import importlib.util
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


RIGHTS_PATH = Path(__file__).with_name("rights_search.py")
SPEC = importlib.util.spec_from_file_location("domain_flip_rights_search", RIGHTS_PATH)
assert SPEC is not None and SPEC.loader is not None
rights_search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rights_search)


def credential_file(tmp_path: Path, token_url: str) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    os.chmod(tmp_path, 0o700)
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({
        "credentials": [{
            "service": "euipo-trademark-search",
            "api_key": "test-client-id",
            "api_secret": "test-only-client-secret",
            "token_url": token_url,
            "account_status": "active",
            "subscription_status": "approved",
            "api_auth_verified": True,
            "environment": "production",
            "token_endpoint_verified": True,
            "token_endpoint_source": "official_portal",
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
            self.wfile.write(body)

        def record(self, body: bytes = b""):
            parsed = urlparse(self.path)
            state["requests"].append({
                "method": self.command,
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "form": parse_qs(body.decode("utf-8")) if body else {},
                "authorization": self.headers.get("Authorization"),
                "client_id": self.headers.get("X-IBM-Client-Id"),
            })

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            self.record(body)
            if urlparse(self.path).path == "/oidc/accessToken":
                self.reply({"access_token": "test-access-token", "token_type": "Bearer", "expires_in": 3600})
            else:
                self.reply({"detail": "not-found"}, status=404)

        def do_GET(self):
            self.record()
            if state.get("api_status", 200) != 200:
                self.reply({"detail": "unavailable"}, status=state["api_status"])
                return
            if urlparse(self.path).path != "/trademark-search/trademarks":
                self.reply({"detail": "not-found"}, status=404)
                return
            page = int(parse_qs(urlparse(self.path).query).get("page", ["0"])[0])
            self.reply({
                "trademarks": [
                    {
                        "applicationNumber": "018123456",
                        "markFeature": "WORD",
                        "markBasis": "EU_TRADEMARK",
                        "wordMarkSpecification": {"verbalElement": "Novara"},
                        "niceClasses": [9, 42],
                        "status": "REGISTERED",
                        "applicationDate": "2024-01-10",
                        "applicants": [{"name": "PRIVATE FIXTURE OWNER"}],
                    },
                ] if page == 0 else [],
                "size": 100,
                "totalElements": state.get("total_elements", 1),
                "totalPages": state.get("total_pages", 1),
                "page": page,
            })

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    return server, thread, root


def stop_api(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


def test_euipo_query_uses_documented_rsql(tmp_path):
    state = {"requests": [], "total_elements": 1, "total_pages": 1}
    server, thread, root = start_api(state)
    try:
        client = rights_search.EUIPORightsSearch(
            credentials_file=credential_file(tmp_path, f"{root}/oidc/accessToken"),
            api_base_url=f"{root}/trademark-search",
        )

        result = client.search_wordmark("novara")

        assert result["status"] == "complete"
        assert result["source"] == "euipo"
        assert result["total_elements"] == 1
        assert result["records"][0]["word_mark"] == "Novara"
        assert "applicants" not in result["records"][0]
        assert "PRIVATE FIXTURE OWNER" not in json.dumps(result)

        token = next(row for row in state["requests"] if row["path"] == "/oidc/accessToken")
        assert token["method"] == "POST"
        assert token["form"]["grant_type"] == ["client_credentials"]
        assert token["form"]["client_id"] == ["test-client-id"]
        assert token["form"]["scope"] == ["uid"]

        search = next(row for row in state["requests"] if row["path"] == "/trademark-search/trademarks")
        assert search["method"] == "GET"
        assert search["query"]["query"] == ["wordMarkSpecification.verbalElement==*novara*"]
        assert search["query"]["page"] == ["0"]
        assert search["query"]["size"] == ["100"]
        assert search["authorization"] == "Bearer test-access-token"
        assert search["client_id"] == "test-client-id"
    finally:
        stop_api(server, thread)


def test_missing_or_failed_euipo_search_is_not_clean(tmp_path):
    missing = rights_search.EUIPORightsSearch(credentials_file=tmp_path / "missing.json")
    missing_result = missing.search_wordmark("novara")
    assert missing_result["status"] == "unavailable"
    assert missing_result["reason_code"] == "credential_missing"

    state = {"requests": [], "api_status": 403}
    server, thread, root = start_api(state)
    try:
        client = rights_search.EUIPORightsSearch(
            credentials_file=credential_file(tmp_path / "authorized", f"{root}/oidc/accessToken"),
            api_base_url=f"{root}/trademark-search",
        )
        failed = client.search_wordmark("novara")
        assert failed["status"] == "unavailable"
        assert failed["reason_code"] == "api_unavailable"
        assert failed["records"] == []
    finally:
        stop_api(server, thread)


def test_unverified_production_token_endpoint_is_not_used(tmp_path):
    state = {"requests": []}
    server, thread, root = start_api(state)
    try:
        credentials = credential_file(tmp_path, f"{root}/oidc/accessToken")
        data = json.loads(credentials.read_text(encoding="utf-8"))
        data["credentials"][0]["token_endpoint_verified"] = False
        credentials.write_text(json.dumps(data), encoding="utf-8")
        os.chmod(credentials, 0o600)
        client = rights_search.EUIPORightsSearch(
            credentials_file=credentials,
            api_base_url=f"{root}/trademark-search",
        )

        result = client.search_wordmark("novara")

        assert result["status"] == "unavailable"
        assert result["reason_code"] == "credential_or_subscription_unverified"
        assert state["requests"] == []
    finally:
        stop_api(server, thread)


def test_incomplete_euipo_pagination_is_not_clean(tmp_path):
    state = {"requests": [], "total_elements": 101, "total_pages": 2}
    server, thread, root = start_api(state)
    try:
        client = rights_search.EUIPORightsSearch(
            credentials_file=credential_file(tmp_path / "authorized", f"{root}/oidc/accessToken"),
            api_base_url=f"{root}/trademark-search",
        )

        result = client.search_wordmark("novara")

        assert result["status"] == "unavailable"
        assert result["reason_code"] == "incomplete_results"
        searches = [row for row in state["requests"] if row["path"] == "/trademark-search/trademarks"]
        assert [row["query"]["page"] for row in searches] == [["0"], ["1"]]
    finally:
        stop_api(server, thread)
