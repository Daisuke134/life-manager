import json
import hashlib
import errno
import os
import shutil
import signal
import plistlib
import sqlite3
import subprocess
import sys
import threading
import time
import pytest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

from runtime.host import resource_admission as admission
from runtime.loop import lm_loop_run as loop_runner
from runtime.loop.lm_loop import PRE_EFFECT_ADMISSION_BLOCKERS
from runtime.loop.lm_loop_run import (
    ADMISSION_CONTROL_RETRY_DELAY_SECONDS,
    ENTRYPOINT_STDERR_TAIL_MAX_BYTES,
    EFFECT_RESULT_HINT_ENTRYPOINTS,
    EFFECT_RESULT_HINT_LOOP_ENTRYPOINTS,
    PRE_EFFECT_HINT_ENTRYPOINTS,
    PRE_EFFECT_HINT_LOOP_IDS,
    _apply_verified_effect_result,
    _admission_class, _dispatch_reserved, _host_admission_deferred, _queue_priority,
    _enqueue_recovery_intent, _persist_effect_identity, _resource_class,
    _heartbeat_loop, _run_admitted, _run_entrypoint,
    _run_entrypoint_with_stderr_capture, _runtime_limit,
    _proven_pre_effect_failure, _sqlite_database_busy,
    _should_enqueue_recovery_intent, _terminal_outcome, _verified_effect_result,
    build_loop_command,
    main as lm_loop_run_main,
)
from runtime.loop.runtime_event import build_runtime_event


_PROTOCOL_PATCHER = None
_DISK_PATCHER = None


def setup_module():
    global _PROTOCOL_PATCHER, _DISK_PATCHER
    _PROTOCOL_PATCHER = patch(
        "runtime.loop.lm_loop_run.durable_protocol_version", return_value=2,
    )
    _PROTOCOL_PATCHER.start()
    _DISK_PATCHER = patch("runtime.loop.lm_loop_run._producer_gate", return_value=None)
    _DISK_PATCHER.start()


def teardown_module():
    _PROTOCOL_PATCHER.stop()
    _DISK_PATCHER.stop()


def test_scheduled_wakes_have_a_finite_one_hour_safety_limit():
    assert _runtime_limit({"cadence": {"start_interval_seconds": 300}}) == 3600
    assert _runtime_limit({"cadence": {"calendar_interval": {"Minute": 5}}}) == 3600
    assert _runtime_limit({"cadence": {"run_at_load": True}}) == 3600


def test_javascript_entrypoint_uses_pinned_runtime_node(tmp_path):
    executable = tmp_path / "worker.mjs"
    executable.write_text("#!/usr/bin/env node\n")
    executable.chmod(0o755)
    node = tmp_path / "node"
    node.write_text("#!/bin/sh\nexit 0\n")
    node.chmod(0o755)
    registry = {"schema_version": 2, "loops": {"example": {
        "label": "ai.anicca.example", "domain": "system",
        "entrypoint": "worker.mjs", "cadence": {"start_interval_seconds": 60},
        "effect_class": "none", "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic", "adapter": "exec", "command": [],
    }}}

    with patch.dict(os.environ, {"LIFE_MANAGER_RUNTIME_NODE": str(node)}):
        assert build_loop_command(registry, "example", tmp_path) == [
            str(node), str(executable),
        ]


def test_python_entrypoint_runs_under_the_runtime_interpreter_not_its_shebang(tmp_path):
    # launchd PATH resolves `#!/usr/bin/env python3` to the system 3.9, which
    # lacks StrEnum; hf-gig-apply-reconcile failed that way on 2026-09-26.
    executable = tmp_path / "worker.py"
    executable.write_text("#!/usr/bin/env python3\n")
    executable.chmod(0o755)
    registry = {"schema_version": 2, "loops": {"example": {
        "label": "ai.anicca.example", "domain": "system",
        "entrypoint": "worker.py", "cadence": {"start_interval_seconds": 60},
        "effect_class": "none", "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }}}
    assert build_loop_command(registry, "example", tmp_path) == [
        sys.executable, str(executable),
    ]


def test_crowdworks_paid_owner_declares_a_bounded_runtime():
    registry = json.loads(
        (Path(__file__).resolve().parents[3] / "config/loop-registry.json").read_text()
    )

    assert registry["loops"]["crowdworks-revenue-paid"]["runtime_timeout_seconds"] == 900


def test_scheduled_wake_can_declare_a_longer_finite_safety_limit():
    assert _runtime_limit({
        "cadence": {"start_interval_seconds": 600},
        "runtime_timeout_seconds": 10800,
    }) == 10800


def test_continuous_owner_has_no_scheduled_wake_deadline():
    assert _runtime_limit({"cadence": {"keep_alive": True}}) is None


def test_ebook_child_environment_loads_postiz_key_from_private_ssot(tmp_path):
    private = tmp_path / ".local/share/anicca"
    private.mkdir(parents=True)
    os.chmod(private, 0o700)
    credentials = private / "credentials.json"
    api_key = "test-postiz-key-not-real"
    credentials.write_text(json.dumps({
        "version": 1,
        "credentials": [{"service": "postiz", "api_key": api_key}],
    }))
    os.chmod(credentials, 0o600)
    base = {
        "LM_EBOOK_PUBLISHING_ENABLED": "true",
        "LM_POSTIZ_API_KEY": "untrusted-inherited-key",
        "LM_DATA_DIR": "untrusted-inherited-data-root",
        "LM_RUNTIME_TENANT_ID": "untrusted-inherited-tenant",
        "KEEP": "value",
    }

    child = loop_runner._child_environment_for_owner(
        "ebook-en-tiktok-daily", base, home=tmp_path,
    )

    assert child["LM_DATA_DIR"] == str(tmp_path / ".local/state/life-manager")
    assert child["LM_RUNTIME_TENANT_ID"] == "dais-local"
    assert child["LM_POSTIZ_API_KEY"] == api_key
    assert base["LM_DATA_DIR"] == "untrusted-inherited-data-root"
    assert base["LM_RUNTIME_TENANT_ID"] == "untrusted-inherited-tenant"
    assert child["KEEP"] == "value"
    assert base["LM_POSTIZ_API_KEY"] == "untrusted-inherited-key"
    assert loop_runner._child_environment_for_owner(
        "article-daily", base, home=tmp_path / "missing-home",
    ) == base


def test_ebook_child_environment_drops_inherited_key_when_ssot_is_unavailable(tmp_path):
    base = {
        "LM_EBOOK_PUBLISHING_ENABLED": "true",
        "LM_POSTIZ_API_KEY": "untrusted-inherited-key",
        "KEEP": "value",
    }

    child = loop_runner._child_environment_for_owner(
        "ebook-ja-tiktok-daily", base, home=tmp_path,
    )

    assert "LM_POSTIZ_API_KEY" not in child
    assert child["KEEP"] == "value"
    assert base["LM_POSTIZ_API_KEY"] == "untrusted-inherited-key"


def test_ebook_child_environment_does_not_inject_key_while_publish_flag_is_closed(tmp_path):
    private = tmp_path / ".local/share/anicca"
    private.mkdir(parents=True)
    os.chmod(private, 0o700)
    credentials = private / "credentials.json"
    credentials.write_text(json.dumps({
        "version": 1,
        "credentials": [{"service": "postiz", "api_key": "test-postiz-key-not-real"}],
    }))
    os.chmod(credentials, 0o600)
    base = {
        "LM_EBOOK_PUBLISHING_ENABLED": "false",
        "LM_POSTIZ_API_KEY": "untrusted-inherited-key",
        "LM_DATA_DIR": "untrusted-inherited-data-root",
        "LM_RUNTIME_TENANT_ID": "untrusted-inherited-tenant",
        "KEEP": "value",
    }

    child = loop_runner._child_environment_for_owner(
        "ebook-ja-instagram-daily", base, home=tmp_path,
    )

    assert child["LM_DATA_DIR"] == str(tmp_path / ".local/state/life-manager")
    assert child["LM_RUNTIME_TENANT_ID"] == "dais-local"
    assert "LM_POSTIZ_API_KEY" not in child
    assert child["KEEP"] == "value"


def test_ebook_child_environment_exposes_renderers_only_to_ebook_lanes():
    inherited_path = "/usr/bin:/bin:/usr/sbin:/sbin"
    base = {"PATH": inherited_path, "LM_EBOOK_PUBLISHING_ENABLED": "false"}

    for owner in (
        "ebook-en-tiktok-daily",
        "ebook-ja-tiktok-daily",
        "ebook-ja-instagram-daily",
    ):
        child = loop_runner._child_environment_for_owner(owner, base)
        assert child["PATH"] == f"/opt/homebrew/bin:{inherited_path}"

    sibling = loop_runner._child_environment_for_owner("article-daily", base)
    assert sibling["PATH"] == inherited_path
    assert base["PATH"] == inherited_path


def test_english_ebook_child_environment_sets_scoped_heygen_cli_path(tmp_path):
    inherited_path = os.pathsep.join(("/usr/bin", "/bin", "/usr/sbin", "/sbin"))
    base = {"PATH": inherited_path, "LM_EBOOK_PUBLISHING_ENABLED": "false"}

    english = loop_runner._child_environment_for_owner(
        "ebook-en-tiktok-daily", base, home=tmp_path,
    )

    assert english["LIFE_MANAGER_HEYGEN"] == str(tmp_path / ".local/bin/heygen")
    assert english["PATH"] == f"/opt/homebrew/bin{os.pathsep}{inherited_path}"

    english_override = loop_runner._child_environment_for_owner(
        "ebook-en-tiktok-daily",
        {**base, "LIFE_MANAGER_HEYGEN": "/opt/custom/heygen"},
        home=tmp_path,
    )
    assert english_override["LIFE_MANAGER_HEYGEN"] == "/opt/custom/heygen"

    japanese = loop_runner._child_environment_for_owner(
        "ebook-ja-tiktok-daily", base, home=tmp_path,
    )
    assert "LIFE_MANAGER_HEYGEN" not in japanese
    assert japanese["PATH"] == f"/opt/homebrew/bin{os.pathsep}{inherited_path}"
    assert loop_runner._child_environment_for_owner(
        "article-daily", base, home=tmp_path,
    ) == base


def test_english_ebook_child_environment_disables_heygen_telemetry_only_for_english_owner(tmp_path):
    base = {"PATH": "/usr/bin:/bin", "LM_EBOOK_PUBLISHING_ENABLED": "false"}

    english = loop_runner._child_environment_for_owner(
        "ebook-en-tiktok-daily", base, home=tmp_path,
    )
    assert english["HEYGEN_NO_ANALYTICS"] == "1"

    japanese = loop_runner._child_environment_for_owner(
        "ebook-ja-tiktok-daily", base, home=tmp_path,
    )
    assert "HEYGEN_NO_ANALYTICS" not in japanese
    assert loop_runner._child_environment_for_owner(
        "article-daily", base, home=tmp_path,
    ) == base


def test_ebook_owner_passes_ssot_postiz_key_to_child_entrypoint(tmp_path):
    private = tmp_path / ".local/share/anicca"
    private.mkdir(parents=True)
    os.chmod(private, 0o700)
    credentials = private / "credentials.json"
    api_key = "test-postiz-key-not-real"
    credentials.write_text(json.dumps({
        "version": 1,
        "credentials": [{"service": "postiz", "api_key": api_key}],
    }))
    os.chmod(credentials, 0o600)
    base = {
        "LM_EBOOK_PUBLISHING_ENABLED": "true",
        "LM_POSTIZ_API_KEY": "untrusted-inherited-key",
    }
    captured = {}

    def run_child(command, *, env=None, **_kwargs):
        captured.update(env or {})
        return 0

    with (patch("runtime.loop.lm_loop_run.Path.home", return_value=tmp_path),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        result = _run_admitted(
            ["/bin/true"], {"cadence": {"keep_alive": True}, "effect_class": "publish"},
            "ebook-en-tiktok-daily", base, tmp_path / "receipt",
        )

    assert result == 0
    assert captured["LM_POSTIZ_API_KEY"] == api_key
    assert base["LM_POSTIZ_API_KEY"] == "untrusted-inherited-key"


def test_resource_class_is_explicit_or_provider_default():
    assert _resource_class({"provider_route": "shared-agent-runner"}) == "agent"
    assert _resource_class({"provider_route": "deterministic"}) == "deterministic"
    assert _resource_class({"provider_route": "deterministic", "resource_class": "agent"}) == "agent"


def test_revenue_admission_requires_an_explicit_registry_contract():
    assert _admission_class({"domain": "earn"}) == "borrow"
    assert _admission_class({
        "domain": "earn", "admission_class": "revenue",
    }) == "revenue"


def test_explicit_registry_priority_is_forwarded_to_durable_admission(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "priority": "critical_paid",
    }
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")) as enqueue,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "paid", {}, receipt) == 75

    assert _queue_priority(entry) == "critical_paid"
    enqueue.assert_called_once_with(
        "deterministic", "paid", admission_class="revenue",
        priority="critical_paid",
    )
    run.assert_not_called()


def test_capacity_busy_blocker_is_only_emitted_before_any_claim_or_child_start(tmp_path):
    """Regression: PRE_EFFECT_ADMISSION_BLOCKERS proves no effect could have
    started, which is only true while the enqueue/claim step failed before a
    child was ever spawned. Pin that the enqueue-side capacity_busy reason
    never reaches claim_durable_resource, transfer_durable_resource, or
    _run_entrypoint.
    """
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "priority": "critical_paid",
    }
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          # A None ticket is what actually short-circuits _run_admitted before
          # any claim attempt; a truthy ticket falls through to claim_durable_resource
          # regardless of the paired reason string.
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(None, "capacity_busy")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource") as claim,
          patch("runtime.loop.lm_loop_run.transfer_durable_resource") as transfer,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        return_code = _run_admitted(["/bin/true"], entry, "paid", {}, receipt)

    assert return_code == 75
    assert json.loads(receipt.read_text())["reason"] == "resource_capacity_busy"
    claim.assert_not_called()
    transfer.assert_not_called()
    run.assert_not_called()

    host_deferred = _host_admission_deferred(receipt, 0)
    _, _, blocker = _terminal_outcome(return_code, host_deferred=host_deferred)
    assert blocker in PRE_EFFECT_ADMISSION_BLOCKERS


def test_fifo_wait_blocker_is_only_emitted_before_any_child_start(tmp_path):
    """Regression sibling to the capacity_busy case: the claim-side fifo_wait
    reason is only reachable when claim_durable_resource itself failed to
    hand back a claim, so transfer_durable_resource/_run_entrypoint (which
    would start the child) must never run for this outcome.
    """
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "priority": "critical_paid",
    }
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "fifo_wait")),
          patch("runtime.loop.lm_loop_run.reserve_available_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource") as transfer,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        return_code = _run_admitted(["/bin/true"], entry, "paid", {}, receipt)

    assert return_code == 75
    assert json.loads(receipt.read_text())["reason"] == "resource_fifo_wait"
    transfer.assert_not_called()
    run.assert_not_called()

    host_deferred = _host_admission_deferred(receipt, 0)
    _, _, blocker = _terminal_outcome(return_code, host_deferred=host_deferred)
    assert blocker in PRE_EFFECT_ADMISSION_BLOCKERS


def test_mobile_publish_entrypoint_uses_occurrence_scoped_admission(tmp_path):
    entry = {
        "cadence": {"calendar_interval": [{"Hour": 8, "Minute": 0}]},
        "provider_route": "deterministic",
        "resource_class": "agent",
        "admission_class": "revenue",
        "priority": "revenue",
        "effect_class": "publish",
        "entrypoint": "apps/life-manager/scripts/mobile-app",
    }
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "effect_unknown")) as claim,
          patch("runtime.loop.lm_loop_run.reserve_available_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "life-manager-honne-ja", {},
            tmp_path / "mobile-receipt", occurrence_id="life-manager-honne-ja:new",
        ) == 75

    enqueue.assert_called_once_with(
        "agent", "life-manager-honne-ja", admission_class="revenue",
        priority="revenue", occurrence_id="life-manager-honne-ja:new",
        effect_scope="occurrence",
    )
    claim.assert_called_once_with(
        "agent", "life-manager-honne-ja", admission_class="revenue",
        effect_scope="occurrence",
    )
    run.assert_not_called()



def test_mobile_wrapper_continues_new_occurrence_after_ownerwide_reconcile_miss(tmp_path):
    repo_root = Path(__file__).parents[3]
    owner = "life-manager-honne-ja"

    def invoke(name, occurrence):
        root = tmp_path / name
        root.mkdir()
        marker = root / "runner-called"
        calls = root / "calls.txt"
        fake_python = root / "python"
        fake_node = root / "node"
        env_file = root / "marketing.env"
        fake_python.write_text(
            "#!/bin/sh\n"
            "printf \"%s\\n\" \"$1\" >> \"$LM_TEST_CALLS\"\n"
            "case \"$1\" in\n"
            "  *mobile-postiz-provider-reconcile.py) exit 1 ;;\n"
            "  *run-with-timeout.py) touch \"$LM_TEST_RUNNER_CALLED\"; exit 0 ;;\n"
            "  *) exit 0 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_node.write_text(
            "#!/bin/sh\nprintf \"%s\\t%s\\t%s\\t%s\\t%s\\n\" fake-runner run anicca-ios https://anicca.app mobile-products/anicca-ios\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o700)
        fake_node.chmod(0o700)
        env_file.write_text(
            "LM_POSTIZ_API_KEY=test-token\nLM_DATA_DIR="+str(root/"data")+"\nLM_RUNTIME_TENANT_ID=dais-local\n",
            encoding="utf-8",
        )
        env_file.chmod(0o600)
        env = {key:value for key,value in os.environ.items()
               if key not in {"LIFE_MANAGER_RELEASE_SHA", "LIFE_MANAGER_OCCURRENCE_ID"}}
        env.update({
            "LIFE_MANAGER_MARKETING_ENV_FILE": str(env_file),
            "LIFE_MANAGER_NODE": str(fake_node),
            "LIFE_MANAGER_PYTHON": str(fake_python),
            "LIFE_MANAGER_LOOP_ID": owner,
            "LIFE_MANAGER_OCCURRENCE_ID": occurrence or "",
            "LM_TEST_CALLS": str(calls),
            "LM_TEST_RUNNER_CALLED": str(marker),
            "TMPDIR": str(root),
        })
        result = subprocess.run(
            [str(repo_root/"apps/life-manager/scripts/mobile-app"), owner],
            cwd=repo_root, env=env, capture_output=True, text=True,
        )
        return result, marker, calls

    current = owner + ":new-slot"
    allowed, allowed_marker, allowed_calls = invoke("allowed", current)
    assert allowed.returncode == 0, allowed.stderr
    assert allowed_marker.exists()
    assert len(allowed_calls.read_text(encoding="utf-8").splitlines()) == 2

    missing, missing_marker, missing_calls = invoke("missing", None)
    assert missing.returncode == 75, missing.stderr
    assert not missing_marker.exists()
    assert len(missing_calls.read_text(encoding="utf-8").splitlines()) == 1


def test_explicit_marketplace_occurrence_scope_is_forwarded_to_admission(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "agent",
        "admission_class": "revenue",
        "priority": "critical_paid",
        "effect_class": "money",
        "entrypoint": "skills/earn/crowdworks/scripts/paid-owner",
        "admission_effect_scope": "occurrence",
    }
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "effect_unknown")) as claim,
          patch("runtime.loop.lm_loop_run.reserve_available_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "crowdworks-revenue-paid", {},
            tmp_path / "paid-receipt", occurrence_id="crowdworks-revenue-paid:new",
        ) == 75

    enqueue.assert_called_once_with(
        "agent", "crowdworks-revenue-paid", admission_class="revenue",
        priority="critical_paid", occurrence_id="crowdworks-revenue-paid:new",
        effect_scope="occurrence",
    )
    claim.assert_called_once_with(
        "agent", "crowdworks-revenue-paid", admission_class="revenue",
        effect_scope="occurrence",
    )
    run.assert_not_called()


