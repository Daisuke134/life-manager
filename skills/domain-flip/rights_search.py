"""Read-only, fail-closed EUIPO word-mark search for .si candidates."""

from __future__ import annotations

import json
import os
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


PRODUCTION_API_BASE_URL = "https://api.euipo.europa.eu/trademark-search"
REGISTER_SI_ADR_URL = "https://www.register.si/en/adr-procedure-guidelines/"
DEFAULT_CREDENTIALS_FILE = Path.home() / ".local/share/anicca/credentials.json"
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_MAX_PAGES = 50
_PAGE_SIZE = 100
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class EUIPOError(RuntimeError):
    """Safe failure code; never includes credentials or provider response text."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _safe_int(value: Any) -> int | None:
    if type(value) is not int or value < 0:
        return None
    return value


def _classes(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: set[str] = set()
    for item in value:
        if isinstance(item, (str, int)) and not isinstance(item, bool):
            number = str(item)
        elif isinstance(item, dict):
            number = next((str(item[key]) for key in ("class", "classNumber", "number", "niceClass")
                           if isinstance(item.get(key), (str, int)) and not isinstance(item.get(key), bool)), "")
        else:
            number = ""
        if re.fullmatch(r"\d{1,2}", number):
            result.add(number)
    return sorted(result, key=int)


class EUIPORightsSearch:
    def __init__(
        self,
        *,
        credentials_file: Path | None = None,
        api_base_url: str = PRODUCTION_API_BASE_URL,
        timeout: float = 20.0,
        opener: Callable[..., Any] | None = None,
    ):
        self.credentials_file = Path(credentials_file or DEFAULT_CREDENTIALS_FILE).expanduser()
        parsed = urllib.parse.urlparse(api_base_url)
        local_test = parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS
        if not ((parsed.scheme == "https" and parsed.netloc == "api.euipo.europa.eu") or
                (local_test and self.credentials_file != DEFAULT_CREDENTIALS_FILE)):
            raise ValueError("api_base_url_invalid")
        self._local_test = local_test
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen
        self._credentials: dict[str, str] | None = None

    def _load_credentials(self) -> dict[str, str]:
        if self._credentials is not None:
            return self._credentials
        try:
            if self.credentials_file.is_symlink():
                raise EUIPOError("credential_store_unsafe")
            file_stat = self.credentials_file.stat()
            dir_stat = self.credentials_file.parent.stat()
        except EUIPOError:
            raise
        except OSError:
            raise EUIPOError("credential_missing") from None
        if (stat.S_IMODE(file_stat.st_mode) != 0o600
                or stat.S_IMODE(dir_stat.st_mode) != 0o700
                or file_stat.st_uid != os.getuid()
                or dir_stat.st_uid != os.getuid()):
            raise EUIPOError("credential_store_unsafe")
        try:
            data = json.loads(self.credentials_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise EUIPOError("credential_store_unsafe") from None
        rows = data.get("credentials") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise EUIPOError("credential_store_unsafe")
        for row in rows:
            if not isinstance(row, dict) or str(row.get("service", "")).casefold() != "euipo-trademark-search":
                continue
            client_id = row.get("api_key")
            client_secret = row.get("api_secret")
            token_url = row.get("token_url")
            endpoint_verified = row.get("token_endpoint_verified") is True
            endpoint_source = row.get("token_endpoint_source") == "official_portal"
            if (not isinstance(client_id, str) or not client_id
                    or not isinstance(client_secret, str) or not client_secret
                    or not isinstance(token_url, str) or not self._trusted_token_url(token_url)
                    or row.get("account_status") != "active"
                    or row.get("subscription_status") != "approved"
                    or row.get("environment") != "production"
                    or row.get("api_auth_verified") is not True
                    or not endpoint_verified or not endpoint_source):
                raise EUIPOError("credential_or_subscription_unverified")
            self._credentials = {
                "client_id": client_id,
                "client_secret": client_secret,
                "token_url": token_url,
            }
            return self._credentials
        raise EUIPOError("credential_missing")

    def _trusted_token_url(self, value: str) -> bool:
        parsed = urllib.parse.urlparse(value)
        if (parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path.rstrip("/") != "/oidc/accessToken"):
            return False
        if (self._local_test and parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS
                and self.credentials_file != DEFAULT_CREDENTIALS_FILE):
            return True
        host = (parsed.hostname or "").lower()
        return (parsed.scheme == "https" and parsed.port in {None, 443}
                and (host == "euipo.europa.eu" or host.endswith(".euipo.europa.eu")))

    def _read_json(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with self._opener(request, timeout=self.timeout) as response:
                payload = response.read(_MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError:
            raise EUIPOError("api_unavailable") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise EUIPOError("api_unavailable") from None
        if len(payload) > _MAX_RESPONSE_BYTES:
            raise EUIPOError("response_too_large")
        try:
            result = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise EUIPOError("response_invalid") from None
        if not isinstance(result, dict):
            raise EUIPOError("response_invalid")
        return result

    def _access_token(self, credentials: dict[str, str]) -> str:
        payload = urllib.parse.urlencode({
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
            "grant_type": "client_credentials",
            "scope": "uid",
        }).encode("utf-8")
        request = urllib.request.Request(
            credentials["token_url"],
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        result = self._read_json(request)
        token = result.get("access_token")
        if not isinstance(token, str) or not token:
            raise EUIPOError("token_response_invalid")
        return token

    @staticmethod
    def _safe_record(row: Any) -> dict[str, Any]:
        if not isinstance(row, dict):
            raise EUIPOError("record_invalid")
        application_number = row.get("applicationNumber")
        if not isinstance(application_number, str) or not re.fullmatch(r"(?:\d{9}|W\d{8}[A-Z]?)", application_number):
            raise EUIPOError("record_invalid")
        word_mark = row.get("wordMarkSpecification")
        name = word_mark.get("verbalElement") if isinstance(word_mark, dict) else None
        status = row.get("status")
        if not isinstance(name, str) or not name.strip() or not isinstance(status, str) or not status:
            raise EUIPOError("record_invalid")
        return {
            "word_mark": name.strip(),
            "office": "EUIPO",
            "status": status,
            "classes": _classes(row.get("niceClasses")),
            "official_record_url": f"{PRODUCTION_API_BASE_URL}/trademarks/{application_number}",
        }

    def search_wordmark(self, candidate: str) -> dict[str, Any]:
        if not isinstance(candidate, str) or not re.fullmatch(r"[a-z0-9-]{1,63}", candidate):
            return self._unavailable("candidate_invalid")
        query = f"wordMarkSpecification.verbalElement==*{candidate}*"
        try:
            credentials = self._load_credentials()
            token = self._access_token(credentials)
            records: list[dict[str, Any]] = []
            evidence_refs = [REGISTER_SI_ADR_URL]
            expected_total: int | None = None
            expected_pages: int | None = None
            pages_to_read = 1
            page = 0
            while page < pages_to_read:
                params = urllib.parse.urlencode({"query": query, "page": page, "size": _PAGE_SIZE})
                url = f"{self.api_base_url}/trademarks?{params}"
                request = urllib.request.Request(
                    url,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                        "X-IBM-Client-Id": credentials["client_id"],
                    },
                    method="GET",
                )
                result = self._read_json(request)
                rows = result.get("trademarks")
                total = _safe_int(result.get("totalElements"))
                total_pages = _safe_int(result.get("totalPages"))
                response_page = _safe_int(result.get("page"))
                response_size = _safe_int(result.get("size"))
                if (not isinstance(rows, list) or total is None or total_pages is None
                        or response_page != page or response_size != _PAGE_SIZE):
                    raise EUIPOError("pagination_unverified")
                if expected_total is None:
                    expected_total = total
                    expected_pages = total_pages
                    pages_to_read = max(1, total_pages)
                    if pages_to_read > _MAX_PAGES:
                        raise EUIPOError("incomplete_results")
                    if total_pages not in {0, 1} and total_pages != (total + _PAGE_SIZE - 1) // _PAGE_SIZE:
                        raise EUIPOError("pagination_unverified")
                    if total == 0 and total_pages > 1:
                        raise EUIPOError("pagination_unverified")
                elif total != expected_total or total_pages != expected_pages:
                    raise EUIPOError("pagination_changed")
                records.extend(self._safe_record(row) for row in rows)
                evidence_refs.append(url)
                page += 1
            if expected_total is None or len(records) != expected_total:
                raise EUIPOError("incomplete_results")
            return {
                "status": "complete",
                "source": "euipo",
                "total_elements": expected_total,
                "records": records,
                "evidence_refs": evidence_refs,
            }
        except EUIPOError as error:
            return self._unavailable(error.code)

    @staticmethod
    def _unavailable(reason_code: str) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "source": "euipo",
            "reason_code": reason_code,
            "records": [],
            "evidence_refs": [REGISTER_SI_ADR_URL],
        }
