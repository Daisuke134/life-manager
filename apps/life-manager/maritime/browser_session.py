"""Tenant-owned Chromium session for one Maritime VM cycle.

The model receives only the loopback CDP endpoint. The browser profile, lease
state, and process lifetime remain under the tenant's private data directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from typing import Callable
from urllib.request import ProxyHandler, build_opener


CDP_HOST = '127.0.0.1'
CDP_PORT = 9229
CDP_URL = f'http://{CDP_HOST}:{CDP_PORT}'
CHROMIUM_PATH = Path('/usr/local/bin/lm-cloud-chromium')
TENANT_PATTERN = re.compile(r'lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
CDP_WEBSOCKET_PATTERN = re.compile(
    r'ws://127\.0\.0\.1:9229/devtools/browser/[A-Za-z0-9-]{8,128}'
)
CDP_BROWSER_UUID_PATTERN = re.compile(r'ws://127\.0\.0\.1:9229/devtools/browser/([A-Za-z0-9-]{8,128})')
OWNER_RECEIPT_MAX_BYTES = 65_536


class BrowserSessionError(RuntimeError):
    """A bounded, non-sensitive browser startup or ownership failure."""


def _private_directory(path: Path, owner: int) -> bool:
    try:
        info = path.lstat()
        return (path.resolve(strict=True) == path and path.is_dir()
                and info.st_uid == owner and (info.st_mode & 0o777) == 0o700)
    except OSError:
        return False


def _ensure_private_directory(path: Path, owner: int) -> None:
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError:
        raise BrowserSessionError('browser_session_unavailable') from None
    if not _private_directory(path, owner):
        error = 'browser_profile_unavailable' if path.name == 'profile' else 'browser_session_path_unavailable'
        raise BrowserSessionError(error)


class MaritimeBrowserSession:
    """Start Chromium under the repository's exact-profile port owner."""

    def __init__(
        self,
        *,
        tenant_id: str,
        data_root: Path | str = Path('/data'),
        release_root: Path | str = Path('/app'),
        chromium_binary: Path | str = CHROMIUM_PATH,
        cloakbrowser_root: Path | str = Path('/opt/cloakbrowser'),
        popen_impl: Callable[..., subprocess.Popen] = subprocess.Popen,
        urlopen_impl: Callable[..., object] | None = None,
        sleep_impl: Callable[[float], None] = time.sleep,
        monotonic_impl: Callable[[], float] = time.monotonic,
        startup_timeout_seconds: float = 60,
    ) -> None:
        if not isinstance(tenant_id, str) or not TENANT_PATTERN.fullmatch(tenant_id):
            raise BrowserSessionError('browser_tenant_binding_invalid')
        self.tenant_id = tenant_id
        self.owner_id = 'maritime-' + tenant_id[3:]
        self.data_root = Path(data_root)
        self.release_root = Path(release_root)
        self.chromium_binary = Path(chromium_binary)
        self.cloakbrowser_root = Path(cloakbrowser_root)
        self.popen_impl = popen_impl
        # The CDP endpoint is local to this VM; never send it through the
        # managed outbound proxy, even when NO_PROXY is absent or incomplete.
        self.urlopen_impl = urlopen_impl or build_opener(ProxyHandler({})).open
        self.sleep_impl = sleep_impl
        self.monotonic_impl = monotonic_impl
        self.startup_timeout_seconds = startup_timeout_seconds
        self.process: subprocess.Popen | None = None
        self.cdp_url = CDP_URL
        self.home: Path | None = None
        self.browser_root: Path | None = None
        self.profile_dir: Path | None = None
        self.state_dir: Path | None = None

    def _prepare_paths(self) -> None:
        try:
            root = self.data_root.resolve(strict=True)
            home = root / self.tenant_id
            owner = os.geteuid()
            if (not self.data_root.is_absolute() or root != self.data_root
                    or not _private_directory(home, owner)):
                raise BrowserSessionError('browser_tenant_binding_invalid')
            browser_root = home / 'browser'
            _ensure_private_directory(browser_root, owner)
            profile = browser_root / 'profile'
            state = browser_root / 'owner-state'
            _ensure_private_directory(profile, owner)
            _ensure_private_directory(state, owner)
            release_root = self.release_root.resolve(strict=True)
            owner_script = release_root / 'runtime/host/browser_port_owner.py'
            binary = self.chromium_binary.resolve(strict=True)
            binary_link_allowed = False
            if self.chromium_binary.is_symlink():
                try:
                    binary.relative_to(self.cloakbrowser_root.resolve(strict=True))
                    binary_link_allowed = self.chromium_binary == CHROMIUM_PATH
                except (OSError, ValueError):
                    binary_link_allowed = False
            if (not self.release_root.is_absolute() or release_root != self.release_root
                    or owner_script.is_symlink() or not owner_script.is_file()
                    or (self.chromium_binary.is_symlink() and not binary_link_allowed)
                    or not binary.is_file()
                    or not os.access(binary, os.X_OK)):
                raise BrowserSessionError('browser_binary_unavailable')
        except BrowserSessionError:
            raise
        except OSError:
            raise BrowserSessionError('browser_session_path_unavailable') from None
        self.home = home
        self.browser_root = browser_root
        self.profile_dir = profile
        self.state_dir = state

    def _cdp_ready(self) -> bool:
        try:
            with self.urlopen_impl(CDP_URL + '/json/version', timeout=0.5) as response:
                payload = json.loads(response.read(65_536))
            websocket = payload.get('webSocketDebuggerUrl') if isinstance(payload, dict) else None
            if not isinstance(websocket, str):
                return False
            match = CDP_BROWSER_UUID_PATTERN.fullmatch(websocket)
            if match is None or CDP_WEBSOCKET_PATTERN.fullmatch(websocket) is None:
                return False
            receipt = self._read_owner_receipt()
            process = self.process
            return bool(receipt and process is not None
                        and receipt['supervisor_pid'] == process.pid
                        and receipt['browser_uuid'] == match.group(1))
        except (OSError, ValueError, TypeError, AttributeError):
            return False

    def _read_owner_receipt(self) -> dict[str, object] | None:
        state_dir = self.state_dir
        if state_dir is None or not _private_directory(state_dir, os.geteuid()):
            return None
        path = state_dir / f'{CDP_PORT}.json'
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
        try:
            fd = os.open(path, flags)
        except OSError:
            return None
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                    or info.st_size <= 0 or info.st_size > OWNER_RECEIPT_MAX_BYTES):
                return None
            raw = os.read(fd, OWNER_RECEIPT_MAX_BYTES + 1)
            if len(raw) > OWNER_RECEIPT_MAX_BYTES:
                return None
            receipt = json.loads(raw)
        except (OSError, ValueError, TypeError):
            return None
        finally:
            os.close(fd)

        required = {
            'owner', 'pid', 'supervisor_pid', 'browser_root_pid', 'listener_pid',
            'browser_uuid', 'port', 'profile_name',
        }
        if (not isinstance(receipt, dict)
                or set(receipt) not in (required, required | {'adopted'})):
            return None
        for key in ('pid', 'supervisor_pid', 'browser_root_pid', 'listener_pid', 'port'):
            value = receipt[key]
            if not isinstance(value, int) or isinstance(value, bool) or value <= 1:
                return None
        if ('adopted' in receipt and not isinstance(receipt['adopted'], bool)):
            return None
        if (receipt['owner'] != self.owner_id
                or receipt['pid'] != receipt['supervisor_pid']
                or receipt['port'] != CDP_PORT
                or receipt['profile_name'] != 'profile'
                or not isinstance(receipt['browser_uuid'], str)
                or re.fullmatch(r'[A-Za-z0-9-]{8,128}', receipt['browser_uuid']) is None):
            return None
        return receipt

    def __enter__(self) -> 'MaritimeBrowserSession':
        self._prepare_paths()

        assert self.home is not None
        assert self.profile_dir is not None
        assert self.state_dir is not None
        owner_script = self.release_root / 'runtime/host/browser_port_owner.py'
        command = [
            sys.executable, '-I', str(owner_script), 'run',
            '--port', str(CDP_PORT), '--profile', str(self.profile_dir),
            '--owner', self.owner_id,
            '--state-dir', str(self.state_dir), '--terminate-adopted-on-exit', '--',
            str(self.chromium_binary), '--headless=new', '--disable-dev-shm-usage',
            '--no-first-run', '--no-default-browser-check',
            '--disable-features=MacAppCodeSignClone,SpareRendererForSitePerProcess',
            '--remote-debugging-address=127.0.0.1', '--remote-allow-origins=*',
            f'--remote-debugging-port={CDP_PORT}',
            f'--user-data-dir={self.profile_dir}', 'about:blank',
        ]
        environment = {'PATH': '/usr/bin:/bin', 'HOME': str(self.home / 'home')}
        try:
            self.process = self.popen_impl(
                command,
                cwd=str(self.release_root),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            raise BrowserSessionError('browser_session_startup_failed') from None

        deadline = self.monotonic_impl() + self.startup_timeout_seconds
        while self.monotonic_impl() < deadline:
            if self.process.poll() is not None:
                self._stop()
                raise BrowserSessionError('browser_session_startup_failed')
            if self._cdp_ready():
                return self
            self.sleep_impl(min(0.1, max(0, deadline - self.monotonic_impl())))
        self._stop()
        raise BrowserSessionError('browser_session_startup_failed')

    def _stop(self) -> None:
        process = self.process
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
            returncode = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            raise BrowserSessionError('browser_session_shutdown_failed') from None
        except OSError:
            raise BrowserSessionError('browser_session_shutdown_failed') from None
        if returncode not in (0, 75):
            raise BrowserSessionError('browser_session_shutdown_failed')
        self.process = None

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> bool:
        self._stop()
        return False