def test_non_mobile_publish_entrypoint_keeps_owner_scoped_admission(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "effect_class": "publish",
        "entrypoint": "skills/earn/article/scripts/article-daily.sh",
    }
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(None, "effect_unknown")) as enqueue,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "article-daily", {},
            tmp_path / "article-receipt", occurrence_id="article-daily:new",
        ) == 75

    enqueue.assert_called_once_with(
        "deterministic", "article-daily", admission_class="revenue",
        occurrence_id="article-daily:new",
    )
    run.assert_not_called()


def test_transient_admission_lock_contention_is_retried_before_deferring(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "priority": "critical_paid",
    }
    claim = tmp_path / "claim"
    claim.write_text("owned")
    enqueue_results = [
        (None, "control_busy"),
        (None, "control_busy"),
        (tmp_path / "ticket", "ready"),
    ]

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                side_effect=enqueue_results) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]),
          patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0),
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep):
        assert _run_admitted(
            ["/bin/true"], entry, "crowdworks-revenue-paid", {},
            tmp_path / "receipt",
        ) == 0

    assert enqueue.call_count == 3
    assert sleep.call_count == 2


def test_transient_sqlite_lock_before_claim_recovers_in_same_wake(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "effect_class": "none",
    }
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({
        "occurrence_id": "browser-probe:wake-recover",
    }))
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource", side_effect=[
              sqlite3.OperationalError("database is locked"),
              sqlite3.OperationalError("database is locked"),
              (tmp_path / "ticket", "ready"),
          ]) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]),
          patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0) as run,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep):
        assert _run_admitted(
            ["/bin/true"], entry, "browser-probe", {}, tmp_path / "receipt",
            occurrence_id="browser-probe:wake-recover",
        ) == 0

    assert enqueue.call_count == 3
    assert sleep.call_count == 2
    run.assert_called_once()


def test_sqlite_busy_classification_prefers_primary_error_code():
    for primary in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        error = sqlite3.OperationalError("not a lock message")
        error.sqlite_errorcode = primary | (7 << 8)
        assert _sqlite_database_busy(error)

    non_busy = sqlite3.OperationalError("database is locked")
    non_busy.sqlite_errorcode = sqlite3.SQLITE_IOERR
    assert not _sqlite_database_busy(non_busy)


def test_persistent_sqlite_lock_before_claim_records_typed_deferred_admission(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "effect_class": "none",
    }
    receipt = tmp_path / "host-admission.json"
    started_ns = time.time_ns()
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                side_effect=sqlite3.OperationalError("database is locked")) as enqueue,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "browser-probe", {}, receipt,
                             occurrence_id="browser-probe:wake-1") == 75

    assert json.loads(receipt.read_text()) == {
        "status": "deferred", "effect": 0,
        "reason": "resource_database_busy",
    }
    assert _terminal_outcome(
        75, host_deferred=_host_admission_deferred(receipt, started_ns),
    ) == (False, True, "host_admission_deferred:resource_database_busy")
    assert enqueue.call_count == 8
    assert sleep.call_count == 7
    run.assert_not_called()


def test_persistent_sqlite_lock_during_claim_records_typed_deferred_admission(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "effect_class": "none",
    }
    receipt = tmp_path / "host-admission.json"
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                side_effect=sqlite3.OperationalError("database is locked")) as claim,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "browser-probe", {}, receipt,
                             occurrence_id="browser-probe:wake-2") == 75

    assert json.loads(receipt.read_text()) == {
        "status": "deferred", "effect": 0,
        "reason": "resource_database_busy",
    }
    assert claim.call_count == 8
    assert sleep.call_count == 7
    run.assert_not_called()


def test_non_busy_sqlite_failure_is_not_retried_or_misclassified(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "effect_class": "none",
    }
    receipt = tmp_path / "host-admission.json"
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                side_effect=sqlite3.OperationalError("disk I/O error")) as enqueue,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "browser-probe", {}, receipt,
            occurrence_id="browser-probe:wake-io-error",
        ) == 75

    assert json.loads(receipt.read_text())["reason"] == "resource_admission_unavailable"
    enqueue.assert_called_once()
    sleep.assert_not_called()
    run.assert_not_called()


def test_nonlock_claim_io_failure_is_not_retried_or_started(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "effect_class": "none",
    }
    receipt = tmp_path / "host-admission.json"
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                side_effect=OSError("claim cleanup I/O failed")) as claim,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "browser-probe", {}, receipt,
            occurrence_id="browser-probe:wake-cleanup-io",
        ) == 75

    assert json.loads(receipt.read_text())["reason"] == "resource_admission_unavailable"
    claim.assert_called_once()
    sleep.assert_not_called()
    run.assert_not_called()


def test_transient_sqlite_lock_during_release_recovers_before_stale_fencing(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "deterministic",
        "effect_class": "publish",
    }
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({
        "occurrence_id": "affiliate-loop:wake-release-retry",
    }))

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        return 0

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource", side_effect=[
              sqlite3.OperationalError("database is locked"),
              [],
          ]) as release,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep,
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(
            ["/bin/true"], entry, "affiliate-loop", {}, tmp_path / "receipt",
            occurrence_id="affiliate-loop:wake-release-retry",
        ) == 0

    assert release.call_count == 2
    sleep.assert_called_once_with(ADMISSION_CONTROL_RETRY_DELAY_SECONDS)


def test_sqlite_lock_during_best_effort_reservation_keeps_terminal_path(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "effect_class": "none",
    }
    receipt = tmp_path / "host-admission.json"
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "capacity_busy")),
          patch("runtime.loop.lm_loop_run.reserve_available_resource",
                side_effect=sqlite3.OperationalError("database is locked")),
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "browser-probe", {}, receipt,
                             occurrence_id="browser-probe:wake-3") == 75

    assert json.loads(receipt.read_text()) == {
        "status": "deferred", "effect": 0,
        "reason": "resource_capacity_busy",
    }
    run.assert_not_called()


def test_wake_occurrence_identity_is_forwarded_to_durable_admission(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "priority": "revenue",
    }
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")) as enqueue,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "connector", {}, receipt,
            occurrence_id="connector:1800000000-1",
        ) == 75

    enqueue.assert_called_once_with(
        "deterministic", "connector", admission_class="revenue",
        priority="revenue", occurrence_id="connector:1800000000-1",
    )
    run.assert_not_called()


def test_old_reservation_only_marker_does_not_advertise_queued_coalescing(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 1800},
        "provider_route": "deterministic", "resource_class": "browser",
        "admission_class": "revenue", "coalesce_reserved_wakes": True,
    }
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "capacity_busy")) as claim,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "life-manager-connector-native", {},
            tmp_path / "receipt", occurrence_id="connector:new",
        ) == 75
    enqueue.assert_called_once_with(
        "browser", "life-manager-connector-native", admission_class="revenue",
        occurrence_id="connector:new",
    )
    claim.assert_called_once_with(
        "browser", "life-manager-connector-native", admission_class="revenue",
    )
    run.assert_not_called()


def test_connector_registry_opt_in_coalesces_queued_scan(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 1800},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "admission_class": "revenue",
        "coalesce_reserved_wakes": True,
        "coalesce_queued_wakes": True,
    }
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")) as enqueue,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "life-manager-connector-native", {},
            tmp_path / "receipt", occurrence_id="connector:new",
        ) == 75
    enqueue.assert_called_once_with(
        "browser", "life-manager-connector-native", admission_class="revenue",
        occurrence_id="connector:new", coalesce_reserved=True,
    )
    run.assert_not_called()


def test_x_repost_uses_revenue_queue_priority_and_coalesces_when_agent_capacity_is_busy(tmp_path):
    registry = json.loads(
        (Path(__file__).parents[3] / "config/loop-registry.json").read_text()
    )["loops"]
    occurrence_id = "x-repost:scheduled-wake-2"
    receipt = tmp_path / "receipt.json"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "queued_coalesced")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "capacity_busy")) as claim,
          patch("runtime.loop.lm_loop_run.reserve_available_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], registry["x-repost"], "x-repost", {}, receipt,
            occurrence_id=occurrence_id,
        ) == 75

    enqueue.assert_called_once_with(
        "agent", "x-repost", admission_class="borrow", priority="revenue",
        occurrence_id=occurrence_id, coalesce_reserved=True,
    )
    claim.assert_called_once_with(
        "agent", "x-repost", admission_class="borrow",
        coalesced_occurrence_id=occurrence_id,
    )
    run.assert_not_called()
    assert json.loads(receipt.read_text())["reason"] == "resource_capacity_busy"


def test_running_child_receives_periodic_claim_heartbeat(tmp_path, monkeypatch):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "priority": "revenue",
    }
    receipt = tmp_path / "receipt"
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({"occurrence_id": "heartbeat-owner:run-1"}))
    heartbeat_seen = threading.Event()
    calls = []

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        assert heartbeat_seen.wait(timeout=1)
        return 0

    def heartbeat(_claim):
        calls.append("heartbeat")
        heartbeat_seen.set()
        return True

    monkeypatch.setattr("runtime.loop.lm_loop_run.HEARTBEAT_INTERVAL_SECONDS", 0.01)
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.heartbeat_durable_resource",
                side_effect=heartbeat),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                side_effect=lambda *_args, **_kwargs: calls.append("release") or []),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(
            ["/bin/true"], entry, "heartbeat-owner", {}, receipt,
            occurrence_id="heartbeat-owner:run-1",
        ) == 0

    assert calls[0] == "heartbeat"
    assert calls[-1] == "release"


def test_heartbeat_failure_sets_cancellation_event(tmp_path, monkeypatch):
    stopped = threading.Event()
    failed = threading.Event()

    def heartbeat(_claim):
        raise OSError("ENOSPC")

    monkeypatch.setattr("runtime.loop.lm_loop_run.HEARTBEAT_INTERVAL_SECONDS", 0.01)
    with patch("runtime.loop.lm_loop_run.heartbeat_durable_resource",
               side_effect=heartbeat):
        _heartbeat_loop(tmp_path / "claim", stopped, failed)

    assert failed.is_set()


def test_admitted_child_is_cancelled_when_heartbeat_fails(tmp_path, monkeypatch):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
    }
    receipt = tmp_path / "receipt"
    claim = tmp_path / "claim"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        deadline = time.monotonic() + 1
        while not kwargs["cancelled"]() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert kwargs["cancelled"]()
        return 0

    monkeypatch.setattr("runtime.loop.lm_loop_run.HEARTBEAT_INTERVAL_SECONDS", 0.01)
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.heartbeat_durable_resource",
                side_effect=OSError("ENOSPC")),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]),
          patch("runtime.loop.lm_loop_run._run_entrypoint",
                side_effect=run_child)):
        assert _run_admitted(
            ["/bin/true"], entry, "heartbeat-owner", {}, receipt,
        ) == 75

    assert json.loads(receipt.read_text())["reason"] == "resource_heartbeat_unavailable"


def test_release_waits_for_inflight_heartbeat_before_closing_claim(tmp_path, monkeypatch):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "priority": "revenue",
    }
    receipt = tmp_path / "receipt"
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({"occurrence_id": "heartbeat-owner:run-2"}))
    heartbeat_started = threading.Event()
    heartbeat_finished = threading.Event()

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        assert heartbeat_started.wait(timeout=1)
        return 0

    def heartbeat(_claim):
        heartbeat_started.set()
        time.sleep(1.2)
        heartbeat_finished.set()
        return False

    def release(*_args, **_kwargs):
        assert heartbeat_finished.is_set()
        return []

    monkeypatch.setattr("runtime.loop.lm_loop_run.HEARTBEAT_INTERVAL_SECONDS", 0.01)
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.heartbeat_durable_resource",
                side_effect=heartbeat),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                side_effect=release),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(
            ["/bin/true"], entry, "heartbeat-owner", {}, receipt,
            occurrence_id="heartbeat-owner:run-2",
        ) == 0


def test_memory_admission_exit_is_deferred_not_failed():
    assert _terminal_outcome(75, host_deferred="resource_capacity_busy") == (
        False, True, "host_admission_deferred:resource_capacity_busy")
    assert _terminal_outcome(124, host_deferred="memory_headroom_low") == (
        False, True, "host_admission_deferred:memory_headroom_low")
    assert _terminal_outcome(75, host_deferred="disk_headroom_low") == (
        False, True, "host_admission_deferred:disk_headroom_low")
    assert _terminal_outcome(75, host_deferred="disk_headroom_unavailable") == (
        False, True, "host_admission_deferred:disk_headroom_unavailable")
    assert _terminal_outcome(75) == (False, False, "entrypoint_exit_75")
    assert _terminal_outcome(1) == (False, False, "entrypoint_exit_1")


def test_memory_deferral_requires_a_fresh_matching_receipt(tmp_path):
    receipt = tmp_path / "memory.json"
    started = time.time_ns()
    receipt.write_text(json.dumps({
        "status": "deferred", "effect": 0, "reason": "capacity_busy",
    }))
    assert _host_admission_deferred(receipt, started) == "capacity_busy"
    receipt.write_text(json.dumps({
        "status": "deferred", "effect": 0, "reason": "x" * 128,
    }))
    assert _host_admission_deferred(receipt, started) == "unknown"
    receipt.write_text(json.dumps({"status": "pass", "effect": 0}))
    assert not _host_admission_deferred(receipt, started)


def test_entrypoint_timeout_terminates_its_process_group():
    started = time.monotonic()
    result = _run_entrypoint(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        timeout_seconds=0.05,
        termination_grace_seconds=0.05,
    )

    assert result == 124
    assert time.monotonic() - started < 2


def test_entrypoint_cancellation_terminates_running_process_group():
    cancelled = threading.Event()
    trigger = threading.Thread(
        target=lambda: (time.sleep(0.05), cancelled.set()), daemon=True,
    )
    trigger.start()
    started = time.monotonic()

    result = _run_entrypoint(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        timeout_seconds=0.4,
        termination_grace_seconds=0.05,
        cancelled=cancelled.is_set,
    )

    trigger.join(timeout=1)
    assert result == 75
    assert time.monotonic() - started < 2


def test_entrypoint_completes_handoff_before_effect_gate(tmp_path):
    handoff = tmp_path / "handoff"
    child = (
        "import pathlib,sys; "
        f"sys.exit(0 if pathlib.Path({str(handoff)!r}).is_file() else 1)"
    )

    result = _run_entrypoint(
        [sys.executable, "-c", child], timeout_seconds=5,
        on_started=lambda pid: handoff.write_text(str(pid)),
    )

    assert result == 0


def test_entrypoint_stderr_capture_is_captured_and_still_passes_through(tmp_path, capfd):
    child = (
        "import os, stat, sys; "
        "sys.stderr.buffer.write(b'boom: precondition missing\\n'); "
        "sys.exit(1 if stat.S_ISREG(os.fstat(2).st_mode) else 86)"
    )
    expected = b"boom: precondition missing\n"
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    result, tail = _run_entrypoint_with_stderr_capture(
        [sys.executable, "-c", child], scratch, timeout_seconds=5,
    )

    assert result == 1
    assert tail == expected[-ENTRYPOINT_STDERR_TAIL_MAX_BYTES:]
    # Passthrough is preserved: the child's stderr still reaches this
    # process's real stderr, exactly like before capture existed.
    captured = capfd.readouterr()
    assert captured.err.encode() == expected
    # The capture file is a private, cleaned-up implementation detail, not a
    # durable artifact -- nothing is left behind in the run's scratch dir.
    assert list(scratch.iterdir()) == []


def test_entrypoint_stderr_capture_replays_bounded_slices_for_large_output(
        tmp_path, capfd, monkeypatch):
    chunk_size = 32 * 1024
    head = b"H" * chunk_size
    middle = b"M" * (200 * 1024)
    final_error = b"ERROR: final failure\n"
    full_output = head + middle + final_error
    marker = b"\n...[stderr truncated]...\n"
    expected_replay = head + marker + full_output[-chunk_size:]
    child = (
        "import sys; "
        f"sys.stderr.buffer.write(b'H' * {chunk_size} + b'M' * {len(middle)} "
        f"+ {final_error!r}); "
        "sys.exit(9)"
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    capture_path = scratch / "entrypoint-stderr.log"
    real_path_open = Path.open
    read_sizes = []
    seek_positions = []

    class BoundedCaptureReader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.handle.close()

        def seek(self, offset, whence=0):
            seek_positions.append((offset, whence))
            return self.handle.seek(offset, whence)

        def tell(self):
            return self.handle.tell()

        def read(self, size=-1):
            read_sizes.append(size)
            assert 0 <= size <= chunk_size
            return self.handle.read(size)

    def observe_open(path, *args, **kwargs):
        handle = real_path_open(path, *args, **kwargs)
        if path == capture_path:
            return BoundedCaptureReader(handle)
        return handle

    real_read_bytes = Path.read_bytes

    def reject_whole_capture_read(path):
        if path == capture_path:
            raise AssertionError("capture must use bounded seek/read")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "open", observe_open)
    monkeypatch.setattr(Path, "read_bytes", reject_whole_capture_read)

    result, tail = _run_entrypoint_with_stderr_capture(
        [sys.executable, "-c", child], scratch, timeout_seconds=5,
    )

    assert result == 9
    assert tail == full_output[-ENTRYPOINT_STDERR_TAIL_MAX_BYTES:]
    assert b"ERROR: final failure\n" in tail
    assert capfd.readouterr().err.encode() == expected_replay
    assert read_sizes == [chunk_size, chunk_size]
    assert (0, os.SEEK_END) in seek_positions
    assert (len(full_output) - chunk_size, os.SEEK_SET) in seek_positions
    assert list(scratch.iterdir()) == []


