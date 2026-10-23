"""Fixed, lazy planner for exact owned public-catalog corrections.

Selection is deterministic over the checked-out six pages and committed catalog.
It creates no authority when there is no real correction to make.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import unquote, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from .authority import OwnedDigitalScope
from .candidate_verification import (CURRENT_PAGE_W3C_URL, CurrentPageCriteria, TechnicalCriteria,
                                     _current_navigation, add_current_page_cue, verify_candidate)
from .collaboration import PlannerContext, PublicFact
from .digital_environment import PAGES, PUBLISH_PREFIX, SOURCE_REPO, audit_sources, validate_catalog, verify_readback
from .digital_handoff import ALLOWED_PATHS, PUBLIC_BASE, OwnedChangeContext
from .models.intervention import Candidate
from .models.source import Source

_SOURCE_LINK = re.compile(re.escape(SOURCE_REPO) + r"/tree/[0-9a-f]{40}/products/manager")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_LICENSE_READY = {"livelihood", "debt", "mental-support"}


class CatalogPlanningUnavailable(RuntimeError):
    """A real catalog opportunity could not be safely evaluated; caller must retain UNKNOWN."""

    status = "UNKNOWN"
    reason = "SOURCE_AUDIT_UNAVAILABLE"

    def __init__(self):
        super().__init__("UNKNOWN:SOURCE_AUDIT_UNAVAILABLE")


@dataclass(frozen=True)
class CatalogOpportunity:
    action: str
    target_path: str
    catalog_id: str
    old_url: str
    expected_url: str
    required_label: str | None


@dataclass(frozen=True)
class CurrentPageOpportunity:
    action: str
    target_path: str


class _Anchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if self.current is not None:
            self.current["children"] = True
        if tag == "a":
            self.current = {"href": values.get("href"), "official": "data-official" in values,
                            "aria": values.get("aria-label"), "text": [], "children": False}
        elif self.current is not None:
            self.current["children"] = True

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.current["label"] = "".join(self.current["text"]).strip()
            self.items.append(self.current)
            self.current = None


def _utcnow():
    return datetime.now(timezone.utc)


def _read_served_bundle():
    """Reuse the fixed provider snapshot reader and bind its raw manifest bytes."""
    path = Path(__file__).resolve().parents[1] / "scripts/phase06_kernel_release.py"
    spec = importlib.util.spec_from_file_location("manager_phase06_kernel_release", path)
    if spec is None or spec.loader is None:
        raise ValueError("fixed served snapshot reader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest_bodies = []
    def capture(url):
        body = module.public_get(url)
        if url == module.PUBLIC_BASE + "manifest.json":
            manifest_bodies.append(body)
        return body
    manifest, bodies = module.served_snapshot(get=capture)
    if len(manifest_bodies) != 1 or json.loads(manifest_bodies[0]) != manifest:
        raise ValueError("served manifest changed during snapshot")
    return manifest, bodies, manifest_bodies[0]


def _read_local_bundle(checkout):
    checkout = Path(checkout)
    if checkout.is_symlink() or not checkout.is_dir():
        raise ValueError("invalid pages checkout")
    bundle = checkout / "manager-support"
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("invalid owned service target")
    manifest_path = bundle / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("invalid owned service manifest")
    from .collaboration import _strict_pairs, _no_nonfinite_constant
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_strict_pairs,
                          parse_constant=_no_nonfinite_constant)
    from .digital_environment import verify_bundle
    verify_bundle(bundle, manifest)
    return bundle, manifest, {name: (bundle / name).read_bytes() for name in PAGES}, manifest_path.read_bytes()


def _observed_row(observations, resource_id, expected_url):
    matches = [row for row in observations if isinstance(row, dict) and row.get("id") == resource_id]
    if len(matches) != 1:
        return None
    row = matches[0]
    if (row.get("status") != "REACHABLE_NOT_OUTCOME" or row.get("http_status") != 200
            or row.get("url") != expected_url or row.get("final_url") != expected_url
            or not isinstance(row.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"])):
        return None
    try:
        observed = datetime.fromisoformat(row["observed_at"])
        if observed.tzinfo is None or observed.utcoffset() is None:
            return None
        age = _utcnow() - observed
        if age < timedelta(0) or age > timedelta(hours=2):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return row


def find_catalog_opportunity(baseline_bodies, catalog, source_observations):
    """Return the first exact bounded catalog fix, or None when evidence is unclear."""
    validate_catalog(catalog)
    if not isinstance(baseline_bodies, dict) or set(baseline_bodies) != PAGES:
        return None
    resources = catalog["resources"]
    for page in sorted(PAGES):
        try:
            parser = _Anchors()
            parser.feed(baseline_bodies[page].decode("utf-8"))
        except (UnicodeError, TypeError):
            return None
        for anchor in parser.items:
            if not anchor["official"]:
                continue
            matches = {r["id"]: r for r in resources if anchor["label"] == r["title"] or anchor["href"] == r["url"]}
            if len(matches) != 1:
                continue
            row = next(iter(matches.values()))
            expected_domain_page = row["domain"] + ".html"
            if page not in (expected_domain_page, "control.html") or row["id"] not in _LICENSE_READY:
                continue
            if _observed_row(source_observations, row["id"], row["url"]) is None:
                continue
            if anchor["href"] != row["url"]:
                if not isinstance(anchor["href"], str) or not anchor["href"]:
                    continue
                return CatalogOpportunity("CORRECT_LINK", page, row["id"], anchor["href"], row["url"], None)
            if (not anchor["label"] and not anchor["aria"] and not anchor["children"]):
                return CatalogOpportunity("IMPROVE_ACCESSIBILITY", page, row["id"], row["url"], row["url"], row["title"])
    return None


def _all_source_rows_ready(audit, catalog):
    if not isinstance(audit, dict) or not isinstance(audit.get("sources"), list):
        return False
    expected = {row["id"]: row["url"] for row in catalog["resources"]}
    if len(audit["sources"]) != len(expected) or {r.get("id") for r in audit["sources"] if isinstance(r, dict)} != set(expected):
        return False
    now = _utcnow()
    for row in audit["sources"]:
        try:
            observed = datetime.fromisoformat(row["observed_at"])
            if (row["status"] != "REACHABLE_NOT_OUTCOME" or row["http_status"] != 200
                    or row["url"] != expected[row["id"]] or row["final_url"] != row["url"]
                    or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"])
                    or observed.tzinfo is None or observed.utcoffset() is None
                    or not timedelta(0) <= now - observed <= timedelta(hours=2)):
                return False
        except (KeyError, TypeError, ValueError):
            return False
    return True


def _source_from_row(resource, observed):
    if resource["id"] not in _LICENSE_READY:
        return None
    # These exact rights values were verified in the retained 2026-10-22 rights audit.
    return Source("official:" + resource["id"], resource["url"], "PDL-1.0", "allowed_with_conditions",
                  observed["sha256"], datetime.fromisoformat(observed["observed_at"]), "public_nonpersonal")


def _read_current_page_reference():
    """Read the exact W3C primary definition; redirects and oversized bodies fail closed."""
    from urllib.error import HTTPError, URLError
    from urllib.request import HTTPRedirectHandler

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*_args,**_kwargs):
            return None

    request=Request(CURRENT_PAGE_W3C_URL,headers={
        "User-Agent":"Manager-Current-Page-Source-Review/1.0","Accept":"text/html"},method="GET")
    try:
        opener=build_opener(NoRedirect())
        with opener.open(request,timeout=15) as response:
            if response.status!=200 or response.geturl()!=CURRENT_PAGE_W3C_URL:
                raise ValueError("W3C primary source response changed")
            body=response.read(2*1024*1024+1)
            if (len(body)>2*1024*1024 or "html" not in response.headers.get("Content-Type","").lower()
                    or b"aria-current" not in body.lower() or b"page" not in body.lower()):
                raise ValueError("W3C current-page definition unavailable")
    except (HTTPError,URLError,OSError,TimeoutError) as exc:
        raise ValueError("W3C primary source unavailable") from exc
    source=Source("w3c:aria-current-1.2",CURRENT_PAGE_W3C_URL,"W3C Document License",
                  "allowed_with_conditions",sha256(body).hexdigest(),_utcnow(),"public_nonpersonal")
    source.verify_content(body)
    return source,body


def _read_owned_baseline_page(target):
    """Bind baseline provenance to a fresh exact GET of the owned current page."""
    from urllib.error import HTTPError, URLError
    from urllib.request import HTTPRedirectHandler

    if target not in {"finance.html","mental.html"}:
        raise ValueError("owned baseline target outside fixed allowlist")

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*_args,**_kwargs):
            return None

    url=PUBLIC_BASE+target
    request=Request(url,headers={"User-Agent":"Manager-Current-Page-Source-Review/1.0",
                                 "Accept":"text/html"},method="GET")
    try:
        opener=build_opener(NoRedirect())
        with opener.open(request,timeout=15) as response:
            if (response.status!=200 or response.geturl()!=url
                    or "html" not in response.headers.get("Content-Type","").lower()):
                raise ValueError("owned baseline response changed")
            body=response.read(2*1024*1024+1)
            if len(body)>2*1024*1024:
                raise ValueError("owned baseline exceeded the fixed body bound")
    except (HTTPError,URLError,OSError,TimeoutError) as exc:
        raise ValueError("owned baseline source unavailable") from exc
    return body,_utcnow()


def _private_workspace(path, checkout):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("workspace symlink refused")
    lexical = Path(os.path.abspath(path))
    resolved = path.resolve()
    source = Path(checkout).resolve()
    repository = Path(__file__).resolve().parents[3]
    if lexical != resolved or any(resolved == root or root in resolved.parents or resolved in root.parents
                                  for root in (source, repository)):
        raise ValueError("workspace overlaps source checkout")
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError("workspace must be a fresh private directory")
    else:
        path.mkdir(mode=0o700, parents=True)
    os.chmod(path, 0o700)
    return path


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _candidate_tree_digest(directory):
    directory = Path(directory)
    expected = PAGES | {"manifest.json"}
    if (directory.is_symlink() or not directory.is_dir()
            or {item.name for item in directory.iterdir()} != expected
            or any(item.is_symlink() or not item.is_file() for item in directory.iterdir())):
        raise ValueError("candidate is not the exact seven-file bundle")
    return sha256(b"".join(name.encode() + b"\0" + sha256((directory / name).read_bytes()).digest()
                             for name in sorted(expected))).hexdigest()


def _materialize(baseline_dir, opportunity, source_commit, output_dir, manifest):
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("candidate output must be fresh")
    output_dir.mkdir(mode=0o700, parents=True)
    for name in sorted(PAGES):
        (output_dir / name).write_bytes((baseline_dir / name).read_bytes())
    (output_dir / "manifest.json").write_bytes((baseline_dir / "manifest.json").read_bytes())

    target = output_dir / opportunity.target_path
    body = target.read_bytes().decode("utf-8")
    if opportunity.action == "ADD_CURRENT_PAGE_CUE":
        body=add_current_page_cue(body.encode("utf-8"),opportunity.target_path).decode("utf-8")
    elif opportunity.action == "CORRECT_LINK":
        old = 'href="' + _escape_html(opportunity.old_url) + '"'
        new = 'href="' + _escape_html(opportunity.expected_url) + '"'
        if body.count(old) != 1:
            raise ValueError("catalog target became ambiguous")
        body = body.replace(old, new, 1)
    else:
        new = 'href="' + _escape_html(opportunity.expected_url) + '"'
        pattern = r'(<a\b[^>]*\bhref="' + re.escape(new[6:-1]) + r'"[^>]*>)\s*</a>'
        body, count = re.subn(pattern, lambda match: match.group(1) + _escape_html(opportunity.required_label) + "</a>", body, count=1)
        if count != 1:
            raise ValueError("exact empty-anchor transform unavailable")
    target.write_text(body, encoding="utf-8")

    for name in PAGES:
        path = output_dir / name
        content = path.read_bytes().decode("utf-8")
        updated, count = _SOURCE_LINK.subn(SOURCE_REPO + "/tree/" + source_commit + "/products/manager", content)
        if count < 1:
            raise ValueError("source revision marker missing")
        path.write_text(updated, encoding="utf-8")
    updated_manifest = dict(manifest)
    updated_manifest["source_commit"] = source_commit
    updated_manifest["files"] = {name: sha256((output_dir / name).read_bytes()).hexdigest() for name in PAGES}
    _write_json(output_dir / "manifest.json", updated_manifest)
    return updated_manifest


def _escape_html(value):
    from html import escape
    return escape(value, quote=True)


def _freshness_scope(started):
    return OwnedDigitalScope("manager-owned-main-v2", frozenset(ALLOWED_PATHS), started,
                             started + timedelta(minutes=10), 7,
                             revoked=os.environ.get("MANAGER_RELEASE_ENABLED", "").lower() != "true")


def _source_audit_file(audit, workspace):
    # audit_sources returns bounded metadata and hashes only; no source body is retained.
    _write_json(workspace / "source-audit.json", audit)


def plan_catalog_change(checkout, workspace, source_commit, now, *, run_id):
    """Prepare one evidence-bound correction, or return None without creating work."""
    if not isinstance(source_commit, str) or _SHA.fullmatch(source_commit) is None:
        raise ValueError("validated main source SHA required")
    if not isinstance(run_id, str) or not re.fullmatch(r"[1-9][0-9]*", run_id):
        raise ValueError("actual workflow run ID required")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware caller observation required")
    started = _utcnow()
    _, local_manifest, local_bodies, local_manifest_bytes = _read_local_bundle(checkout)
    served_manifest, served_bodies, served_manifest_bytes = _read_served_bundle()
    if (served_manifest != local_manifest or served_bodies != local_bodies
            or served_manifest_bytes != local_manifest_bytes):
        raise ValueError("served and checkout seven-file bundles differ")
    verify_readback(served_manifest, served_bodies)

    manager_root = Path(__file__).resolve().parents[1]
    catalog_path = manager_root / "public_goods/service/catalog.json"
    if catalog_path.is_symlink() or not catalog_path.is_file():
        raise ValueError("fixed catalog unavailable")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    validate_catalog(catalog)

    # Existing v1 repairs retain priority; the current-page cue is a separate v2 path.
    legacy_potential = _potential_opportunity(local_bodies, catalog)
    current_potential = None if legacy_potential is not None else find_current_page_opportunity(local_bodies)
    if legacy_potential is None and current_potential is None:
        return None

    try:
        audit = audit_sources(catalog)
    except Exception:
        raise CatalogPlanningUnavailable() from None
    work = _private_workspace(workspace, checkout)
    _source_audit_file(audit, work)
    if not _all_source_rows_ready(audit, catalog):
        raise CatalogPlanningUnavailable()
    if legacy_potential is not None:
        opportunity = find_catalog_opportunity(local_bodies, catalog, audit["sources"])
        if opportunity is None:
            raise CatalogPlanningUnavailable()
        resource = next(row for row in catalog["resources"] if row["id"] == opportunity.catalog_id)
        observed = _observed_row(audit["sources"], resource["id"], resource["url"])
        source = _source_from_row(resource, observed) if observed else None
        if source is None:
            raise CatalogPlanningUnavailable()
        official_sources = (source,)
    else:
        opportunity = find_current_page_opportunity(local_bodies)
        if opportunity is None:
            return None
        try:
            baseline_bytes, baseline_observed_at = _read_owned_baseline_page(opportunity.target_path)
            if baseline_bytes != local_bodies[opportunity.target_path]:
                raise ValueError("current served baseline changed during source binding")
            w3c_source, w3c_reference_bytes = _read_current_page_reference()
        except ValueError:
            raise CatalogPlanningUnavailable() from None
        target_url = PUBLIC_BASE + opportunity.target_path
        baseline_source = Source("owned-baseline:" + opportunity.target_path, target_url,
                                 "Owned public baseline bytes", "allowed_with_conditions",
                                 sha256(baseline_bytes).hexdigest(),
                                 baseline_observed_at, "public_nonpersonal")
        official_sources = (baseline_source, w3c_source)

    baseline_dir = work / "baseline"
    candidate_dir = work / "candidate"
    baseline_dir.mkdir(mode=0o700)
    for name in sorted(PAGES):
        (baseline_dir / name).write_bytes(local_bodies[name])
    (baseline_dir / "manifest.json").write_bytes(local_manifest_bytes)
    _materialize(baseline_dir, opportunity, source_commit, candidate_dir, local_manifest)

    criteria_at = _utcnow()
    for source in official_sources:
        source.require_fresh(criteria_at,48)
    if legacy_potential is not None:
        candidate = Candidate("catalog-" + run_id + "-" + opportunity.catalog_id, opportunity.action,
                              PUBLISH_PREFIX + opportunity.target_path, (official_sources[0].source_id,),
                              "verified_official_link_target" if opportunity.action == "CORRECT_LINK" else "accessible_link_label")
        criteria = TechnicalCriteria(candidate, opportunity.old_url, opportunity.expected_url,
                                     opportunity.required_label, official_sources, criteria_at)
        context = PlannerContext("Make one reviewed official-support link correction or accessible label repair.",
                                 (PublicFact(official_sources[0],
                                             f"Official source {resource['id']} returned HTTP 200 at its catalog URL; this establishes reachability, not outcome."),),
                                 criteria_at)
    else:
        candidate = Candidate("current-page-" + run_id + "-" + opportunity.target_path.removesuffix(".html"),
                              opportunity.action,PUBLISH_PREFIX + opportunity.target_path,
                              tuple(source.source_id for source in official_sources),"current_page_navigation_cue")
        criteria = CurrentPageCriteria(candidate,official_sources,w3c_reference_bytes,criteria_at)
        context = PlannerContext("Add one machine-readable current-page cue to the owned header navigation.",
                                 (PublicFact(official_sources[0],
                                             "The exact owned public page GET has one header-navigation self-link and no current-page cue."),
                                  PublicFact(official_sources[1],
                                             "W3C WAI-ARIA 1.2 defines the page token for the current page; this technical definition does not establish human benefit.")),
                                 criteria_at)
    assessment = verify_candidate(baseline_dir, candidate_dir, criteria)
    if assessment.status != "VERIFIED_TECHNICAL":
        shutil.rmtree(candidate_dir)
        return None
    scope = _freshness_scope(started)
    candidate_digest = _candidate_tree_digest(candidate_dir)
    verify_candidate_in_browser(candidate_dir, source_commit, candidate_digest)
    if _candidate_tree_digest(candidate_dir) != candidate_digest:
        raise ValueError("candidate bytes changed during browser verification")
    final_assessment = verify_candidate(baseline_dir, candidate_dir, criteria)
    if final_assessment.status != "VERIFIED_TECHNICAL" or final_assessment.candidate_digest != assessment.candidate_digest:
        raise ValueError("candidate changed after browser verification")
    owned_context = OwnedChangeContext(run_id, context, baseline_dir, candidate_dir, criteria)
    return owned_context, final_assessment, scope


def find_current_page_opportunity(baseline_bodies):
    """Choose one exact current-page cue in fixed finance then mental order."""
    if not isinstance(baseline_bodies,dict) or set(baseline_bodies)!=PAGES:
        return None
    for page in ("finance.html","mental.html"):
        status,_=_current_navigation(baseline_bodies[page],page)
        if status=="MISSING":
            return CurrentPageOpportunity("ADD_CURRENT_PAGE_CUE",page)
        if status!="CURRENT":
            return None
    return None


def _potential_opportunity(bodies, catalog):
    """Cheap no-network probe for only the two fixed transform shapes."""
    validate_catalog(catalog)
    for page in sorted(PAGES):
        parser = _Anchors()
        try:
            parser.feed(bodies[page].decode("utf-8"))
        except (UnicodeError, TypeError):
            return None
        for anchor in parser.items:
            if not anchor["official"]:
                continue
            matches = {r["id"]: r for r in catalog["resources"] if anchor["label"] == r["title"] or anchor["href"] == r["url"]}
            if len(matches) != 1:
                continue
            resource = next(iter(matches.values()))
            if resource["id"] not in _LICENSE_READY or page not in (resource["domain"] + ".html", "control.html"):
                continue
            if anchor["href"] != resource["url"] and isinstance(anchor["href"], str) and anchor["href"]:
                return CatalogOpportunity("CORRECT_LINK", page, resource["id"], anchor["href"], resource["url"], None)
            if anchor["href"] == resource["url"] and not anchor["label"] and not anchor["aria"] and not anchor["children"]:
                return CatalogOpportunity("IMPROVE_ACCESSIBILITY", page, resource["id"], resource["url"], resource["url"], resource["title"])
    return None


def _sanitized_environment():
    blocked = ("GITHUB_", "ACTIONS_", "AWS_", "AZURE_", "GOOGLE_", "SUPABASE_", "DATABASE_", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "_KEY", "AUTH", "CREDENTIAL", "COOKIE", "SESSION", "BEARER")
    blocked += ("SSH_AUTH_SOCK", "SSH_ASKPASS", "GIT_", "NPM_CONFIG_", "NETRC", "CURL_HOME", "DOCKER_CONFIG")
    env = {k: v for k, v in os.environ.items() if not any(part in k.upper() for part in blocked)}
    env["NPM_CONFIG_USERCONFIG"] = os.devnull
    env["MANAGER_BASE_URL"] = "http://127.0.0.1:8765/"
    return env


def _report_counts(report):
    tests = []
    def visit(suite):
        if not isinstance(suite, dict):
            return
        tests.extend(suite.get("specs", []))
        for child in suite.get("suites", []):
            visit(child)
    for suite in report.get("suites", []):
        visit(suite)
    by_project = {"desktop": 0, "mobile": 0}
    passed = skipped = unexpected = total = 0
    for spec in tests:
        for test in spec.get("tests", []):
            total += 1
            project = test.get("projectName")
            if project not in by_project:
                unexpected += 1
                continue
            by_project[project] += 1
            results = test.get("results", [])
            if test.get("expectedStatus") == "skipped" or any(r.get("status") == "skipped" for r in results):
                skipped += 1
            elif test.get("expectedStatus") != "passed" or len(results) != 1 or results[0].get("status") != "passed":
                unexpected += 1
            else:
                passed += 1
    return {"total": total, "by_project": by_project, "passed": passed, "skipped": skipped, "unexpected": unexpected}


def verify_candidate_in_browser(candidate_dir, source_sha, candidate_digest):
    """Run the locked existing browser suite against this exact private candidate."""
    return _verify_candidate_in_browser(candidate_dir, source_sha, candidate_digest, Path(__file__).resolve().parents[1])


def _start_candidate_server(candidate_dir, candidate_digest):
    candidate_dir = Path(candidate_dir)
    files = {name: (candidate_dir / name).read_bytes() for name in PAGES | {"manifest.json"}}
    if _candidate_tree_digest(candidate_dir) != candidate_digest:
        raise ValueError("candidate digest changed before browser server bind")

    class CandidateHandler(BaseHTTPRequestHandler):
        def _respond(self, include_body):
            path = unquote(urlsplit(self.path).path)
            name = path.removeprefix("/")
            if path != "/" + name or name not in files:
                self.send_error(404)
                return
            body = files[name]
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if name == "manifest.json" else "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if include_body:
                self.wfile.write(body)

        def do_GET(self):
            self._respond(True)

        def do_HEAD(self):
            self._respond(False)

        def log_message(self, *_args):
            pass

    class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
        # Permit a fresh owned listener after our own prior connections enter TIME_WAIT.
        # An active incumbent listener still blocks bind because SO_REUSEPORT stays off.
        allow_reuse_address = True
        allow_reuse_port = False

    try:
        server = ExclusiveThreadingHTTPServer(("127.0.0.1", 8765), CandidateHandler)
    except OSError:
        raise ValueError("candidate browser port unavailable") from None
    thread = Thread(target=server.serve_forever, name="manager-owned-candidate-http", daemon=True)
    thread.start()
    try:
        opener = build_opener(ProxyHandler({}))
        for name, expected in files.items():
            request = Request("http://127.0.0.1:8765/" + name, method="GET")
            with opener.open(request, timeout=5) as response:
                if response.status != 200 or response.read() != expected:
                    raise ValueError("loopback candidate bytes differ")
    except Exception:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        raise ValueError("candidate browser server attestation failed") from None
    return server, thread


def _verify_candidate_in_browser(candidate_dir, source_sha, candidate_digest, manager_root):
    if not _SHA.fullmatch(source_sha) or not re.fullmatch(r"[a-f0-9]{64}", candidate_digest):
        raise ValueError("browser candidate binding required")
    candidate_dir = Path(candidate_dir)
    if candidate_dir.is_symlink() or not candidate_dir.is_dir():
        raise ValueError("browser candidate directory invalid")
    from .digital_environment import verify_bundle
    candidate_manifest = json.loads((candidate_dir / "manifest.json").read_text(encoding="utf-8"))
    verify_bundle(candidate_dir, candidate_manifest)
    if candidate_manifest.get("source_commit") != source_sha:
        raise ValueError("browser source SHA differs from candidate manifest")
    if _candidate_tree_digest(candidate_dir) != candidate_digest:
        raise ValueError("candidate digest changed before browser run")
    manager_root = Path(manager_root)
    suite = manager_root / "tests/e2e"
    output_root = manager_root / "output"
    output = output_root / "service"
    if output_root.is_symlink() or output.is_symlink():
        raise ValueError("browser report path symlink refused")
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    report_path = output / "browser-results.json"
    if report_path.exists() or report_path.is_symlink():
        report_path.unlink()
    server_env = _sanitized_environment()
    server, server_thread = _start_candidate_server(candidate_dir, candidate_digest)
    try:
        proc = subprocess.run(["npm", "test"], cwd=suite, env=server_env, capture_output=True,
                             text=True, timeout=600, check=False)
        if proc.returncode != 0 or not report_path.is_file() or report_path.is_symlink():
            raise ValueError("browser suite failed or fresh report missing")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        counts = _report_counts(report)
        if (counts != {"total": 16, "by_project": {"desktop": 8, "mobile": 8},
                       "passed": 16, "skipped": 0, "unexpected": 0}):
            raise ValueError("browser report did not contain the exact expected passing suite")
        if _candidate_tree_digest(candidate_dir) != candidate_digest:
            raise ValueError("candidate bytes changed during browser suite")
        if json.loads((candidate_dir / "manifest.json").read_text(encoding="utf-8")).get("source_commit") != source_sha:
            raise ValueError("candidate source SHA changed during browser suite")
        return {"status": "VERIFIED_BROWSER", "source_sha": source_sha,
                "candidate_digest": candidate_digest, "bundle_sha256": _candidate_tree_digest(candidate_dir),
                "counts": counts, "report_sha256": sha256(report_path.read_bytes()).hexdigest()}
    except subprocess.TimeoutExpired as exc:
        raise ValueError("browser suite timed out") from exc
    finally:
        server.shutdown()
        server_thread.join(timeout=5)
        server.server_close()
