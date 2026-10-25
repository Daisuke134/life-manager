"""Versioned Railway-worker to privileged-publisher request contract.

The request only identifies a previously prepared intent. It is not a grant,
does not carry credentials, and must be revalidated by the GitHub workflow
against its own immutable source, current target and protected owner scope.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .digital_handoff import LEASE, MAIN_SOURCE_REF, canonical_bytes, validate_intent
from .models.source import _aware


SCHEMA_VERSION = "manager.owned-workflow-request.v2"
_OWNER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_REQUEST_BYTES = 8192
_WORKFLOW_DISPATCH_URL = (
    "https://api.github.com/repos/Daisuke134/life-manager/actions/workflows/"
    "manager-phase06-service.yml/dispatches"
)
_FIELDS = frozenset({
    "schema_version", "owner_id", "effect_key", "packet_sha256",
    "source_commit", "expected_parent", "created_at", "expires_at", "request_id",
})


class RuntimeConfigurationError(RuntimeError):
    """The process is not running in the configured, persistent owner host."""


@dataclass(frozen=True)
class RailwayRuntimeIdentity:
    """Non-secret facts needed to bind one worker boot to its deployed host."""

    project_id: str
    environment_id: str
    service_id: str
    service_name: str
    deployment_id: str
    volume_name: str
    volume_mount_path: str
    repository_owner: str
    repository_name: str
    source_branch: str
    source_commit: str
    owner_id: str
    interval_seconds: int
    owner_enabled: bool
    dispatch_token_available: bool


@dataclass(frozen=True)
class WorkflowDispatchResult:
    """A dispatch acknowledgment, never evidence that publishing completed."""

    status: str
    request_id: str
    http_status: int | None


@dataclass(frozen=True)
class WorkflowRunObservation:
    """Read-only correlation to an exact request-named GitHub workflow run."""

    status: str
    request_id: str
    run_id: int | None = None
    run_status: str | None = None
    conclusion: str | None = None
    run_url: str | None = None
    matching_runs: int = 0


@dataclass(frozen=True)
class GithubRefObservation:
    """Read-only observation of one fixed GitHub branch head."""

    status: str
    branch: str
    commit_sha: str | None = None


@dataclass(frozen=True)
class WorkflowSubmissionResult:
    """Durable one-shot submission state; `sent` is not publish evidence."""

    status: str
    request_id: str
    sent: bool
    http_status: int | None


@dataclass(frozen=True)
class WorkflowBridgeResult:
    """Durable request state after read-only run reconciliation and one send."""

    status: str
    request_id: str
    sent: bool
    run_id: int | None
    run_status: str | None
    http_status: int | None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _post_github_workflow(url, headers, body, timeout):
    request = Request(url, data=body, headers=headers, method="POST")
    with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        return response.status


def _get_github_workflow_runs(url, headers, timeout):
    request = Request(url, headers=headers, method="GET")
    with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        return response.status, response.read(1024 * 1024 + 1)


def read_github_ref_commit(branch, *, token, get=None):
    """Read only the repository's fixed main or gh-pages ref; failure is UNKNOWN."""
    if branch not in {"main", "gh-pages"}:
        raise ValueError("only the fixed Manager source and Pages branches are readable")
    if type(token) is not str or not token.strip():
        raise RuntimeConfigurationError("workflow dispatch credential is not configured")
    url = ("https://api.github.com/repos/Daisuke134/life-manager/git/ref/heads/"
           + branch)
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "Manager-Owned-Workflow-Bridge/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        status, raw = (get or _get_github_workflow_runs)(url, headers, 10)
    except (TimeoutError, OSError, URLError):
        return GithubRefObservation("UNKNOWN", branch)
    if status != 200 or type(raw) not in (bytes, str) or len(raw) > 65536:
        return GithubRefObservation("UNKNOWN", branch)
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError):
        return GithubRefObservation("UNKNOWN", branch)
    ref = data.get("ref") if type(data) is dict else None
    obj = data.get("object") if type(data) is dict else None
    sha = obj.get("sha") if type(obj) is dict else None
    expected_url = f"https://api.github.com/repos/Daisuke134/life-manager/git/commits/{sha}"
    if (ref != "refs/heads/" + branch
            or type(sha) is not str or not _SHA1.fullmatch(sha)
            or obj.get("type") != "commit" or obj.get("url") != expected_url):
        return GithubRefObservation("UNKNOWN", branch)
    return GithubRefObservation("FOUND", branch, sha)


