import unittest

from job_search_loop.mercor_auth_readback import (
    auth_snapshot_expression,
    classify_auth_snapshot,
)


class MercorAuthReadbackTests(unittest.TestCase):
    def test_requires_authenticated_official_surface(self):
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/explore",
            visible_text="Explore Applications Earnings Profile",
            login_form_visible=False,
            authenticated_api_status=200,
        ), "authenticated")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/explore",
            visible_text="Explore Profile Sign in",
            login_form_visible=False,
            authenticated_api_status=200,
        ), "authenticated")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/login",
            visible_text="Continue to Mercor Google",
            login_form_visible=True,
        ), "logged_out")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/login",
            visible_text="Continue to Mercor Google",
            login_form_visible=False,
        ), "indeterminate")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/explore",
            visible_text="Loading Explore",
            login_form_visible=False,
        ), "indeterminate")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/explore",
            visible_text="Explore Applications Earnings Profile",
            login_form_visible=False,
            authenticated_api_status=403,
        ), "indeterminate")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/login",
            visible_text="Sign in to Mercor",
            login_form_visible=True,
            authenticated_api_status=403,
        ), "indeterminate")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/jobs/apply/candidate-one?returnPath=%2Fexplore",
            visible_text=(
                "General business strategy Evaluator Application\n"
                "3 of 3 steps done\nWork Authorization\n"
                "Your application has been submitted!\nView application"
            ),
            login_form_visible=False,
            authenticated_api_status=200,
        ), "authenticated")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/jobs/apply/candidate-one?returnPath=%2Fexplore",
            visible_text="Sign in to continue your application",
            login_form_visible=True,
        ), "logged_out")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/explore",
            visible_text="Explore Applications Earnings Profile",
            login_form_visible=False,
            authenticated_navigation_visible=True,
        ), "indeterminate")
        self.assertEqual(classify_auth_snapshot(
            url="https://example.com/",
            visible_text="Explore Applications Earnings Profile",
        ), "indeterminate")

    def test_expired_firebase_token_cannot_pass_a_lenient_api_probe(self):
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/explore",
            visible_text="Explore Applications Earnings Profile",
            login_form_visible=False,
            authenticated_api_status=200,
            firebase_token_expired=True,
            firebase_token_refreshed=False,
        ), "logged_out")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/explore",
            visible_text="Explore Applications Earnings Profile",
            login_form_visible=False,
            authenticated_api_status=200,
            firebase_token_expired=False,
            firebase_token_refreshed=True,
        ), "authenticated")

    def test_auth_snapshot_refreshes_expired_firebase_records_in_place(self):
        expression = auth_snapshot_expression()
        self.assertIn("securetoken.googleapis.com/v1/token", expression)
        self.assertIn("firebase_token_refreshed", expression)
        self.assertIn("expirationTime", expression)
        self.assertIn("readwrite", expression)


if __name__ == "__main__":
    unittest.main()
