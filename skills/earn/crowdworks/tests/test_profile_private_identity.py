"""Private CrowdWorks input fails closed before browser or profile effects."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest

from skills.earn.crowdworks.tests.test_account_identity import Page, dashboard


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
CANDIDATE = {
    "version": 1,
    "candidate": {"name": "別の利用者"},
    "facts": [{"id": "design", "claim": "ロゴを制作できる", "evidence": "本人の制作記録"}],
}


def provider():
    return {
        "version": 1, "provider_employee_id": "5432107", "display_name": "別の利用者",
        "occupation": "デザイナー", "status": "available", "hours_limit": "11-20",
        "min_hourly_wage": 2000, "max_hourly_wage": 4000, "web_meeting": "available",
        "simple_introduction": "本人の短い紹介", "introduction": "本人のデザイン実績",
        "job_categories": ["ロゴ作成"],
        "skills": [{"name": "Illustrator", "level": "3", "years": 3, "note": "本人の作品"}],
    }


def write_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.fixture
def profile(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LIFE_MANAGER_STATE_ROOT", str(tmp_path / "state"))
    registry = tmp_path / "browsers.toml"
    registry.write_text("", encoding="utf-8")
    monkeypatch.setenv("AI_BROWSER_REGISTRY", str(registry))
    for key in ("CDP", "CDP_PORT", "CLOAK_CDP_BASE_URL", "LIFE_MANAGER_LOOP_ID",
                "LIFE_MANAGER_BROWSER_IDENTITY", "LIFE_MANAGER_BROWSER_TARGET_OWNER",
                "LIFE_MANAGER_BROWSER_LEASE_IDENTITY"):
        monkeypatch.delenv(key, raising=False)
    spec = importlib.util.spec_from_file_location("crowdworks_private_profile_test", SCRIPTS / "profile.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    with monkeypatch.context() as guard:
        original = Path.read_text

        def read(path, *args, **kwargs):
            assert not path.is_relative_to(home), "import must not read private input"
            return original(path, *args, **kwargs)

        guard.setattr(Path, "read_text", read)
        spec.loader.exec_module(module)
    return module


def assert_setup(profile, operation):
    with pytest.raises(profile.SetupRequired) as caught:
        operation()
    error = caught.value
    assert str(error) == "setup_required"
    assert isinstance(error.missing, list) and error.missing
    assert all(isinstance(key, str) and re.fullmatch(r"[a-z][a-z0-9_.]*", key)
               for key in error.missing)
    assert "private-marker" not in json.dumps(error.missing)
    return error.missing


@pytest.mark.parametrize("account_id", ["5432107", 5432107])
def test_load_config_preserves_only_the_private_users_fields(profile, tmp_path, account_id):
    value = provider() | {"provider_employee_id": account_id}
    path = write_json(tmp_path / "provider.json", value)

    assert profile.load_config(path) == value | {"provider_employee_id": "5432107"}


@pytest.mark.parametrize("account_id", [True, 0, -1, 5.5, "0", "１２３", "5432107/path"])
def test_load_config_rejects_nonpositive_or_nonascii_identity(profile, tmp_path, account_id):
    path = write_json(tmp_path / "provider.json", provider() | {"provider_employee_id": account_id})
    before = path.read_bytes()
    assert_setup(profile, lambda: profile.load_config(path))
    assert path.read_bytes() == before


@pytest.mark.parametrize("field,value", [
    ("occupation_detail", {"id": "2", "label": ""}),
    ("occupation_detail", {"id": "private-marker", "label": "デザイナー"}),
    ("occupation_detail", {"id": "2", "label": "デザイナー", "extra": "private-marker"}),
    ("avatar_path", ""),
    ("avatar_path", 42),
])
def test_optional_private_fields_are_validated(profile, tmp_path, field, value):
    path = write_json(tmp_path / "provider.json", provider() | {field: value})
    assert_setup(profile, lambda: profile.load_config(path))


@pytest.mark.parametrize("kind", ["missing", "malformed", "mode", "symlink", "directory"])
def test_provider_input_is_private_regular_json_without_repair(profile, tmp_path, kind):
    path = tmp_path / "provider.json"
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(write_json(tmp_path / "target.json", provider()))
    elif kind != "missing":
        write_json(path, provider())
        if kind == "mode":
            path.chmod(0o644)
        else:
            path.write_text('{"private-marker":', encoding="utf-8")
    before = sorted(item.name for item in tmp_path.iterdir())
    before_bytes = path.read_bytes() if path.is_file() else None
    before_mode = path.lstat().st_mode if path.exists() else None
    assert_setup(profile, lambda: profile.load_config(path))
    assert sorted(item.name for item in tmp_path.iterdir()) == before
    if before_bytes is not None:
        assert path.read_bytes() == before_bytes
        assert path.lstat().st_mode == before_mode


def test_load_identity_reuses_candidate_validation_and_explicit_provider(profile, tmp_path):
    candidate = write_json(tmp_path / "candidate.json", CANDIDATE)
    value = provider() | {"provider_employee_id": 5432107}
    local_provider = write_json(tmp_path / "provider.json", value)
    before = (candidate.read_bytes(), local_provider.read_bytes())

    identity = profile.load_identity(candidate, local_provider)

    assert identity == {"candidate": CANDIDATE,
                        "provider": value | {"provider_employee_id": "5432107"},
                        "account_id": "5432107"}
    assert (candidate.read_bytes(), local_provider.read_bytes()) == before
    fact = CANDIDATE["facts"][0] | {"id": "private-marker"}
    broken = CANDIDATE | {"facts": [fact, fact]}
    write_json(candidate, broken)
    assert "candidate_profile" in assert_setup(profile, lambda: profile.load_identity(candidate, local_provider))


def test_default_identity_reports_both_missing_inputs_without_creating_them(profile):
    home = Path.home()
    missing = assert_setup(profile, profile.load_identity)
    assert "candidate_profile" in missing
    assert any(key.startswith("provider_profile") for key in missing)
    assert list(home.iterdir()) == []


@pytest.mark.parametrize("configured", [False, True])
def test_account_id_cli_validates_explicit_inputs_without_browser_or_writes(profile, tmp_path, monkeypatch, configured):
    candidate, local_provider = tmp_path / "candidate.json", tmp_path / "provider.json"
    if configured:
        write_json(candidate, CANDIDATE)
        write_json(local_provider, provider())
    calls = []
    monkeypatch.setattr(profile, "_defaults", lambda: calls.append("browser") or pytest.fail("browser forbidden"))
    out, err = io.StringIO(), io.StringIO()
    before = sorted(item.name for item in tmp_path.iterdir())

    code = profile.main(["account-id", "--candidate-profile", str(candidate),
                         "--provider-profile", str(local_provider)], stdout=out, stderr=err)

    if configured:
        assert code == 0
        assert out.getvalue() == "5432107\n"
    else:
        assert code == 78
        result = json.loads(out.getvalue())
        assert result["ok"] is False and result["error"] == "setup_required"
        assert "candidate_profile" in result["missing"]
    assert err.getvalue() == ""
    assert calls == []
    assert sorted(item.name for item in tmp_path.iterdir()) == before


@pytest.mark.parametrize("name", ["run_observe", "run_apply"])
@pytest.mark.parametrize("receipt_exists", [False, True])
def test_missing_config_precedes_browser_defaults_and_preserves_receipt(profile, tmp_path, monkeypatch, name, receipt_exists):
    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append("external")
        raise AssertionError("setup must precede browser defaults")

    monkeypatch.setattr(profile, "_defaults", forbidden)
    receipt = tmp_path / "receipt.json"
    if receipt_exists:
        receipt.write_bytes(b'{"pending":"preserve-me"}')
    before = receipt.read_bytes() if receipt_exists else None
    kwargs = {"config_path": tmp_path / "missing-provider.json",
              "browser_factory": forbidden, "ownership_checker": forbidden}
    if name == "run_apply":
        kwargs["receipt_path"] = receipt
    result = getattr(profile, name)(**kwargs)

    assert result["ok"] is False and result["error"] == "setup_required"
    assert result["profile_effect_count"] == 0
    assert result["missing"]
    assert calls == []
    assert receipt.exists() is receipt_exists
    if receipt_exists:
        assert receipt.read_bytes() == before
    assert list(Path.home().iterdir()) == []


def test_observe_accepts_optional_detail_but_apply_requires_it_before_browser(profile, tmp_path, monkeypatch):
    path = write_json(tmp_path / "provider.json", provider())
    observed = []
    page = object()
    monkeypatch.setattr(profile, "observe_page", lambda target, config: observed.append((target, config)) or {"ok": True})
    monkeypatch.setattr(profile, "_defaults", lambda: pytest.fail("missing detail must precede browser"))

    assert profile.run_observe(config_path=path, page=page)["ok"] is True
    assert observed == [(page, provider())]
    result = profile.run_apply(config_path=path)
    assert result["error"] == "setup_required"
    assert result["profile_effect_count"] == 0
    assert any("occupation_detail" in key for key in result["missing"])


def profile_page(profile, monkeypatch, config, *, employee="5432107", avatar=True):
    spec = importlib.util.spec_from_file_location("crowdworks_private_profile_account_test", SCRIPTS / "account.py")
    account = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, account)
    spec.loader.exec_module(account)
    page = Page(dashboard(employee=employee, own_card=employee is not None))
    page.visits, page.events, page.effects = [], [], []
    goto, account_id = page.goto, account._account_id

    def navigate(url):
        page.visits.append(url)
        goto(url)

    def identify(target):
        page.events.append(("account", target.url))
        return account_id(target)

    def body(target):
        page.events.append(("profile", target.url))
        return config["display_name"] + " " + config["introduction"]

    page.goto = navigate
    monkeypatch.setattr(account, "_account_id", identify)
    monkeypatch.setattr(profile, "_account_module", lambda: account, raising=False)
    fields = {
        'input[name="profile[display_name]"]': config["display_name"],
        'textarea[name="employee[introduction]"]': config["introduction"],
        'select[name="employee[status]"]': config["status"],
        'select[name="employee[hours_limit]"]': config["hours_limit"],
        'input[name="employee[min_hourly_wage]"]': str(config["min_hourly_wage"]),
        'input[name="employee[max_hourly_wage]"]': str(config["max_hourly_wage"]),
        'input[name="employee[web_meeting]"]:checked': config["web_meeting"],
    }
    monkeypatch.setattr(profile, "_body", body)
    monkeypatch.setattr(profile, "_field", lambda _page, selector, *_args: fields[selector])
    monkeypatch.setattr(profile, "_selected_label", lambda *_args: config["occupation"])
    monkeypatch.setattr(profile, "_occupation_details", lambda _page: [config["occupation_detail"]])
    monkeypatch.setattr(profile, "_checked_labels", lambda _page: config["job_categories"])
    monkeypatch.setattr(profile, "_public_occupation_detail", lambda _page: config["occupation_detail"])
    monkeypatch.setattr(profile, "_public_avatar", lambda _page: {
        "present": True, "aligned": avatar, "hash": profile._hash("synthetic-official-avatar"),
    })
    monkeypatch.setattr(profile, "_public_skills", lambda _page: [
        skill | {"years": profile._years_label(skill["years"])} for skill in config["skills"]])
    monkeypatch.setattr(profile, "_fill", lambda *_args: None)
    monkeypatch.setattr(profile, "_form", lambda *_args: SimpleNamespace(click=lambda: page.effects.append("submit")))
    return page


@pytest.mark.parametrize("employee", ["87654321", None])
def test_apply_rejects_wrong_or_unobserved_dashboard_before_profile_reads(profile, tmp_path, monkeypatch, employee):
    value = provider() | {"occupation_detail": {"id": "2", "label": "デザイナー"}}
    path = write_json(tmp_path / "provider.json", value)
    page = profile_page(profile, monkeypatch, value, employee=employee)

    result = profile.run_apply(config_path=path, page=page)

    assert result["ok"] is False
    assert result["profile_effect_count"] == 0
    assert page.events == [("account", "https://crowdworks.jp/dashboard")]
    assert page.visits == ["https://crowdworks.jp/dashboard"]
    assert page.effects == []


def test_observe_uses_dashboard_identity_then_only_the_private_public_urls(profile, monkeypatch):
    config = provider() | {"occupation_detail": {"id": "2", "label": "デザイナー"}}
    page = profile_page(profile, monkeypatch, config)

    result = profile.observe_page(page, config)

    assert result["provider_employee_id"] == "5432107"
    assert result["official_public_url"] == "https://crowdworks.jp/public/employees/5432107"
    assert page.events[0] == ("account", "https://crowdworks.jp/dashboard")
    assert page.visits[0] == "https://crowdworks.jp/dashboard"
    public = [url for url in page.visits if "/public/employees/" in url]
    assert public == ["https://crowdworks.jp/public/employees/5432107",
                      "https://crowdworks.jp/public/employees/5432107/occupations"]
    assert page.effects == []


def test_missing_private_avatar_stops_apply_before_profile_submit(profile, monkeypatch):
    config = provider() | {"occupation_detail": {"id": "2", "label": "デザイナー"}}
    page = profile_page(profile, monkeypatch, config, avatar=False)

    missing = assert_setup(profile, lambda: profile._apply_page(page, config, "fixture"))

    assert any("avatar_path" in key for key in missing)
    assert page.effects == []


def test_aligned_profile_returns_private_identity_without_avatar_input_or_effect(profile, monkeypatch):
    config = provider() | {"occupation_detail": {"id": "2", "label": "デザイナー"}}
    page = profile_page(profile, monkeypatch, config)

    result = profile._apply_page(page, config, "fixture")

    assert result["ok"] is True
    assert result["provider_employee_id"] == "5432107"
    assert result["official_public_url"] == "https://crowdworks.jp/public/employees/5432107"
    assert result["profile_effect_count"] == result["avatar_effect_count"] == 0
    assert result["changed_fields"] == []
    assert page.effects == []