def test_entrypoint_without_stderr_capture_is_unaffected(capfd):
    child = "import sys; sys.stderr.write('untouched\\n'); sys.exit(1)"

    result = _run_entrypoint([sys.executable, "-c", child], timeout_seconds=5)

    assert result == 1
    captured = capfd.readouterr()
    assert "untouched" in captured.err


def test_detached_grandchild_stderr_write_after_run_returns_does_not_epipe(tmp_path):
    # The entrypoint forks a grandchild, detaches it (start_new_session),
    # and exits immediately -- the grandchild keeps the (now stale, unlinked)
    # capture file's fd open and writes to it well after
    # _run_entrypoint_with_stderr_capture has already returned, read the
    # file back, and deleted it. A pipe would make that write raise
    # EPIPE/SIGPIPE once this process closed its read end; a regular file
    # has no such failure mode.
    marker = tmp_path / "grandchild-ok"
    grandchild = (
        "import sys, time; "
        "time.sleep(0.3); "
        "sys.stderr.write('grandchild output'); "
        "sys.stderr.flush(); "
        f"open({str(marker)!r}, 'w').write('ok')"
    )
    child = (
        "import subprocess, sys; "
        f"subprocess.Popen([{sys.executable!r}, '-c', {grandchild!r}], "
        "start_new_session=True); "
        "sys.exit(1)"
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    result, _tail = _run_entrypoint_with_stderr_capture(
        [sys.executable, "-c", child], scratch, timeout_seconds=5,
    )

    assert result == 1
    assert not (scratch / "entrypoint-stderr.log").exists()
    deadline = time.monotonic() + 5
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert marker.read_text() == "ok"


def test_acquired_slot_keeps_the_full_entrypoint_runtime_budget(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner", "runtime_timeout_seconds": 123}
    claim = tmp_path / "claim"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        return 0

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=["next"]) as release,
          patch("runtime.loop.lm_loop_run.transfer_durable_resource") as transfer,
          patch("runtime.loop.lm_loop_run._dispatch_reserved") as dispatch,
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child) as run):
        assert _run_admitted(["/bin/true"], entry, "example", {}, tmp_path / "receipt") == 0
    assert run.call_args.kwargs["timeout_seconds"] == 123
    transfer.assert_called_once_with(claim, 4242)
    release.assert_called_once_with(claim, requeue=False, reserve=True)
    dispatch.assert_called_once_with(["next"])


def test_control_plane_safety_loops_bypass_data_plane_admission(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "deterministic", "runtime_timeout_seconds": 900}
    for loop_id in ("life-manager-release-reconciler", "life-manager-recovery-supervisor",
                    "life-manager-disk-cleanup", "life-manager-health-observer",
                    "capafy-loop-healthcheck",
                    "lm-fence-reconciler"):
        receipt = tmp_path / f"receipt-{loop_id}"
        with (patch("runtime.loop.lm_loop_run.memory_free_percent") as memory,
              patch("runtime.loop.lm_loop_run.durable_protocol_version",
                    return_value=1) as protocol,
              patch("runtime.loop.lm_loop_run.try_acquire_resource") as acquire,
              patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0) as run):
            assert _run_admitted(
                ["/bin/true"], entry, loop_id, {}, receipt,
            ) == 0

        memory.assert_not_called()
        if loop_id == "capafy-loop-healthcheck":
            protocol.assert_not_called()
        else:
            protocol.assert_called_once_with()
        acquire.assert_not_called()
        run.assert_called_once()
        call_args, call_kwargs = run.call_args
        assert call_args == (["/bin/true"],)
        assert call_kwargs["env"] == {"LIFE_MANAGER_LOOP_ID": loop_id}
        assert call_kwargs["timeout_seconds"] == 900
        # The capture wrapper hands _run_entrypoint a real fd, not a pipe.
        assert isinstance(call_kwargs["stderr_capture_fd"], int)
        assert json.loads(receipt.read_text()) == {
            "effect": 0,
            "reason": "control_plane_exempt",
            "status": "pass",
        }

def test_cleanup_control_caller_passes_the_real_occurrence_to_receipt_writer(tmp_path):
    entry = {"cadence":{"start_interval_seconds":300}, "provider_route":"deterministic"}
    with (patch("runtime.loop.lm_loop_run._run_entrypoint_with_stderr_capture",return_value=(0,b"")) as capture,
          patch("runtime.loop.lm_loop_run.reserve_available_resource",return_value=None),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run.clear_no_effect_unknown_resource")):
        _run_admitted(["/bin/true"],entry,"life-manager-disk-cleanup",{},tmp_path/"receipt",
                      occurrence_id="life-manager-disk-cleanup:scheduled-1")
    assert capture.call_args.kwargs["env"]["LIFE_MANAGER_OCCURRENCE_ID"] == "life-manager-disk-cleanup:scheduled-1"


def test_exempt_entrypoints_receive_native_occurrence_without_inheriting_foreign_context(tmp_path):
    cases = [
        ("life-manager-release-reconciler", {"start_interval_seconds": 60}),
        ("life-manager-release-reconciler", {"keep_alive": True}),
        ("continuous-owner", {"keep_alive": True}),
    ]
    for index, (loop_id, cadence) in enumerate(cases):
        for occurrence in (f"{loop_id}:native-wake", None):
            output = tmp_path / f"child-{index}-{bool(occurrence)}.json"
            env = {"LIFE_MANAGER_RUN_ID": "native-wake",
                   "LIFE_MANAGER_OCCURRENCE_ID": "other-owner:stale",
                   "LIFE_MANAGER_RESULT_HINT_PATH": str(tmp_path / "foreign-hint")}
            command = [sys.executable, "-c",
                       "import json,os,sys; from pathlib import Path; "
                       "Path(sys.argv[1]).write_text(json.dumps({k:os.environ.get(k) for k in "
                       "('LIFE_MANAGER_RUN_ID','LIFE_MANAGER_OCCURRENCE_ID',"
                       "'LIFE_MANAGER_RESULT_HINT_PATH')}))", str(output)]
            claimed = []
            with (patch("runtime.loop.lm_loop_run.clear_no_effect_unknown_resource"),
                  patch("runtime.loop.lm_loop_run.durable_protocol_version", return_value=1),
                  patch("runtime.loop.lm_loop_run.try_acquire_resource") as acquire):
                assert _run_admitted(command, {"cadence": cadence, "effect_class": "none"},
                                     loop_id, env, tmp_path / "receipt",
                                     occurrence_id=occurrence, on_claimed=claimed.append) == 0
            child = json.loads(output.read_text())
            assert child["LIFE_MANAGER_OCCURRENCE_ID"] == occurrence
            assert child["LIFE_MANAGER_RESULT_HINT_PATH"] is None
            assert child["LIFE_MANAGER_RUN_ID"] == "native-wake"
            assert env["LIFE_MANAGER_OCCURRENCE_ID"] == "other-owner:stale"
            assert claimed == []
            acquire.assert_not_called()


def test_control_plane_no_effect_owner_clears_stale_fence(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 300},
             "provider_route": "deterministic", "effect_class": "none",
             "runtime_timeout_seconds": 900}
    with (patch("runtime.loop.lm_loop_run.clear_no_effect_unknown_resource",
                return_value=1) as clear,
          patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0)):
        assert _run_admitted(
            ["/bin/true"], entry, "capafy-loop-healthcheck", {},
            tmp_path / "receipt",
        ) == 0
    clear.assert_called_once_with("capafy-loop-healthcheck")


def test_successful_safety_wake_dispatches_waiting_owner_without_taking_a_slot(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 300},
             "provider_route": "deterministic"}
    with (patch("runtime.loop.lm_loop_run.durable_protocol_version", return_value=2),
          patch("runtime.loop.lm_loop_run.try_acquire_resource") as acquire,
          patch("runtime.loop.lm_loop_run.reserve_available_resource",
                return_value=["waiting-owner"]) as reserve,
          patch("runtime.loop.lm_loop_run._dispatch_reserved") as dispatch,
          patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0)):
        assert _run_admitted(["/bin/true"], entry, "life-manager-disk-cleanup",
                             {}, tmp_path / "receipt") == 0
    acquire.assert_not_called()
    reserve.assert_called_once_with()
    dispatch.assert_called_once_with(["waiting-owner"])


def test_v1_protocol_uses_legacy_nonretaining_admission(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    claim = tmp_path / "claim"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        return 0

    with (patch("runtime.loop.lm_loop_run.durable_protocol_version", return_value=1),
          patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.try_acquire_resource",
                return_value=(claim, "acquired")) as acquire,
          patch("runtime.loop.lm_loop_run.release_resource") as release,
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource") as enqueue,
          patch("runtime.loop.lm_loop_run.transfer_durable_resource") as transfer,
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(
            ["/bin/true"], entry, "example", {}, tmp_path / "receipt",
        ) == 0

    acquire.assert_called_once_with(
        "agent", "example", admission_class="borrow",
        retain_ticket=False, required_protocol=1,
    )
    enqueue.assert_not_called()
    transfer.assert_called_once_with(claim, 4242)
    release.assert_called_once_with(claim)


def test_started_child_timeout_and_signal_mark_effect_unknown_before_release(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "deterministic", "resource_class": "browser",
             "admission_class": "revenue"}
    for exit_code in (124, 143):
        claim = tmp_path / f"claim-{exit_code}"
        claim.write_text("owned")

        def run_child(*_args, **kwargs):
            kwargs["on_started"](4242)
            return exit_code

        with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
              patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                    return_value=(tmp_path / "ticket", "ready")),
              patch("runtime.loop.lm_loop_run.claim_durable_resource",
                    return_value=(claim, "acquired")),
              patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
              patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                    return_value=[]) as release,
              patch("runtime.loop.lm_loop_run._dispatch_reserved"),
              patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
            assert _run_admitted(["/bin/true"], entry, "connector", {},
                                 tmp_path / f"receipt-{exit_code}") == exit_code
        release.assert_called_once_with(
            claim, requeue=False, reserve=True, effect_unknown=True)


def test_none_effect_child_failure_requeues_without_effect_unknown(tmp_path):
    """A control/report loop has no external effect to fence after a failed child."""
    claim = tmp_path / "claim-none-effect"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "agent",
            "admission_class": "borrow", "effect_class": "none",
        }, "marketing-owner-events", {}, tmp_path / "receipt") == 1
    release.assert_called_once_with(claim, requeue=False, reserve=True)


def test_proven_pre_effect_failure_releases_owner_for_next_wake(tmp_path):
    claim = tmp_path / "claim"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        hint = Path(kwargs["env"]["LIFE_MANAGER_RESULT_HINT_PATH"])
        hint.write_text('{"status":"pre_effect_failure","effect":0}\n')
        hint.chmod(0o600)
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "agent",
            "admission_class": "revenue",
            "entrypoint": "skills/earn/crowdworks/scripts/paid-owner",
        }, "paid", {}, tmp_path / "receipt") == 1
    release.assert_called_once_with(claim, requeue=False, reserve=True)


def test_allowlisted_owner_hint_exists_before_child_spawn(tmp_path):
    claim = tmp_path / "claim-host-pre-effect"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        hint = Path(kwargs["env"]["LIFE_MANAGER_RESULT_HINT_PATH"])
        assert hint.is_file()
        assert json.loads(hint.read_text(encoding="utf-8")) == {
            "status": "pre_effect_failure", "effect": 0,
        }
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "agent",
            "admission_class": "revenue",
            "entrypoint": "skills/earn/mercor/scripts/reply-owner",
        }, "mercor-reply", {}, tmp_path / "receipt") == 1
    release.assert_called_once_with(claim, requeue=False, reserve=True)


def test_writer_article_resume_pre_effect_failure_releases_without_unknown_fence(tmp_path):
    claim = tmp_path / "claim-writer-resume"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        hint = Path(kwargs["env"]["LIFE_MANAGER_RESULT_HINT_PATH"])
        hint.write_text('{"status":"pre_effect_failure","effect":0}\n')
        hint.chmod(0o600)
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 300},
            "provider_route": "shared-agent-runner", "resource_class": "agent",
            "admission_class": "borrow",
            "entrypoint": "skills/writer-agent/scripts/article-resume-pending.sh",
        }, "article-resume", {}, tmp_path / "receipt") == 1
    release.assert_called_once_with(claim, requeue=False, reserve=True)


def test_mercor_application_and_reply_pre_effect_hints_are_allowlisted():
    assert "skills/earn/mercor/scripts/application-owner" in PRE_EFFECT_HINT_ENTRYPOINTS
    assert "skills/earn/mercor/scripts/reply-owner" in PRE_EFFECT_HINT_ENTRYPOINTS


def test_crowdworks_application_and_reply_pre_effect_hints_are_allowlisted():
    assert "skills/earn/crowdworks/scripts/application-owner" in PRE_EFFECT_HINT_ENTRYPOINTS
    assert "skills/earn/crowdworks/scripts/reply-owner" in PRE_EFFECT_HINT_ENTRYPOINTS


def test_cross_venue_report_pre_effect_hint_is_allowlisted_by_loop_id():
    assert "investment-cross-venue-report" in PRE_EFFECT_HINT_LOOP_IDS


def test_lancers_application_pre_effect_hint_is_allowlisted():
    assert "skills/earn/lancers/scripts/application-owner" in PRE_EFFECT_HINT_ENTRYPOINTS


def test_lancers_storefront_pre_effect_hint_is_allowlisted():
    assert "skills/earn/lancers/scripts/storefront-owner" in PRE_EFFECT_HINT_ENTRYPOINTS


def test_affiliate_loop_pre_effect_hint_is_allowlisted():
    assert "skills/affiliate/affiliate" in PRE_EFFECT_HINT_ENTRYPOINTS


def test_storefront_direct_pre_effect_hint_is_scoped_by_loop_id_not_entrypoint():
    # entry_dispatch.py is a shared registry entrypoint for hf-gig-storefront-direct,
    # hf-gig-apply-direct and hf-gig-apply-reconcile. The two effect owners
    # implement no-mutation-attempted tracking, so trust must key on loop_id, not
    # on this shared entrypoint string.
    assert "hf-gig-storefront-direct" in PRE_EFFECT_HINT_LOOP_IDS
    assert "runtime/loop/entry_dispatch.py" not in PRE_EFFECT_HINT_ENTRYPOINTS
    assert "hf-gig-apply-direct" in PRE_EFFECT_HINT_LOOP_IDS
    assert "hf-gig-apply-reconcile" not in PRE_EFFECT_HINT_LOOP_IDS


def test_storefront_direct_loop_id_hint_is_honored_via_entry_dispatch(tmp_path):
    claim = tmp_path / "claim-storefront-direct"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        hint = Path(kwargs["env"]["LIFE_MANAGER_RESULT_HINT_PATH"])
        assert hint.is_file()
        assert json.loads(hint.read_text(encoding="utf-8")) == {
            "status": "pre_effect_failure", "effect": 0,
        }
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "agent",
            "admission_class": "revenue", "effect_class": "publish",
            "entrypoint": "runtime/loop/entry_dispatch.py",
        }, "hf-gig-storefront-direct", {}, tmp_path / "receipt") == 1
    release.assert_called_once_with(claim, requeue=False, reserve=True)


def test_investment_loop_id_hint_is_honored_for_pre_effect_failures(tmp_path):
    for loop_id in ("alpaca-investment-live", "alpaca-investment-paper"):
        claim = tmp_path / f"claim-{loop_id}"
        claim.write_text("owned")

        def run_child(*_args, **kwargs):
            kwargs["on_started"](4242)
            hint = Path(kwargs["env"]["LIFE_MANAGER_RESULT_HINT_PATH"])
            assert json.loads(hint.read_text(encoding="utf-8")) == {
                "status": "pre_effect_failure", "effect": 0,
            }
            return 78

        with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
              patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                    return_value=(tmp_path / f"ticket-{loop_id}", "ready")),
              patch("runtime.loop.lm_loop_run.claim_durable_resource",
                    return_value=(claim, "acquired")),
              patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
              patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                    return_value=[]) as release,
              patch("runtime.loop.lm_loop_run._dispatch_reserved"),
              patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
            assert _run_admitted(["/bin/true"], {
                "cadence": {"start_interval_seconds": 300},
                "provider_route": "shared-agent-runner", "resource_class": "agent",
                "admission_class": "revenue", "effect_class": "money",
                "entrypoint": "skills/alpaca-investment/run.py",
            }, loop_id, {}, tmp_path / f"receipt-{loop_id}") == 78
        release.assert_called_once_with(claim, requeue=False, reserve=True)


def test_apply_direct_loop_id_releases_failure_before_submit_boundary(tmp_path):
    claim = tmp_path / "claim-apply-direct"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        hint = Path(kwargs["env"]["LIFE_MANAGER_RESULT_HINT_PATH"])
        assert json.loads(hint.read_text()) == {
            "status": "pre_effect_failure", "effect": 0,
        }
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "agent",
            "admission_class": "revenue", "effect_class": "application",
            "entrypoint": "runtime/loop/entry_dispatch.py",
        }, "hf-gig-apply-direct", {}, tmp_path / "receipt") == 1
    release.assert_called_once_with(claim, requeue=False, reserve=True)


def test_apply_direct_loop_id_fences_failure_after_submit_boundary(tmp_path):
    claim = tmp_path / "claim-apply-direct"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        Path(kwargs["env"]["LIFE_MANAGER_RESULT_HINT_PATH"]).unlink()
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "agent",
            "admission_class": "revenue", "effect_class": "application",
            "entrypoint": "runtime/loop/entry_dispatch.py",
        }, "hf-gig-apply-direct", {}, tmp_path / "receipt") == 1
    release.assert_called_once_with(
        claim, requeue=False, reserve=True, effect_unknown=True)


def test_generic_child_hint_cannot_clear_unknown_effect(tmp_path):
    claim = tmp_path / "claim"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        assert "LIFE_MANAGER_RESULT_HINT_PATH" not in kwargs["env"]
        hint = tmp_path / "entrypoint-result.json"
        hint.write_text('{"status":"pre_effect_failure","effect":0}\n')
        hint.chmod(0o600)
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "browser",
            "admission_class": "revenue", "entrypoint": "skills/connector/run.sh",
        }, "connector", {}, tmp_path / "receipt") == 1
    release.assert_called_once_with(
        claim, requeue=False, reserve=True, effect_unknown=True)


