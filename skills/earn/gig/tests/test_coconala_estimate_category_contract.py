import importlib.util
import unittest
from unittest import mock
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "coconala_estimate_browser.py"
SPEC = importlib.util.spec_from_file_location("coconala_estimate_browser", MODULE_PATH)
assert SPEC and SPEC.loader
browser = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(browser)


class CategoryTypeContractTests(unittest.TestCase):
    def test_main_and_nested_tabs_keep_the_same_client_owner(self):
        owners = []

        class Tab:
            ws = "ws://example"

            def __init__(self, *_args, **kwargs):
                owners.append(kwargs.get("owner"))

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        async def inspect(*_args, **_kwargs):
            return {"own_user_path": "/users/me", "messages": []}

        instance = browser.CoconalaEstimateBrowser(
            None, "https://coconala.com/mypage/direct_message/12",
            "https://coconala.com/direct_offers/add/12",
            owner="coconala-reply-12",
        )
        with mock.patch.object(browser.collector, "DefaultTab", Tab), \
             mock.patch.object(browser.collector, "inspect_message_page", inspect), \
             mock.patch.object(browser.collector, "validate_page_identity"), \
             mock.patch.object(browser.collector, "direct_thread_head_projection", return_value={}):
            instance.__enter__()
            instance.fresh_thread_context("/users/me")
            instance.__exit__()

        self.assertEqual(owners, ["coconala-reply-12", "coconala-reply-12"])

    def test_required_shape_proves_visible_row_in_both_paths(self):
        required = (
            "state.row_present&&!state.control_disabled&&!state.row_hidden"
            "&&state.enabled_option_count>0"
        )

        self.assertIn("row_present:!!row", browser.CATEGORY_TYPE_CONTRACT_JS)
        self.assertIn(required, browser.select_sub_expression("Web制作"))
        self.assertIn(required, browser.fill_expression({
            "master_category_label": "Web",
            "sub_category_label": "Web制作",
            "category_type_label": "サイト修正",
            "title": "title",
            "content": "content",
            "price_jpy": 10000,
            "purchase_plan": "single",
        }, "2026-08-20"))

    def test_optional_and_exact_label_guards_remain_fail_closed(self):
        optional = (
            "state.control_disabled&&state.row_hidden"
            "&&state.enabled_option_count===0"
        )
        exact_one = (
            "filter(o=>(o.textContent||\"\").trim()===label&&!o.disabled&&o.value);"
            "if(options.length!==1)"
        )

        select_sub = browser.select_sub_expression("Web制作")
        fill = browser.fill_expression({
            "master_category_label": "Web",
            "sub_category_label": "Web制作",
            "category_type_label": "サイト修正",
            "title": "title",
            "content": "content",
            "price_jpy": 10000,
            "purchase_plan": "single",
        }, "2026-08-20")

        self.assertIn(optional, select_sub)
        self.assertIn(optional, fill)
        self.assertIn(exact_one, select_sub)
        self.assertIn("return options.length===1?options[0]:null", fill)


if __name__ == "__main__":
    unittest.main()
