import importlib.util
import errno
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from skills.earn.lancers.tests.test_create_package import _FakeTick
from skills.earn.lancers.tests.test_storefront_offer_reads_catalog import _private_catalog, _private_product


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/storefront_offer.py"
TITLE_STEM = "AI・API連携の自動運用システムを設計・実装し"


def _module():
    spec = importlib.util.spec_from_file_location("lancers_portfolio_readback_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Link:
    def __init__(self, text, href):
        self.text, self.href = text, href

    def inner_text(self):
        return self.text

    def get_attribute(self, name):
        return self.href if name == "href" else None


class Page:
    def __init__(self, links):
        self.links = links

    @contextmanager
    def expect_response(self, _predicate, **_kwargs):
        yield SimpleNamespace(value=SimpleNamespace(status=200))

    def goto(self, *_args, **_kwargs):
        return None

    def locator(self, _selector):
        return SimpleNamespace(all=lambda: self.links)


def _links(*ids):
    return [Link(TITLE_STEM + "ました", f"/profile/keiodaisuke/portfolio_popup/{i}") for i in ids]


def test_pinned_portfolio_is_found_when_a_same_title_duplicate_exists():
    # 2026-10-18: a second public portfolio (757333) with the same title appeared on
    # /myportfolio; the pinned 743987 is still there, so the readback must pick it.
    module = _module()
    found = module._portfolio(Page(_links("757333", "743987")), {"title_stem": TITLE_STEM, "external_id": "743987"})
    assert found == {
        "portfolio_external_id": "743987",
        "portfolio_url": "https://www.lancers.jp/profile/keiodaisuke/portfolio_popup/743987",
        "portfolio_duplicate_external_ids": ["757333"],
    }


def test_pinned_portfolio_missing_among_same_title_rows_stays_invalid():
    module = _module()
    with pytest.raises(module.OfferError, match="portfolio_readback_invalid"):
        module._portfolio(Page(_links("757333")), {"title_stem": TITLE_STEM, "external_id": "743987"})


def test_unpinned_duplicate_titles_stay_ambiguous():
    module = _module()
    with pytest.raises(module.OfferError, match="portfolio_readback_invalid"):
        module._portfolio(Page(_links("757333", "743987")), {"title_stem": TITLE_STEM, "external_id": ""})


def test_pinned_portfolio_absent_never_reads_as_create_me():
    # None makes _ensure_portfolio create a new portfolio: a pinned row that did not render
    # is the likely origin of duplicate 757333. A pin with zero title matches is invalid.
    module = _module()
    with pytest.raises(module.OfferError, match="portfolio_readback_invalid"):
        module._portfolio(Page([]), {"title_stem": TITLE_STEM, "external_id": "743987"})
    assert module._portfolio(Page([]), {"title_stem": TITLE_STEM, "external_id": ""}) is None


def test_same_title_duplicates_are_surfaced():
    module = _module()
    found = module._portfolio(Page(_links("757333", "743987")), {"title_stem": TITLE_STEM, "external_id": "743987"})
    assert found["portfolio_duplicate_external_ids"] == ["757333"]


def test_roster_reports_same_title_duplicates():
    module = _module()
    item = {"title_stem": TITLE_STEM, "external_id": "743987"}
    module._portfolio = lambda page, value: (
        {"portfolio_external_id": "743987", "portfolio_duplicate_external_ids": ["757333"]}
        if value is item else {"portfolio_external_id": "743964"})
    page = SimpleNamespace(goto=lambda *a, **k: None, url="https://www.lancers.jp/myplan",
                           locator=lambda _s: SimpleNamespace(all=lambda: []))
    roster = module._roster(page, {"superseded_listing_ids": [], "portfolio": {"external_id": "743964"},
                                   "software_portfolio": item})
    assert roster["portfolio_duplicate_external_ids"] == {"portfolio": [], "software_portfolio": ["757333"]}


def test_query_string_on_a_duplicate_href_is_not_part_of_its_id():
    module = _module()
    links = _links("743987") + [Link(TITLE_STEM + "ました", "/profile/keiodaisuke/portfolio_popup/757333?ref=x")]
    found = module._portfolio(Page(links), {"title_stem": TITLE_STEM, "external_id": "743987"})
    assert found["portfolio_duplicate_external_ids"] == ["757333"]


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _first_portfolio(tmp_path, monkeypatch, *, key="software_portfolio", absent=False, catalog=False):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = _private_product(tmp_path / "owner", **({"catalog_family": "other"} if catalog else {}))
    catalog_path = _private_catalog(path.parent) if catalog else None
    module = _module()
    state = tmp_path / "state/application.json"
    # Seed an actual listing receipt before removing just the target portfolio's ID.
    product, _, _ = module._product(path, catalog_path)
    module._write_receipt(state, product, {"detail_views": 7})
    ledger = state.with_name("listing.json")
    receipt = _json(ledger) | {"observed_at": "2026-01-02T03:04:05Z"}
    ledger.write_text(json.dumps(receipt))
    raw = _json(path)
    raw["owner_note"] = {"keep": "本人の入力"}
    if absent:
        del raw[key]["external_id"]
    else:
        raw[key]["external_id"] = ""
    path.write_text(json.dumps(raw, ensure_ascii=False))
    page = Page([Link(item["title_stem"] + "ました",
                      f"/profile/other-seller/portfolio_popup/{item['external_id']}")
                 for name in ("portfolio", "software_portfolio")
                 if (item := raw[name]).get("external_id")])
    tick = _FakeTick()
    calls = SimpleNamespace(apply=[], ensure=[], created=[], pending=[], readback=[], forbidden=[])
    new_page = tick._new_owned_page
    monkeypatch.setattr(tick, "_new_owned_page", lambda browser: (new_page(browser), page)[1])
    monkeypatch.setattr(module, "_load", lambda *_args: tick)

    def forbidden(*_args, **_kwargs):
        calls.forbidden.append("external")
        raise AssertionError("実ブラウザまたは作成禁止callbackへ到達")

    def apply(_page, value, _image):
        calls.apply.append(json.loads(json.dumps(value)))
        return {"ok": True, "aligned": True, "action": "unchanged"}

    readback = module._portfolio

    def portfolio(_page, item):
        calls.readback.append(dict(item))
        return readback(_page, item)

    def ensure(_page, value, _image, target):
        calls.ensure.append(target)
        item = value[target]
        effect = int(not item.get("external_id"))
        if effect:
            calls.pending.append(_json(ledger).get("pending_create"))
            calls.created.append(target)
            page.links.append(Link(item["title_stem"] + "ました",
                                   "/profile/other-seller/portfolio_popup/88001"))
        return portfolio(_page, item) | {"portfolio_effect_count": effect}

    monkeypatch.setattr(module, "_apply", apply)
    monkeypatch.setattr(module, "_ensure_portfolio", ensure)
    monkeypatch.setattr(module, "_portfolio", portfolio)
    monkeypatch.setattr(module, "_profile", lambda *_args: {"profile_effect_count": 0})
    monkeypatch.setattr(module, "_demand", lambda *_args: {"detail_views": 7})
    monkeypatch.setattr(module, "_public", forbidden)
    monkeypatch.setattr(module, "create_package", forbidden)
    return SimpleNamespace(module=module, path=path, state=state, ledger=ledger, key=key,
                           catalog=catalog_path, page=page, tick=tick, calls=calls, forbidden=forbidden)


def _resume_readback_only(case, monkeypatch):
    for name in ("_apply", "_ensure_portfolio", "_profile"):
        monkeypatch.setattr(case.module, name, case.forbidden)
    case.calls.readback.clear()


@pytest.mark.parametrize("key", ["portfolio", "software_portfolio"])
@pytest.mark.parametrize("absent", [False, True], ids=["empty", "missing"])
def test_first_portfolio_apply_saves_only_real_id(tmp_path, monkeypatch, key, absent):
    case = _first_portfolio(tmp_path, monkeypatch, key=key, absent=absent, catalog=True)
    before = _json(case.path)

    result = case.module.run(True, case.path, case.state, catalog_path=case.catalog)

    assert result["ok"] is True
    assert _json(case.path) == before | {key: before[key] | {"external_id": "88001"}}
    assert case.calls.created == [key]
    pending, = case.calls.pending
    assert pending is not None
    assert {name: pending[name] for name in ("kind", "product_id", "product_version", "seller_path")} == {
        "kind": key, "product_id": "other-user-product", "product_version": 1,
        "seller_path": "/profile/other-seller"}
    assert len(pending["content_sha256"]) == 64
    assert "pending_create" not in _json(case.ledger)
    assert case.calls.forbidden == []
    assert case.tick.opened_pages == case.tick.closed_pages == 1


def test_first_portfolio_pending_write_enospc_prevents_ensure(tmp_path, monkeypatch):
    case = _first_portfolio(tmp_path, monkeypatch)
    before = _json(case.path)
    write = case.module._write_private

    def full(target, value):
        if Path(target) == case.ledger and "pending_create" in value:
            raise OSError(errno.ENOSPC, "fixture full")
        write(target, value)

    monkeypatch.setattr(case.module, "_write_private", full)
    result = case.module.run(True, case.path, case.state)

    assert result["ok"] is False and result["error"] == "private_storage"
    assert case.key not in case.calls.ensure
    assert case.calls.created == []
    assert _json(case.path) == before
    assert "pending_create" not in _json(case.ledger)
    assert case.tick.opened_pages == case.tick.closed_pages


def _fail_product_write(case, monkeypatch):
    write = case.module._write_private

    def full(target, value):
        if Path(target) == case.path:
            raise OSError(errno.ENOSPC, "fixture full")
        write(target, value)

    monkeypatch.setattr(case.module, "_write_private", full)
    return write


def test_first_portfolio_receipt_enospc_keeps_confirmed_id(tmp_path, monkeypatch):
    case = _first_portfolio(tmp_path, monkeypatch)

    def full(*_args):
        raise OSError(errno.ENOSPC, "fixture full")

    monkeypatch.setattr(case.module, "_write_receipt", full)
    result = case.module.run(True, case.path, case.state)

    assert result["ok"] is False and result["logged_in"] is True
    assert result.get("software_portfolio_external_id") == "88001"
    assert _json(case.path)[case.key]["external_id"] == "88001"
    assert case.calls.created == [case.key] and case.calls.forbidden == []
    assert case.tick.opened_pages == case.tick.closed_pages == 1


def test_first_portfolio_product_enospc_recovers_by_readback_without_second_create(tmp_path, monkeypatch):
    case = _first_portfolio(tmp_path, monkeypatch)
    before = _json(case.path)
    write = _fail_product_write(case, monkeypatch)

    first = case.module.run(True, case.path, case.state)

    assert first["ok"] is False and first["logged_in"] is True
    assert first.get("software_portfolio_external_id") == "88001"
    assert _json(case.path) == before
    assert "pending_create" in _json(case.ledger)
    observed_at = _json(case.ledger)["observed_at"]
    monkeypatch.setattr(case.module, "_write_private", write)
    _resume_readback_only(case, monkeypatch)

    second = case.module.run(True, case.path, case.state)

    assert second["ok"] is True
    assert _json(case.path) == before | {case.key: before[case.key] | {"external_id": "88001"}}
    assert case.calls.created == [case.key] and case.calls.forbidden == []
    assert len(case.calls.readback) == 1
    assert "pending_create" not in _json(case.ledger)
    assert _json(case.ledger)["observed_at"] == observed_at
    assert case.tick.opened_pages == case.tick.closed_pages == 2


@pytest.mark.parametrize("cleanup_fails", [False, True], ids=["restored", "cleanup-failed"])
def test_first_portfolio_clear_enospc_recovers_with_pin_and_preserves_receipt(tmp_path, monkeypatch, cleanup_fails):
    case = _first_portfolio(tmp_path, monkeypatch)
    write = case.module._write_private

    def full_on_clear(target, value):
        if Path(target) == case.ledger and "pending_create" not in value:
            raise OSError(errno.ENOSPC, "fixture full")
        write(target, value)

    monkeypatch.setattr(case.module, "_write_private", full_on_clear)
    first = case.module.run(True, case.path, case.state)

    assert first["ok"] is False and first["logged_in"] is True
    assert _json(case.path)[case.key]["external_id"] == "88001"
    assert "pending_create" in _json(case.ledger)
    receipt = _json(case.ledger)
    monkeypatch.setattr(case.module, "_write_private", write)
    _resume_readback_only(case, monkeypatch)
    if cleanup_fails:
        close = case.tick._close_owned_page
        monkeypatch.setattr(case.tick, "_close_owned_page", lambda page: (close(page), False)[1])

    second = case.module.run(True, case.path, case.state)

    if cleanup_fails:
        assert second["ok"] is False and second["error"] == "cleanup_failed"
    else:
        assert second["ok"] is True
    assert len(case.calls.readback) == 1
    assert case.calls.readback[0]["external_id"] == "88001"
    assert case.calls.created == [case.key] and case.calls.forbidden == []
    assert _json(case.ledger) == {k: v for k, v in receipt.items() if k != "pending_create"}
    assert case.tick.opened_pages == case.tick.closed_pages == 2


@pytest.mark.parametrize("ids", [[], ["88001", "88002"]], ids=["zero", "duplicate"])
def test_first_portfolio_pending_ambiguous_readback_never_creates(tmp_path, monkeypatch, ids):
    case = _first_portfolio(tmp_path, monkeypatch)
    write = _fail_product_write(case, monkeypatch)
    first = case.module.run(True, case.path, case.state)
    assert first["ok"] is False and first["logged_in"] is True
    before, ledger = _json(case.path), _json(case.ledger)
    assert "pending_create" in ledger
    case.page.links = [Link(before[case.key]["title_stem"] + "ました",
                            f"/profile/other-seller/portfolio_popup/{value}") for value in ids]
    monkeypatch.setattr(case.module, "_write_private", write)
    _resume_readback_only(case, monkeypatch)

    result = case.module.run(True, case.path, case.state)

    assert result["ok"] is False and result["logged_in"] is not False
    assert _json(case.path) == before and _json(case.ledger) == ledger
    assert len(case.calls.readback) == 1
    assert case.calls.created == [case.key] and case.calls.forbidden == []
    assert case.tick.opened_pages == case.tick.closed_pages == 2


@pytest.mark.parametrize("field", ["description", "listing_external_id"])
@pytest.mark.parametrize("when", ["during_create", "pending_resume"])
def test_first_portfolio_changed_input_never_attaches_old_id(tmp_path, monkeypatch, field, when):
    case = _first_portfolio(tmp_path, monkeypatch)
    changed = _json(case.path)
    changed[field] = "91002" if field == "listing_external_id" else changed[field] + " 本人の更新"
    if when == "during_create":
        ensure = case.module._ensure_portfolio

        def change_during_create(*args):
            found = ensure(*args)
            if args[-1] == case.key:
                case.path.write_text(json.dumps(changed))
            return found

        monkeypatch.setattr(case.module, "_ensure_portfolio", change_during_create)
    else:
        write = _fail_product_write(case, monkeypatch)
        first = case.module.run(True, case.path, case.state)
        assert first["ok"] is False and first["logged_in"] is True
        assert "pending_create" in _json(case.ledger)
        case.path.write_text(json.dumps(changed))
        monkeypatch.setattr(case.module, "_write_private", write)
        _resume_readback_only(case, monkeypatch)
    pending = _json(case.ledger).get("pending_create")

    result = case.module.run(True, case.path, case.state)

    assert result["ok"] is False and result["logged_in"] is not False
    assert _json(case.path) == changed
    assert "pending_create" in _json(case.ledger)
    if when == "pending_resume":
        assert _json(case.ledger)["pending_create"] == pending
    assert case.calls.created == [case.key] and case.calls.forbidden == []


def test_first_portfolio_apply_reloads_product_inside_account_lock(tmp_path, monkeypatch):
    case = _first_portfolio(tmp_path, monkeypatch)

    @contextmanager
    def lock(_path):
        changed = _json(case.path) | {"listing_external_id": "91002"}
        case.path.write_text(json.dumps(changed))
        yield

    monkeypatch.setattr(case.tick, "account_lock", lock)
    result = case.module.run(True, case.path, case.state)

    assert case.calls.apply[0]["listing_external_id"] == "91002"
    assert result["ok"] is True
    assert _json(case.path)["listing_external_id"] == "91002"
    assert _json(case.path)[case.key]["external_id"] == "88001"


@pytest.mark.parametrize("absent", [False, True], ids=["empty", "missing"])
def test_first_portfolio_apply_still_requires_real_listing_id(tmp_path, monkeypatch, absent):
    case = _first_portfolio(tmp_path, monkeypatch)
    raw = _json(case.path)
    if absent:
        del raw["listing_external_id"]
    else:
        raw["listing_external_id"] = ""
    case.path.write_text(json.dumps(raw))
    monkeypatch.setattr(case.module, "_load", case.forbidden)

    result = case.module.run(True, case.path, case.state)

    assert result["ok"] is False and result["error"] == "setup_required"
    assert case.calls.forbidden == [] and case.tick.opened_pages == 0
    assert _json(case.path) == raw


@pytest.mark.parametrize("absent", [False, True], ids=["empty", "missing"])
@pytest.mark.parametrize("roster", [False, True], ids=["inspect", "roster"])
def test_first_portfolio_inspect_keeps_primary_id_strict(tmp_path, monkeypatch, absent, roster):
    case = _first_portfolio(tmp_path, monkeypatch, key="portfolio", absent=absent)
    before = _json(case.path)
    monkeypatch.setattr(case.module, "_load", case.forbidden)

    result = case.module.run(False, case.path, case.state, roster=roster)

    assert result["ok"] is False and result["error"] == "setup_required"
    assert case.calls.forbidden == [] and case.tick.opened_pages == 0
    assert _json(case.path) == before