def test_mobile_child_receives_effect_result_hint_path(tmp_path):
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({
        "occurrence_id": "life-manager-honne-ja:run-1",
    }))
    observed = {}

    def run_child(*_args, **kwargs):
        observed.update(kwargs["env"])
        kwargs["on_started"](4242)
        return 0

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "postiz", "resource_class": "agent",
            "admission_class": "revenue", "effect_class": "publish",
            "entrypoint": "apps/life-manager/scripts/mobile-app",
        }, "life-manager-honne-ja", {}, tmp_path / "host-admission.json",
            occurrence_id="life-manager-honne-ja:run-1") == 0

    assert EFFECT_RESULT_HINT_ENTRYPOINTS == frozenset({
        "apps/life-manager/scripts/ebook-distribute-daily.sh",
        "apps/life-manager/scripts/mobile-app",
    })
    assert "apps/life-manager/scripts/ebook-distribute-daily.sh" in PRE_EFFECT_HINT_ENTRYPOINTS
    assert "apps/life-manager/scripts/mobile-app" in PRE_EFFECT_HINT_ENTRYPOINTS
    assert {"ebook-en-tiktok-daily", "ebook-ja-instagram-daily", "ebook-ja-tiktok-daily"} <= PRE_EFFECT_HINT_LOOP_IDS
    assert observed["LIFE_MANAGER_RESULT_HINT_PATH"] == str(
        tmp_path / "entrypoint-result.json")


def test_owner_effect_result_hint_requires_exact_loop_and_entrypoint(tmp_path):
    def observed_env(loop_id, entrypoint, run_id):
        claim = tmp_path / f"claim-{run_id}"
        claim.write_text(json.dumps({"occurrence_id": f"{loop_id}:{run_id}"}))
        observed = {}

        def run_child(*_args, **kwargs):
            observed.update(kwargs["env"])
            kwargs["on_started"](4242)
            return 0

        with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
              patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                    return_value=(tmp_path / f"ticket-{run_id}", "ready")),
              patch("runtime.loop.lm_loop_run.claim_durable_resource",
                    return_value=(claim, "acquired")),
              patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
              patch("runtime.loop.lm_loop_run.release_and_reserve_resource", return_value=[]),
              patch("runtime.loop.lm_loop_run._dispatch_reserved"),
              patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
            assert _run_admitted(["/bin/true"], {
                "cadence": {"start_interval_seconds": 60},
                "provider_route": "deterministic", "resource_class": "deterministic",
                "admission_class": "borrow", "effect_class": "message",
                "entrypoint": entrypoint,
            }, loop_id, {}, tmp_path / f"receipt-{run_id}",
                occurrence_id=f"{loop_id}:{run_id}") == 0
        return observed

    cfo = observed_env(
        "life-manager-cfo-hourly", "skills/cfo/run.sh", "cfo-run-1")
    assert cfo["LIFE_MANAGER_LOOP_ID"] == "life-manager-cfo-hourly"
    assert cfo["LIFE_MANAGER_RESULT_HINT_PATH"] == str(
        tmp_path / "entrypoint-result.json")
    assert EFFECT_RESULT_HINT_LOOP_ENTRYPOINTS == {
        "life-manager-cfo-hourly": "skills/cfo/run.sh",
        "marketing-treg-lead-signals-weekly": "skills/earn/marketing-engine/intel/treg-lead-signals-weekly",
    }

    treg = observed_env(
        "marketing-treg-lead-signals-weekly",
        "skills/earn/marketing-engine/intel/treg-lead-signals-weekly",
        "treg-run-1",
    )
    assert treg["LIFE_MANAGER_LOOP_ID"] == "marketing-treg-lead-signals-weekly"
    assert treg["LIFE_MANAGER_RESULT_HINT_PATH"] == str(
        tmp_path / "entrypoint-result.json")

    sibling = observed_env("other-loop", "skills/cfo/run.sh", "sibling-run")
    assert "LIFE_MANAGER_RESULT_HINT_PATH" not in sibling
    wrong_entrypoint = observed_env(
        "life-manager-cfo-hourly", "skills/cfo/other.sh", "wrong-entrypoint")
    assert "LIFE_MANAGER_RESULT_HINT_PATH" not in wrong_entrypoint
    wrong_treg_entrypoint = observed_env(
        "marketing-treg-lead-signals-weekly",
        "skills/earn/marketing-engine/intel/treg/wrong-entrypoint",
        "wrong-treg-entrypoint",
    )
    assert "LIFE_MANAGER_RESULT_HINT_PATH" not in wrong_treg_entrypoint


def test_cfo_nonzero_telegram_result_keeps_message_effect_unknown(tmp_path):
    occurrence = "life-manager-cfo-hourly:telegram-run-incomplete-counters"
    claim = tmp_path / "claim-cfo"
    claim.write_text(json.dumps({"occurrence_id": occurrence}))
    observed = {}

    def run_child(*_args, **kwargs):
        observed.update(kwargs["env"])
        kwargs["on_started"](4242)
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket-cfo", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 3600},
            "provider_route": "deterministic", "resource_class": "deterministic",
            "admission_class": "borrow", "priority": "revenue",
            "effect_class": "message", "runtime_timeout_seconds": 45,
            "entrypoint": "skills/cfo/run.sh",
        }, "life-manager-cfo-hourly", {}, tmp_path / "receipt-cfo",
            occurrence_id=occurrence) == 1

    assert observed["LIFE_MANAGER_LOOP_ID"] == "life-manager-cfo-hourly"
    assert observed["LIFE_MANAGER_RESULT_HINT_PATH"] == str(
        tmp_path / "entrypoint-result.json")
    assert not (tmp_path / "receipt-cfo" / "entrypoint-result.json").exists()
    release.assert_called_once_with(
        claim, requeue=False, reserve=True, effect_unknown=True)


def test_mobile_publish_failure_after_hint_clear_keeps_unknown_effect_fence(tmp_path):
    claim = tmp_path / "claim-mobile"
    claim.write_text(json.dumps({
        "occurrence_id": "life-manager-honne-ja:run-1",
    }))

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        hint = Path(kwargs["env"]["LIFE_MANAGER_RESULT_HINT_PATH"])
        assert hint.is_file(), "mobile publisher must begin with a fail-closed no-effect marker"
        assert json.loads(hint.read_text(encoding="utf-8")) == {
            "status": "pre_effect_failure", "effect": 0,
        }
        hint.unlink()
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "postiz", "resource_class": "agent",
            "admission_class": "revenue", "effect_class": "publish",
            "entrypoint": "apps/life-manager/scripts/mobile-app",
        }, "life-manager-honne-ja", {}, tmp_path / "mobile-receipt",
            occurrence_id="life-manager-honne-ja:run-1") == 1

    release.assert_called_once_with(
        claim, requeue=False, reserve=True, effect_unknown=True)


def test_pre_effect_hint_fails_closed_when_absent_or_malformed(tmp_path):
    absent = tmp_path / "absent.json"
    malformed = tmp_path / "malformed.json"
    malformed.write_text("not-json\n", encoding="utf-8")
    malformed.chmod(0o600)

    assert _proven_pre_effect_failure(absent) is False
    assert _proven_pre_effect_failure(malformed) is False
def _write_effect_result(path, **overrides):
    value = {
        "schema_version": 1,
        "kind": "life_manager_effect_result",
        "status": "verified_effect",
        "effect": 1,
        "owner_id": "life-manager-honne-ja",
        "occurrence_id": "life-manager-honne-ja:run-1",
        "provider": "postiz",
        "provider_receipt_id": "postiz-post-1",
        "effect_status": "reconciled",
    }
    value.update(overrides)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return value


def test_verified_mobile_effect_result_requires_exact_private_identity(tmp_path):
    hint = tmp_path / "entrypoint-result.json"
    _write_effect_result(hint)

    assert _verified_effect_result(
       hint, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
    ) == ("reconciled", "postiz://posts/postiz-post-1")
    _write_effect_result(hint, schema_version=True)
    assert _verified_effect_result(
        hint, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
    ) is None
    _write_effect_result(hint, effect=True)
    assert _verified_effect_result(
        hint, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
    ) is None

    _write_effect_result(hint, occurrence_id="life-manager-honne-ja:other")
    assert _verified_effect_result(
        hint, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
    ) is None
    _write_effect_result(hint)
    hint.chmod(0o644)
    assert _verified_effect_result(
        hint, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
    ) is None


def test_verified_mobile_effect_result_rejects_symlink_and_unknown_fields(tmp_path):
    outside = tmp_path / "outside.json"
    _write_effect_result(outside)
    symlink = tmp_path / "entrypoint-result.json"
    symlink.symlink_to(outside)
    assert _verified_effect_result(
        symlink, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
    ) is None

    malformed = tmp_path / "malformed.json"
    _write_effect_result(malformed, unexpected=True)
    assert _verified_effect_result(
        malformed, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
    ) is None


def test_verified_cfo_telegram_effect_result_uses_message_receipt_ref(tmp_path):
    hint = tmp_path / "entrypoint-result.json"
    _write_effect_result(
        hint,
        owner_id="life-manager-cfo-hourly",
        occurrence_id="life-manager-cfo-hourly:telegram-run-1",
        provider="telegram",
        provider_receipt_id="9142",
        effect_status="verified",
    )

    assert _verified_effect_result(
        hint, "life-manager-cfo-hourly", "life-manager-cfo-hourly:telegram-run-1",
        entrypoint="skills/cfo/run.sh",
    ) == ("verified", "telegram://messages/9142")

    event = build_runtime_event(
        loop_id="life-manager-cfo-hourly", domain="financial", run_id="telegram-run-1",
        release_sha="a" * 40, provider="deterministic", profile_alias=None,
        effect_class="message", succeeded=True, blocker=None,
        claimed_occurrence_id="life-manager-cfo-hourly:telegram-run-1",
    )
    upgraded = _apply_verified_effect_result(
        event, ("verified", "telegram://messages/9142"),
    )
    assert upgraded["provider"] == "telegram"
    assert upgraded["provider_receipt_id"] == "9142"
    assert upgraded["official_readback_ref"] == "telegram://messages/9142"
    assert "telegram://messages/9142" in upgraded["evidence_refs"]

    assert _verified_effect_result(
        hint, "life-manager-cfo-hourly", "life-manager-cfo-hourly:telegram-run-1",
        entrypoint="skills/cfo/other.sh",
    ) is None
    assert _verified_effect_result(
        hint, "life-manager-cfo-hourly", "life-manager-cfo-hourly:other-run",
        entrypoint="skills/cfo/run.sh",
    ) is None
    _write_effect_result(hint, provider_receipt_id="bad/receipt")
    assert _verified_effect_result(
        hint, "life-manager-cfo-hourly", "life-manager-cfo-hourly:telegram-run-1",
        entrypoint="skills/cfo/run.sh",
    ) is None
def _write_no_effect_result(path, **overrides):
    value = {
        'schema_version': 1,
        'kind': 'life_manager_no_effect_result',
        'status': 'verified_no_effect',
        'effect': 0,
        'owner_id': 'ebook-ja-tiktok-daily',
        'occurrence_id': 'ebook-ja-tiktok-daily:run-off-slot',
        'reason': 'no_due_slot',
    }
    value.update(overrides)
    path.write_text(json.dumps(value) + '\n', encoding='utf-8')
    path.chmod(0o600)
    return value


def test_verified_no_effect_result_requires_exact_identity_and_allowed_entrypoint(tmp_path):
    hint = tmp_path / 'entrypoint-result.json'
    _write_no_effect_result(hint)
    reader = getattr(loop_runner, '_verified_no_effect_result', None)
    assert callable(reader)
    if not callable(reader):
        return

    entrypoint = 'apps/life-manager/scripts/ebook-distribute-daily.sh'
    expected = (
        'not_applicable',
        'lm-no-effect://ebook-ja-tiktok-daily/ebook-ja-tiktok-daily:run-off-slot/no_due_slot',
    )
    assert reader(hint, 'ebook-ja-tiktok-daily',
                  'ebook-ja-tiktok-daily:run-off-slot', entrypoint) == expected
    english_owner = 'ebook-en-tiktok-daily'
    english_occurrence = f'{english_owner}:render-run-1'
    _write_no_effect_result(
        hint, owner_id=english_owner, occurrence_id=english_occurrence,
        reason='render_not_ready',
    )
    assert reader(hint, english_owner, english_occurrence, entrypoint) == (
        'not_applicable',
        f'lm-no-effect://{english_owner}/{english_occurrence}/render_not_ready',
    )
    _write_no_effect_result(hint, schema_version=True)
    assert reader(hint, 'ebook-ja-tiktok-daily',
                  'ebook-ja-tiktok-daily:run-off-slot', entrypoint) is None
    _write_no_effect_result(hint, effect=False)
    assert reader(hint, 'ebook-ja-tiktok-daily',
                  'ebook-ja-tiktok-daily:run-off-slot', entrypoint) is None
    _write_no_effect_result(hint, reason=[])
    try:
        invalid_reason = reader(hint, 'ebook-ja-tiktok-daily',
                                'ebook-ja-tiktok-daily:run-off-slot', entrypoint)
    except TypeError as error:
        assert False, f'array reason must fail closed without raising: {error}'
    assert invalid_reason is None

    _write_no_effect_result(hint, occurrence_id='ebook-ja-tiktok-daily:other')
    assert reader(hint, 'ebook-ja-tiktok-daily',
                  'ebook-ja-tiktok-daily:run-off-slot', entrypoint) is None
    _write_no_effect_result(hint, reason='arbitrary')
    assert reader(hint, 'ebook-ja-tiktok-daily',
                  'ebook-ja-tiktok-daily:run-off-slot', entrypoint) is None
    _write_no_effect_result(hint)
    mobile_owner = 'life-manager-anicca-en-affirmation-instagram'
    mobile_occurrence = f'{mobile_owner}:off-slot-1'
    _write_no_effect_result(hint, owner_id=mobile_owner,
                            occurrence_id=mobile_occurrence)
    assert reader(hint, mobile_owner, mobile_occurrence,
                  'apps/life-manager/scripts/mobile-app') == (
                      'not_applicable',
                      f'lm-no-effect://{mobile_owner}/{mobile_occurrence}/no_due_slot',
                  )
    _write_no_effect_result(hint, owner_id=mobile_owner,
                            occurrence_id=mobile_occurrence,
                            reason='daily_limit_reached')
    assert reader(hint, mobile_owner, mobile_occurrence,
                  'apps/life-manager/scripts/mobile-app') == (
                      'not_applicable',
                      f'lm-no-effect://{mobile_owner}/{mobile_occurrence}/daily_limit_reached',
                  )
    _write_no_effect_result(hint, reason='daily_limit_reached')
    assert reader(hint, 'ebook-ja-tiktok-daily',
                  'ebook-ja-tiktok-daily:run-off-slot', entrypoint) is None
    assert reader(hint, mobile_owner, mobile_occurrence,
                  'apps/life-manager/scripts/other-mobile-app') is None
    hint.write_text('{"status":"pre_effect_failure","effect":0}\n', encoding='utf-8')
    hint.chmod(0o600)
    assert reader(hint, 'ebook-ja-tiktok-daily',
                  'ebook-ja-tiktok-daily:run-off-slot', entrypoint) is None


def test_verified_no_effect_result_marks_the_terminal_as_no_effect():
    owner = 'ebook-ja-tiktok-daily'
    occurrence = f'{owner}:run-off-slot'
    ref = f'lm-no-effect://{owner}/{occurrence}/no_due_slot'
    event = build_runtime_event(
        loop_id=owner, domain='growth', run_id='run-off-slot',
        release_sha='a' * 40, provider='postiz', profile_alias=None,
        effect_class='publish', succeeded=True, blocker=None,
        claimed_occurrence_id=occurrence,
    )

    updated = _apply_verified_effect_result(event, ('not_applicable', ref))

    assert updated['effect_class'] == 'none'
    assert updated['effect_status'] == 'not_applicable'
    assert updated['evidence_refs'][-1] == ref
def test_verified_mobile_effect_result_upgrades_only_success_event(tmp_path):
    event = build_runtime_event(
        loop_id="life-manager-honne-ja", domain="growth", run_id="run-1",
        release_sha="a" * 40, provider="postiz", profile_alias=None,
        effect_class="publish", succeeded=True, blocker=None,
        claimed_occurrence_id="life-manager-honne-ja:run-1",
    )
    upgraded = _apply_verified_effect_result(
        event, ("verified", "postiz://posts/postiz-post-1"),
    )
    assert upgraded["effect_status"] == "verified"
    assert upgraded["evidence_refs"][-1] == "postiz://posts/postiz-post-1"

    failed = {**event, "status": "fail", "blocker": "entrypoint_exit_1"}
    assert _apply_verified_effect_result(
        failed, ("verified", "postiz://posts/postiz-post-1"),
    )["effect_status"] == "unknown"


def test_main_projects_exact_mobile_result_into_terminal_event(tmp_path):
    release = tmp_path / "release"
    (release / "config").mkdir(parents=True)
    (release / "apps/life-manager/config").mkdir(parents=True)
    (release / "config/loop-registry.json").write_text(json.dumps({
        "loops": {"life-manager-honne-ja": {
            "label": "ai.anicca.life-manager-honne-ja",
            "domain": "growth",
            "entrypoint": "apps/life-manager/scripts/mobile-app",
            "provider_route": "postiz",
            "effect_class": "publish",
            "state_root": str(tmp_path / "unused-state"),
        }},
    }), encoding="utf-8")
    (release / "RELEASE.json").write_text(json.dumps({
        "sha": "a" * 40,
    }), encoding="utf-8")
    (release / "apps/life-manager/config/product-loop-catalog.json").write_text(json.dumps({
        "loops": [{"id": "mobile-apps", "job_ids": ["life-manager-honne-ja"]}],
    }), encoding="utf-8")
    events = []

    def run_admitted(_command, _entry, loop_id, _env, receipt, *,
                     occurrence_id, on_claimed, on_stderr_tail=lambda _tail: None,
                     on_storage_failure=None, on_terminal_event=None):
        on_claimed(occurrence_id)
        receipt.write_text('{"status":"pass","effect":0}\n', encoding="utf-8")
        receipt.chmod(0o600)
        _write_effect_result(
            receipt.parent / "entrypoint-result.json",
            owner_id=loop_id,
            occurrence_id=occurrence_id,
            effect_status="verified",
        )
        return 0

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(tmp_path / "state"),
              "LIFE_MANAGER_RUN_ID": "run-1",
              "WAKE_ID": "wake-1",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/true"]),
          patch("runtime.loop.lm_loop_run._run_admitted", side_effect=run_admitted),
          patch("runtime.loop.lm_loop_run.append_runtime_event",
                side_effect=lambda _path, event: events.append(event)),
          patch("runtime.loop.lm_loop_run._enqueue_recovery_intent") as enqueue):
        assert lm_loop_run_main(["life-manager-honne-ja", str(release)]) == 0

    assert events[-1]["status"] == "pass"
    assert events[-1]["effect_status"] == "verified"
    assert events[-1]["evidence_refs"][-1] == "postiz://posts/postiz-post-1"
    assert events[-1]["product_loop_id"] == "mobile-apps"
    assert events[-1]["job_id"] == "life-manager-honne-ja"
    assert events[-1]["owner_id"] == "life-manager-honne-ja"
    assert events[-1]["wake_id"] == "wake-1"
    assert events[-1]["occurrence_id"] == "life-manager-honne-ja:run-1"
    assert events[-1]["exit_code"] == 0
    assert events[-1]["failure_layer"] == "clean"
    assert events[-1]["error_class"] is None
    assert events[-1]["retryable"] is False
    assert events[-1]["next_action"] == "none"
    assert events[-1]["provider_receipt_id"] == "postiz-post-1"
    assert events[-1]["official_readback_ref"] == "postiz://posts/postiz-post-1"
    assert len(events[-1]["loaded_argv_sha256"]) == 64
    assert len(events[-1]["loaded_env_sha256"]) == 64
    enqueue.assert_not_called()


