#!/usr/bin/env python3
"""Give each loop its own browser space so they stop destroying each other's work.

Every loop drives the same Chromium. When gig is halfway through a 応募 form and the clip loop
navigates "the" tab, gig's work is gone — and neither loop can tell that it happened.

CDP has the answer already: Target.createBrowserContext is "Similar to an incognito profile but you
can have more than one". So each task leases its own context, and nothing another loop does can reach
into it. Contexts do not share cookies, so the lease seeds the fresh context from the session vault —
the same trick as Playwright's storageState ("reuse this state and start already authenticated").

    python3 cdp_context_lease.py acquire gig            # -> {"context_id":..., "target_id":..., "ws":...}
    python3 cdp_context_lease.py release gig            # dispose the context (tabs die with it)
    python3 cdp_context_lease.py gc --idle-min 45       # reap contexts a crashed loop left behind
    python3 cdp_context_lease.py list
"""
import asyncio
import contextlib
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.request
from urllib.parse import urlparse

try:
    import websockets
except ImportError:
    print(json.dumps({"ok": False, "reason": "pip install websockets"}))
    sys.exit(1)


def _cdp_base():
    return os.environ.get("CLOAK_CDP_BASE_URL", "http://127.0.0.1:9222").rstrip("/")


def _vault_path():
    return os.path.expanduser(
        os.environ.get(
            "CLOAK_SESSION_VAULT_FILE",
            "~/.cloak/vault/daily-driver/auth-state.json",
        )
    )


def _vault_writeback_path():
    return os.path.expanduser(
        os.environ.get("CLOAK_SESSION_VAULT_WRITEBACK_FILE", _vault_path())
    )


def _leases_path():
    return os.path.expanduser(
        os.environ.get("CLOAK_CONTEXT_LEASES_FILE", "~/.cloak/vault/leases.json")
    )


def _max_contexts():
    raw = os.environ.get("CLOAK_BROWSER_MAX_CONTEXTS", "16")
    try:
        limit = int(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "CLOAK_BROWSER_MAX_CONTEXTS must be an integer from 1 to 128"
        ) from error
    if not 1 <= limit <= 128:
        raise ValueError("CLOAK_BROWSER_MAX_CONTEXTS must be an integer from 1 to 128")
    return limit


def _cookie_domains():
    raw = os.environ.get("CLOAK_CONTEXT_COOKIE_DOMAINS", "")
    return tuple(
        value.strip().lower().lstrip(".")
        for value in raw.split(",")
        if value.strip().lstrip(".")
    )


def _cookie_in_scope(cookie, domains):
    if not domains:
        return True
    domain = str(cookie.get("domain") or "").strip().lower().lstrip(".")
    return any(domain == allowed or domain.endswith("." + allowed) for allowed in domains)


def _acquire_url(argv):
    if len(argv) > 3 and isinstance(argv[3], str) and not argv[3].startswith("--"):
        return argv[3]
    return "about:blank"


def _operation_lock_path(target_id):
    leases_dir = os.path.dirname(_leases_path())
    return os.path.join(leases_dir, "operations", f"{target_id}.lock")


def _ledger_lock_path():
    return _leases_path() + ".lock"


def _vault_lock_path():
    return _vault_writeback_path() + ".lock"


def _gc_lock_path():
    return _leases_path() + ".gc.lock"


