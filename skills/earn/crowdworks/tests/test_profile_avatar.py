from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "profile.py"
SPEC = importlib.util.spec_from_file_location("crowdworks_profile_avatar_test", MODULE_PATH)
assert SPEC and SPEC.loader
profile = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = profile
SPEC.loader.exec_module(profile)


def test_default_public_avatar_is_not_aligned() -> None:
    source = (
        "https://cw-assets.crowdworks.jp/vite/2026-09/1/packs/legacy/"
        "images/user_picture/default/140x140-example.png"
    )

    assert profile._avatar_aligned(source) is False


def test_uploaded_public_avatar_is_aligned() -> None:
    source = "https://crowdworks.jp/user_picture/123456/140x140-example.jpg"

    assert profile._avatar_aligned(source) is True


def test_current_attachment_avatar_is_read_back() -> None:
    source = "https://crowdworks.jp/attachments/59139511.jpg?width=200&height=200"

    class Locator:
        first = None

        def __init__(self) -> None:
            self.first = self

        def wait_for(self, **_kwargs: object) -> None:
            return None

        def count(self) -> int:
            return 1

        def get_attribute(self, name: str) -> str | None:
            return source if name == "src" else None

    class Page:
        def locator(self, selector: str) -> Locator:
            assert 'img[alt="userIcon"]' in selector
            return Locator()

    assert profile._public_avatar(Page()) == {
        "present": True,
        "aligned": True,
        "hash": profile._hash(source),
    }


def test_relative_current_attachment_avatar_is_resolved_before_readback() -> None:
    source = "/attachments/59139971.jpg?width=200&height=200"
    absolute = "https://crowdworks.jp/attachments/59139971.jpg?width=200&height=200"

    class Locator:
        first = None

        def __init__(self) -> None:
            self.first = self

        def wait_for(self, **_kwargs: object) -> None:
            return None

        def count(self) -> int:
            return 1

        def get_attribute(self, name: str) -> str | None:
            return source if name == "src" else None

    class Page:
        def locator(self, _selector: str) -> Locator:
            return Locator()

    assert profile._public_avatar(Page()) == {
        "present": True,
        "aligned": True,
        "hash": profile._hash(absolute),
    }


def test_avatar_validation_uses_an_explicit_private_asset(tmp_path: Path) -> None:
    expected = tmp_path / "my-avatar.jpg"
    expected.write_bytes(b"private-avatar")

    assert profile._validated_avatar(expected) == expected


def test_matching_official_components_need_no_profile_mutation() -> None:
    config = {
        "display_name": "Kaito｜AI自動化",
        "occupation": "AI関連サービス",
        "occupation_detail": {"id": "142", "label": "プロンプトエンジニア"},
        "status": "available",
        "hours_limit": "31-40",
        "min_hourly_wage": 3000,
        "max_hourly_wage": 5000,
        "web_meeting": "available",
        "introduction": "AI・ソフトウェア開発と研修支援",
        "job_categories": ["Webプログラミング", "AIシステム開発"],
        "skills": [
            {"name": "Python", "level": "4", "years": 3, "note": "業務自動化"},
            {"name": "TypeScript", "level": "3", "years": 3, "note": "Web開発"},
        ],
    }
    components = profile._expected_components(config)
    components["avatar"] = {"aligned": True}

    assert profile._profile_aligned(components, config) is True

    components["occupation"]["hash"] = profile._hash("プロンプトエンジニア")
    assert profile._profile_aligned(components, config) is False


def test_private_profile_owns_crowdworks_public_fields(tmp_path: Path) -> None:
    provider_path = tmp_path / "provider.json"
    value = {
        "version": 1, "provider_employee_id": "543210", "display_name": "別の利用者",
        "occupation": "デザイナー", "simple_introduction": "本人の短い紹介",
        "introduction": "本人のデザイン実績", "status": "available",
        "hours_limit": "11-20", "min_hourly_wage": 2000, "max_hourly_wage": 4000,
        "web_meeting": "available", "job_categories": ["ロゴ作成"],
        "skills": [{"name": "Illustrator", "level": "3", "years": 3, "note": "本人の作品"}],
        "occupation_detail": {"id": "2", "label": "デザイナー"},
        "avatar_path": "my-avatar.jpg",
    }
    (tmp_path / "my-avatar.jpg").write_bytes(b"private-avatar")
    provider_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    provider_path.chmod(0o600)

    config = profile.load_config(provider_path)

    assert config == value | {"avatar_path": str(tmp_path / "my-avatar.jpg")}


def test_buyer_visible_detail_occupation_is_required_for_alignment() -> None:
    config = {
        "display_name": "Kaito｜AI自動化",
        "occupation": "ITエンジニア",
        "occupation_detail": {"id": "1", "label": "システムエンジニア（SE）"},
        "status": "available",
        "hours_limit": "31-40",
        "min_hourly_wage": 3000,
        "max_hourly_wage": 5000,
        "web_meeting": "available",
        "introduction": "ソフトウェア開発とAI自動化、教育研修支援",
        "job_categories": ["Webプログラミング"],
        "skills": [
            {"name": "Python", "level": "4", "years": 3, "note": "業務自動化"},
            {"name": "TypeScript", "level": "3", "years": 3, "note": "Web開発"},
        ],
    }
    components = profile._expected_components(config)
    components["avatar"] = {"aligned": True}
    components["occupation_detail"]["hash"] = profile._hash("142:プロンプトエンジニア")

    assert profile._profile_aligned(components, config) is False


