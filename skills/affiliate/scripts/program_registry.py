#!/usr/bin/env python3
"""Validate and query the versioned Affiliate program research registry."""

import argparse
import hashlib
import hmac
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from job_journal import JobStateError, resume_effect, start_effect, unresolved_effect, verify_effect


REQUIRED = {
    "id", "priority", "network", "decision", "program_url", "terms_url",
    "commission", "next_action", "evidence",
    "credential_ref",
}

GETRESPONSE_URL = "https://dash.partnerstack.com/application?company=getresponse&group=default"
GETRESPONSE_APPLICATION_API = "https://api.partnerstack.com/api/network_applications/stck_NCzCmpfaODzjl3"
ELEVENLABS_HOME = "https://elevenlabs.io/app/home"
ELEVENLABS_LINKS = "https://dash.partnerstack.com/elevenlabsinc/links"
TTS_PLACEMENT = "elevenlabs-text-to-speech-api-for-developers"
TTS_LINK_FIELD = "TTS API affiliate link"
TTS_DESTINATION = "https://elevenlabs.io/text-to-speech"
DEFAULT_ELEVENLABS_DESTINATION = "https://elevenlabs.io"
GETRESPONSE_PROMOTION = (
    "We publish evidence-led English software buying guides on aniccaai.com and disclose "
    "affiliate relationships before calls to action. We distribute each guide through "
    "@selawmqt on X, measure provider-side clicks and approved commissions, and update "
    "articles from official product documentation. For GetResponse, we will create "
    "email-marketing and automation comparison and how-to content for creators and small "
    "businesses, then link readers directly to GetResponse from the relevant article."
)


