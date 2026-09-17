import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/storefront_offer.py"


def test_public_profile_stays_aligned_when_mypage_score_widget_disappears():
    spec = importlib.util.spec_from_file_location("lancers_profile_readback_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    class Locator:
        def __init__(self, values):
            self.values = values

        def count(self):
            return len(self.values)

        def all_inner_texts(self):
            return self.values

        def inner_text(self):
            return self.values[0]

        def get_attribute(self, name):
            return self.values[0] if name == "src" else None

    class Page:
        url = ""

        def goto(self, url, **_kwargs):
            self.url = url
            return SimpleNamespace(status=200)

        def locator(self, selector):
            return Locator({
                ".p-profile-media__sub-title-link": ["業務自動化を支援します"],
                "p.p-profile-introduction__text": ["実装と運用を支援します"],
                "img.p-profile-media__avatar-image": ["https://example.test/avatar.jpg"],
                ".js-regularRankCheckPercent": [],
            }.get(selector, []))

        def get_by_role(self, *_args, **_kwargs):
            return Locator([])

    product = {"seller_profile": {
        "public_path": "/profile/keiodaisuke",
        "subtitle": "業務自動化を支援します",
        "description": "実装と運用を支援します",
    }}
    result = module._profile(Page(), product, Path("unused-avatar.jpg"), False)
    assert result == {
        "profile_aligned": True, "profile_photo_aligned": True,
        "profile_completion_percent": None, "profile_effect_count": 0,
    }

    class RedirectPage(Page):
        def goto(self, url, **kwargs):
            response = super().goto(url, **kwargs)
            if url.endswith("/mypage"):
                self.url = "https://www.lancers.jp/user/login"
            return response

    with pytest.raises(module.OfferError, match="profile_readback_invalid"):
        module._profile(RedirectPage(), product, Path("unused-avatar.jpg"), False)

    class DuplicatePhotoPromptPage(Page):
        def get_by_role(self, *_args, **_kwargs):
            return Locator(["register", "register"])

    duplicate = module._profile(DuplicatePhotoPromptPage(), product, Path("unused-avatar.jpg"), False)
    assert duplicate["profile_aligned"] is False
    assert duplicate["profile_photo_aligned"] is False