def dispatch_owned_workflow(request, *, token, post=None):
    """Submit one fixed main workflow request; never retry an ambiguous POST.

    HTTP 204 means GitHub accepted the workflow dispatch request. It does not
    prove that a run started, passed admission, published, or reached Pages.
    """
    if type(request) is not OwnedWorkflowRequest:
        raise ValueError("validated owned workflow request required")
    if type(token) is not str or not token.strip():
        raise RuntimeConfigurationError("workflow dispatch credential is not configured")
    payload = {
        "ref": "main",
        "inputs": {
            "owned_request": request.to_json(),
            "request_id": request.request_id,
        },
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "User-Agent": "Manager-Owned-Workflow-Bridge/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        status = (post or _post_github_workflow)(
            _WORKFLOW_DISPATCH_URL, headers, body, 10)
    except HTTPError as exc:
        status = exc.code
    except (TimeoutError, OSError, URLError):
        return WorkflowDispatchResult("UNKNOWN", request.request_id, None)
    if type(status) is not int or not 100 <= status <= 599:
        return WorkflowDispatchResult("UNKNOWN", request.request_id, None)
    if status == 204:
        outcome = "ACCEPTED"
    elif 400 <= status < 500 and status not in (408, 425, 429):
        outcome = "REJECTED"
    else:
        outcome = "UNKNOWN"
    return WorkflowDispatchResult(outcome, request.request_id, status)


def submit_reserved_owned_workflow(journal, request, *, token, post=None, now=None):
    """Claim and send one previously durable request, with no automatic retry."""
    from .outbox import OwnedEffectJournal
    if type(journal) is not OwnedEffectJournal or type(request) is not OwnedWorkflowRequest:
        raise ValueError("owned effect journal and typed workflow request required")
    if type(token) is not str or not token.strip():
        raise RuntimeConfigurationError("workflow dispatch credential is not configured")
    stored = journal.workflow_dispatch_record(request.request_id)
    if stored is None or stored.request_json != request.to_json():
        raise PermissionError("workflow request was not durably reserved with these exact bytes")
    current, claimed = journal.claim_workflow_dispatch(request.request_id, now=now)
    if not claimed:
        status = current.status
        if status == "SENDING":
            status = "UNKNOWN"
        return WorkflowSubmissionResult(status, request.request_id, False,
                                        current.http_status)
    result = dispatch_owned_workflow(request, token=token, post=post)
    stored = journal.save_workflow_dispatch_result(result)
    return WorkflowSubmissionResult(stored.status, request.request_id, True,
                                    stored.http_status)


def observe_owned_workflow_run(request, *, token, get=None, max_pages=10):
    """Find exact request evidence across bounded pages; absence never authorizes resend."""
    if type(request) is not OwnedWorkflowRequest:
        raise ValueError("validated owned workflow request required")
    if type(token) is not str or not token.strip():
        raise RuntimeConfigurationError("workflow dispatch credential is not configured")
    if type(max_pages) is not int or not 1 <= max_pages <= 10:
        raise ValueError("workflow run lookup page bound must be 1..10")
    endpoint = _WORKFLOW_DISPATCH_URL.removesuffix("/dispatches") + "/runs?"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "Manager-Owned-Workflow-Bridge/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    title = "Manager owned request " + request.request_id
    matches = []
    exhausted = False
    for page in range(1, max_pages + 1):
        query = urlencode({"branch": "main", "event": "workflow_dispatch",
                           "head_sha": request.source_commit, "per_page": "100",
                           "page": str(page)})
        try:
            status, raw = (get or _get_github_workflow_runs)(endpoint + query, headers, 10)
        except (TimeoutError, OSError, URLError):
            return WorkflowRunObservation("UNKNOWN", request.request_id)
        if status != 200 or type(raw) not in (bytes, str) or len(raw) > 1024 * 1024:
            return WorkflowRunObservation("UNKNOWN", request.request_id)
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, UnicodeDecodeError):
            return WorkflowRunObservation("UNKNOWN", request.request_id)
        runs = data.get("workflow_runs") if type(data) is dict else None
        if type(runs) is not list or len(runs) > 100:
            return WorkflowRunObservation("UNKNOWN", request.request_id)
        matches.extend(run for run in runs if type(run) is dict
                       and run.get("display_title") == title
                       and run.get("head_sha") == request.source_commit
                       and run.get("head_branch") == "main"
                       and run.get("event") == "workflow_dispatch")
        if len(matches) > 1:
            return WorkflowRunObservation("DUPLICATE", request.request_id,
                                          matching_runs=len(matches))
        if len(runs) < 100:
            exhausted = True
            break
    if not exhausted or len(matches) != 1:
        return WorkflowRunObservation("UNKNOWN", request.request_id,
                                      matching_runs=len(matches))
    run = matches[0]
    run_id = run.get("id")
    run_status = run.get("status")
    conclusion = run.get("conclusion")
    expected_url = f"https://github.com/Daisuke134/life-manager/actions/runs/{run_id}"
    if (type(run_id) is not int or run_id <= 0
            or run_status not in {"queued", "in_progress", "completed"}
            or (conclusion is not None and type(conclusion) is not str)
            or run.get("html_url") != expected_url):
        return WorkflowRunObservation("UNKNOWN", request.request_id)
    return WorkflowRunObservation("FOUND", request.request_id, run_id, run_status,
                                  conclusion, expected_url, 1)


