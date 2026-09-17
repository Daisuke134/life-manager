import unittest

from job_search_loop.mercor_auth_readback import classify_auth_snapshot


class MercorAuthReadbackTests(unittest.TestCase):
    def test_requires_authenticated_official_surface(self):
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/explore",
            visible_text="Explore Applications Earnings Profile",
            login_form_visible=False,
        ), "authenticated")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/explore",
            visible_text="Explore Profile Sign in",
            login_form_visible=False,
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
            url="https://work.mercor.com/jobs/apply/candidate-one?returnPath=%2Fexplore",
            visible_text=(
                "General business strategy Evaluator Application\n"
                "3 of 3 steps done\nWork Authorization\n"
                "Your application has been submitted!\nView application"
            ),
            login_form_visible=False,
        ), "authenticated")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/jobs/apply/candidate-one?returnPath=%2Fexplore",
            visible_text="Sign in to continue your application",
            login_form_visible=True,
        ), "logged_out")
        self.assertEqual(classify_auth_snapshot(
            url="https://example.com/",
            visible_text="Explore Applications Earnings Profile",
        ), "indeterminate")


if __name__ == "__main__":
    unittest.main()
