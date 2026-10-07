"""Sedo Basic API listing adapter with receipt-safe XML handling."""

from __future__ import annotations

import json
import hashlib
import re
import os
import stat
from datetime import datetime, timezone
from html.parser import HTMLParser
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable


PRODUCTION_BASE_URL = "https://api.sedo.com/api/v1/"
PRODUCTION_FEE_PAGE_URL = "https://sedo.com/us/what-we-offer/price-list/"
DEFAULT_CREDENTIALS_FILE = Path.home() / ".local/share/anicca/credentials.json"
_ALLOWED_TEST_HOSTS = {"127.0.0.1", "localhost", "::1"}


class SedoError(RuntimeError):
    """Stable Sedo adapter error that never includes API credentials or payloads."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class CredentialMissing(SedoError):
    def __init__(self):
        super().__init__("credential_missing")


class CredentialStoreUnsafe(SedoError):
    def __init__(self):
        super().__init__("credential_store_unsafe")


class EffectUnknown(SedoError):
    def __init__(self):
        super().__init__("effect_unknown")


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(node: ET.Element, name: str) -> str | None:
    for child in node.iter():
        if _local_name(child.tag) == name:
            return (child.text or "").strip()
    return None


def _decimal(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise SedoError("price_invalid") from None
    if not amount.is_finite() or amount < 0:
        raise SedoError("price_invalid")
    return amount


def _currency(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().upper()
    return {"0": "EUR", "1": "USD", "2": "GBP"}.get(value, value)


def _domain(domain: str) -> str:
    if (not isinstance(domain, str) or domain != domain.lower()
            or not domain.endswith(".si") or domain.count(".") != 1):
        raise ValueError("domain_invalid")
    label = domain[:-3]
    if (not label or label.startswith("-") or label.endswith("-")
            or any(not (char.isascii() and (char.isalnum() or char == "-")) for char in label)):
        raise ValueError("domain_invalid")
    return domain


class SedoClient:
    def __init__(
        self,
        *,
        credentials_file: Path | None = None,
        base_url: str = PRODUCTION_BASE_URL,
        fee_page_url: str = PRODUCTION_FEE_PAGE_URL,
        timeout: float = 20.0,
        opener: Callable[..., Any] | None = None,
    ):
        self.credentials_file = Path(credentials_file or DEFAULT_CREDENTIALS_FILE).expanduser()
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in _ALLOWED_TEST_HOSTS
        ):
            raise ValueError("base_url_invalid")
        if parsed.scheme == "https" and parsed.netloc != "api.sedo.com":
            raise ValueError("base_url_invalid")
        self.base_url = base_url.rstrip("/") + "/"
        fee_page = urllib.parse.urlparse(fee_page_url)
        fee_local = fee_page.scheme == "http" and fee_page.hostname in _ALLOWED_TEST_HOSTS
        if not ((fee_page.scheme == "https" and fee_page.netloc == "sedo.com"
                 and fee_page.path == "/us/what-we-offer/price-list/") or
                (fee_local and parsed.scheme == "http" and parsed.hostname in _ALLOWED_TEST_HOSTS)):
            raise ValueError("fee_page_url_invalid")
        self.fee_page_url = fee_page_url
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen
        self._credentials: dict[str, str] | None = None

    def fee_schedule(self) -> dict[str, Any]:
        """Read current public seller rates; use the maximum route commission for policy."""
        request = urllib.request.Request(
            self.fee_page_url,
            headers={"Accept": "text/html", "User-Agent": "LifeManager-domain-flip/1"},
            method="GET",
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                payload = response.read(4 * 1024 * 1024 + 1)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            raise SedoError("fee_read_failed") from None
        if not payload or len(payload) > 4 * 1024 * 1024:
            raise SedoError("fee_read_invalid")
        try:
            parser = _VisibleText()
            parser.feed(payload.decode("utf-8"))
            text = re.sub(r"\s+", " ", " ".join(parser.parts))
        except (UnicodeError, ValueError):
            raise SedoError("fee_read_invalid") from None
        lowered = text.casefold()
        direct_heading = "other domain sales through the sedo marketplace"
        mls_heading = "domain sales through the sedomls network"
        category_i_heading = "top level domains (tld) - category i"
        category_ii_heading = "top level domains (tld) - category ii"
        direct_start = lowered.find(direct_heading)
        mls_start = lowered.find(mls_heading)
        category_start = lowered.find(category_i_heading)
        category_end = lowered.find(category_ii_heading, category_start + 1) if category_start >= 0 else -1
        if min(direct_start, mls_start, category_start) < 0 or mls_start <= direct_start:
            raise SedoError("fee_terms_missing")
        direct_text = lowered[direct_start:mls_start]
        mls_end = lowered.find("domain sale: minimum fees", mls_start + len(mls_heading))
        mls_text = lowered[mls_start:mls_end if mls_end > mls_start else None]
        category_text = lowered[category_start:category_end if category_end > category_start else None]
        direct_match = re.search(r"\b(\d{1,2})%\s+commission will apply", direct_text)
        mls_match = re.search(r"\b(\d{1,2})%\s+of the gross sale price", mls_text)
        minimum_match = re.search(r"minimum sales price\s*(\d+)\s*usd/eur/gbp", category_text)
        if (not direct_match or not mls_match
                or not minimum_match
                or re.search(r"(?<![a-z0-9-])\.si(?![a-z0-9-])", category_text) is None):
            raise SedoError("fee_terms_unverified")
        direct_rate = Decimal(direct_match.group(1)) / Decimal("100")
        mls_rate = Decimal(mls_match.group(1)) / Decimal("100")
        maximum_rate = max(direct_rate, mls_rate)
        return {
            "sedo_fee_rate": format(maximum_rate, "f"),
            "direct_marketplace_fee_rate": format(direct_rate, "f"),
            "sedomls_fee_rate": format(mls_rate, "f"),
            "domain_category": "I",
            "minimum_sale_price_eur": minimum_match.group(1),
            "readback_verified": True,
            "readback_at": datetime.now(timezone.utc).isoformat(),
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "evidence_refs": [PRODUCTION_FEE_PAGE_URL],
        }

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
            if not isinstance(row, dict) or str(row.get("service", "")).lower() != "sedo":
                continue
            partnerid = row.get("partnerid")
            signkey = row.get("signkey")
            username = row.get("username")
            password = row.get("password")
            if (str(partnerid).isdigit() and isinstance(signkey, str) and signkey
                    and isinstance(username, str) and username and len(username) <= 25
                    and isinstance(password, str) and password and len(password) <= 16):
                self._credentials = {
                    "partnerid": str(int(partnerid)),
                    "signkey": signkey,
                    "username": username,
                    "password": password,
                }
                return self._credentials
        raise CredentialMissing()

    def _request(
        self,
        method: str,
        function: str,
        *,
        params: list[tuple[str, str]] | None = None,
        mutating: bool = False,
    ) -> bytes:
        url = urllib.parse.urljoin(self.base_url, function)
        data = urllib.parse.urlencode(params or []).encode("utf-8") if method == "POST" else None
        if method == "GET" and params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Accept": "application/xml",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "LifeManager-domain-flip/1",
            },
            method=method,
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if mutating and error.code >= 500:
                raise EffectUnknown() from None
            raise SedoError("http_error") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            if mutating:
                raise EffectUnknown() from None
            raise SedoError("provider_read_failed") from None

    @staticmethod
    def _parse_xml(payload: bytes) -> ET.Element:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            raise SedoError("xml_invalid") from None
        if _local_name(root.tag).upper() == "SEDOFAULT":
            code = _text(root, "faultcode") or "unknown"
            safe_code = "".join(char for char in code if char.isalnum())[:24]
            raise SedoError(f"provider_fault:{safe_code or 'unknown'}")
        return root

    def _credential_params(self) -> list[tuple[str, str]]:
        credentials = self._load_credentials()
        return [
            ("partnerid", credentials["partnerid"]),
            ("signkey", credentials["signkey"]),
            ("username", credentials["username"]),
            ("password", credentials["password"]),
            ("output_method", "xml"),
        ]

    def _ai_category_path(self) -> list[str]:
        xml = self._request(
            "GET",
            "DomainCategories",
            params=[("output_method", "xml"), ("language", "en")],
        )
        root = self._parse_xml(xml)
        for main in root.iter():
            if (_local_name(main.tag) != "maincategory"
                    or (main.get("name") or "").casefold() != "computers"):
                continue
            for subcategory in main.iter():
                if (_local_name(subcategory.tag) == "subcategory1"
                        and (subcategory.get("name") or "").casefold() == "artificial intelligence"):
                    main_id, subcategory_id = main.get("id"), subcategory.get("id")
                    if main_id and subcategory_id:
                        return [main_id, subcategory_id]
        raise SedoError("ai_category_unavailable")

    @staticmethod
    def _price_text(value: Decimal) -> str:
        if value <= 0:
            raise ValueError("price_invalid")
        rounded = value.quantize(Decimal("0.01"))
        if rounded != value:
            raise ValueError("price_precision_invalid")
        return format(rounded, "f")

    def insert_for_sale(
        self,
        domain: str,
        price_eur: Decimal,
        min_price_eur: Decimal,
    ) -> dict[str, Any]:
        domain = _domain(domain)
        price = _decimal(price_eur)
        min_price = _decimal(min_price_eur)
        if min_price <= 0 or price < min_price:
            raise ValueError("price_range_invalid")
        categories = self._ai_category_path()
        params = self._credential_params()
        index = 0
        entry = [
            (f"domainentry[{index}][domain]", domain),
            *[(f"domainentry[{index}][category][{i}]", category)
              for i, category in enumerate(categories)],
            (f"domainentry[{index}][forsale]", "1"),
            (f"domainentry[{index}][price]", self._price_text(price)),
            (f"domainentry[{index}][minprice]", self._price_text(min_price)),
            (f"domainentry[{index}][fixedprice]", "0"),
            (f"domainentry[{index}][currency]", "0"),
            (f"domainentry[{index}][domainlanguage]", "en"),
        ]
        xml = self._request("POST", "DomainInsert", params=params + entry, mutating=True)
        root = self._parse_xml(xml)
        items = [node for node in root.iter() if _local_name(node.tag) == "item"]
        for item in items:
            if _text(item, "domain") == domain:
                status = (_text(item, "status") or "").casefold()
                if status != "ok":
                    raise SedoError("domain_insert_rejected")
                return {
                    "domain": domain,
                    "status": "listing-pending",
                    "listed": False,
                    "provider": "sedo",
                    "provider_receipt_id": None,
                    "readback_verified": False,
                    "price_eur": price,
                    "min_price_eur": min_price,
                    "category_ids": categories,
                }
        raise SedoError("domain_insert_response_missing")

    def domain_status(self, domain: str) -> dict[str, Any]:
        domain = _domain(domain)
        params = self._credential_params() + [("domainlist[0]", domain)]
        xml = self._request("POST", "DomainStatus", params=params)
        root = self._parse_xml(xml)
        item = next((node for node in root.iter()
                     if _local_name(node.tag) == "item" and _text(node, "domain") == domain), None)
        if item is None:
            return {"domain": domain, "listed": False, "status": "not-found",
                    "provider": "sedo", "provider_receipt_id": None, "readback_verified": True}
        currency = _currency(_text(item, "currency"))
        price = _decimal(_text(item, "price") or "0")
        domain_status = _text(item, "domainstatus")
        for_sale = (_text(item, "forsale") or "").lower() in {"true", "1"}
        known = domain_status in {"0", "1"} and currency in {"EUR", "USD", "GBP"}
        if not known:
            raise SedoError("domain_status_unverified")
        listed = domain_status == "1" and for_sale
        return {
            "domain": domain,
            "listed": listed,
            "status": "listed" if listed else "not-listed",
            "price": price,
            "currency": currency,
            "provider": "sedo",
            "provider_receipt_id": None,
            "readback_verified": True,
        }

    def domain_list(self, domains: list[str]) -> list[dict[str, Any]]:
        if not isinstance(domains, list) or not domains or len(domains) > 100:
            raise ValueError("domain_list_invalid")
        clean_domains = [_domain(domain) for domain in domains]
        params = self._credential_params() + [
            ("startfrom", "0"),
            ("results", str(len(clean_domains))),
            ("orderby", "0"),
        ]
        params.extend((f"domain[{index}]", domain) for index, domain in enumerate(clean_domains))
        xml = self._request("POST", "DomainList", params=params)
        root = self._parse_xml(xml)
        result: list[dict[str, Any]] = []
        for item in root.iter():
            if _local_name(item.tag) != "item":
                continue
            domain = _text(item, "domain")
            if domain not in clean_domains:
                continue
            currency = _currency(_text(item, "currency"))
            price = _decimal(_text(item, "price") or "0")
            min_price = _decimal(_text(item, "minprice") or "0")
            result.append({
                "domain": domain,
                "listed": (_text(item, "forsale") or "").lower() in {"true", "1"},
                "price": price,
                "min_price": min_price,
                "fixed_price": (_text(item, "fixedprice") or "0") == "1",
                "currency": currency,
                "domain_language": _text(item, "domainlanguage"),
                "provider": "sedo",
                "readback_verified": True,
            })
        return result