def reconcile_reserved_owned_workflow(journal, request_id, *, token, post=None, get=None,
                                      now=None):
    """Reconcile first, then submit only a never-claimed durable request once.

    An UNKNOWN lookup is not proof that GitHub has no run. It permits a send
    only while the durable journal still says READY, which is atomically changed
    to SENDING before the network request. Every later wake is read-only unless
    a run has already been proven; this function never retries an ambiguous POST.
    """
    from .outbox import OwnedEffectJournal
    if type(journal) is not OwnedEffectJournal:
        raise ValueError("owned effect journal required")
    if type(request_id) is not str or not _SHA256.fullmatch(request_id):
        raise ValueError("stable owned workflow request ID required")
    record = journal.workflow_dispatch_record(request_id)
    if record is None:
        raise ValueError("workflow request was not durably reserved")
    request = parse_owned_workflow_request(record.request_json)
    if request.request_id != request_id or request.effect_key != record.effect_key:
        raise PermissionError("durable workflow request binding is corrupt")
    intent = journal.record(record.effect_key)
    if intent is None:
        raise PermissionError("durable workflow intent is missing")
    validate_owned_workflow_request(
        request, packet=json.loads(intent.packet_json),
        expected_owner_id=request.owner_id, current_parent=request.expected_parent)

    def result(current, sent=False):
        status = "UNKNOWN" if current.status == "SENDING" else current.status
        return WorkflowBridgeResult(status, request_id, sent, current.run_id,
                                    current.run_status, current.http_status)

    if record.status in {"REJECTED", "PRESENT"}:
        return result(record)
    observed = observe_owned_workflow_run(request, token=token, get=get)
    if observed.status != "UNKNOWN":
        record = journal.save_workflow_run_observation(observed)
        return result(record)

    sent = False
    if record.status == "READY":
        submission = submit_reserved_owned_workflow(
            journal, request, token=token, post=post, now=now)
        sent = submission.sent
        record = journal.workflow_dispatch_record(request_id)
        # A run may appear between the first lookup and our POST response.
        observed = observe_owned_workflow_run(request, token=token, get=get)
        if observed.status != "UNKNOWN":
            record = journal.save_workflow_run_observation(observed)
    else:
        record = journal.workflow_dispatch_record(request_id)
    return result(record, sent)


