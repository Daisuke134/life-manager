"""Minimal Openprovider REST adapter for .si lookup and registration."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable


PRODUCTION_BASE_URL = "https://api.openprovider.eu/v1"
DEFAULT_CREDENTIALS_FILE = Path.home() / ".local/share/anicca/credentials.json"
_ALLOWED_TEST_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ProviderError(RuntimeError):
    """Stable provider failure without response or credential contents."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class CredentialMissing(ProviderError):
    def __init__(self):
        super().__init__("credential_missing")


class CredentialStoreUnsafe(ProviderError):
    def __init__(self):
        super().__init__("credential_store_unsafe")


class EffectUnknown(ProviderError):
    def __init__(self):
        super().__init__("effect_unknown")


def _money(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ProviderError("price_invalid") from None
    if not amount.is_finite() or amount < 0:
        raise ProviderError("price_invalid")
    return amount


def _domain_parts(domain: str) -> tuple[str, str]:
    if not isinstance(domain, str) or domain != domain.lower() or not domain.endswith(".si"):
        raise ValueError("domain_invalid")
    label = domain[:-3]
    if not label or "." in label or label.startswith("-") or label.endswith("-"):
        raise ValueError("domain_invalid")
    if any(not (character.isascii() and (character.isalnum() or character == "-"))
           for character in label):
        raise ValueError("domain_invalid")
    return label, "si"


def _contact_fingerprint(owner_handle: Any) -> str | None:
    if not isinstance(owner_handle, str) or not owner_handle:
        return None
    return hashlib.sha256(owner_handle.encode("utf-8")).hexdigest()


def _safe_domain(data: dict[str, Any]) -> dict[str, Any]:
    domain_value = data.get("domain")
    if isinstance(domain_value, dict):
        name = domain_value.get("name")
        extension = domain_value.get("extension")
        domain = f"{name}.{extension}" if name and extension else None
    elif isinstance(domain_value, str):
        domain = domain_value
    else:
        domain = None
    safe = {
        "id": str(data["id"]) if data.get("id") is not None else None,
        "domain": domain,
        "status": data.get("status") if isinstance(data.get("status"), str) else None,
        "activation_date": data.get("activation_date"),
        "expiration_date": data.get("expiration_date"),
        "renewal_date": data.get("renewal_date"),
        "owner_contact_fingerprint": _contact_fingerprint(data.get("owner_handle")),
    }
    return {key: value for key, value in safe.items() if value is not None}


class OpenProviderClient:
    def __init__(
        self,
        *,
        credentials_file: Path | None = None,
        base_url: str = PRODUCTION_BASE_URL,
        timeout: float = 20.0,
        opener: Callable[..., Any] | None = None,
    ):
        self.credentials_file = Path(credentials_file or DEFAULT_CREDENTIALS_FILE).expanduser()
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in _ALLOWED_TEST_HOSTS
        ):
            raise ValueError("base_url_invalid")
        if parsed.scheme == "https" and parsed.netloc != "api.openprovider.eu":
            raise ValueError("base_url_invalid")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen
        self._token: str | None = None
        self._credentials: dict[str, str] | None = None

    def _load_credentials(self) -> dict[str, str]:
        if self._credentials is not None:
            return self._credentials
        try:
            if self.credentials_file.is_symlink():
                raise CredentialStoreUnsafe()
            file_stat = self.credentials_file.stat()
            dir_stat = self.credentials_file.parent.stat()
        except CredentialStoreUnsafe:
            raise
        except OSError:
            raise CredentialMissing() from None
        if (stat.S_IMODE(file_stat.st_mode) != 0o600
                or stat.S_IMODE(dir_stat.st_mode) != 0o700
                or file_stat.st_uid != os.getuid()
                or dir_stat.st_uid != os.getuid()):
            raise CredentialStoreUnsafe()
        try:
            data = json.loads(self.credentials_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise CredentialStoreUnsafe() from None
        rows = data.get("credentials") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise CredentialStoreUnsafe()
        for row in rows:
            if not isinstance(row, dict) or str(row.get("service", "")).lower() != "openprovider":
                continue
            username = row.get("username")
            password = row.get("password")
            if isinstance(username, str) and username and isinstance(password, str) and password:
                self._credentials = {"username": username, "password": password}
                return self._credentials
        raise CredentialMissing()

    def _exchange(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        authenticated: bool = True,
        mutating: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Accept": "application/json", "User-Agent": "LifeManager-domain-flip/1"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if authenticated:
            token = self._get_token()
            headers["Authorization"] = f"Bearer {token}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self._opener(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            if mutating and error.code >= 500:
                raise EffectUnknown() from None
            raise ProviderError("http_error") from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
            if mutating:
                raise EffectUnknown() from None
            raise ProviderError("provider_read_failed") from None
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            if mutating:
                raise EffectUnknown() from None
            raise ProviderError("response_invalid") from None
        if not isinstance(document, dict) or type(document.get("code")) is not int:
            if mutating:
                raise EffectUnknown() from None
            raise ProviderError("response_invalid")
        if document["code"] != 0:
            if mutating:
                raise EffectUnknown() from None
            raise ProviderError("provider_code_nonzero")
        data = document.get("data")
        if not isinstance(data, dict):
            if mutating:
                raise EffectUnknown() from None
            raise ProviderError("response_data_invalid")
        return document, data

    def _get_token(self) -> str:
        if self._token is not None:
            return self._token
        credentials = self._load_credentials()
        _, data = self._exchange(
            "POST",
            "/auth/login",
            payload={
                "username": credentials["username"],
                "password": credentials["password"],
                "ip": "0.0.0.0",
            },
            authenticated=False,
        )
        token = data.get("token")
        if not isinstance(token, str) or not token:
            raise ProviderError("auth_token_missing")
        self._token = token
        return token

    def check_domain(self, name: str) -> dict[str, Any]:
        label, extension = _domain_parts(name)
        document, data = self._exchange(
            "POST",
            "/domains/check",
            payload={
                "domains": [{"name": label, "extension": extension}],
                "with_price": True,
            },
        )
        results = data.get("results")
        if not isinstance(results, list):
            raise ProviderError("availability_response_invalid")
        row = next((item for item in results
                    if isinstance(item, dict) and item.get("domain") == name), None)
        if row is None:
            raise ProviderError("availability_result_missing")
        status = row.get("status")
        if status == "free":
            available: bool | None = True
        elif status == "active":
            available = False
        else:
            raise ProviderError("availability_status_unknown")
        safe_result = {
            key: row[key] for key in ("domain", "status", "reason", "is_premium", "price")
            if key in row
        }
        return {
            "domain": name,
            "available": available,
            "status": status,
            "provider": "openprovider",
            "provider_receipt_id": None,
            "readback_verified": True,
            "readback_payload": {"code": document["code"], "result": safe_result},
        }

    def _price(self, name: str, operation: str) -> tuple[dict[str, Any], Decimal, str]:
        label, extension = _domain_parts(name)
        query: dict[str, Any] = {
            "domain.name": label,
            "domain.extension": extension,
            "operation": operation,
        }
        if operation == "create":
            query["period"] = 1
        document, data = self._exchange("GET", "/domains/prices", query=query)
        price_group = data.get("price")
        reseller_price = price_group.get("reseller") if isinstance(price_group, dict) else None
        if not isinstance(reseller_price, dict):
            raise ProviderError("price_response_invalid")
        currency = reseller_price.get("currency")
        if not isinstance(currency, str) or not currency:
            raise ProviderError("price_currency_missing")
        amount = _money(reseller_price.get("price"))
        if amount <= 0:
            raise ProviderError("price_invalid")
        safe_payload = {
            "code": document["code"],
            "price": {"currency": currency, "amount": format(amount, "f")},
            "is_premium": data.get("is_premium"),
            "is_promotion": data.get("is_promotion"),
        }
        return safe_payload, amount, currency

    def quote_create(
        self,
        name: str,
        funding_fx_basis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        create_readback, registration_amount, currency = self._price(name, "create")
        renewal_readback, renewal_amount, renewal_currency = self._price(name, "renew")
        if currency != renewal_currency:
            raise ProviderError("price_currency_inconsistent")
        quote: dict[str, Any] = {
            "domain": name,
            "provider": "openprovider",
            "available": None,
            "currency": currency,
            "registration_amount": registration_amount,
            "renewal_amount": renewal_amount,
            "registration_cost_eur": None,
            "renewal_cost_eur": None,
            "provider_receipt_id": None,
            "readback_verified": True,
            "readback_payloads": {
                "create": create_readback,
                "renew": renewal_readback,
            },
            "fx_verified": False,
            "fx_basis_receipt_id": None,
            "fx_evidence_refs": [],
        }
        if currency == "EUR":
            quote.update(
                registration_cost_eur=registration_amount,
                renewal_cost_eur=renewal_amount,
                final_charge_eur=registration_amount,
            )
            return quote

        basis = funding_fx_basis if isinstance(funding_fx_basis, dict) else {}
        rate = _money(basis.get("eur_per_account_unit")) if basis.get("eur_per_account_unit") is not None else None
        if (basis.get("verified") is not True
                or basis.get("account_currency") != currency
                or not isinstance(basis.get("funding_receipt_id"), str)
                or not basis.get("funding_receipt_id")
                or rate is None or rate <= 0
                or not isinstance(basis.get("evidence_refs"), list)
                or not basis["evidence_refs"]
                or not all(isinstance(ref, str) and ref.strip() for ref in basis["evidence_refs"])):
            return quote
        quote.update(
            registration_cost_eur=registration_amount * rate,
            renewal_cost_eur=renewal_amount * rate,
            final_charge_eur=registration_amount * rate,
            fx_verified=True,
            fx_basis_receipt_id=basis["funding_receipt_id"],
            fx_evidence_refs=list(basis["evidence_refs"]),
        )
        return quote

    def register(self, name: str, owner_handle: str, idempotency_key: str) -> dict[str, Any]:
        label, extension = _domain_parts(name)
        if not isinstance(owner_handle, str) or not owner_handle:
            raise ValueError("owner_handle_invalid")
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ValueError("idempotency_key_invalid")
        _, data = self._exchange(
            "POST",
            "/domains",
            payload={
                "domain": {"name": label, "extension": extension},
                "owner_handle": owner_handle,
                "period": 1,
                "unit": "y",
                "autorenew": "off",
                "is_private_whois_enabled": False,
            },
            mutating=True,
        )
        domain_id = data.get("id")
        if not isinstance(domain_id, (int, str)) or not str(domain_id).isdigit():
            raise EffectUnknown()
        return {
            "domain": name,
            "domain_id": str(domain_id),
            "status": "submitted",
            "provider": "openprovider",
            "provider_receipt_id": str(domain_id),
            "readback_verified": False,
            "idempotency_key": idempotency_key,
        }

    def get_domain(self, domain_id: int | str) -> dict[str, Any]:
        if not str(domain_id).isdigit():
            raise ValueError("domain_id_invalid")
        _, data = self._exchange("GET", f"/domains/{domain_id}")
        if not isinstance(data, dict):
            raise ProviderError("domain_readback_invalid")
        result = _safe_domain(data)
        if not result.get("domain") or not result.get("id"):
            raise ProviderError("domain_readback_invalid")
        result.update(provider="openprovider", provider_receipt_id=result["id"], readback_verified=True)
        return result

    def list_domains(self) -> list[dict[str, Any]]:
        _, data = self._exchange(
            "GET",
            "/domains",
            query={"extension": "si", "limit": 100, "offset": 0},
        )
        rows = data.get("results")
        total = data.get("total")
        if not isinstance(rows, list):
            raise ProviderError("domain_list_invalid")
        if type(total) is not int or total != len(rows):
            raise ProviderError("domain_list_incomplete")
        safe_rows = [_safe_domain(row) for row in rows if isinstance(row, dict)]
        if len(safe_rows) != len(rows):
            raise ProviderError("domain_list_invalid")
        return safe_rows