def test_public_detail_occupation_reads_exact_buyer_visible_id_and_label() -> None:
    class Item:
        def get_attribute(self, name: str) -> str | None:
            return "/public/employees/occupation/1" if name == "href" else None

        def inner_text(self) -> str:
            return "システムエンジニア（SE）"

    class Items:
        def count(self) -> int:
            return 1

        def nth(self, _index: int) -> Item:
            return Item()

    class Page:
        def locator(self, selector: str) -> Items:
            assert "/public/employees/occupation/" in selector
            return Items()

    assert profile._public_occupation_detail(Page()) == {
        "id": "1",
        "label": "システムエンジニア（SE）",
    }


def test_skill_alignment_includes_public_level_years_and_note() -> None:
    config = {
        "display_name": "Kaito｜AI自動化",
        "occupation": "ITエンジニア",
        "occupation_detail": {"id": "1", "label": "システムエンジニア（SE）"},
        "status": "available",
        "hours_limit": "31-40",
        "min_hourly_wage": 3000,
        "max_hourly_wage": 5000,
        "web_meeting": "available",
        "introduction": "ソフトウェア開発",
        "job_categories": ["Webプログラミング"],
        "skills": [{"name": "Python", "level": "4", "years": 3, "note": "業務自動化"}],
    }
    components = profile._expected_components(config)
    components["avatar"] = {"aligned": True}
    assert profile._profile_aligned(components, config) is True

    components["skills"]["hash"] = profile._hash("Python|4|1〜3年|別の備考")
    assert profile._profile_aligned(components, config) is False


def test_profile_rejects_year_band_the_provider_cannot_project() -> None:
    try:
        profile._years_label(4)
    except profile.ProfileError as error:
        assert error.code == "profile_skill_years_invalid"
    else:
        raise AssertionError("unsupported year band was accepted")


def test_stale_same_name_skill_is_deleted_before_exact_rebuild() -> None:
    class Locator:
        def __init__(self, page: "Page", kind: str) -> None:
            self.page = page
            self.kind = kind
            self.first = self

        def count(self) -> int:
            return self.page.rows if self.kind == "rows" else 1

        def locator(self, selector: str) -> "Locator":
            assert selector == 'a[data-method="delete"]'
            return Locator(self.page, "delete")

        def click(self) -> None:
            self.page.rows -= 1

    class Page:
        rows = 1
        url = profile.SKILLS_URL

        def locator(self, selector: str) -> Locator:
            assert selector in {'tr[id^="user_skills_"]', "body"}
            return Locator(self, "rows" if selector.startswith("tr") else "body")

        def once(self, event: str, callback: object) -> None:
            assert event == "dialog"

        def wait_for_load_state(self, **_kwargs: object) -> None:
            return None

        def goto(self, url: str) -> None:
            self.url = url

    page = Page()
    profile._delete_all_skills(page)
    assert page.rows == 0


def test_hidden_stale_occupation_checkbox_is_cleared_without_clicking() -> None:
    class HiddenCheckbox:
        checked = True
        evaluated = False

        def evaluate(self, script: str, checked: bool) -> bool:
            assert "dispatchEvent" in script
            assert "return e.checked" in script
            self.evaluated = True
            self.checked = checked
            return self.checked

    checkbox = HiddenCheckbox()
    profile._set_checkbox(checkbox, False)
    assert checkbox.checked is False
    assert checkbox.evaluated is True


def test_skill_readback_ignores_provider_action_column() -> None:
    class Cell:
        def __init__(self, value: str) -> None:
            self.value = value

        def inner_text(self) -> str:
            return self.value

    class Cells:
        def __init__(self, values: list[str]) -> None:
            self.values = values

        def count(self) -> int:
            return len(self.values)

        def nth(self, index: int) -> Cell:
            return Cell(self.values[index])

    class Row:
        def locator(self, selector: str) -> Cells:
            assert selector == "td"
            return Cells(["Python", "4:上級", "1〜3年", "業務自動化", "編集 削除"])

    class Rows:
        def count(self) -> int:
            return 1

        def nth(self, index: int) -> Row:
            assert index == 0
            return Row()

    class Page:
        def locator(self, selector: str) -> Rows:
            assert selector == 'tr[id^="user_skills_"]'
            return Rows()

    assert profile._public_skills(Page()) == [
        {"name": "Python", "level": "4:上級", "years": "1〜3年", "note": "業務自動化"}
    ]
    assert profile._skills_value(profile._public_skills(Page()), public=True) == profile._skills_value(
        [{"name": "Python", "level": "4", "years": 3, "note": "業務自動化"}]
    )


def test_public_skill_star_width_is_level_id() -> None:
    class PublicLevel:
        def inner_text(self) -> str:
            return ""

        def evaluate(self, script: str) -> str:
            assert "stars-active" in script
            assert "stars-inactive" in script
            return "4"

    assert profile._skill_level(PublicLevel()) == "4"