def load_registry(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("market") != "en":
        raise ValueError("unsupported program registry")
    programs = data.get("programs")
    if not isinstance(programs, list) or not programs:
        raise ValueError("empty program registry")
    ids = set()
    for program in programs:
        if set(program) != REQUIRED or program["id"] in ids:
            raise ValueError("invalid or duplicate program record")
        if not program["program_url"].startswith("https://"):
            raise ValueError("program URL must use HTTPS")
        ids.add(program["id"])
    return sorted(programs, key=lambda item: item["priority"])


def credential_state(program):
    secret_ref = program["credential_ref"]
    if secret_ref is None:
        return {"id": program["id"], "credential_state": "NOT_CONFIGURED"}
    parsed = urlparse(secret_ref)
    if parsed.scheme != "keychain" or not parsed.netloc or not parsed.path[1:]:
        raise ValueError("invalid credential reference")
    environment = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "HOME": pwd.getpwuid(os.getuid()).pw_dir,
    }
    result = subprocess.run(
        [
            "/usr/bin/security", "find-generic-password", "-s", parsed.netloc,
            "-a", parsed.path[1:], "-w",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
        env=environment,
    )
    state = "VERIFIED_NONEMPTY" if result.returncode == 0 and result.stdout.strip() else "MISSING_OR_EMPTY"
    return {"id": program["id"], "credential_ref": secret_ref, "credential_state": state}


def ensure_credential_section(text, label, source_label, credential_ref):
    section = re.search(rf"(?ms)^## {re.escape(label)}\n.*?(?=^## |\Z)", text)
    if section is not None:
        return text
    if not source_label:
        raise ValueError("private credential section is missing")
    source = re.search(rf"(?ms)^## {re.escape(source_label)}\n.*?(?=^## |\Z)", text)
    login = re.search(r"(?m)^- Login:\s*(.+)$", source.group() if source else "")
    if login is None:
        raise ValueError("source credential login is missing")
    return text.rstrip() + (
        f"\n\n## {label}\n"
        f"- Login: {login.group(1).strip()}\n"
        "- Password: \n"
        f"- Keychain: `{credential_ref}`\n"
        "- Verification: `UNVERIFIED`\n"
    )


def store_credential(program, label, markdown_path, verification, source_label=None):
    secret_ref = program["credential_ref"]
    if secret_ref is None:
        raise ValueError("credential reference is not configured")
    parsed = urlparse(secret_ref)
    if parsed.scheme != "keychain" or not parsed.netloc or not parsed.path[1:]:
        raise ValueError("invalid credential reference")
    secret = sys.stdin.buffer.readline().rstrip(b"\r\n")
    if len(secret) < 12 or b"\x00" in secret:
        raise ValueError("credential must contain at least 12 non-NUL bytes")
    markdown_path = markdown_path.expanduser()
    text = markdown_path.read_text(encoding="utf-8")
    text = ensure_credential_section(text, label, source_label, secret_ref)
    section = re.search(
        rf"(?ms)^## {re.escape(label)}\n.*?(?=^## |\Z)", text,
    )
    if section is None or not re.search(r"(?m)^- Password: .*$", section.group()):
        raise ValueError("private credential section is missing")
    updated_section = re.sub(
        r"(?m)^- Password: .*$",
        "- Password: " + secret.decode("utf-8"),
        section.group(),
        count=1,
    )
    updated_section = re.sub(
        r"(?m)^- Verification: .*$",
        f"- Verification: `{verification}`",
        updated_section,
        count=1,
    )
    updated = text[:section.start()] + updated_section + text[section.end():]
    markdown_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{markdown_path.name}.", dir=markdown_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(updated)
        os.chmod(temporary, 0o600)
        os.replace(temporary, markdown_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    if secret.decode("utf-8") not in markdown_path.read_text(encoding="utf-8"):
        raise ValueError("private Markdown readback mismatch")

    environment = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "HOME": pwd.getpwuid(os.getuid()).pw_dir,
    }
    subprocess.run(
        [
            "/usr/bin/security", "add-generic-password", "-U", "-s", parsed.netloc,
            "-a", parsed.path[1:], "-w", secret.decode("utf-8"),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=True,
        env=environment,
    )
    readback = subprocess.run(
        [
            "/usr/bin/security", "find-generic-password", "-s", parsed.netloc,
            "-a", parsed.path[1:], "-w",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=True,
        env=environment,
    ).stdout.rstrip(b"\r\n")
    if not hmac.compare_digest(secret, readback):
        raise ValueError("Keychain readback mismatch")
    return {
        "id": program["id"],
        "credential_ref": secret_ref,
        "keychain_state": "VERIFIED_NONEMPTY",
        "private_markdown_state": "VERIFIED_NONEMPTY",
    }


def store_login(label, markdown_path, login):
    if not login or len(login) > 320 or any(character.isspace() for character in login):
        raise ValueError("login must be one non-empty token")
    markdown_path = markdown_path.expanduser()
    text = markdown_path.read_text(encoding="utf-8")
    section = re.search(rf"(?ms)^## {re.escape(label)}\n.*?(?=^## |\Z)", text)
    if section is None or not re.search(r"(?m)^- Login: .*$", section.group()):
        raise ValueError("private credential section is missing")
    updated_section = re.sub(
        r"(?m)^- Login: .*$", "- Login: " + login, section.group(), count=1,
    )
    updated = text[:section.start()] + updated_section + text[section.end():]
    fd, temporary = tempfile.mkstemp(prefix=".affiliate-credentials.", dir=markdown_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(updated)
        os.chmod(temporary, 0o600)
        os.replace(temporary, markdown_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    if login not in markdown_path.read_text(encoding="utf-8"):
        raise ValueError("private Markdown login readback mismatch")
    return {"label": label, "private_markdown_login_state": "VERIFIED_NONEMPTY"}


def store_link(label, field, markdown_path, link):
    if not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9 -]{1,63} (affiliate|verification) link", field,
    ):
        raise ValueError("invalid private-link field")
    parsed = urlparse(link)
    if parsed.scheme != "https" or not parsed.netloc or any(character.isspace() for character in link):
        raise ValueError("private link must be one HTTPS URL")
    markdown_path = markdown_path.expanduser()
    text = markdown_path.read_text(encoding="utf-8")
    section = re.search(rf"(?ms)^## {re.escape(label)}\n.*?(?=^## |\Z)", text)
    if section is None:
        raise ValueError("private credential section is missing")
    field_pattern = rf"(?m)^- {re.escape(field)}: .*$"
    if re.search(field_pattern, section.group()):
        updated_section = re.sub(field_pattern, f"- {field}: {link}", section.group(), count=1)
    else:
        updated_section = section.group().rstrip() + f"\n- {field}: {link}\n"
    updated = text[:section.start()] + updated_section + text[section.end():]
    fd, temporary = tempfile.mkstemp(prefix=".affiliate-links.", dir=markdown_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(updated)
        os.chmod(temporary, 0o600)
        os.replace(temporary, markdown_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    if link not in markdown_path.read_text(encoding="utf-8"):
        raise ValueError("private Markdown link readback mismatch")
    return {"label": label, "field": field, "private_markdown_link_state": "VERIFIED_NONEMPTY"}


def atomic_receipt(path, payload):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _elevenlabs_links(page):
    return page.evaluate(
        """async () => {
            const partnershipResponse = await fetch(
              'https://api.partnerstack.com/api/companies/partnerships/elevenlabsinc',
              {credentials: 'include'});
            const partnership = await partnershipResponse.json().catch(() => ({}));
            if ([401, 403].includes(partnershipResponse.status)) {
              return {state: 'AUTH_REQUIRED', partnership_http: partnershipResponse.status,
                      ensure_http: null, items: []};
            }
            if (!partnershipResponse.ok) {
              return {state: 'PROVIDER_UNAVAILABLE', partnership_http: partnershipResponse.status,
                      ensure_http: null, items: []};
            }
            const key = partnership?.data?.key;
            if (!key) {
              return {state: 'PROVIDER_SCHEMA_INVALID',
                      partnership_http: partnershipResponse.status,
                      ensure_http: null, items: []};
            }
            const response = await fetch(
              `https://api.partnerstack.com/api/links/ensure/${key}`,
              {method: 'POST', credentials: 'include'});
            const body = await response.json().catch(() => ({}));
            return {
              state: [401, 403].includes(response.status) ? 'AUTH_REQUIRED'
                : response.ok ? 'READY' : 'PROVIDER_UNAVAILABLE',
              partnership_http: partnershipResponse.status,
              ensure_http: response.status,
              items: body?.data?.items || [],
            };
        }"""
    )


def _link_identity(item):
    url = str(item.get("url", ""))
    parsed = urlparse(url)
    fingerprints = {
        hashlib.sha256(value.encode()).hexdigest()
        for value in (url, parsed.hostname + parsed.path if parsed.hostname else "", parsed.path)
        if value
    }
    return {
        "provider_link_key": item.get("key"),
        "tracking_custom_link_id": item.get("tracking_custom_link_id"),
        "slug": item.get("slug"),
        "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
        "link_fingerprints": sorted(fingerprints),
        "destination_sha256": hashlib.sha256(str(item.get("dest", "")).encode()).hexdigest(),
    }


def placement_link_field(placement):
    return f"Placement {hashlib.sha256(placement.encode()).hexdigest()[:16]} affiliate link"


def elevenlabs_link_action(
    state, cdp_port, private_markdown, placement, create=False,
    title=None, description=None, destination=None,
):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,80}", placement):
        raise ValueError("invalid ElevenLabs placement")
    if placement == TTS_PLACEMENT:
        title = title or "ElevenLabs TTS API developer benchmark"
        description = description or (
            "Decision-stage benchmark for developers evaluating the ElevenLabs text-to-speech API."
        )
        destination = destination or TTS_DESTINATION
        private_field = TTS_LINK_FIELD
    else:
        if not all(isinstance(value, str) and value.strip() for value in (title, description)):
            raise ValueError("generic placement metadata is required")
        destination = destination or DEFAULT_ELEVENLABS_DESTINATION
        private_field = placement_link_field(placement)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError("Playwright is unavailable") from error
    receipt_path = state / "program-links" / f"{placement}.json"
    job = unresolved_effect(state, "PARTNERSTACK_PLACEMENT_LINK", placement)
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
        pages = [page for context in browser.contexts for page in context.pages]
        if len(pages) != 1:
            raise ValueError("expected one PartnerStack browser page")
        page = pages[0]
        try:
            page.goto(ELEVENLABS_LINKS, wait_until="domcontentloaded", timeout=20_000)
            observed = _elevenlabs_links(page)
            if observed.get("state") == "AUTH_REQUIRED":
                result = {
                    "schema_version": 1,
                    "receipt_type": "PARTNERSTACK_PLACEMENT_LINK",
                    "provider": "elevenlabs",
                    "state": "AUTH_REQUIRED",
                    "reason": "PARTNERSTACK_AUTH_REQUIRED",
                    "placement": placement,
                    "provider_http_status": (
                        observed.get("ensure_http")
                        or observed.get("partnership_http")
                    ),
                    "provider_effect_started": False,
                    "changed": False,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
                atomic_receipt(receipt_path, result)
                return result
            match = next((item for item in observed["items"] if item.get("slug") == placement), None)
            if create and match is None and job:
                result = {
                    "schema_version": 1, "receipt_type": "PARTNERSTACK_PLACEMENT_LINK",
                    "provider": "elevenlabs", "state": "RECONCILE_PENDING",
                    "placement": placement, "job_id": job["job_id"],
                    "deduplicated": True,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
                atomic_receipt(receipt_path, result)
                return result
            if create and match is None:
                page.get_by_text(
                    re.compile(r"^(カスタムリンク|Custom links?)")
                ).first.wait_for(timeout=15_000)
                page.get_by_text(re.compile(r"^(カスタムリンクの作成|Create custom link)$")).click()
                page.get_by_placeholder(re.compile(r"^(タイトル|Title)$")).fill(title[:160])
                page.locator("textarea").fill(description[:500])
                page.get_by_text("https://elevenlabs.io", exact=True).click()
                destinations = page.get_by_role("option").all_inner_texts()
                selected_destination = next((
                    candidate for candidate in (
                        destination, TTS_DESTINATION, DEFAULT_ELEVENLABS_DESTINATION,
                    ) if candidate in destinations
                ), destinations[0] if destinations else None)
                if not selected_destination:
                    raise ValueError("PartnerStack exposed no allowed destination")
                page.get_by_role("option", name=selected_destination, exact=True).click()
                page.get_by_placeholder("your-custom-link").fill(placement)
                job = start_effect(
                    state, "PARTNERSTACK_PLACEMENT_LINK", placement,
                    {"operation": "create_custom_link", "placement": placement,
                     "destination": selected_destination},
                    {"state": "ABSENT", "placement": placement}, 86_400,
                )
                page.get_by_role("button", name=re.compile(r"^(リンクを作成|Create link)$")).last.click()
                for _ in range(20):
                    page.wait_for_timeout(500)
                    observed = _elevenlabs_links(page)
                    match = next((item for item in observed["items"] if item.get("slug") == placement), None)
                    if match:
                        break
            if not create:
                page.get_by_text(
                    re.compile(r"^(カスタムリンク|Custom links?)")
                ).first.wait_for(timeout=15_000)
                page.get_by_text(re.compile(r"^(カスタムリンクの作成|Create custom link)$")).click()
                page.get_by_text("https://elevenlabs.io", exact=True).click()
                destinations = page.get_by_role("option").all_inner_texts()
                result = {
                    "schema_version": 1, "receipt_type": "PARTNERSTACK_LINK_CAPABILITY",
                    "provider": "elevenlabs", "state": "FORM_OBSERVED",
                    "required_fields": ["title", "description", "destination", "slug"],
                    "allowed_destination_count": len(destinations),
                    "allowed_destination_sha256": hashlib.sha256(
                        json.dumps(destinations, sort_keys=True).encode()
                    ).hexdigest(),
                    "existing_link_count": len(observed["items"]),
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
                atomic_receipt(state / "program-links" / "capability.json", result)
                return result
            if not match or not str(match.get("url", "")).startswith("https://try.elevenlabs.io/"):
                raise ValueError("PartnerStack custom-link readback is ambiguous")
            store_link("ElevenLabs", private_field, private_markdown, match["url"])
            external = {"state": "VERIFIED", "placement": placement, **_link_identity(match)}
            if job:
                verify_effect(state, job["job_id"], external)
            result = {
                "schema_version": 1, "receipt_type": "PARTNERSTACK_PLACEMENT_LINK",
                "provider": "elevenlabs", **external,
                "private_link_state": "VERIFIED_NONEMPTY",
                "private_link_field": private_field,
                "deduplicated": job is None,
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
            atomic_receipt(receipt_path, result)
            return result
        finally:
            page.goto(ELEVENLABS_HOME, wait_until="domcontentloaded", timeout=20_000)


def apply_getresponse(state, cdp_port, profile_path):
    """Submit the one admitted GetResponse application under a durable effect fence."""
    receipt_path = state / "program-applications" / "getresponse.json"
    if receipt_path.is_file():
        prior = json.loads(receipt_path.read_text(encoding="utf-8"))
        if prior.get("state") in {
            "APPLICATION_PENDING", "APPROVED", "REJECTED", "SUBMISSION_REJECTED",
            "ELIGIBILITY_BLOCKED",
        }:
            return {**prior, "deduplicated": True}
    pending_job = unresolved_effect(state, "PROVIDER_APPLICATION", "getresponse")
    profile = json.loads(profile_path.expanduser().read_text(encoding="utf-8"))
    linkedin = str(profile.get("candidate", {}).get("linkedin_url", ""))
    if not linkedin.startswith(("https://linkedin.com/", "https://www.linkedin.com/")):
        raise ValueError("verified LinkedIn profile is unavailable")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError("Playwright is unavailable") from error
    job = None
    result = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
        pages = [page for context in browser.contexts for page in context.pages]
        if len(pages) != 1:
            raise ValueError("expected one PartnerStack browser page")
        page = pages[0]
        try:
            page.goto(GETRESPONSE_URL, wait_until="domcontentloaded", timeout=20_000)
            page.get_by_text("GetResponse Affiliate Application", exact=True).wait_for(timeout=15_000)
            provider_application = page.evaluate(
                """async url => {
                    const response = await fetch(url, {credentials: 'include'});
                    const body = await response.json();
                    const data = body && body.data || {};
                    return {http: response.status, key: data.key || null,
                            status: data.status || null, created_at: data.created_at || null};
                }""",
                GETRESPONSE_APPLICATION_API,
            )
            rendered_before = page.locator("body").inner_text()
            eligibility_blocked = (
                "PartnerStack Marketplaceのロックを解除する" in rendered_before
                or "unlock partnerstack marketplace" in rendered_before.casefold()
            )
            if eligibility_blocked and not provider_application.get("key"):
                external = {
                    "state": "ELIGIBILITY_BLOCKED",
                    "url": page.url,
                    "rendered_text_sha256": hashlib.sha256(
                        rendered_before.encode()
                    ).hexdigest(),
                }
                if pending_job:
                    verify_effect(state, pending_job["job_id"], external)
                result = {
                    "schema_version": 1, "receipt_type": "PROGRAM_APPLICATION",
                    "program": "getresponse", **external, "deduplicated": False,
                }
                atomic_receipt(receipt_path, result)
                return result
            if provider_application.get("key"):
                external = {
                    "state": "APPLICATION_PENDING",
                    "url": page.url,
                    "provider_key_sha256": hashlib.sha256(
                        str(provider_application["key"]).encode()
                    ).hexdigest(),
                    "provider_status": provider_application.get("status"),
                }
                if pending_job:
                    verify_effect(state, pending_job["job_id"], external)
                result = {
                    "schema_version": 1, "receipt_type": "PROGRAM_APPLICATION",
                    "program": "getresponse", **external, "deduplicated": True,
                }
                atomic_receipt(receipt_path, result)
                return result
            required_locked = page.locator("input[required][disabled]")
            if required_locked.count() != 3 or not all(
                required_locked.nth(index).input_value().strip() for index in range(3)
            ):
                raise ValueError("PartnerStack identity prefill is incomplete")
            turnstile = page.locator("input[name='cf-turnstile-response']")
            page.wait_for_function(
                "() => !!document.querySelector(\"input[name='cf-turnstile-response']\")?.value",
                timeout=20_000,
            )
            if turnstile.count() != 1 or not turnstile.input_value().strip():
                raise ValueError("PartnerStack Turnstile token is unavailable")
            page.locator("input[name='field_qlNDAL0eQOe6Pk']").fill("Anicca")
            page.locator("input[name='field_PeKF0gSPmi9TIk']").fill("https://aniccaai.com")
            page.locator("input[name='field_7xRPJ4InAwZY8I']").fill("ElevenLabs")
            page.locator("textarea[required]").fill(GETRESPONSE_PROMOTION)
            page.locator("input[name='field_sETYP00rsB0hyP']").fill(
                f"https://x.com/selawmqt {linkedin}"
            )
            country = page.get_by_role("button", name=re.compile(r"^(国を選択|Select country)$", re.I))
            country.click()
            page.get_by_role("option", name="Japan", exact=True).click()
            agency_no = page.get_by_text("No", exact=True)
            agency_no.click()
            if not page.locator("input[type='checkbox']").nth(1).is_checked():
                raise ValueError("agency answer was not selected")
            submit = page.get_by_role(
                "button", name=re.compile(r"^(申し込みを提出|Submit application)$", re.I),
            )
            if not submit.is_enabled():
                raise ValueError("GetResponse application is not submittable")
            if pending_job:
                job = resume_effect(state, "PROVIDER_APPLICATION", "getresponse")
            else:
                job = start_effect(
                    state, "PROVIDER_APPLICATION", "getresponse",
                    {
                        "operation": "submit_application", "program": "getresponse",
                        "application_url": GETRESPONSE_URL,
                        "website": "https://aniccaai.com",
                        "promotion_sha256": hashlib.sha256(GETRESPONSE_PROMOTION.encode()).hexdigest(),
                    },
                    {"state": "FORM_READY", "url": page.url}, 86400,
                )
            with page.expect_response(
                lambda response: (
                    response.request.method == "POST"
                    and response.url.rstrip("/") == "https://api.partnerstack.com/api/applications"
                ),
                timeout=20_000,
            ) as response_info:
                submit.click(timeout=5_000)
            response = response_info.value
            if 200 <= response.status < 300:
                try:
                    page.wait_for_function(
                        """async url => {
                            const response = await fetch(url, {credentials: 'include'});
                            const body = await response.json();
                            return !!(body && body.data && body.data.key);
                        }""",
                        arg=GETRESPONSE_APPLICATION_API,
                        timeout=10_000,
                        polling=500,
                    )
                except Exception:
                    pass
            provider_application = page.evaluate(
                """async url => {
                    const response = await fetch(url, {credentials: 'include'});
                    const body = await response.json();
                    const data = body && body.data || {};
                    return {http: response.status, key: data.key || null,
                            status: data.status || null, created_at: data.created_at || null};
                }""",
                GETRESPONSE_APPLICATION_API,
            )
            accepted = 200 <= response.status < 300 and bool(provider_application.get("key"))
            rejected = 400 <= response.status < 500
            state_name = (
                "APPLICATION_PENDING" if accepted
                else "SUBMISSION_REJECTED" if rejected
                else "SUBMISSION_AMBIGUOUS"
            )
            rendered = page.locator("body").inner_text()
            result = {
                "schema_version": 1, "receipt_type": "PROGRAM_APPLICATION",
                "program": "getresponse", "state": state_name,
                "application_url": GETRESPONSE_URL,
                "observed_url": page.url,
                "rendered_text_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
                "submit_http_status": response.status,
                "provider_readback_http_status": provider_application.get("http"),
                "provider_key_sha256": (
                    hashlib.sha256(str(provider_application["key"]).encode()).hexdigest()
                    if provider_application.get("key") else None
                ),
                "provider_status": provider_application.get("status"),
                "job_id": job["job_id"], "deduplicated": False,
            }
            if accepted or rejected:
                verify_effect(state, job["job_id"], {
                    "state": state_name, "url": page.url,
                    "submit_http_status": response.status,
                    "provider_key_sha256": result["provider_key_sha256"],
                    "provider_status": result["provider_status"],
                })
            atomic_receipt(receipt_path, result)
        finally:
            page.goto(ELEVENLABS_HOME, wait_until="domcontentloaded", timeout=20_000)
    return result


def main():
    parser = argparse.ArgumentParser(prog="affiliate programs")
    parser.add_argument("command", choices=("list", "next", "credential", "store-credential", "store-login", "store-link", "apply", "observe-link-form", "acquire-placement-link"))
    parser.add_argument("--decision", action="append", default=[])
    parser.add_argument("--id")
    parser.add_argument("--label")
    parser.add_argument("--source-label")
    parser.add_argument("--field")
    parser.add_argument("--placement")
    parser.add_argument("--credential-ref")
    parser.add_argument("--state", type=Path, default=Path("~/.local/state/life-manager/affiliate"))
    parser.add_argument("--cdp-port", type=int, default=9324)
    parser.add_argument("--profile", type=Path, default=Path("~/.config/anicca/job-search/profile.json"))
    parser.add_argument(
        "--verification",
        choices=("SAVED_BEFORE_SUBMIT", "VERIFIED_LOGIN"),
        default="SAVED_BEFORE_SUBMIT",
    )
    parser.add_argument(
        "--private-markdown",
        type=Path,
        default=Path("~/.config/anicca/affiliate-credentials.md"),
    )
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / "config" / "programs" / "en-candidates.json"
    programs = load_registry(path)
    if args.decision:
        programs = [item for item in programs if item["decision"] in args.decision]
    if args.id:
        programs = [item for item in programs if item["id"] == args.id]
    if args.command in ("credential", "store-credential", "store-login", "store-link", "apply", "observe-link-form", "acquire-placement-link"):
        if len(programs) != 1:
            return 3
        if args.credential_ref:
            programs[0] = {**programs[0], "credential_ref": args.credential_ref}
        if args.command in ("observe-link-form", "acquire-placement-link"):
            if programs[0]["id"] != "elevenlabs":
                raise ValueError("ElevenLabs link adapter is required")
            if args.command == "acquire-placement-link" and not args.placement:
                raise ValueError("--placement is required")
            result = elevenlabs_link_action(
                args.state.expanduser(), args.cdp_port, args.private_markdown.expanduser(),
                args.placement or TTS_PLACEMENT,
                create=args.command == "acquire-placement-link",
            )
        elif args.command == "apply":
            if programs[0]["id"] != "getresponse":
                raise ValueError("application adapter is unavailable")
            result = apply_getresponse(args.state.expanduser(), args.cdp_port, args.profile)
        elif args.command == "credential":
            result = credential_state(programs[0])
        elif args.command == "store-login":
            if not args.label:
                raise ValueError("--label is required")
            result = store_login(args.label, args.private_markdown, sys.stdin.readline().strip())
        elif args.command == "store-link":
            if not args.label or not args.field:
                raise ValueError("--label and --field are required")
            result = store_link(
                args.label, args.field, args.private_markdown, sys.stdin.readline().strip(),
            )
        else:
            if not args.label:
                raise ValueError("--label is required")
            result = store_credential(
                programs[0], args.label, args.private_markdown, args.verification,
                args.source_label,
            )
    else:
        result = programs[:1] if args.command == "next" else programs
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result else 3


if __name__ == "__main__":
    raise SystemExit(main())