def test_main_preserves_live_relay_after_terminal_commit(tmp_path):
    release = _write_prestart_lock_release(tmp_path)
    state = tmp_path / "state"
    with (patch.dict(os.environ, {"LIFE_MANAGER_STATE_ROOT": str(state),
              "LIFE_MANAGER_RUN_ID": "live-relay-run", "WAKE_ID": "wake-1"}),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/true"]),
          patch("runtime.loop.lm_loop_run._run_admitted", return_value=0),
          patch("runtime.loop.lm_loop_run.append_runtime_event"),
          patch("runtime.loop.central_cleanup._diagnostic_relay_live", return_value=True),
          patch("runtime.loop.lm_loop_run.remove_owned_tree") as remove):
        assert lm_loop_run_main(["example-publisher", str(release)]) == 0
    assert (state / "loop-tmp/example-publisher/live-relay-run").exists()
    remove.assert_not_called()


@pytest.mark.parametrize("mode", ["finite", "continuous"])
def test_main_bounds_repeated_stdio_and_preserves_legacy_logs_and_terminals(tmp_path, mode):
    release = _write_prestart_lock_release(tmp_path)
    policy = json.loads((Path(__file__).resolve().parents[3] / "config/storage-policy.json").read_text())
    policy["defaults"]["diagnostic_segment_bytes"] = 65536
    (release / "config/storage-policy.json").write_text(json.dumps(policy))
    logs = tmp_path / "logs"
    logs.mkdir(mode=0o700)
    logs.chmod(0o755)  # Existing launchd roots can be readable without being private.
    old_out, old_err = logs / "launchd.out.log", logs / "launchd.err.log"
    for path in (old_out, old_err):
        path.write_bytes(b"existing shared diagnostic\n")
    state = tmp_path / "state"
    helper = tmp_path / "owner.py"
    helper.write_text(
        "import os,sys\nfrom pathlib import Path\nfrom contextlib import nullcontext\n"
        "from unittest.mock import patch\n"
        "from runtime.loop import lm_loop_run as runner\n"
        "command=[sys.executable,'-c','import os; os.write(1,b\"o\"*(3*1024*1024)); os.write(2,b\"e\"*(3*1024*1024)); raise SystemExit(7)']\n"
        "def run(command,entry,owner,env,receipt,**kwargs):\n"
        " if sys.argv[2]=='continuous': return runner._run_entrypoint(command,env=env)\n"
        " return runner._run_entrypoint_with_stderr_capture(command,receipt.parent,env=env)[0]\n"
        "with patch.object(runner,'_apply_lock',return_value=nullcontext()),patch.object(runner,'build_loop_command',return_value=command),patch.object(runner,'_run_admitted',side_effect=run),patch.object(runner,'_should_enqueue_recovery_intent',return_value=False):\n"
        " for i in range(3):\n"
        "  os.environ['LIFE_MANAGER_RUN_ID']=f'run-{i}'\n"
        "  assert runner.main(['example-publisher',sys.argv[1]])==7\n"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[3]),
           "LIFE_MANAGER_LOG_ROOT": str(logs), "LIFE_MANAGER_STATE_ROOT": str(state)}
    with old_out.open("ab") as out, old_err.open("ab") as err:
        subprocess.run([sys.executable, "-B", str(helper), str(release), mode],
                       env=env, stdout=out, stderr=err, check=True, timeout=30)
    assert old_out.read_bytes() == b"existing shared diagnostic\n"
    assert old_err.read_bytes() == b"existing shared diagnostic\n"
    for stream in ("out", "err"):
        files = list((logs / "bounded").glob(f"launchd-example-publisher.{stream}.log*"))
        assert files
        assert sum(path.stat().st_size for path in files) <= 131072
    events = [json.loads(line) for line in (state / "events.jsonl").read_text().splitlines()]
    terminal = [row for row in events if row.get("exit_code") is not None]
    assert len(terminal) == 3
    assert all(row["exit_code"] == 7 and row["status"] == "fail" for row in terminal)
    assert logs.stat().st_mode & 0o777 == 0o755
    assert (logs / "bounded").stat().st_mode & 0o777 == 0o700


def test_cleanup_safety_owner_runs_when_bounded_log_startup_has_enospc(tmp_path):
    owner = "life-manager-disk-cleanup"
    release = _write_prestart_lock_release(tmp_path)
    registry_path = release / "config/loop-registry.json"
    registry = json.loads(registry_path.read_text())
    entry = registry["loops"].pop("example-publisher")
    entry.update(label=f"ai.anicca.{owner}", effect_class="none", provider_route="deterministic")
    registry["loops"][owner] = entry
    registry_path.write_text(json.dumps(registry))
    policy = Path(__file__).resolve().parents[3] / "config/storage-policy.json"
    (release / "config/storage-policy.json").write_bytes(policy.read_bytes())
    state = tmp_path / "state"
    with (patch.dict(os.environ, {"LIFE_MANAGER_STATE_ROOT": str(state),
              "LIFE_MANAGER_LOG_ROOT": str(tmp_path / "logs"), "LIFE_MANAGER_RUN_ID": "cleanup-1"}),
          patch.object(loop_runner, "_apply_lock", return_value=nullcontext()),
          patch.object(loop_runner, "build_loop_command", return_value=["/bin/true"]),
          patch.object(loop_runner, "_run_admitted", return_value=0),
          patch.object(loop_runner, "bounded_launchd_output", side_effect=OSError(errno.ENOSPC, "fixture"))):
        assert lm_loop_run_main([owner, str(release)]) == 0
    events = [json.loads(line) for line in (state / "events.jsonl").read_text().splitlines()]
    assert events[-1]["owner_id"] == owner
    assert events[-1]["status"] == "pass"


@pytest.mark.parametrize("identity_outcome", ["rejected", "save_exception", "persisted", "not_written"])
def test_failed_run_cleans_scratch_only_after_effect_identity_is_safe(tmp_path, identity_outcome):
    release = _write_prestart_lock_release(tmp_path)
    state = tmp_path / "state"
    scratch = state / "loop-tmp/example-publisher/run-1"
    sidecar = scratch / "effect-identity.jsonl"
    value = {
        "schema_version": 1, "kind": "life_manager_effect_identity",
        "runtime_run_id": "run-1", "occurrence_id": "example-publisher:run-1",
        "loop_id": "example-publisher", "job_id": "example-publisher",
        "effect_key": "marketing:video:honne-ai:tiktok:creative:" + "a" * 64 + ":" + "b" * 64,
        "product_id": "honne-ai", "format_id": "reelclaw",
        "form": "relationship-confession", "locale": "ja", "platform": "tiktok",
        "creative_id": "creative", "slot": "2026-07-30T12:30:00.000Z",
        "integration_ref": "integration://postiz/tiktok/honne-ai-ja",
        "account_id": "@honnevideo",
        "video_sha256": "a" * 64, "caption_sha256": "b" * 64,
    }
    raw = json.dumps({"unverified": "preserve original"} if identity_outcome == "rejected" else value) + "\n"

    def run_admitted(_command, _entry, _loop_id, _env, receipt, *, on_claimed, occurrence_id, **_kwargs):
        on_claimed(occurrence_id)
        receipt.write_text('{"status":"pass","effect":0}\n')
        receipt.chmod(0o600)
        if identity_outcome != "not_written":
            sidecar.write_text(raw)
            sidecar.chmod(0o600)
        return 1

    identity_patch = (patch("runtime.loop.lm_loop_run._persist_effect_identity",
                            side_effect=ValueError("identity unavailable"))
                      if identity_outcome == "save_exception" else nullcontext())
    events = []
    with (patch.dict(os.environ, {"LIFE_MANAGER_STATE_ROOT": str(state), "LIFE_MANAGER_RUN_ID": "run-1"}),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/true"]),
          patch("runtime.loop.lm_loop_run._run_admitted", side_effect=run_admitted),
          patch("runtime.loop.lm_loop_run.append_runtime_event", side_effect=lambda _p, e: events.append(e)),
          patch("runtime.loop.lm_loop_run._enqueue_recovery_intent"), identity_patch):
        assert lm_loop_run_main(["example-publisher", str(release)]) == 1

    assert events[-1]["status"] == "fail"
    if identity_outcome in {"rejected", "save_exception"}:
        assert sidecar.is_file(), "failed identity persistence must retain the only original"
        assert sidecar.read_text() == raw
        assert (scratch / ".terminal-unrecorded").is_file()
        diagnostic = json.loads((state / "scratch-cleanup-diagnostics/run-1.json").read_text())
        assert diagnostic["terminal_saved"] is True
        assert diagnostic["cleanup_status"] == "held_effect_identity_unrecorded"
        assert diagnostic["cleanup_operation"] == "persist_effect_identity"
        from runtime.loop.central_cleanup import scratch_gc
        assert scratch_gc({state}, starts={})["removed"] == 0
        assert sidecar.read_text() == raw
    else:
        assert not scratch.exists(), "safe completed runs must still clean their own scratch"
        if identity_outcome == "persisted":
            assert (state / "effect-identities/run-1.jsonl").read_text() == raw


def test_main_records_false_terminal_scratch_cleanup_without_changing_business_result(tmp_path):
    release = _write_prestart_lock_release(tmp_path)
    state_root = tmp_path / "state"
    events = []
    scratch = state_root / "loop-tmp/example-publisher/run-1"

    def run_admitted(_command, _entry, _loop_id, _env, receipt, **_kwargs):
        receipt.write_text('{"status":"pass","effect":0}\n', encoding="utf-8")
        receipt.chmod(0o600)
        return 0

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(state_root),
              "LIFE_MANAGER_RUN_ID": "run-1",
              "WAKE_ID": "wake-1",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/true"]),
          patch("runtime.loop.lm_loop_run._run_admitted", side_effect=run_admitted),
          patch("runtime.loop.lm_loop_run.append_runtime_event",
                side_effect=lambda _path, event: events.append(event)),
          patch("runtime.loop.lm_loop_run.remove_owned_tree", return_value=False)):
        assert lm_loop_run_main(["example-publisher", str(release)]) == 0

    assert events[-1]["status"] == "pass"
    diagnostic_path = state_root / "scratch-cleanup-diagnostics/run-1.json"
    assert diagnostic_path.is_file()
    assert scratch not in diagnostic_path.parents
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    assert diagnostic["run_id"] == "run-1"
    assert diagnostic["owner_id"] == "example-publisher"
    assert diagnostic["occurrence_id"] == "example-publisher:run-1"
    assert diagnostic["release_sha"] == "a" * 40
    assert diagnostic["terminal_saved"] is True
    assert diagnostic["phase"] == "terminal_cleanup"
    assert diagnostic["cleanup_status"] == "preserved"
    assert diagnostic["scratch_path"] == "loop-tmp/example-publisher/run-1"
    assert diagnostic["loaded_argv_sha256"] == events[-1]["loaded_argv_sha256"]
    assert diagnostic["loaded_env_sha256"] == events[-1]["loaded_env_sha256"]
    assert diagnostic["command"] == "bin/example-publisher"
    assert diagnostic["error_class"] is None
    assert diagnostic["errno"] is None
    assert diagnostic["scratch_identity"]["inode"] == scratch.stat().st_ino
    assert diagnostic["scratch_identity"]["mode"] == "0700"
    assert diagnostic["scratch_identity"]["path_present"] is True
    assert diagnostic["scratch_identity"]["path_matches_open"] is True
    assert diagnostic["scratch_identity"]["terminal_marker_remaining"] is False
    assert scratch.is_dir()


def test_main_records_cleanup_exception_without_changing_business_result(tmp_path):
    release = _write_prestart_lock_release(tmp_path)
    state_root = tmp_path / "state"
    events = []

    def run_admitted(_command, _entry, _loop_id, _env, receipt, **_kwargs):
        receipt.write_text('{"status":"pass","effect":0}\n', encoding="utf-8")
        receipt.chmod(0o600)
        return 0

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(state_root),
              "LIFE_MANAGER_RUN_ID": "run-1",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/true"]),
          patch("runtime.loop.lm_loop_run._run_admitted", side_effect=run_admitted),
          patch("runtime.loop.lm_loop_run.append_runtime_event",
                side_effect=lambda _path, event: events.append(event)),
          patch("runtime.loop.lm_loop_run.remove_owned_tree",
                side_effect=OSError(13, "private cleanup path"))):
        assert lm_loop_run_main(["example-publisher", str(release)]) == 0

    assert events[-1]["status"] == "pass"
    diagnostic_raw = (state_root / "scratch-cleanup-diagnostics/run-1.json").read_text()
    diagnostic = json.loads(diagnostic_raw)
    assert diagnostic["cleanup_status"] == "error"
    assert diagnostic["cleanup_operation"] == "remove_owned_tree"
    assert diagnostic["error_class"] == "PermissionError"
    assert diagnostic["errno"] == 13
    assert diagnostic["scratch_identity"]["terminal_marker_remaining"] is False
    assert "private cleanup path" not in diagnostic_raw


def test_main_keeps_scratch_protected_when_terminal_event_is_not_saved(tmp_path):
    release = _write_prestart_lock_release(tmp_path)
    state_root = tmp_path / "state"
    scratch = state_root / "loop-tmp/example-publisher/run-1"
    events = []

    def run_admitted(_command, _entry, _loop_id, _env, receipt, **_kwargs):
        receipt.write_text('{"status":"pass","effect":0}\n', encoding="utf-8")
        receipt.chmod(0o600)
        return 0

    def append_event(_path, event):
        if len(events) == 0:
            events.append(event)
            return
        raise OSError(28, "terminal write unavailable")

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(state_root),
              "LIFE_MANAGER_RUN_ID": "run-1",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/true"]),
          patch("runtime.loop.lm_loop_run._run_admitted", side_effect=run_admitted),
          patch("runtime.loop.lm_loop_run.append_runtime_event", side_effect=append_event),
          patch("runtime.loop.lm_loop_run.remove_owned_tree") as remove):
        assert lm_loop_run_main(["example-publisher", str(release)]) == 78

    diagnostic = json.loads((state_root / "scratch-cleanup-diagnostics/run-1.json").read_text())
    assert diagnostic["terminal_saved"] is False
    assert diagnostic["phase"] == "terminal_unrecorded_hold"
    assert diagnostic["cleanup_status"] == "held_terminal_unrecorded"
    assert diagnostic["error_class"] == "OSError"
    assert diagnostic["errno"] == 28
    assert diagnostic["scratch_identity"]["path_matches_open"] is True
    assert diagnostic["scratch_identity"]["terminal_marker_remaining"] is True
    assert (scratch / ".terminal-unrecorded").is_file()
    remove.assert_not_called()


def test_main_reports_typed_diagnostic_when_cleanup_record_cannot_be_written(
        tmp_path, capsys):
    release = _write_prestart_lock_release(tmp_path)
    state_root = tmp_path / "state"
    events = []

    def run_admitted(_command, _entry, _loop_id, _env, receipt, **_kwargs):
        receipt.write_text('{"status":"pass","effect":0}\n', encoding="utf-8")
        receipt.chmod(0o600)
        return 0

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(state_root),
              "LIFE_MANAGER_RUN_ID": "run-1",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/true"]),
          patch("runtime.loop.lm_loop_run._run_admitted", side_effect=run_admitted),
          patch("runtime.loop.lm_loop_run.append_runtime_event",
                side_effect=lambda _path, event: events.append(event)),
          patch("runtime.loop.lm_loop_run.remove_owned_tree", return_value=False),
          patch("runtime.loop.lm_loop_run._atomic_json",
                side_effect=PermissionError(13, "private diagnostic path"))):
        assert lm_loop_run_main(["example-publisher", str(release)]) == 0

    captured = capsys.readouterr()
    diagnostic = json.loads(captured.err)
    assert diagnostic["event"] == "scratch_cleanup_diagnostic_write_failed"
    assert diagnostic["run_id"] == "run-1"
    assert diagnostic["owner_id"] == "example-publisher"
    assert diagnostic["phase"] == "diagnostic_record"
    assert diagnostic["cleanup_status"] == "preserved"
    assert diagnostic["error_class"] == "PermissionError"
    assert diagnostic["errno"] == 13
    assert "private diagnostic path" not in captured.err


def _write_prestart_lock_release(tmp_path):
    release = tmp_path / "release"
    (release / "config").mkdir(parents=True)
    (release / "apps/life-manager/config").mkdir(parents=True)
    (release / "config/loop-registry.json").write_text(json.dumps({
        "loops": {"example-publisher": {
            "label": "ai.anicca.example-publisher",
            "domain": "earn",
            "entrypoint": "bin/example-publisher",
            "provider_route": "test-provider",
            "effect_class": "publish",
            "state_root": str(tmp_path / "unused-state"),
        }},
    }), encoding="utf-8")
    (release / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}), encoding="utf-8")
    (release / "apps/life-manager/config/product-loop-catalog.json").write_text(json.dumps({
        "loops": [{"id": "publisher-products", "job_ids": ["example-publisher"]}],
    }), encoding="utf-8")
    return release


def test_main_records_apply_lock_busy_before_dispatch(tmp_path):
    release = _write_prestart_lock_release(tmp_path)
    state_root = tmp_path / "state"
    event_path = state_root / "events.jsonl"

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(state_root),
              "LIFE_MANAGER_RUN_ID": "run-1",
              "WAKE_ID": "wake-1",
              "LIFE_MANAGER_APPLY_LOCK_WAIT_SECONDS": "0",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock",
                side_effect=RuntimeError("production apply is already owned")),
          patch("runtime.loop.lm_loop_run.build_loop_command") as build_command,
          patch("runtime.loop.lm_loop_run.reset_loop_scratch") as reset_scratch,
          patch("runtime.loop.lm_loop_run._run_admitted") as run_admitted,
          patch("runtime.loop.lm_loop_run.try_acquire_resource") as acquire_resource,
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource") as enqueue_resource):
        assert lm_loop_run_main(["example-publisher", str(release)]) == 78

    assert event_path.exists()
    events = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1
    event = events[0]
    assert event["phase"] == "report"
    assert event["status"] == "blocked"
    assert event["loop_id"] == event["job_id"] == event["owner_id"] == "example-publisher"
    assert event["product_loop_id"] == "publisher-products"
    assert event["run_id"] == "run-1"
    assert event["wake_id"] == "wake-1"
    assert event["occurrence_id"] == "example-publisher:run-1"
    assert event["release_sha"] == "a" * 40
    assert event["effect_class"] == "publish"
    assert event["effect_status"] == "not_applicable"
    assert event["blocker"] == event["error_class"] == "apply_lock_busy"
    assert event["failure_layer"] == "runtime"
    assert event["exit_code"] == 78
    assert event["retryable"] is True
    assert event["next_action"] == "retry_after_eligibility"
    assert event["loaded_argv_sha256"] is None
    assert event["provider_receipt_id"] is None
    assert event["official_readback_ref"] is None
    assert not (state_root / "loop-tmp/example-publisher/run-1").exists()
    build_command.assert_not_called()
    reset_scratch.assert_not_called()
    run_admitted.assert_not_called()
    acquire_resource.assert_not_called()
    enqueue_resource.assert_not_called()