def read_railway_runtime_identity(
    env=None,
    *,
    expected_project_id,
    expected_environment_id,
    expected_service_id,
    expected_volume_name,
    source_root,
    state_root,
    mount_check=os.path.ismount,
    allow_read_only_recovery=False,
):
    """Fail closed unless Railway identity, immutable source and state mount match.

    Expected IDs must come from deployment configuration controlled separately
    from Railway's runtime identity variables. The dispatch credential is only
    checked for presence here and is deliberately not copied into the result.
    This preflight performs no network requests and grants no publish authority.
    """
    env = os.environ if env is None else env
    if type(allow_read_only_recovery) is not bool:
        raise RuntimeConfigurationError("read-only recovery mode must be explicit")

    def required(name):
        value = env.get(name)
        if type(value) is not str or not value or value != value.strip():
            raise RuntimeConfigurationError("missing or malformed Railway owner configuration")
        return value

    expected = {
        "RAILWAY_PROJECT_ID": expected_project_id,
        "RAILWAY_ENVIRONMENT_ID": expected_environment_id,
        "RAILWAY_SERVICE_ID": expected_service_id,
        "RAILWAY_VOLUME_NAME": expected_volume_name,
    }
    if any(type(value) is not str or not value or value != value.strip() for value in expected.values()):
        raise RuntimeConfigurationError("trusted expected Railway identity is required")
    actual = {name: required(name) for name in expected}
    if actual != expected:
        raise RuntimeConfigurationError("Railway deployment identity does not match configured owner")

    service_name = required("RAILWAY_SERVICE_NAME")
    deployment_id = required("RAILWAY_DEPLOYMENT_ID")
    mount_text = required("RAILWAY_VOLUME_MOUNT_PATH")
    repository_owner = required("RAILWAY_GIT_REPO_OWNER")
    repository_name = required("RAILWAY_GIT_REPO_NAME")
    source_branch = required("RAILWAY_GIT_BRANCH")
    source_commit = required("RAILWAY_GIT_COMMIT_SHA")
    owner_enabled_setting = required("MANAGER_OWNER_ENABLED")
    owner_id = required("MANAGER_OWNER_ID")
    interval_text = required("MANAGER_INTERVAL_SECONDS")
    dispatch_token = env.get("MANAGER_WORKFLOW_DISPATCH_TOKEN")

    if (repository_owner, repository_name, source_branch) != ("Daisuke134", "life-manager", "main"):
        raise RuntimeConfigurationError("worker must run from the approved repository main release")
    if type(source_commit) is not str or not _SHA1.fullmatch(source_commit):
        raise RuntimeConfigurationError("immutable source commit is required")
    if owner_enabled_setting not in {"true", "false"}:
        raise RuntimeConfigurationError("the single configured owner switch must be true or false")
    owner_enabled = owner_enabled_setting == "true"
    dispatch_token_available = type(dispatch_token) is str and bool(dispatch_token.strip())
    if not allow_read_only_recovery and not owner_enabled:
        raise RuntimeConfigurationError("the single configured owner must be explicitly enabled")
    try:
        _owner_id(owner_id)
        interval_seconds = int(interval_text)
    except (ValueError, TypeError) as exc:
        raise RuntimeConfigurationError("valid owner identity and bounded cadence are required") from exc
    if str(interval_seconds) != interval_text or not 1 <= interval_seconds <= 86400:
        raise RuntimeConfigurationError("valid owner identity and bounded cadence are required")
    if not allow_read_only_recovery and not dispatch_token_available:
        raise RuntimeConfigurationError("privileged publisher credential is not configured")

    try:
        source = Path(source_root).resolve(strict=True)
        state = Path(state_root).resolve(strict=True)
        mounted = Path(mount_text).resolve(strict=True)
        if not source.is_dir() or not state.is_dir() or not mounted.is_dir():
            raise RuntimeConfigurationError("source and persistent state directories are required")
        if mounted != state or mounted != Path(state_root).resolve(strict=True):
            raise RuntimeConfigurationError("state root must be the configured Railway volume mount")
        if source == state or source in state.parents or state in source.parents:
            raise RuntimeConfigurationError("source and persistent state must be separate trees")
        if not mount_check(mounted):
            raise RuntimeConfigurationError("configured state path is not an attached persistent volume")
    except RuntimeConfigurationError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeConfigurationError("Railway source and persistent state paths are unavailable") from exc

    return RailwayRuntimeIdentity(
        project_id=actual["RAILWAY_PROJECT_ID"],
        environment_id=actual["RAILWAY_ENVIRONMENT_ID"],
        service_id=actual["RAILWAY_SERVICE_ID"],
        service_name=service_name,
        deployment_id=deployment_id,
        volume_name=actual["RAILWAY_VOLUME_NAME"],
        volume_mount_path=str(mounted),
        repository_owner=repository_owner,
        repository_name=repository_name,
        source_branch=source_branch,
        source_commit=source_commit,
        owner_id=owner_id,
        interval_seconds=interval_seconds,
        owner_enabled=owner_enabled,
        dispatch_token_available=dispatch_token_available,
    )


def _owner_id(value):
    if type(value) is not str or not _OWNER_ID.fullmatch(value):
        raise ValueError("bounded configured owner identity required")
    return value


def _request_id(fields):
    return sha256(canonical_bytes(fields)).hexdigest()


def _stable_packet_digest(packet):
    """Bind the full validated intent, including its original lease timestamps."""
    validate_intent(packet)
    stable = {key: value for key, value in packet.items()
              if key != "packet_sha256"}
    return sha256(canonical_bytes(stable)).hexdigest()