@contextlib.contextmanager
def _ledger_lock():
    lock_path = _ledger_lock_path()
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def _vault_lock():
    lock_path = _vault_lock_path()
    os.makedirs(os.path.dirname(lock_path), mode=0o700, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as handle:
        os.chmod(lock_path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def _seed_locks():
    """Freeze base and overlay vaults while one context chooses and installs its seed."""
    with contextlib.ExitStack() as stack:
        for path in sorted({_vault_path(), _vault_writeback_path()}):
            lock_path = path + ".lock"
            os.makedirs(os.path.dirname(lock_path), mode=0o700, exist_ok=True)
            handle = stack.enter_context(open(lock_path, "a+", encoding="utf-8"))
            os.chmod(lock_path, 0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            stack.callback(fcntl.flock, handle.fileno(), fcntl.LOCK_UN)
        yield


@contextlib.contextmanager
def _gc_singleflight():
    """Let at most one slow context reaper run for a lease ledger."""
    path = _gc_lock_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _page_ws(target_id):
    return f"ws://{urlparse(_cdp_base()).netloc}/devtools/page/{target_id}"


def _browser_ws():
    d = json.loads(
        urllib.request.urlopen(f"{_cdp_base()}/json/version", timeout=8).read()
    )
    return d["webSocketDebuggerUrl"]


async def _calls(pairs, timeout=20.0):
    """Run several CDP calls on one browser connection; returns the list of results.

    The whole batch shares one deadline. recv() used to wait forever, so disposing a
    context whose renderer was wedged hung this script until the caller's subprocess limit
    killed it (measured 2026-08-06: the gig loop's target recovery died inside `release`).
    A browser that keeps the socket open while never answering must become an exception
    here, not a hang.
    """
    out = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    async with websockets.connect(
        _browser_ws(), max_size=64 * 1024 * 1024, open_timeout=min(10.0, timeout)
    ) as ws:
        for i, (method, params) in enumerate(pairs, start=1):
            await ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError(f"{method} did not answer within {timeout}s")
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=remaining))
                if msg.get("id") == i:
                    if "error" in msg:
                        raise RuntimeError(f"{method}: {msg['error']}")
                    out.append(msg.get("result", {}))
                    break
    return out


async def _page_calls(ws_url, pairs, timeout=20.0):
    """Run CDP calls against one exact leased page target."""
    out = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    async with websockets.connect(
        ws_url, max_size=64 * 1024 * 1024, open_timeout=min(10.0, timeout)
    ) as ws:
        for i, (method, params) in enumerate(pairs, start=1):
            await ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError(f"{method} did not answer within {timeout}s")
                message = json.loads(await asyncio.wait_for(ws.recv(), timeout=remaining))
                if message.get("id") == i:
                    if "error" in message:
                        raise RuntimeError(f"{method}: {message['error']}")
                    out.append(message.get("result", {}))
                    break
    return out


def _pid_alive(pid):
    """Is the process that last proved it holds this lease still running?

    Every acquire()/heartbeat() call is a subprocess of its actual direct-loop holder
    (a one-shot owner pid, or application_parent.py's pid for LeaseHandle's background
    heartbeat thread), so os.getppid() at call time is a legitimate, stable holder id --
    the same holder keeps calling heartbeat with the same ppid until it exits or crashes.
    A -9'd holder never updates `ts` again either, so gc's existing idle_min window already
    catches it eventually; this lets gc catch it on its very next run instead of waiting up
    to idle_min. Unknown/missing pid (legacy rows, or a race writing it) means "cannot tell"
    -- never treated as dead, so it falls back to the idle_min-only path untouched.
    """
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours -- never claimed here, so leave it alone
    except OSError:
        return None  # inconclusive: do not reap on an ambiguous signal


def _holder_pid():
    """Return the durable caller that owns the lease, not a `$()` subshell."""
    configured = os.environ.get("AI_BROWSER_HOLDER_PID", "")
    try:
        pid = int(configured)
    except (TypeError, ValueError):
        pid = 0
    if 0 < pid <= 2_147_483_647 and _pid_alive(pid) is True:
        return pid
    return os.getppid()


def _leases():
    leases_path = _leases_path()
    if os.path.exists(leases_path):
        try:
            with open(leases_path, encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            pass
    return {}


def _save(d):
    leases_path = _leases_path()
    os.makedirs(os.path.dirname(leases_path), exist_ok=True)
    tmp = leases_path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, leases_path)


async def _target_answers(ws_url, timeout):
    try:
        async with websockets.connect(
            ws_url, open_timeout=timeout, ping_interval=None, max_size=1 << 20
        ) as ws:
            await ws.send(json.dumps({
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {"expression": "1", "returnByValue": True},
            }))
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return False
                message = json.loads(await asyncio.wait_for(ws.recv(), timeout=remaining))
                if message.get("id") == 1:
                    return "error" not in message
    except Exception:
        return False


def target_responds(ws_url, timeout=6.0):
    """Does this leased page still answer, or is its renderer wedged?

    A held lease was reused on trust. When gig fills a 応募 form and then navigates that
    same target, the renderer stops and takes its CDP endpoint with it -- the loop's own
    domain-skills already record that -- and the lease keeps handing the dead target back
    on every later pass. On 2026-08-05 that turned one wedged renderer into
    cdp_Page.enable_timeout_after_30s on every B2 for hours: the apply lane could not run
    at all, and nothing in the lease could tell that the thing it was lending was gone.

    Runtime.evaluate of `1` is the cheapest question a live renderer always answers.
    """
    if not ws_url:
        return False
    try:
        return asyncio.run(_target_answers(ws_url, timeout))
    except Exception:
        return False


def _browser_context_exists(context_id):
    """Read the browser's authoritative context inventory; None means inconclusive."""
    if not context_id:
        return False
    try:
        (result,) = asyncio.run(_calls([("Target.getBrowserContexts", {})]))
    except Exception:
        return None
    context_ids = result.get("browserContextIds")
    if not isinstance(context_ids, list):
        return None
    return context_id in context_ids


_PROVISIONING_TIMEOUT_SECONDS = 120


def _provisioning_expired(held, now=None):
    if not isinstance(held, dict) or held.get("provisioning") is not True:
        return False
    now = time.time() if now is None else now
    deadline = held.get("provisioning_deadline")
    if not isinstance(deadline, (int, float)) or isinstance(deadline, bool):
        started = held.get("provisioning_started_at", held.get("ts"))
        if not isinstance(started, (int, float)) or isinstance(started, bool):
            return False
        deadline = started + _PROVISIONING_TIMEOUT_SECONDS
    return now >= deadline


def _lease_is_stale(held, now, idle_min=None):
    """Dead/expired rows are reclaimable immediately; normal rows retain idle GC."""
    if not isinstance(held, dict):
        return False
    if held.get("cleanup_pending") is True:
        return True
    if held.get("parked") is True:
        return False
    if held.get("provisioning") is True:
        return _provisioning_expired(held, now) or _pid_alive(held.get("pid")) is False
    return (
        _pid_alive(held.get("pid")) is False
        or (idle_min is not None and now - held.get("ts", 0) > idle_min * 60)
    )


def _new_slot_blocked(task):
    with _ledger_lock():
        leases = _leases()
        return task not in leases and len(leases) >= _max_contexts()


def _recover_capacity_if_needed(task, wait_seconds=25.0):
    """Reap a bounded stale batch when this task or capacity needs recovery."""
    with _ledger_lock():
        leases = _leases()
        held = leases.get(task)
        needs_reap = _lease_is_stale(held, time.time())
        blocked = task not in leases and len(leases) >= _max_contexts()
    if not needs_reap and not blocked:
        return
    result = gc(idle_min=45, max_reaps=8, priority_task=task)
    if result.get("skipped") != "gc_already_running":
        return
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        with _ledger_lock():
            leases = _leases()
            held = leases.get(task)
            needs_reap = _lease_is_stale(held, time.time())
            blocked = task not in leases and len(leases) >= _max_contexts()
        if not needs_reap and not blocked:
            return
        time.sleep(0.1)


def acquire(task, url="about:blank", no_seed=False):
    with _seed_locks():
        return _acquire_with_seed_locked(task, url=url, no_seed=no_seed)


def _acquire_with_seed_locked(task, url="about:blank", no_seed=False):
    # Routine browser admission must not wait for whole-ledger maintenance. At the
    # actual capacity boundary, however, reclaim one stale row (or briefly wait for the
    # existing single-flight reaper) so this same wake can make forward progress.
    cookies, overlay_origins, seed_fingerprint = _seed_material(url, no_seed)
    _recover_capacity_if_needed(task)
    reservation_token = None
    current_holder = _holder_pid()
    with _ledger_lock():
        leases = _leases()
        held = leases.get(task)
        if held and held.get("provisioning") is True:
            if _pid_alive(held.get("pid")) is not False:
                raise RuntimeError("lease_busy")
            if held.get("context_id"):
                held["provisioning"] = False
                held["cleanup_pending"] = True
                held["ts"] = 0
                held["pid"] = None
                leases[task] = held
            else:
                leases.pop(task, None)
            _save(leases)
            held = leases.get(task)
        parked = bool(held) and held.get("parked") is True
        seed_changed = (parked and seed_fingerprint is not None
                        and held.get("seed_fingerprint") != seed_fingerprint)
        holder_pid_state = _pid_alive(held.get("pid")) if held and not parked else None
        if (held and not parked and held.get("pid") != current_holder
                and holder_pid_state is not False
                and held.get("cleanup_pending") is not True):
            raise RuntimeError("lease_busy")
        holder_dead = bool(held) and not parked and holder_pid_state is False
        if held and (seed_changed or holder_dead or held.get("cleanup_pending") is True or not target_responds(
            held.get("ws") or _page_ws(held.get("target_id") or "")
        )):
            # Dead holder (confirmed via the free, local pid check -- no need to spend up
            # to target_responds()'s 6s network round trip proving what os.kill() already
            # answered) or dead renderer. Drop the whole context so the next block builds a
            # fresh one; waiting out target_responds() here -- or worse, leaving the row for
            # gc's idle_min window -- let a provably-dead holder's leaked context sit open
            # and degrade the shared browser for every other lane in the meantime (measured
            # 2026-09-05: job-search-daily's dead pid 55895 sat in the ledger for 26 wakes
            # of an unrelated task, gig-storefront-direct, timing out on acquire, until a
            # manual `gc --idle-min 0` reaped it).
            try:
                asyncio.run(_calls([(
                    "Target.disposeBrowserContext",
                    {"browserContextId": held.get("context_id")},
                )]))
            except Exception as error:
                if _browser_context_exists(held.get("context_id")) is not False:
                    held["cleanup_pending"] = True
                    held["cleanup_error_type"] = type(error).__name__
                    held["ts"] = 0
                    held["pid"] = None
                    leases[task] = held
                    _save(leases)
                    raise RuntimeError("context_cleanup_pending") from error
            leases.pop(task, None)
            _save(leases)
            held = None
        if held:  # one task owns one durable fence until release
            changed = False
            if held.pop("parked", None) is True:
                held["token"] = secrets.token_hex(16)
                held["generation"] = int(held.get("generation") or 0) + 1
                changed = True
            if not isinstance(held.get("token"), str):
                held["token"] = secrets.token_hex(16)
                changed = True
            if isinstance(held.get("generation"), bool) or not isinstance(held.get("generation"), int):
                held["generation"] = 1
                changed = True
            held["ts"] = int(time.time())
            # Whoever is calling acquire() right now is the current holder, even if a
            # different (now-dead) process originally created this row -- record its ppid so
            # gc's fast pid-liveness path tracks the real owner, not a crashed predecessor.
            held["pid"] = current_holder
            held.pop("cleanup_pending", None)
            held.pop("cleanup_error_type", None)
            changed = True
            if changed:
                leases[task] = held
                _save(leases)
            return {"ok": True, "reused": True, **held}

        if len(leases) >= _max_contexts():
            parked_rows = [
                (name, row) for name, row in leases.items()
                if row.get("parked") is True
            ]
            if not parked_rows:
                raise RuntimeError("browser_context_limit")
            parked_task, parked = min(
                parked_rows,
                key=lambda item: (item[1].get("ts", 0), item[0]),
            )
            try:
                asyncio.run(_calls([(
                    "Target.disposeBrowserContext",
                    {"browserContextId": parked.get("context_id")},
                )]))
            except Exception as error:
                if _browser_context_exists(parked.get("context_id")) is not False:
                    parked["cleanup_pending"] = True
                    parked["cleanup_error_type"] = type(error).__name__
                    parked["ts"] = 0
                    leases[parked_task] = parked
                    _save(leases)
                    raise RuntimeError("context_cleanup_pending") from error
            leases.pop(parked_task, None)
            _save(leases)

        reservation_token = secrets.token_hex(16)
        provisioning_started_at = time.time()
        leases[task] = {
            "provisioning": True,
            "token": reservation_token,
            "generation": 1,
            "pid": current_holder,
            "ts": int(provisioning_started_at),
            "provisioning_started_at": provisioning_started_at,
            "provisioning_deadline": (
                provisioning_started_at + _PROVISIONING_TIMEOUT_SECONDS
            ),
        }
        _save(leases)

    # Context creation and cookie seeding can take tens of seconds. The ledger lock
    # protects only admission/finalization; holding it here serializes every unrelated
    # task behind one slow browser operation.
    ctx_id = None
    try:
        (ctx,) = asyncio.run(_calls([("Target.createBrowserContext", {})]))
        ctx_id = ctx["browserContextId"]
        with _ledger_lock():
            leases = _leases()
            reserved = leases.get(task)
            if not (reserved and reserved.get("provisioning") is True
                    and reserved.get("token") == reservation_token):
                raise RuntimeError("lease_reservation_lost")
            reserved["context_id"] = ctx_id
            leases[task] = reserved
            _save(leases)

        calls = []
        if cookies:
            calls.append(("Storage.setCookies", {"cookies": cookies, "browserContextId": ctx_id}))
        seed_before_app = _has_web_storage_for_origin(url, overlay_origins)
        calls.append(("Target.createTarget", {
            "url": "about:blank" if seed_before_app else url,
            "browserContextId": ctx_id,
        }))
        results = asyncio.run(_calls(calls))
        target_id = results[-1]["targetId"]
        try:
            storage_origins_seeded = (
                _seed_web_storage(_page_ws(target_id), url, overlay_origins)
                if seed_before_app else 0
            )
        except Exception:
            with contextlib.suppress(Exception):
                asyncio.run(_calls([(
                    "Target.disposeBrowserContext", {"browserContextId": ctx_id}
                )]))
            raise

        lease = {
            "context_id": ctx_id,
            "target_id": target_id,
            "ws": _page_ws(target_id),
            "ts": int(time.time()),
            "cookies_seeded": len(cookies),
            "storage_origins_seeded": storage_origins_seeded,
            "seed_fingerprint": seed_fingerprint,
            "token": secrets.token_hex(16),
            "generation": 1,
            "pid": _holder_pid(),
        }
        with _ledger_lock():
            leases = _leases()
            reserved = leases.get(task)
            if not (reserved and reserved.get("provisioning") is True
                    and reserved.get("token") == reservation_token):
                raise RuntimeError("lease_reservation_lost")
            leases[task] = lease
            _save(leases)
        return {"ok": True, "reused": False, **lease}
    except Exception:
        disposed = ctx_id is None
        if ctx_id is not None:
            try:
                asyncio.run(_calls([(
                    "Target.disposeBrowserContext", {"browserContextId": ctx_id}
                )]))
                disposed = True
            except Exception:
                disposed = _browser_context_exists(ctx_id) is False
        with _ledger_lock():
            leases = _leases()
            reserved = leases.get(task)
            if (reserved and reserved.get("provisioning") is True
                    and reserved.get("token") == reservation_token):
                if disposed:
                    leases.pop(task, None)
                else:
                    reserved.pop("provisioning", None)
                    reserved.pop("provisioning_started_at", None)
                    reserved.pop("provisioning_deadline", None)
                    reserved["cleanup_pending"] = True
                    reserved["context_id"] = ctx_id
                    reserved["ts"] = 0
                    reserved["pid"] = None
                    leases[task] = reserved
                _save(leases)
        raise


def _fence_matches(held, token, generation):
    if token is None and generation is None:  # legacy callers remain supported
        return True
    return token == held.get("token") and generation == held.get("generation")


def heartbeat(task, token=None, generation=None):
    with _ledger_lock():
        leases = _leases()
        held = leases.get(task)
        if not held:
            # The ledger mtime rides inside `reason` because that is the only field
            # callers propagate: application_parent's LeaseHandle raises
            # lease_command_failed:{reason} from the returned JSON, and its stderr is
            # captured but never read. No caller string-matches "lease_not_found"
            # exactly (verified across the accepted callers), so
            # extending the string is safe -- and if any residual clobberer remains,
            # the mtime in the parent-error evidence pinpoints the overwrite.
            try:
                ledger_mtime = os.path.getmtime(_leases_path())
            except OSError:
                ledger_mtime = None
            return {"ok": False, "reason": f"lease_not_found ledger_mtime={ledger_mtime}"}
        if not _fence_matches(held, token, generation):
            return {"ok": False, "reason": "lease_fence_mismatch"}
        held["ts"] = int(time.time())
        held["pid"] = _holder_pid()  # same holder proving liveness again; keep pid current
        leases[task] = held
        _save(leases)
        return {
            "ok": True,
            "task": task,
            "token": held.get("token"),
            "generation": held.get("generation"),
            "ts": held["ts"],
        }


def _normalized_cookie_domain(value):
    return str(value or "").strip().lower().lstrip(".")


def _cookie_matches_domain(cookie, domains):
    cookie_domain = _normalized_cookie_domain(cookie.get("domain"))
    return any(
        cookie_domain == domain or cookie_domain.endswith(f".{domain}")
        for domain in domains
    )


def _normalized_origin(value):
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    default_port = (parsed.scheme == "https" and parsed.port in {None, 443}) or (
        parsed.scheme == "http" and parsed.port in {None, 80}
    )
    netloc = parsed.hostname.lower() if default_port else f"{parsed.hostname.lower()}:{parsed.port}"
    return f"{parsed.scheme}://{netloc}"


def _seed_material(target_url, no_seed=False):
    """Load exactly what a new context receives and bind parked reuse to that state."""
    cookies = []
    origins = []
    vault_path = _vault_path()
    vault_exists = os.path.exists(vault_path)
    if not no_seed and vault_exists:
        with open(vault_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            cookies = payload.get("cookies", [])
            origins = payload.get("origins", [])
    overlay_path = _vault_writeback_path()
    overlay_exists = overlay_path != vault_path and os.path.exists(overlay_path)
    if not no_seed and overlay_exists:
        with open(overlay_path, encoding="utf-8") as handle:
            overlay = json.load(handle)
        if isinstance(overlay, dict):
            overlay_cookies = overlay.get("cookies", [])
            overlay_origins = overlay.get("origins", [])
            overlay_domains = {
                _normalized_cookie_domain(cookie.get("domain"))
                for cookie in overlay_cookies if isinstance(cookie, dict)
            }
            cookies = [
                cookie for cookie in cookies if isinstance(cookie, dict)
                and _normalized_cookie_domain(cookie.get("domain")) not in overlay_domains
            ] + [cookie for cookie in overlay_cookies if isinstance(cookie, dict)]
            origins = overlay_origins
    cookies = [cookie for cookie in cookies if isinstance(cookie, dict)]
    cookie_domains = _cookie_domains()
    if cookie_domains:
        cookies = [cookie for cookie in cookies if _cookie_in_scope(cookie, cookie_domains)]
    target_origin = _normalized_origin(target_url)
    scoped_origins = [
        row for row in origins if isinstance(row, dict)
        and _normalized_origin(row.get("origin")) == target_origin
    ] if isinstance(origins, list) else []
    fingerprint = hashlib.sha256(json.dumps(
        {"cookies": cookies, "origins": scoped_origins, "no_seed": bool(no_seed)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest() if no_seed or vault_exists or overlay_exists else None
    return cookies, origins if isinstance(origins, list) else [], fingerprint


def _has_web_storage_for_origin(target_url, origins):
    target_origin = _normalized_origin(target_url)
    return any(
        isinstance(row, dict)
        and _normalized_origin(row.get("origin")) == target_origin
        and (row.get("localStorage") or row.get("sessionStorage"))
        for row in origins if isinstance(origins, list)
    )


def _seed_web_storage(ws_url, target_url, origins):
    target_origin = _normalized_origin(target_url)
    matching_local = []
    matching_session = []
    for row in origins if isinstance(origins, list) else []:
        if not isinstance(row, dict) or _normalized_origin(row.get("origin")) != target_origin:
            continue
        matching_local = [
            {"name": item.get("name"), "value": item.get("value")}
            for item in row.get("localStorage", []) if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("value"), str)
        ]
        matching_session = [
            {"name": item.get("name"), "value": item.get("value")}
            for item in row.get("sessionStorage", []) if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("value"), str)
        ]
        break
    if not target_origin or not (matching_local or matching_session):
        return 0

    source = """(()=>{
      if(location.origin!==%s) return;
      for(const item of %s) localStorage.setItem(item.name,item.value);
      for(const item of %s) sessionStorage.setItem(item.name,item.value);
    })()""" % (
        json.dumps(target_origin), json.dumps(matching_local), json.dumps(matching_session)
    )
    asyncio.run(_page_calls(ws_url, [
        ("Page.addScriptToEvaluateOnNewDocument", {"source": source}),
        ("Page.navigate", {"url": target_url}),
    ], timeout=15.0))
    return len(matching_local) + len(matching_session)


def commit_cookies(
    task, domains, token=None, generation=None, origin=None, local_storage_keys=None,
    session_storage_keys=None,
):
    """Merge one leased context's provider cookies into its seed vault.

    Isolated contexts are deliberately disposable, but a provider may refresh or mint its
    authentication cookies inside one. Persist only the caller-declared provider domains;
    never replace another provider's cookies and never erase a prior session from an empty
    or inconclusive context read.
    """
    normalized_domains = sorted({_normalized_cookie_domain(domain) for domain in domains})
    if not normalized_domains or any("." not in domain for domain in normalized_domains):
        return {"ok": False, "reason": "invalid_cookie_domain"}
    normalized_storage_origin = _normalized_origin(origin) if origin else ""
    storage_keys = sorted({
        key for key in (local_storage_keys or [])
        if isinstance(key, str) and key and len(key) <= 256
    })
    session_keys = sorted({
        key for key in (session_storage_keys or [])
        if isinstance(key, str) and key and len(key) <= 256
    })
    if (origin or storage_keys or session_keys) and (
        not normalized_storage_origin or not (storage_keys or session_keys)
    ):
        return {"ok": False, "reason": "invalid_local_storage_scope"}

    with _ledger_lock():
        held = _leases().get(task)
        if not held:
            return {"ok": False, "reason": "lease_not_found"}
        if not _fence_matches(held, token, generation):
            return {"ok": False, "reason": "lease_fence_mismatch"}
        held = dict(held)

    lock_path = _operation_lock_path(held["target_id"])
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as operation_lock:
        fcntl.flock(operation_lock.fileno(), fcntl.LOCK_EX)
        try:
            (result,) = asyncio.run(_calls([(
                "Storage.getCookies",
                {"browserContextId": held["context_id"]},
            )]))
            storage_items = []
            session_items = []
            if storage_keys or session_keys:
                expression = (
                    "JSON.stringify({local:Object.fromEntries(%s.map(k=>[k,localStorage.getItem(k)])),"
                    "session:Object.fromEntries(%s.map(k=>[k,sessionStorage.getItem(k)]))})"
                    % (json.dumps(storage_keys), json.dumps(session_keys))
                )
                (storage_result,) = asyncio.run(_page_calls(
                    held["ws"],
                    [("Runtime.evaluate", {"expression": expression, "returnByValue": True})],
                ))
                if storage_result.get("exceptionDetails"):
                    return {"ok": False, "reason": "local_storage_read_failed"}
                raw = storage_result.get("result", {}).get("value")
                values = json.loads(raw) if isinstance(raw, str) else {}
                local_values = values.get("local", {}) if isinstance(values, dict) else {}
                session_values = values.get("session", {}) if isinstance(values, dict) else {}
                storage_items = [
                    {"name": key, "value": local_values[key]}
                    for key in storage_keys
                    if isinstance(local_values.get(key), str) and local_values[key]
                ]
                session_items = [
                    {"name": key, "value": session_values[key]}
                    for key in session_keys
                    if isinstance(session_values.get(key), str) and session_values[key]
                ]
        finally:
            fcntl.flock(operation_lock.fileno(), fcntl.LOCK_UN)

    context_cookies = result.get("cookies", [])
    matching = [
        cookie for cookie in context_cookies
        if isinstance(cookie, dict) and _cookie_matches_domain(cookie, normalized_domains)
    ]
    if not matching:
        return {"ok": False, "reason": "no_matching_context_cookies"}
    if storage_keys and not storage_items:
        return {"ok": False, "reason": "no_matching_local_storage"}
    if session_keys and not session_items:
        return {"ok": False, "reason": "no_matching_session_storage"}

    vault_path = _vault_writeback_path()
    with _vault_lock():
        prior = {}
        if os.path.exists(vault_path):
            with open(vault_path, encoding="utf-8") as handle:
                prior = json.load(handle)
        prior_cookies = prior.get("cookies", []) if isinstance(prior, dict) else []
        preserved = [
            cookie for cookie in prior_cookies
            if isinstance(cookie, dict) and not _cookie_matches_domain(cookie, normalized_domains)
        ]
        payload = dict(prior) if isinstance(prior, dict) else {}
        payload["ts"] = int(time.time())
        payload["cookies"] = preserved + matching
        if storage_keys or session_keys:
            prior_origins = payload.get("origins", [])
            payload["origins"] = [
                row for row in prior_origins
                if isinstance(row, dict)
                and _normalized_origin(row.get("origin")) != normalized_storage_origin
            ] + [{
                "origin": normalized_storage_origin,
                "localStorage": storage_items,
                "sessionStorage": session_items,
            }]
        os.makedirs(os.path.dirname(vault_path), mode=0o700, exist_ok=True)
        temporary = f"{vault_path}.{os.getpid()}.tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.chmod(temporary, 0o600)
        os.replace(temporary, vault_path)
        os.chmod(vault_path, 0o600)

    return {
        "ok": True,
        "task": task,
        "domains": normalized_domains,
        "cookies_committed": len(matching),
        "cookies_preserved": len(preserved),
        "local_storage_committed": len(storage_items),
        "session_storage_committed": len(session_items),
    }


def release(task, token=None, generation=None):
    with _ledger_lock():
        leases = _leases()
        held = leases.get(task)
        if not held:
            return {"ok": True, "note": f"{task} held no context"}
        if not _fence_matches(held, token, generation):
            return {"ok": False, "reason": "lease_fence_mismatch"}
        held = dict(held)

    # CDP can take its full network deadline. Never make unrelated acquire/heartbeat/
    # park callers queue behind that I/O; the operation lock protects this target and
    # the token/generation/context compare below protects the ledger finalization.
    lock_path = _operation_lock_path(held["target_id"])
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as operation_lock:
        fcntl.flock(operation_lock.fileno(), fcntl.LOCK_EX)
        dispose_note = None
        disposed = False
        try:
            asyncio.run(_calls([(
                "Target.disposeBrowserContext",
                {"browserContextId": held["context_id"]},
            )]))
            disposed = True
        except Exception as e:
            disposed = _browser_context_exists(held.get("context_id")) is False
            if not disposed:
                dispose_note = f"context_left_for_gc: {type(e).__name__}"
        finally:
            fcntl.flock(operation_lock.fileno(), fcntl.LOCK_UN)

    with _ledger_lock():
        leases = _leases()
        current = leases.get(task)
        same_lease = bool(current) and (
            _fence_matches(current, held.get("token"), held.get("generation"))
            and current.get("context_id") == held.get("context_id")
            and current.get("target_id") == held.get("target_id")
        )
        if same_lease and disposed:
            leases.pop(task, None)
            _save(leases)
        elif same_lease and not disposed:
            # Keep a durable tombstone. Dropping this row would make the live context
            # unreachable to gc, so every later wake could leak another renderer.
            current["cleanup_pending"] = True
            current["cleanup_error_type"] = dispose_note.rsplit(": ", 1)[-1]
            current["ts"] = 0
            current["pid"] = None
            leases[task] = current
            _save(leases)
        result = {"ok": True, "released": task, "context_id": held["context_id"]}
        if dispose_note:
            result["note"] = dispose_note
            result["cleanup_pending"] = True
        return result


def park(task, token=None, generation=None):
    """Return ownership while keeping a healthy authenticated context for the next wake."""
    with _ledger_lock():
        leases = _leases()
        held = leases.get(task)
        if not held:
            return {"ok": True, "note": f"{task} held no context"}
        if not _fence_matches(held, token, generation):
            return {"ok": False, "reason": "lease_fence_mismatch"}
        held = dict(held)

    # A renderer probe is bounded but still network I/O. Probe without the fleet-wide
    # ledger lock, then finalize only if this exact lease identity still owns the row.
    if not target_responds(held.get("ws") or _page_ws(held.get("target_id") or "")):
        return {"ok": False, "reason": "target_unhealthy"}
    with _ledger_lock():
        leases = _leases()
        current = leases.get(task)
        if not current or not (
            _fence_matches(current, held.get("token"), held.get("generation"))
            and current.get("context_id") == held.get("context_id")
            and current.get("target_id") == held.get("target_id")
        ):
            return {"ok": False, "reason": "lease_fence_mismatch"}
        current["parked"] = True
        current["pid"] = None
        current["ts"] = int(time.time())
        leases[task] = current
        _save(leases)
        return {
            "ok": True,
            "parked": task,
            "context_id": current["context_id"],
            "target_id": current["target_id"],
        }


def gc(idle_min=45, max_reaps=None, priority_task=None):
    with _gc_singleflight() as acquired:
        if not acquired:
            return {
                "ok": True,
                "reaped": [],
                "still_held": [],
                "cleanup_pending": [],
                "skipped": "gc_already_running",
            }
        return _gc_owned(
            idle_min, max_reaps=max_reaps, priority_task=priority_task
        )


def _dispose_candidate(item):
    task, held = item
    try:
        asyncio.run(_calls([(
            "Target.disposeBrowserContext",
            {"browserContextId": held["context_id"]},
        )]))
        disposed = True
    except Exception:
        # Run the authoritative fallback in this same worker so a slow or wedged
        # inventory probe cannot serialize the other claimed contexts.
        disposed = _browser_context_exists(held.get("context_id")) is False
    return task, held, disposed


def _dispose_candidates(candidates, priority_task=None):
    if not candidates:
        return []
    results = []
    remaining = dict(candidates)
    if priority_task in remaining:
        results.append(_dispose_candidate((priority_task, remaining.pop(priority_task))))
    if not remaining:
        return results
    # max_reaps bounds candidates when the caller selects a batch; the hard ceiling
    # also keeps an unbounded maintenance GC from opening an unbounded number of sockets.
    workers = min(8, len(remaining))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results.extend(executor.map(_dispose_candidate, remaining.items()))
    return results


def _gc_owned(idle_min=45, max_reaps=None, priority_task=None):
    """A loop killed with -9 never releases. Reap whatever it left holding.

    gc used to read+dispose+save without the ledger lock -- the only such path in this
    file. Its dispose calls are slow (real CDP round trips), so any heartbeat()/acquire()
    write landing during that window got silently overwritten by gc's unconditional
    `_save(leases)` of its stale start-of-call snapshot: the victim's next heartbeat then
    returned lease_not_found. Fix: read candidates under the lock, dispose outside it (so
    other callers are not blocked on slow CDP calls), then re-open the lock per row and
    only pop it if the ledger still shows the *same* lease (same context/target id) and it
    is *still* stale -- a concurrent heartbeat or re-acquire between read and finalize
    survives untouched.

    Accepted edge: a 45-min-stale row re-acquired via acquire's reuse path during the
    dispose window survives with a dead context; the next acquire's target_responds
    check detects the corpse and rebuilds it (self-healing, reviewer-accepted).

    Pid-liveness fast path: idle_min alone means a holder killed with -9 can sit in the
    ledger for up to idle_min before this reaps it, even though acquire()/heartbeat()
    already stamp `pid` = the calling process's ppid on every successful call (D4). A row
    whose recorded pid is confirmed dead right now is reaped on this call regardless of
    idle_min -- missing/inconclusive pid (legacy rows, or _pid_alive's ambiguous-signal
    case) never triggers this path, so it only ever narrows the reap window, never widens
    who gets reaped.
    """
    now = time.time()
    with _ledger_lock():
        leases = _leases()
        candidates = {
            task: dict(held)
            for task, held in leases.items()
            if _lease_is_stale(held, now, idle_min)
        }
        if max_reaps is not None:
            ordered = list(candidates.items())
            if priority_task in candidates:
                ordered.insert(0, ordered.pop(next(
                    index for index, item in enumerate(ordered)
                    if item[0] == priority_task
                )))
            candidates = dict(ordered[:max(0, int(max_reaps))])

    reaped = []
    for task, held, disposed in _dispose_candidates(candidates, priority_task=priority_task):
        with _ledger_lock():
            leases = _leases()
            current = leases.get(task)
            same_lease = (
                current is not None
                and current.get("context_id") == held.get("context_id")
                and current.get("target_id") == held.get("target_id")
                and (
                    held.get("provisioning") is not True
                    or current.get("token") == held.get("token")
                )
            )
            still_stale = same_lease and _lease_is_stale(current, now, idle_min)
            if still_stale and disposed:
                leases.pop(task, None)
                _save(leases)
                reaped.append(task)

    with _ledger_lock():
        final_leases = _leases()
        still_held = list(final_leases)
        cleanup_pending = sorted(
            task for task, held in final_leases.items()
            if isinstance(held, dict) and held.get("cleanup_pending") is True
        )
    return {
        "ok": True,
        "reaped": reaped,
        "still_held": still_held,
        "cleanup_pending": cleanup_pending,
    }


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        token = sys.argv[sys.argv.index("--token") + 1] if "--token" in sys.argv else None
        generation = int(sys.argv[sys.argv.index("--generation") + 1]) if "--generation" in sys.argv else None
        if cmd == "acquire":
            out = acquire(
                arg or "unnamed",
                url=_acquire_url(sys.argv),
                no_seed="--no-seed" in sys.argv,
            )
        elif cmd == "heartbeat":
            out = heartbeat(arg or "unnamed", token=token, generation=generation)
        elif cmd == "release":
            out = release(arg or "unnamed", token=token, generation=generation)
        elif cmd == "park":
            out = park(arg or "unnamed", token=token, generation=generation)
        elif cmd == "commit-cookies":
            domains = [
                sys.argv[index + 1]
                for index, value in enumerate(sys.argv[:-1])
                if value == "--domain"
            ]
            out = commit_cookies(
                arg or "unnamed", domains, token=token, generation=generation,
                origin=(sys.argv[sys.argv.index("--origin") + 1] if "--origin" in sys.argv else None),
                local_storage_keys=[
                    sys.argv[index + 1]
                    for index, value in enumerate(sys.argv[:-1])
                    if value == "--local-storage-key"
                ],
                session_storage_keys=[
                    sys.argv[index + 1]
                    for index, value in enumerate(sys.argv[:-1])
                    if value == "--session-storage-key"
                ],
            )
        elif cmd == "gc":
            idle = int(sys.argv[sys.argv.index("--idle-min") + 1]) if "--idle-min" in sys.argv else 45
            out = gc(idle)
        elif cmd == "list":
            out = {"ok": True, "leases": _leases()}
        else:
            out = {"ok": False, "reason": f"unknown command {cmd}"}
    except Exception as e:
        out = {"ok": False, "reason": f"{type(e).__name__}: {e}"}
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0 if out.get("ok") else 1)