def test_main_records_scratch_enospc_and_allows_next_wake(tmp_path):
    release = _write_prestart_lock_release(tmp_path)
    registry_path = release / "config/loop-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["loops"]["example-publisher"]["effect_class"] = "none"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    state_root = tmp_path / "state"
    events = []

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(state_root),
              "LIFE_MANAGER_RUN_ID": "run-1",
              "WAKE_ID": "wake-1",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/true"]),
          patch("runtime.loop.lm_loop_run.reset_loop_scratch",
                side_effect=OSError(errno.ENOSPC, "No space left on device")),
          patch("runtime.loop.lm_loop_run.append_runtime_event",
                side_effect=lambda _path, event: events.append(event)),
          patch("runtime.loop.lm_loop_run._run_admitted") as run_admitted):
        assert lm_loop_run_main(["example-publisher", str(release)]) == 78

    assert len(events) == 1
    failed = events[0]
    assert failed["phase"] == "report"
    assert failed["status"] == "fail"
    assert failed["loop_id"] == failed["job_id"] == failed["owner_id"] == "example-publisher"
    assert failed["run_id"] == "run-1"
    assert failed["occurrence_id"] == "example-publisher:run-1"
    assert failed["effect_status"] == "not_applicable"
    assert failed["blocker"] == "scratch_enospc"
    assert failed["error_class"] == "storage_write_failed_pre_effect"
    assert failed["exit_code"] == 78
    assert failed["retryable"] is True
    assert failed["next_action"] == "retry_after_cleanup"
    assert failed["storage_failure"]["effect_started"] is False
    assert failed["error_detail"] == "scratch allocation failed; errno=28"
    assert failed["evidence_refs"] == []
    assert failed["provider_receipt_id"] is None
    assert failed["official_readback_ref"] is None
    assert not (state_root / "loop-tmp/example-publisher/run-1").exists()
    run_admitted.assert_not_called()

    def run_next_wake(_command, _entry, _loop_id, _env, receipt, **_kwargs):
        receipt.write_text('{"status":"pass","effect":0}\n', encoding="utf-8")
        receipt.chmod(0o600)
        return 0

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(state_root),
              "LIFE_MANAGER_RUN_ID": "run-2",
              "WAKE_ID": "wake-2",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/true"]),
          patch("runtime.loop.lm_loop_run.append_runtime_event",
                side_effect=lambda _path, event: events.append(event)),
          patch("runtime.loop.lm_loop_run._run_admitted", side_effect=run_next_wake)):
        assert lm_loop_run_main(["example-publisher", str(release)]) == 0

    assert events[-1]["status"] == "pass"
    assert events[-1]["effect_status"] == "not_applicable"
    assert events[-1]["run_id"] == "run-2"


def test_main_emits_structured_scratch_enospc_if_terminal_event_cannot_be_written(
        tmp_path, capsys):
    release = _write_prestart_lock_release(tmp_path)
    registry_path = release / "config/loop-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["loops"]["example-publisher"]["effect_class"] = "none"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    state_root = tmp_path / "state"

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(state_root),
              "LIFE_MANAGER_RUN_ID": "run-1",
              "WAKE_ID": "wake-1",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/true"]),
          patch("runtime.loop.lm_loop_run.reset_loop_scratch",
                side_effect=OSError(errno.ENOSPC, "No space left on device")),
          patch("runtime.loop.lm_loop_run.append_runtime_event",
                side_effect=OSError(errno.ENOSPC, "No space left on device")),
          patch("runtime.loop.lm_loop_run._run_admitted") as run_admitted):
        assert lm_loop_run_main(["example-publisher", str(release)]) == 78

    diagnostic = json.loads(capsys.readouterr().err)
    assert diagnostic["event"] == "runtime_event_write_failed"
    assert diagnostic["loop_id"] == diagnostic["job_id"] == diagnostic["owner_id"] == "example-publisher"
    assert diagnostic["run_id"] == "run-1"
    assert diagnostic["occurrence_id"] == "example-publisher:run-1"
    assert diagnostic["phase"] == "report"
    assert diagnostic["command"] == "bin/example-publisher"
    assert diagnostic["blocker"] == "scratch_enospc"
    assert diagnostic["effect_status"] == "not_applicable"
    assert diagnostic["effect"] == 0
    assert diagnostic["readback"] == 0
    assert diagnostic["operation_errno"] == errno.ENOSPC
    assert diagnostic["writer_errno"] == errno.ENOSPC
    assert diagnostic["retryable"] is True
    assert diagnostic["next_action"] == "retry_after_cleanup"
    run_admitted.assert_not_called()


def test_main_reports_sanitized_prestart_event_write_failure(tmp_path, capsys):
    release = _write_prestart_lock_release(tmp_path)
    private_events_path = tmp_path / "private" / "events.jsonl"
    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(tmp_path / "state"),
              "LIFE_MANAGER_RUN_ID": "run-1",
              "WAKE_ID": "wake-1",
              "LIFE_MANAGER_APPLY_LOCK_WAIT_SECONDS": "0",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock",
                side_effect=RuntimeError("production apply is already owned")),
          patch("runtime.loop.lm_loop_run.append_runtime_event",
                side_effect=PermissionError(
                    13, f"token=private {private_events_path}",
                    str(private_events_path))),
          patch("runtime.loop.lm_loop_run.build_loop_command") as build_command,
          patch("runtime.loop.lm_loop_run._run_admitted") as run_admitted):
        assert lm_loop_run_main(["example-publisher", str(release)]) == 78

    captured = capsys.readouterr()
    assert captured.out == ""
    diagnostic = json.loads(captured.err)
    assert diagnostic["event"] == "runtime_event_write_failed"
    assert diagnostic["loop_id"] == diagnostic["job_id"] == diagnostic["owner_id"] == "example-publisher"
    assert diagnostic["wake_id"] == "wake-1"
    assert diagnostic["run_id"] == "run-1"
    assert diagnostic["occurrence_id"] == "example-publisher:run-1"
    assert diagnostic["release_sha"] == "a" * 40
    assert diagnostic["blocker"] == "apply_lock_busy"
    assert diagnostic["effect_class"] == "publish"
    assert diagnostic["effect_status"] == "not_applicable"
    assert diagnostic["error_class"] == "apply_lock_busy"
    assert diagnostic["exit_code"] == 78
    assert diagnostic["retryable"] is True
    assert diagnostic["next_action"] == "retry_after_eligibility"
    assert diagnostic["loaded_argv_sha256"] is None
    assert diagnostic["provider_receipt_id"] is None
    assert diagnostic["official_readback_ref"] is None
    assert diagnostic["writer_error_type"] == "PermissionError"
    assert diagnostic["writer_errno"] == 13
    assert "/Users" not in captured.err
    assert "events.jsonl" not in captured.err
    assert "token=private" not in captured.err
    assert str(tmp_path) not in captured.err
    build_command.assert_not_called()
    run_admitted.assert_not_called()


def test_main_does_not_classify_body_runtime_error_as_lock_contention(tmp_path, capsys):
    release = _write_prestart_lock_release(tmp_path)
    event_path = tmp_path / "state/events.jsonl"
    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(tmp_path / "state"),
              "LIFE_MANAGER_RUN_ID": "run-1",
              "WAKE_ID": "wake-1",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command",
                side_effect=RuntimeError("production apply is already owned")),
          patch("runtime.loop.lm_loop_run.append_runtime_event") as append_event):
        assert lm_loop_run_main(["example-publisher", str(release)]) == 78

    assert not event_path.exists()
    assert "lm-loop-run: production apply is already owned" in capsys.readouterr().err
    append_event.assert_not_called()


def test_shared_runner_failure_emits_one_exact_recovery_intent(tmp_path):
    release = tmp_path / "release"
    (release / "config").mkdir(parents=True)
    (release / "config/loop-registry.json").write_text(json.dumps({
        "loops": {"example": {
            "label": "ai.anicca.example", "domain": "system",
            "entrypoint": "bin/example", "provider_route": "deterministic",
            "effect_class": "none", "state_root": str(tmp_path / "unused-state"),
        }},
    }), encoding="utf-8")
    (release / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}), encoding="utf-8")
    events = []

    def fail(_command, _entry, _loop_id, _env, receipt, **_kwargs):
        receipt.write_text('{"status":"pass","effect":0}\n', encoding="utf-8")
        receipt.chmod(0o600)
        return 1

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(tmp_path / "state"),
              "LIFE_MANAGER_RUN_ID": "run-1",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/false"]),
          patch("runtime.loop.lm_loop_run._run_admitted", side_effect=fail),
          patch("runtime.loop.lm_loop_run.append_runtime_event",
                side_effect=lambda _path, event: events.append(event)),
          patch("runtime.loop.lm_loop_run._enqueue_recovery_intent", return_value=True) as enqueue):
        assert lm_loop_run_main(["example", str(release)]) == 1

    enqueue.assert_called_once()
    queued_event = enqueue.call_args.args[1]
    assert queued_event["status"] == "fail"
    assert queued_event["owner_id"] == "example"
    assert queued_event["occurrence_id"] == "example:run-1"
    assert queued_event["release_sha"] == "a" * 40


def test_recovery_enqueue_is_replay_zero_and_fences_unknown_effect(tmp_path):
    queue = tmp_path / "recovery" / "intents.jsonl"
    event = build_runtime_event(
        loop_id="affiliate-loop", domain="growth", run_id="run-1",
        release_sha="a" * 40, provider="deterministic", profile_alias=None,
        effect_class="publish", succeeded=False, blocker="entrypoint_exit_1",
        exit_code=1,
    )
    with patch.dict(os.environ, {
        "LIFE_MANAGER_RECOVERY_INTENTS_PATH": str(queue),
        "LIFE_MANAGER_RUNTIME_NODE": shutil.which("node"),
        "PATH": "/usr/bin:/bin",
    }):
        assert _enqueue_recovery_intent(Path(__file__).resolve().parents[3], event, tmp_path)
        assert _enqueue_recovery_intent(Path(__file__).resolve().parents[3], event, tmp_path)
    rows = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["record_type"] == "recovery_intent"
    assert rows[0]["occurrence_id"] == "affiliate-loop:run-1"
    assert rows[0]["action"] == "hold_effect_unknown"
    assert rows[0]["retryable"] is False
    assert rows[0]["mutates_external_effect"] is False


def test_recovery_enqueue_skips_success_admission_and_paid_owned_jobs():
    failed = build_runtime_event(
        loop_id="example", domain="system", run_id="run-1", release_sha="a" * 40,
        provider="deterministic", profile_alias=None, effect_class="none",
        succeeded=False, blocker="entrypoint_exit_1", exit_code=1,
    )
    admitted = build_runtime_event(
        loop_id="example", domain="system", run_id="run-2", release_sha="a" * 40,
        provider="deterministic", profile_alias=None, effect_class="none",
        succeeded=False, deferred=True, blocker="host_admission_deferred:resource_capacity_busy",
        exit_code=75,
    )
    succeeded = build_runtime_event(
        loop_id="example", domain="system", run_id="run-3", release_sha="a" * 40,
        provider="deterministic", profile_alias=None, effect_class="none",
        succeeded=True, blocker=None, exit_code=0,
    )
    assert _should_enqueue_recovery_intent({"priority": "support"}, failed)
    assert not _should_enqueue_recovery_intent({"priority": "support"}, admitted)
    assert not _should_enqueue_recovery_intent({"priority": "support"}, succeeded)
    assert not _should_enqueue_recovery_intent({
        "priority": "critical_paid", "entrypoint": "skills/earn/gig/scripts/paid-direct-owner",
    }, failed)
    assert not _should_enqueue_recovery_intent({
        "priority": "support", "entrypoint": "runtime/loop/recovery-supervisor-cli.mjs",
    }, failed)


def test_admitted_child_receives_exact_host_occurrence_identity(tmp_path):
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({"occurrence_id": "connector:run-123"}))
    observed = {}

    def run_child(*_args, **kwargs):
        observed.update(kwargs["env"])
        kwargs["on_started"](4242)
        return 0

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")) as claim_admission,
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "browser",
            "admission_class": "revenue", "coalesce_queued_wakes": True,
        }, "connector", {}, tmp_path / "receipt",
            occurrence_id="connector:run-123") == 0
    claim_admission.assert_called_once_with(
        "browser", "connector", admission_class="revenue",
        coalesced_occurrence_id="connector:run-123")
    assert observed["LIFE_MANAGER_OCCURRENCE_ID"] == "connector:run-123"


def test_unknown_effect_identity_moves_from_scratch_to_private_state(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    sidecar = scratch / "effect-identity.jsonl"
    sidecar.write_text(json.dumps({
        "schema_version": 1,
        "kind": "life_manager_effect_identity",
        "runtime_run_id": "run-1",
        "occurrence_id": "life-manager-honne-ja:run-1",
        "loop_id": "life-manager-honne-ja",
        "job_id": "job-1",
        "effect_key": "marketing:video:honne-ai:tiktok:creative:" + "a" * 64 + ":" + "b" * 64,
        "product_id": "honne-ai",
        "format_id": "reelclaw",
        "form": "relationship-confession",
        "locale": "ja",
        "platform": "tiktok",
        "creative_id": "creative",
        "slot": "2026-07-30T12:30:00.000Z",
        "integration_ref": "integration://postiz/tiktok/honne-ai-ja",
        "account_id": "@honnevideo",
        "video_sha256": "a" * 64,
        "caption_sha256": "b" * 64,
    }) + "\n", encoding="utf-8")
    sidecar.chmod(0o600)
    state_root = tmp_path / "state"

    result = _persist_effect_identity(
        sidecar, state_root, "life-manager-honne-ja", "run-1",
        "life-manager-honne-ja:run-1",
    )

    assert result.status == "persisted"
    assert result.ref == "lm-effect://life-manager-honne-ja/run-1/identity.jsonl"
    persisted = state_root / "effect-identities" / "run-1.jsonl"
    assert json.loads(persisted.read_text(encoding="utf-8"))["job_id"] == "job-1"
    assert persisted.stat().st_mode & 0o777 == 0o600


def test_unknown_effect_identity_missing_sidecar_reports_not_written(tmp_path):
    state_root = tmp_path / "state"
    missing = tmp_path / "absent.jsonl"
    result = _persist_effect_identity(
        missing, state_root, "life-manager-honne-ja", "run-0",
        "life-manager-honne-ja:run-0",
    )
    assert result.status == "not_written"
    assert result.ref is None


def test_unknown_effect_identity_rejects_symlink_and_malformed_sidecars(tmp_path):
    state_root = tmp_path / "state"
    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"job_id":"outside"}\n', encoding="utf-8")
    outside.chmod(0o600)
    symlink = tmp_path / "symlink.jsonl"
    symlink.symlink_to(outside)
    result = _persist_effect_identity(
        symlink, state_root, "life-manager-honne-ja", "run-1",
        "life-manager-honne-ja:run-1",
    )
    assert result.status == "rejected"
    assert result.ref is None
    assert not (state_root / "effect-identities" / "run-1.jsonl").exists()

    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text('{"job_id":"missing-schema"}\n', encoding="utf-8")
    malformed.chmod(0o600)
    result = _persist_effect_identity(
        malformed, state_root, "life-manager-honne-ja", "run-2",
        "life-manager-honne-ja:run-2",
    )
    assert result.status == "rejected"
    assert result.ref is None


def test_unknown_effect_identity_rejects_cross_field_mismatch_and_destination_symlink(tmp_path):
    def row(**overrides):
        value = {
            "schema_version": 1,
            "kind": "life_manager_effect_identity",
            "runtime_run_id": "run-3",
            "occurrence_id": "life-manager-honne-ja:run-3",
            "loop_id": "life-manager-honne-ja",
            "job_id": "marketing-video-publication:job-3",
            "effect_key": "marketing:video:honne-ai:tiktok:creative:" + "a" * 64 + ":" + "b" * 64,
            "product_id": "honne-ai",
            "format_id": "reelclaw",
            "form": "relationship-confession",
            "locale": "ja",
            "platform": "tiktok",
            "creative_id": "creative",
            "slot": "2026-07-30T12:30:00.000Z",
            "integration_ref": "integration://postiz/tiktok/honne-ai-ja",
            "account_id": "@honnevideo",
            "video_sha256": "a" * 64,
            "caption_sha256": "b" * 64,
        }
        value.update(overrides)
        return value

    state_root = tmp_path / "state"
    mismatch = tmp_path / "mismatch.jsonl"
    mismatch.write_text(json.dumps(row(video_sha256="c" * 64)) + "\n", encoding="utf-8")
    mismatch.chmod(0o600)
    result = _persist_effect_identity(
        mismatch, state_root, "life-manager-honne-ja", "run-3",
        "life-manager-honne-ja:run-3",
    )
    assert result.status == "rejected"
    assert result.ref is None

    mismatch.write_text(json.dumps(row(integration_ref="integration://postiz/instagram/honne-ai-ja")) + "\n", encoding="utf-8")
    mismatch.chmod(0o600)
    result = _persist_effect_identity(
        mismatch, state_root, "life-manager-honne-ja", "run-3",
        "life-manager-honne-ja:run-3",
    )
    assert result.status == "rejected"
    assert result.ref is None

    state_root.mkdir()
    destination = state_root / "effect-identities"
    outside = tmp_path / "outside-identities"
    outside.mkdir()
    destination.symlink_to(outside, target_is_directory=True)
    valid = tmp_path / "valid.jsonl"
    valid.write_text(json.dumps(row()) + "\n", encoding="utf-8")
    valid.chmod(0o600)
    result = _persist_effect_identity(
        valid, state_root, "life-manager-honne-ja", "run-3",
        "life-manager-honne-ja:run-3",
    )
    assert result.status == "rejected"
    assert result.ref is None
    assert not (outside / "run-3.jsonl").exists()

    media = [f"{chr(97 + i)}" * 64 for i in range(6)]
    media_order = hashlib.sha256(
        json.dumps(media, ensure_ascii=False, separators=(",", ":")).encode(),
    ).hexdigest()
    carousel = row(
        product_id="anicca-ios",
        platform="instagram",
        effect_key="marketing:carousel:anicca-ios:creative:" + "d" * 64 + ":" + media_order + ":" + "e" * 64,
        integration_ref="integration://postiz/instagram/anicca-carousel",
        account_id="@anicca.carousel",
        video_sha256=None,
        caption_sha256="e" * 64,
        pack_sha256="d" * 64,
        media_sha256=media,
        media_order_sha256=media_order,
    )
    carousel_path = tmp_path / "carousel.jsonl"
    carousel_path.write_text(json.dumps(carousel) + "\n", encoding="utf-8")
    carousel_path.chmod(0o600)
    result = _persist_effect_identity(
        carousel_path, tmp_path / "carousel-state", "life-manager-honne-ja", "run-3",
        "life-manager-honne-ja:run-3",
    )
    assert result.status == "persisted"
    assert result.ref == "lm-effect://life-manager-honne-ja/run-3/identity.jsonl"
    carousel["product_id"] = "anicca-ios"
    carousel["effect_key"] = "marketing:carousel:anicca-ios:creative:" + "d" * 64 + ":" + media_order + ":" + "e" * 64
    carousel["media_sha256"] = None
    carousel_path.write_text(json.dumps(carousel) + "\n", encoding="utf-8")
    carousel_path.chmod(0o600)
    result = _persist_effect_identity(
        carousel_path, tmp_path / "carousel-state", "life-manager-honne-ja", "run-3",
        "life-manager-honne-ja:run-3",
    )
    assert result.status == "rejected"
    assert result.ref is None