@dataclass(frozen=True)
class OwnedWorkflowRequest:
    schema_version: str
    owner_id: str
    effect_key: str
    packet_sha256: str
    source_commit: str
    expected_parent: str
    created_at: str
    expires_at: str
    request_id: str

    def __post_init__(self):
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported owned workflow request schema")
        _owner_id(self.owner_id)
        if (type(self.effect_key) is not str or not _SHA256.fullmatch(self.effect_key)
                or type(self.packet_sha256) is not str or not _SHA256.fullmatch(self.packet_sha256)
                or type(self.source_commit) is not str or not _SHA1.fullmatch(self.source_commit)
                or type(self.expected_parent) is not str or not _SHA1.fullmatch(self.expected_parent)
                or type(self.created_at) is not str or type(self.expires_at) is not str
                or type(self.request_id) is not str or not _SHA256.fullmatch(self.request_id)):
            raise ValueError("immutable effect, packet, source and parent digests required")
        try:
            created = _aware(datetime.fromisoformat(self.created_at))
            expires = _aware(datetime.fromisoformat(self.expires_at))
        except (TypeError, ValueError) as exc:
            raise ValueError("original owned intent lease timestamps required") from exc
        if (created.isoformat() != self.created_at or expires.isoformat() != self.expires_at
                or expires != created + LEASE):
            raise ValueError("owned workflow request must preserve the exact six-hour lease")
        if self.request_id != _request_id(self.to_dict(include_request_id=False)):
            raise ValueError("owned workflow request digest mismatch")

    def to_dict(self, *, include_request_id=True):
        value = {
            "schema_version": self.schema_version,
            "owner_id": self.owner_id,
            "effect_key": self.effect_key,
            "packet_sha256": self.packet_sha256,
            "source_commit": self.source_commit,
            "expected_parent": self.expected_parent,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }
        if include_request_id:
            value["request_id"] = self.request_id
        return value

    def to_json(self):
        return canonical_bytes(self.to_dict()).decode("utf-8")


def create_owned_workflow_request(packet, owner_id, expected_parent):
    """Build a minimal stable reference from a validated durable intent."""
    validate_intent(packet)
    if packet["ref"] != MAIN_SOURCE_REF:
        raise ValueError("owned workflow requests require the versioned main publisher")
    owner_id = _owner_id(owner_id)
    if type(expected_parent) is not str or not _SHA1.fullmatch(expected_parent):
        raise ValueError("immutable current target parent required")
    fields = {
        "schema_version": SCHEMA_VERSION,
        "owner_id": owner_id,
        "effect_key": packet["effect_key"],
        "packet_sha256": _stable_packet_digest(packet),
        "source_commit": packet["candidate"]["source_commit"],
        "expected_parent": expected_parent,
        "created_at": packet["created_at"],
        "expires_at": packet["expires_at"],
    }
    return OwnedWorkflowRequest(**fields, request_id=_request_id(fields))


def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate owned workflow request field")
        result[key] = value
    return result


def parse_owned_workflow_request(raw):
    """Parse exact JSON/dict fields; reject duplicate or caller-added inputs."""
    if type(raw) is str:
        if len(raw.encode("utf-8")) > _MAX_REQUEST_BYTES:
            raise ValueError("owned workflow request is oversized")
        try:
            value = json.loads(raw, object_pairs_hook=_strict_pairs)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid owned workflow request JSON") from exc
    elif type(raw) is dict:
        value = raw
    else:
        raise ValueError("owned workflow request JSON object required")
    if type(value) is not dict or set(value) != _FIELDS:
        raise ValueError("unknown or missing owned workflow request field")
    return OwnedWorkflowRequest(**value)


def validate_owned_workflow_request(request, *, packet, expected_owner_id, current_parent):
    """Rebind a request to trusted workflow facts; request fields grant no power."""
    if type(request) is not OwnedWorkflowRequest:
        request = parse_owned_workflow_request(request)
    validate_intent(packet)
    expected_owner_id = _owner_id(expected_owner_id)
    if type(current_parent) is not str or not _SHA1.fullmatch(current_parent):
        raise ValueError("immutable current target parent required")
    expected = create_owned_workflow_request(packet, expected_owner_id, current_parent)
    if request != expected:
        raise PermissionError("owned request differs from protected owner, packet or target parent")
    return request