def test_noncoalesced_child_uses_claimed_older_occurrence(tmp_path):
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({"occurrence_id": "example:older"}))
    observed = {}
    claimed = []

    def run_child(*_args, **kwargs):
        observed.update(kwargs["env"])
        kwargs["on_started"](4242)
        return 0

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "agent",
            "admission_class": "revenue",
        }, "example", {}, tmp_path / "receipt", occurrence_id="example:new",
            on_claimed=claimed.append) == 0
    assert observed["LIFE_MANAGER_OCCURRENCE_ID"] == "example:older"
    assert claimed == ["example:older"]


def test_v1_protocol_coexists_with_live_legacy_owner_without_sqlite(tmp_path, monkeypatch):
    root = tmp_path / "admission"
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(root))
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_FINITE_RUNS", "1")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_AGENT_RUNS", "1")
    legacy, reason = admission.try_acquire(
        "agent", "legacy", retain_ticket=False,
    )
    assert legacy is not None and reason == "acquired"
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    receipt = tmp_path / "receipt"
    try:
        with (patch("runtime.loop.lm_loop_run.durable_protocol_version", return_value=1),
              patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
              patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
            assert _run_admitted(
                ["/bin/true"], entry, "candidate", {}, receipt,
            ) == 75
        run.assert_not_called()
        assert json.loads(receipt.read_text())["reason"] == "resource_capacity_busy"
        assert not (root / "admission-v2.sqlite3").exists()
    finally:
        admission.release(legacy)


def test_busy_resource_admission_defers_without_waiting_or_starting_child(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "capacity_busy")) as acquire,
          patch("runtime.loop.lm_loop_run.reserve_available_resource",
                return_value=[]) as reserve,
          patch("runtime.loop.lm_loop_run._dispatch_reserved") as dispatch,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        started = time.monotonic()
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75
    assert time.monotonic() - started < 0.5
    enqueue.assert_called_once_with("agent", "example", admission_class="borrow")
    acquire.assert_called_once_with("agent", "example", admission_class="borrow")
    reserve.assert_called_once_with(); dispatch.assert_called_once_with([])
    run.assert_not_called()
    assert json.loads(receipt.read_text()) == {
        "effect": 0,
        "reason": "resource_capacity_busy",
        "status": "deferred",
    }


def test_all_coconala_lanes_enter_revenue_admission(tmp_path):
    registry = json.loads(
        (Path(__file__).parents[3] / "config/loop-registry.json").read_text()
    )["loops"]
    loop_ids = (
        "hf-gig-apply-direct",
        "hf-gig-reply-detector",
        "hf-gig-paid-direct",
        "hf-gig-storefront-direct",
    )
    assert all(registry[loop_id].get("admission_class") == "revenue"
               for loop_id in loop_ids)
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "capacity_busy")) as claim,
          patch("runtime.loop.lm_loop_run.reserve_available_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        for loop_id in loop_ids:
            assert _run_admitted(
                ["/bin/true"], registry[loop_id], loop_id, {},
                tmp_path / f"{loop_id}.json",
            ) == 75

    expected_enqueue = []
    for loop_id in loop_ids:
        kwargs = {
            "admission_class": "revenue",
            "priority": registry[loop_id]["priority"],
        }
        if registry[loop_id].get("effect_class") == "none":
            kwargs["allow_no_effect_recovery"] = True
        if registry[loop_id].get("coalesce_queued_wakes") is True:
            kwargs["coalesce_reserved"] = True
        expected_enqueue.append(call("agent", loop_id, **kwargs))
    assert enqueue.call_args_list == expected_enqueue
    assert claim.call_args_list == [
        call("agent", loop_id, admission_class="revenue") for loop_id in loop_ids
    ]
    run.assert_not_called()


def test_lancers_effect_lanes_enter_revenue_admission():
    registry = json.loads(
        (Path(__file__).parents[3] / "config/loop-registry.json").read_text()
    )["loops"]
    loop_ids = (
        "lancers-revenue-application",
        "lancers-revenue-negotiate",
        "lancers-revenue-paid",
        "lancers-revenue-storefront",
    )
    assert all(registry[loop_id].get("admission_class") == "revenue"
               for loop_id in loop_ids)


def test_all_marketplace_revenue_lanes_use_agent_revenue_admission():
    registry = json.loads(
        (Path(__file__).parents[3] / "config/loop-registry.json").read_text()
    )["loops"]
    loop_ids = (
        "crowdworks-revenue-application",
        "crowdworks-revenue-reply",
        "crowdworks-revenue-paid",
        "lancers-revenue-application",
        "lancers-revenue-negotiate",
        "lancers-revenue-paid",
        "lancers-revenue-storefront",
        "mercor-revenue-application",
        "mercor-revenue-reply",
        "mercor-revenue-paid",
    )
    assert all(registry[loop_id].get("resource_class") == "agent"
               for loop_id in loop_ids)
    assert all(registry[loop_id].get("admission_class") == "revenue"
               for loop_id in loop_ids)


def test_unavailable_admission_becomes_deferred_receipt(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                side_effect=RuntimeError),
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75
    run.assert_not_called()
    assert json.loads(receipt.read_text())["reason"] == "resource_admission_unavailable"


def test_invalid_memory_threshold_fails_closed(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    for value in ("0", "-1", "101"):
        with (patch.dict(os.environ, {"LIFE_MANAGER_MIN_MEMORY_FREE_PERCENT": value}),
              patch("runtime.loop.lm_loop_run.enqueue_durable_resource") as acquire,
              patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
            assert _run_admitted(["/bin/true"], entry, "example", {}, tmp_path / value) == 64
        acquire.assert_not_called(); run.assert_not_called()


def test_entrypoint_blocks_signal_until_handler_owns_child(monkeypatch):
    class Process:
        pid = 43210
        def poll(self): return None
        def wait(self, timeout=None): return 0

    def launch(*_args, **_kwargs):
        os.kill(os.getpid(), signal.SIGTERM)
        return Process()

    monkeypatch.setattr("runtime.loop.lm_loop_run.subprocess.Popen", launch)
    with patch("runtime.loop.lm_loop_run.os.killpg") as killpg:
        assert _run_entrypoint(["/bin/true"], timeout_seconds=1) == 75
    killpg.assert_called_once_with(43210, signal.SIGTERM)


def test_entrypoint_treats_permission_denied_signal_forward_as_already_exited(monkeypatch):
    class Process:
        pid = 43210
        def poll(self): return None
        def wait(self, timeout=None): return 0

    def launch(*_args, **_kwargs):
        os.kill(os.getpid(), signal.SIGTERM)
        return Process()

    monkeypatch.setattr("runtime.loop.lm_loop_run.subprocess.Popen", launch)
    with patch("runtime.loop.lm_loop_run.os.killpg", side_effect=PermissionError):
        assert _run_entrypoint(["/bin/true"], timeout_seconds=1) == 75


def test_cancelled_before_atomic_handoff_never_starts_child():
    with patch("runtime.loop.lm_loop_run.subprocess.Popen") as launch:
        assert _run_entrypoint(["/bin/true"], cancelled=lambda: True) == 75
    launch.assert_not_called()


def test_signal_during_claim_retry_stops_before_effect_child(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "effect_class": "publish",
    }

    def interrupt_claim(*_args, **_kwargs):
        os.kill(os.getpid(), signal.SIGTERM)
        return None, "control_busy"

    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                side_effect=interrupt_claim) as claim,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75

    assert json.loads(receipt.read_text())["reason"] == "resource_admission_interrupted"
    claim.assert_called_once()
    sleep.assert_not_called()
    run.assert_not_called()


def test_signal_after_pass_receipt_cannot_start_effect_child(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    claim = tmp_path / "claim"
    original_write = __import__("runtime.loop.lm_loop_run", fromlist=["_atomic_json"])._atomic_json

    def write_then_stop(path, value):
        original_write(path, value)
        if value.get("reason") == "resource_slot_acquired":
            os.kill(os.getpid(), signal.SIGTERM)

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]),
          patch("runtime.loop.lm_loop_run._atomic_json", side_effect=write_then_stop),
          patch("runtime.loop.lm_loop_run.subprocess.Popen") as launch):
        assert _run_admitted(["/bin/true"], entry, "example", {}, tmp_path / "receipt") == 75
    launch.assert_not_called()


def test_signal_during_memory_probe_defers_before_child(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}

    def interrupted_probe():
        os.kill(os.getpid(), signal.SIGTERM)
        return 50

    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", side_effect=interrupted_probe),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource") as acquire,
          patch("runtime.loop.lm_loop_run.subprocess.Popen") as launch):
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75
    enqueue.assert_called_once(); acquire.assert_not_called(); launch.assert_not_called()
    assert json.loads(receipt.read_text())["reason"] == "resource_admission_interrupted"


def test_memory_deferral_preserves_queue_and_releases_reservation(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")),
          patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=None),
          patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.claim_durable_resource") as claim):
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75
    defer.assert_called_once_with("example")
    claim.assert_not_called()
    assert json.loads(receipt.read_text())["reason"] == "memory_headroom_unavailable"


def test_low_or_unknown_numeric_disk_headroom_does_not_defer_finite_owner(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner", "effect_class": "application"}
    for available in [0, None]:
        receipt = tmp_path / "host-admission.json"
        with (patch("runtime.loop.lm_loop_run.disk_free_bytes", return_value=available, create=True) as disk,
              patch("runtime.loop.lm_loop_run._producer_gate", return_value=None, create=True) as gate,
              patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
              patch("runtime.loop.lm_loop_run.enqueue_durable_resource", return_value=(tmp_path / "ticket", "ready")) as enqueue,
              patch("runtime.loop.lm_loop_run.claim_durable_resource", return_value=(tmp_path / "claim", "acquired")) as claim,
              patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
              patch("runtime.loop.lm_loop_run.release_and_reserve_resource", return_value=[]) as release,
              patch("runtime.loop.lm_loop_run._run_entrypoint_with_stderr_capture", return_value=(0,b"")) as child):
            assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 0
        enqueue.assert_called_once(); claim.assert_called_once(); child.assert_called_once()
        gate.assert_has_calls([call(), call()]); disk.assert_not_called()
        defer.assert_not_called(); release.assert_called_once()
        result = json.loads(receipt.read_text())
        assert result["status"] == "pass" and result["effect"] == 0


def test_explicit_operator_disk_stop_still_defers_before_queue_and_provider_child(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner", "effect_class": "application"}
    receipt = tmp_path / "host-admission.json"
    stop = tmp_path / "disk-writers.stop"
    with (patch("runtime.loop.lm_loop_run.disk_free_bytes", return_value=3*1024**3, create=True) as disk,
          patch("runtime.loop.lm_loop_run._producer_gate", return_value=("disk_writers_stop", stop), create=True) as gate,
          patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource", return_value=(tmp_path / "ticket", "ready")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource", return_value=(tmp_path / "claim", "acquired")) as claim,
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource", return_value=[]) as release,
          patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run._run_entrypoint_with_stderr_capture", return_value=(0,b"")) as child):
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75
    gate.assert_called_once(); disk.assert_not_called()
    enqueue.assert_not_called(); claim.assert_not_called(); release.assert_not_called(); child.assert_not_called()
    defer.assert_called_once_with("example")
    result = json.loads(receipt.read_text())
    assert result["status"] == "deferred" and result["effect"] == 0
    assert result["reason"] == "disk_writers_stop" and result["phase"] == "pre_enqueue"
    assert result["flag_path"] == str(stop)


def test_healthy_disk_boundary_keeps_finite_dispatch_without_numeric_probe(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner", "effect_class": "application"}
    receipt = tmp_path / "host-admission.json"
    with (patch("runtime.loop.lm_loop_run.disk_free_bytes", return_value=2*1024**3, create=True) as disk,
          patch("runtime.loop.lm_loop_run._producer_gate", return_value=None, create=True) as gate,
          patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource", return_value=(tmp_path / "ticket","ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource", return_value=(tmp_path / "claim","acquired")),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",return_value=[]),
          patch("runtime.loop.lm_loop_run._run_entrypoint_with_stderr_capture",return_value=(0,b"")) as child):
        assert _run_admitted(["/bin/true"],entry,"example",{},receipt)==0
    child.assert_called_once()
    gate.assert_has_calls([call(), call()]); disk.assert_not_called()


def test_numeric_disk_drop_after_claim_does_not_requeue_finite_work(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner", "effect_class": "application"}
    receipt = tmp_path / "host-admission.json"
    claim = tmp_path / "claim"
    with (patch("runtime.loop.lm_loop_run.disk_free_bytes", side_effect=[3*1024**3,0], create=True) as disk,
          patch("runtime.loop.lm_loop_run._producer_gate", return_value=None, create=True) as gate,
          patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource", return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource", return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource", return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved") as dispatch,
          patch("runtime.loop.lm_loop_run._run_entrypoint_with_stderr_capture", return_value=(0,b"")) as child):
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 0
    child.assert_called_once(); dispatch.assert_not_called()
    gate.assert_has_calls([call(), call()]); disk.assert_not_called()
    release.assert_called_once()
    result=json.loads(receipt.read_text())
    assert result["status"] == "pass" and result["effect"] == 0


def test_control_and_continuous_owner_bypass_disk_preflight(tmp_path):
    control_entry = {"cadence": {"start_interval_seconds": 60},
                     "provider_route": "deterministic", "effect_class": "none"}
    continuous_entry = {"cadence": {"keep_alive": True},
                        "provider_route": "shared-agent-runner", "effect_class": "application"}
    with (patch("runtime.host.disk_admission.shutil.disk_usage",
                side_effect=AssertionError("exempt owner must bypass disk preflight")) as disk,
          patch("runtime.loop.lm_loop_run.clear_no_effect_unknown_resource"),
          patch("runtime.loop.lm_loop_run.reserve_available_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0) as run_child):
        assert _run_admitted(["/bin/true"], control_entry, "life-manager-disk-cleanup",
                             {}, tmp_path / "control.json") == 0
        assert _run_admitted(["/bin/true"], continuous_entry, "continuous-owner",
                             {}, tmp_path / "continuous.json") == 0

    disk.assert_not_called()
    assert run_child.call_count == 2


def test_post_claim_memory_deferral_requeues_without_dispatch(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    claim = tmp_path / "claim"
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.memory_free_percent", side_effect=[50, 10]),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved") as dispatch,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "example", {}, tmp_path / "receipt") == 75
    release.assert_called_once_with(claim, requeue=True, reserve=False)
    dispatch.assert_not_called(); run.assert_not_called()


def test_terminal_event_precedes_requeue_when_memory_drops_after_claim(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner", "effect_class": "application"}
    claim = tmp_path / "claim"
    events = []

    def persist_terminal(return_code, occurrence_id, stderr_tail):
        events.append(("terminal", return_code, occurrence_id, stderr_tail))
        return True

    def release(_claim, **options):
        events.append(("release", options))
        return []

    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.memory_free_percent", side_effect=[50, 10]),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                side_effect=release),
          patch("runtime.loop.lm_loop_run._run_entrypoint_with_stderr_capture") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "example", {}, tmp_path / "receipt",
            on_terminal_event=persist_terminal,
        ) == 75

    assert events[0] == ("terminal", 75, None, b"")
    assert events[1] == ("release", {"requeue": True, "reserve": False})
    run.assert_not_called()


def test_dispatch_reserved_kicks_only_current_loaded_idle_label(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    (current / "bin").mkdir(); agents.mkdir()
    safe = current / "bin/launchctl-safe"; safe.write_text("safe")
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row}}))
    plist = {"ProgramArguments": [str(current.resolve() / "bin/lm-loop-run"),
                                   "example", str(current.resolve())]}
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps(plist))
    outputs = [
        subprocess.CompletedProcess(
            [], 0, "arguments = {\n" + "\n".join(plist["ProgramArguments"])
            + "\n}\nstate = not running",
        ),
        subprocess.CompletedProcess([], 0, ""),
        subprocess.CompletedProcess([], 0, "state = running"),
    ]
    with patch("runtime.loop.lm_loop_run.subprocess.run", side_effect=outputs) as run:
        assert _dispatch_reserved(["example"], current=current, agents_dir=agents) == ["example"]
    commands = [call.args[0][1] for call in run.call_args_list]
    assert commands == ["print", "kickstart", "print"]
    assert "-k" not in run.call_args_list[1].args[0]


def test_dispatch_reserved_cancels_missing_registry_owner(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {},
    }))

    with (patch("runtime.loop.lm_loop_run.cancel_durable_resource") as cancel,
          patch("runtime.loop.lm_loop_run.subprocess.run") as run):
        assert _dispatch_reserved(
            ["retired"], current=current, agents_dir=agents,
        ) == []

    cancel.assert_called_once_with("retired")
    run.assert_not_called()


def test_dispatch_scans_past_sixteen_stale_releases_to_healthy_owner(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    loop_ids = [f"stale-{index}" for index in range(17)] + ["healthy"]
    rows = {}
    for loop_id in loop_ids:
        label = f"ai.anicca.{loop_id}"
        rows[loop_id] = {
            "label": label, "domain": "earn", "entrypoint": "bin/example",
            "cadence": {"start_interval_seconds": 300}, "effect_class": "none",
            "state_root": f"~/.local/state/life-manager/{loop_id}",
            "log_root": f"~/.local/state/life-manager/{loop_id}/logs",
            "cleanup": {"max_runs": 10, "max_age_days": 7},
            "provider_route": "deterministic",
        }
        args = ([str(current.resolve() / "bin/lm-loop-run"), loop_id, str(current.resolve())]
                if loop_id == "healthy" else ["/old/bin/lm-loop-run", loop_id, "/old"])
        (agents / f"{label}.plist").write_bytes(plistlib.dumps({"ProgramArguments": args}))
    (current / "config/loop-registry.json").write_text(json.dumps({"schema_version": 2, "loops": rows}))

    def launchctl_result(args, **_kwargs):
        if args[1] == "kickstart":
            return subprocess.CompletedProcess(args, 0, "")
        expected = [str(current.resolve() / "bin/lm-loop-run"), "healthy", str(current.resolve())]
        return subprocess.CompletedProcess(
            args, 0, "arguments = {\n" + "\n".join(expected) + "\n}\nstate = waiting")

    with (patch("runtime.loop.lm_loop_run.defer_durable_resource", return_value=True),
          patch("runtime.loop.lm_loop_run.reserve_available_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run.subprocess.run", side_effect=launchctl_result)):
        assert _dispatch_reserved(loop_ids, current=current, agents_dir=agents) == ["healthy"]


def test_dispatch_reserved_tolerates_missing_owner_cancel_failure(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {},
    }))

    for error in (OSError("admission unavailable"),
                  sqlite3.OperationalError("database is locked")):
        with (patch("runtime.loop.lm_loop_run.cancel_durable_resource",
                    side_effect=error) as cancel,
              patch("runtime.loop.lm_loop_run.subprocess.run") as run):
            assert _dispatch_reserved(
                ["retired"], current=current, agents_dir=agents,
            ) == []

        cancel.assert_called_once_with("retired")
        run.assert_not_called()


def test_dispatch_reserved_rejects_stale_loaded_release_prefix(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))
    expected = [str(current.resolve() / "bin/lm-loop-run"),
                "example", str(current.resolve())]
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": expected,
    }))
    stale = [*expected[:-1], f"{current.resolve()}-stale"]
    observed = subprocess.CompletedProcess(
        [], 0, "arguments = {\n" + "\n".join(stale) + "\n}\nstate = not running",
    )

    with (patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run", return_value=observed) as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    defer.assert_called_once_with("example", cooldown_seconds=60)
    assert run.call_count == 1


def test_dispatch_drift_defers_unverified_loaded_release(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "none",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": ["/old/bin/lm-loop-run", "example", "/old"],
    }))
    with (patch("runtime.loop.lm_loop_run.apply_live", create=True,
                side_effect=AssertionError("queued owner rebound")),
          patch("runtime.loop.lm_loop_run.defer_durable_resource", return_value=False) as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run") as run):
        assert _dispatch_reserved(["example"], current=current, agents_dir=agents) == []
    defer.assert_called_once_with("example", cooldown_seconds=60)
    run.assert_not_called()


def test_dispatch_kicks_queued_owner_on_valid_loaded_main_release(tmp_path):
    releases = tmp_path / "releases"
    current = releases / "new"
    old = releases / "old"
    agents = tmp_path / "agents"
    for release in (current, old):
        (release / "config").mkdir(parents=True)
        (release / "bin").mkdir()
        (release / "bin/lm-loop-run").write_text("#!/bin/sh\n")
        (release / "config/runtime-capabilities.json").write_text(
            json.dumps({"resource_admission": 2}))
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "system", "entrypoint": "bin/lm-loop-run",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "none",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic", "resource_class": "browser",
    }
    for release in (current, old):
        (release / "config/loop-registry.json").write_text(json.dumps({
            "schema_version": 2, "loops": {"example": row},
        }))
        (release / "RELEASE.json").write_text(json.dumps({
            "sha": "a" * 40, "provenance": "ancestor-of-origin-main",
            "release_paths": "ALL",
        }))
    old_args = [str(old / "bin/lm-loop-run"), "example", str(old)]
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": old_args,
    }))
    idle = subprocess.CompletedProcess(
        [], 0, "arguments = {\n" + "\n".join(old_args) + "\n}\nstate = not running",
    )
    running = subprocess.CompletedProcess(
        [], 0, "arguments = {\n" + "\n".join(old_args) + "\n}\nstate = running",
    )
    with (patch("runtime.loop.lm_loop_run.apply_live", create=True,
                side_effect=AssertionError("queued owner rebound")),
          patch("runtime.loop.lm_loop_run.subprocess.run",
                side_effect=[idle, subprocess.CompletedProcess([], 0, ""), running]) as run):
        assert _dispatch_reserved(["example"], current=current, agents_dir=agents) == ["example"]
    assert [item.args[0][1] for item in run.call_args_list] == [
        "print", "kickstart", "print",
    ]


def test_dispatch_release_drift_preserves_real_sqlite_waiter(tmp_path, monkeypatch):
    admission_root = tmp_path / "admission"
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(admission_root))
    admission.activate_durable_v2()
    admission.enqueue_durable("deterministic", "example", admission_class="borrow")
    assert admission.reserve_available() == ["example"]

    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": ["/old-release/bin/lm-loop-run", "example", "/old-release"],
    }))

    assert _dispatch_reserved(["example"], current=current, agents_dir=agents) == []
    with sqlite3.connect(admission_root / "admission-v2.sqlite3") as connection:
        assert connection.execute(
            "SELECT owner_id FROM queue WHERE owner_id='example'"
        ).fetchone() == ("example",)
        assert connection.execute(
            "SELECT owner_id FROM reservations WHERE owner_id='example'"
        ).fetchone() is None


def test_dispatch_drift_immediately_hands_free_slot_to_healthy_follower(
        tmp_path, monkeypatch):
    admission_root = tmp_path / "admission"
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(admission_root))
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_FINITE_RUNS", "1")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_DETERMINISTIC_RUNS", "1")
    admission.activate_durable_v2()
    admission.enqueue_durable("deterministic", "drifted", admission_class="borrow")
    admission.enqueue_durable("deterministic", "healthy", admission_class="borrow")
    assert admission.reserve_available() == ["drifted"]

    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    rows = {}
    for loop_id in ("drifted", "healthy"):
        rows[loop_id] = {
            "label": f"ai.anicca.{loop_id}", "domain": "earn",
            "entrypoint": "bin/example", "cadence": {"start_interval_seconds": 300},
            "effect_class": "none", "state_root": f"~/.local/state/life-manager/{loop_id}",
            "log_root": f"~/.local/state/life-manager/{loop_id}/logs",
            "cleanup": {"max_runs": 10, "max_age_days": 7},
            "provider_route": "deterministic",
        }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": rows,
    }))
    healthy_args = [str(current.resolve() / "bin/lm-loop-run"),
                    "healthy", str(current.resolve())]
    (agents / "ai.anicca.drifted.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": ["/old/bin/lm-loop-run", "drifted", "/old"],
    }))
    (agents / "ai.anicca.healthy.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": healthy_args,
    }))

    def launchctl_result(args, **_kwargs):
        if args[1] == "kickstart":
            return subprocess.CompletedProcess(args, 0, "")
        detail = "arguments = {\n" + "\n".join(healthy_args) + "\n}\nstate = waiting"
        return subprocess.CompletedProcess(args, 0, detail)

    with patch("runtime.loop.lm_loop_run.subprocess.run", side_effect=launchctl_result):
        started = _dispatch_reserved(["drifted"], current=current, agents_dir=agents)
    assert started == ["healthy"]
    with sqlite3.connect(admission_root / "admission-v2.sqlite3") as connection:
        assert connection.execute(
            "SELECT owner_id FROM queue WHERE owner_id='drifted'"
        ).fetchone() == ("drifted",)


def test_dispatch_reserved_keeps_running_owner_reservation(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))
    expected = [str(current.resolve() / "bin/lm-loop-run"),
                "example", str(current.resolve())]
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": expected,
    }))
    observed = subprocess.CompletedProcess(
        [], 0, "arguments = {\n" + "\n".join(expected) + "\n}\nstate = running",
    )

    with (patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run", return_value=observed) as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    defer.assert_not_called()
    assert run.call_count == 1


def test_dispatch_reserved_rejects_loaded_output_without_explicit_idle_state(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))
    expected = [str(current.resolve() / "bin/lm-loop-run"),
                "example", str(current.resolve())]
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": expected,
    }))
    observed = subprocess.CompletedProcess(
        [], 0, "arguments = {\n" + "\n".join(expected) + "\n}\nruns = 1",
    )

    with (patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run", return_value=observed) as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    defer.assert_called_once_with("example", cooldown_seconds=60)
    assert run.call_count == 1


def test_dispatch_reserved_rejects_noncanonical_installed_argv(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))
    prefixed = [sys.executable, "-m", "runtime.loop.lm_loop_run",
                "example", str(current.resolve())]
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": prefixed,
    }))

    with (patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run") as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    defer.assert_called_once_with("example", cooldown_seconds=60)
    run.assert_not_called()


def test_dispatch_reserved_defers_owner_with_missing_plist(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))

    with (patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run") as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    defer.assert_called_once_with("example", cooldown_seconds=60)
    run.assert_not_called()


def test_real_child_receives_sigterm_after_atomic_handoff(tmp_path):
    ready = tmp_path / "ready"
    child = (
        "import pathlib,signal,time,sys; "
        "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
        f"pathlib.Path({str(ready)!r}).write_text('ready'); time.sleep(60)"
    )
    runner = (
        "import sys; from runtime.loop.lm_loop_run import _run_entrypoint; "
        f"sys.exit(_run_entrypoint([sys.executable, '-c', {child!r}], timeout_seconds=60))"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", runner], cwd=str(Path(__file__).parents[3]),
        env={**os.environ, "PYTHONPATH": "."})
    deadline = time.monotonic() + 10
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(.01)
    assert ready.exists()
    os.kill(process.pid, signal.SIGTERM)
    assert process.wait(timeout=5) == 0


def test_wrapper_sigkill_keeps_effect_child_claim_live(tmp_path, monkeypatch):
    admission_root = tmp_path / "admission"
    ready = tmp_path / "ready"
    receipt = tmp_path / "receipt.json"
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(admission_root))
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_FINITE_RUNS", "1")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_AGENT_RUNS", "1")
    child = (
        "import pathlib,signal,time,sys; "
        "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
        f"pathlib.Path({str(ready)!r}).write_text('ready'); time.sleep(60)"
    )
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "shared-agent-runner",
    }
    runner = (
        "import os,pathlib,sys; "
        "from runtime.loop import lm_loop_run; "
        "from runtime.loop.lm_loop_run import _run_admitted; "
        "lm_loop_run.disk_free_bytes=lambda _path: 3*1024**3; "
        f"entry={entry!r}; command=[sys.executable,'-c',{child!r}]; "
        f"sys.exit(_run_admitted(command,entry,'example',os.environ.copy(),"
        f"pathlib.Path({str(receipt)!r})))"
    )
    wrapper = subprocess.Popen(
        [sys.executable, "-c", runner], cwd=str(Path(__file__).parents[3]),
        env={**os.environ, "PYTHONPATH": "."},
    )
    child_pid = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            rows = list((admission_root / "owners").glob("*.json"))
            if rows and ready.exists():
                row = json.loads(rows[0].read_text())
                if row.get("phase") == "running":
                    child_pid = row["pid"]
                    break
            time.sleep(.01)
        assert child_pid is not None

        os.kill(wrapper.pid, signal.SIGKILL)
        assert wrapper.wait(timeout=5) == -signal.SIGKILL
        admission = __import__(
            "runtime.host.resource_admission", fromlist=["process_start"],
        )
        assert admission.process_start(child_pid)

        queued, reason = admission.enqueue_durable("agent", "example")
        assert queued is None and reason == "owner_busy"
        with sqlite3.connect(admission_root / "admission-v2.sqlite3") as connection:
            assert connection.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 0
        duplicate, reason = admission.claim_durable("agent", "example")
        assert duplicate is None and reason == "ticket_missing"
        os.killpg(child_pid, signal.SIGTERM)
        deadline = time.monotonic() + 5
        while admission.process_start(child_pid) and time.monotonic() < deadline:
            time.sleep(.01)
        assert not admission.process_start(child_pid)
        assert admission.reserve_available() == []
        with sqlite3.connect(admission_root / "admission-v2.sqlite3") as connection:
            assert connection.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 0
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
            wrapper.wait(timeout=5)
        if child_pid is not None:
            try:
                os.killpg(child_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def test_heartbeat_loop_tolerates_transient_control_busy(tmp_path, monkeypatch):
    stopped = threading.Event()
    failed = threading.Event()
    results = iter([RuntimeError("control_busy"), RuntimeError("control_busy"), True])

    def heartbeat(_claim):
        value = next(results)
        if isinstance(value, Exception):
            raise value
        stopped.set()
        return value

    monkeypatch.setattr("runtime.loop.lm_loop_run.HEARTBEAT_INTERVAL_SECONDS", 0.01)
    with patch("runtime.loop.lm_loop_run.heartbeat_durable_resource", side_effect=heartbeat):
        _heartbeat_loop(tmp_path / "claim", stopped, failed)
    assert not failed.is_set()


def test_heartbeat_loop_fails_when_busy_outlasts_tolerance(tmp_path, monkeypatch):
    stopped = threading.Event()
    failed = threading.Event()
    monkeypatch.setattr("runtime.loop.lm_loop_run.HEARTBEAT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr("runtime.loop.lm_loop_run.HEARTBEAT_BUSY_TOLERANCE_SECONDS", 0.05)
    with patch("runtime.loop.lm_loop_run.heartbeat_durable_resource",
               side_effect=RuntimeError("control_busy")):
        _heartbeat_loop(tmp_path / "claim", stopped, failed)
    assert failed.is_set()


def test_heartbeat_loop_fails_immediately_when_ownership_is_lost(tmp_path, monkeypatch):
    stopped = threading.Event()
    failed = threading.Event()
    monkeypatch.setattr("runtime.loop.lm_loop_run.HEARTBEAT_INTERVAL_SECONDS", 0.01)
    with patch("runtime.loop.lm_loop_run.heartbeat_durable_resource", return_value=False) as beat:
        _heartbeat_loop(tmp_path / "claim", stopped, failed)
    assert failed.is_set() and beat.call_count == 1


def test_main_waits_for_a_label_apply_lock_that_frees_up(tmp_path):
    """2026-10-08: a wake that lands while its label is being applied used to exit 78 at once and
    the daily one-shot (article-daily 06:00) was lost for the day. It now waits for the short
    per-label apply to finish."""
    release = _write_prestart_lock_release(tmp_path)
    state_root = tmp_path / "state"
    attempts = []

    class _Free:
        def __enter__(self):
            return None

        def __exit__(self, *_):
            return False

    def lock(*_a, **_k):
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("production apply is already owned")
        return _Free()

    with (patch.dict(os.environ, {"LIFE_MANAGER_STATE_ROOT": str(state_root),
                                  "LIFE_MANAGER_RUN_ID": "run-w", "WAKE_ID": "wake-w"}, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", side_effect=lock),
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep,
          patch("runtime.loop.lm_loop_run.build_loop_command", side_effect=RuntimeError("past-the-lock")),
          patch("runtime.loop.lm_loop_run.try_acquire_resource"),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource")):
        lm_loop_run_main(["example-publisher", str(release)])

    assert len(attempts) == 3, "it must keep trying until the lock frees"
    assert sleep.call_count == 2
    events_file = state_root / "events.jsonl"
    blockers = [json.loads(l).get("blocker") for l in events_file.read_text().splitlines()] if events_file.exists() else []
    assert "apply_lock_busy" not in blockers, "a lock that freed up must not be recorded as busy"


def test_registered_entrypoint_stderr_uses_bounded_owned_relay(tmp_path, capfd):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    child = "import os; os.write(2,b'first-'+b'x'*(4*1024**2)+b'-last')"
    env = {**os.environ, "LIFE_MANAGER_LOOP_ID": "life-manager-disk-cleanup", "LIFE_MANAGER_RUN_ID": "run-1", "LIFE_MANAGER_OCCURRENCE_ID": "life-manager-disk-cleanup:run-1", "LIFE_MANAGER_RELEASE_SHA": "a"*40}
    rc, tail = _run_entrypoint_with_stderr_capture([sys.executable, "-c", child], scratch, env=env, timeout_seconds=10)
    assert rc == 0 and tail.endswith(b'-last')
    assert (scratch / "stderr-relay/relay-result.json").is_file()
    retained = sum(p.stat().st_size for p in (scratch / "stderr-relay").iterdir() if p.is_file())
    assert retained <= 2*1024**2 + 40*1024
    captured = capfd.readouterr().err
    assert captured.startswith("first-") and captured.endswith("-last")


def test_terminal_event_enospc_fences_effectful_owner_before_next_wake(
        tmp_path, monkeypatch):
    release = _write_prestart_lock_release(tmp_path)
    registry_path = release / "config/loop-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["loops"]["example-publisher"].update({
        "cadence": {"start_interval_seconds": 60},
        "resource_class": "browser",
        "admission_class": "revenue",
    })
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    state_root = tmp_path / "state"
    admission_root = tmp_path / "admission"
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(admission_root))
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_FINITE_RUNS", "1")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_BROWSER_RUNS", "1")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MIN_REVENUE_RUNS", "0")
    admission.activate_durable_v2()

    effects = []
    next_occurrences = []
    dispatches = []
    append_runtime_event = loop_runner.append_runtime_event

    def run_child(_command, _log_dir, *, on_started, **_kwargs):
        on_started(os.getpid())
        next_occurrences.append(admission.enqueue_durable(
            "browser", "example-publisher", admission_class="revenue",
            occurrence_id="example-publisher:run-2",
        ))
        effects.append("published")
        return 0, b""

    def append_event(path, event):
        if event.get("phase") == "report":
            raise OSError(errno.ENOSPC, "terminal receipt unavailable")
        append_runtime_event(path, event)

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(state_root),
              "LIFE_MANAGER_RUN_ID": "run-1",
              "WAKE_ID": "wake-1",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command",
                return_value=["/bin/true"]),
          patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run._run_entrypoint_with_stderr_capture",
                side_effect=run_child),
          patch("runtime.loop.lm_loop_run.append_runtime_event",
                side_effect=append_event),
          patch("runtime.loop.lm_loop_run._dispatch_reserved",
                side_effect=lambda loop_ids: dispatches.extend(loop_ids))):
        result = lm_loop_run_main(["example-publisher", str(release)])

    assert effects == ["published"]
    assert next_occurrences[0][0] is not None
    assert dispatches == []
    scratch = state_root / "loop-tmp/example-publisher/run-1"
    assert (scratch / ".terminal-unrecorded").is_file()
    assert result != 0

    next_claim, reason = admission.claim_durable(
        "browser", "example-publisher", admission_class="revenue",
    )
    if next_claim is not None:
        admission.release_and_reserve(next_claim, effect_unknown=True, reserve=False)
    assert next_claim is None and reason == "effect_unknown"
