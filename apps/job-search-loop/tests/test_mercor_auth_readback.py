import inspect
import unittest
import asyncio
import json

import pytest

from job_search_loop import mercor_auth_readback as auth

from job_search_loop.mercor_auth_readback import (
    auth_snapshot_expression,
    classify_auth_snapshot,
    observe,
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
            firebase_token_expired=True,
            firebase_token_refresh_failed=True,
        ), "indeterminate")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/explore",
            visible_text="Explore Applications Earnings Profile",
            login_form_visible=False,
            authenticated_api_status=200,
            firebase_token_refresh_invalid=True,
        ), "logged_out")
        self.assertEqual(classify_auth_snapshot(
            url="https://work.mercor.com/explore",
            visible_text="Explore Applications Earnings Profile",
            login_form_visible=False,
            authenticated_api_status=200,
            firebase_token_refreshed=True,
            firebase_navigation_verified=False,
        ), "indeterminate")
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
        self.assertIn("profile_surface_visible", expression)
        self.assertIn("textarea#summary", expression)
        self.assertIn("Page.reload", inspect.getsource(observe))
        self.assertIn("https://work.mercor.com/profile?tab=resume", inspect.getsource(observe))
        self.assertIn("firebase_profile_readback_verified", inspect.getsource(observe))


if __name__ == "__main__":
    unittest.main()


@pytest.mark.parametrize("matched,status", [(True, "authenticated"), (False, "indeterminate"), (None, "indeterminate")])
def test_observe_binds_the_session_to_the_expected_email(monkeypatch, matched, status):
    expressions = []

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

    async def call(_ws, _request_id, method, params):
        assert method == "Runtime.evaluate"
        expressions.append(params["expression"])
        return {"result": {"value": json.dumps({
            "url": "https://work.mercor.com/explore", "text": "Explore Applications Profile",
            "authenticated_api_status": 200, "firebase_identity_matched": matched,
        })}}

    monkeypatch.setattr(auth.websockets, "connect", lambda *_args, **_kwargs: Connection())
    monkeypatch.setattr(auth, "_call", call)

    result = asyncio.run(observe("ws://127.0.0.1/devtools/page/fixture", expected_email="owner@fixture.invalid"))

    assert result["status"] == status
    assert result["firebase_identity_matched"] is matched
    assert 'const expectedEmail="owner@fixture.invalid"' in expressions[0]


def test_missing_expected_identity_does_not_open_a_browser(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("unbound browser observation is forbidden")

    monkeypatch.setattr(auth.websockets, "connect", forbidden)
    assert asyncio.run(observe("ws://127.0.0.1/devtools/page/fixture"))["status"] == "indeterminate"


@pytest.mark.parametrize("override", [None, "JOB_SEARCH_PROFILE", "MERCOR_PROFILE"])
def test_cli_reads_the_existing_private_profile_override(tmp_path, monkeypatch, capsys, override):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    for key in ("MERCOR_PROFILE", "JOB_SEARCH_PROFILE"):
        monkeypatch.delenv(key, raising=False)
    profile = tmp_path / ("private-profile.json" if override else ".config/anicca/job-search/profile.json")
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(json.dumps({"version": 1, "candidate": {
        "name": "Fixture owner", "application_email": "other-owner@fixture.invalid"},
        "facts": [{"id": "one", "claim": "fixture", "evidence": "fixture"}]}))
    if override:
        monkeypatch.setenv(override, str(profile))
    observed = []

    async def observe_bound(ws_url, *, expected_email=None):
        observed.append((ws_url, expected_email))
        return {"status": "authenticated", "firebase_identity_matched": True}

    monkeypatch.setattr(auth, "observe", observe_bound)
    output = tmp_path / "result.json"
    assert auth.main(["--ws", "ws://localhost/fixture", "--output", str(output)]) == 0
    assert observed == [("ws://localhost/fixture", "other-owner@fixture.invalid")]
    assert "other-owner@fixture.invalid" not in capsys.readouterr().out


def test_cli_missing_private_profile_is_indeterminate_without_observation(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "missing"))
    for key in ("MERCOR_PROFILE", "JOB_SEARCH_PROFILE"):
        monkeypatch.delenv(key, raising=False)

    async def forbidden(*_args, **_kwargs):
        pytest.fail("missing identity must not trigger login or observation")

    monkeypatch.setattr(auth, "observe", forbidden)
    output = tmp_path / "result.json"
    assert auth.main(["--ws", "ws://localhost/fixture", "--output", str(output)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "indeterminate"


def test_cli_explicit_email_passes_to_observation_without_printing_identity(tmp_path, monkeypatch, capsys):
    observed = []

    async def observe_bound(ws, *, expected_email):
        observed.append(expected_email)
        return {"status": "authenticated", "firebase_identity_matched": True}

    monkeypatch.setattr(auth, "observe", observe_bound)
    assert auth.main(["--ws", "ws://localhost/fixture", "--expected-email", "owner@fixture.invalid",
                      "--output", str(tmp_path / "output.json")]) == 0
    assert observed == ["owner@fixture.invalid"]
    assert "owner@fixture.invalid" not in capsys.readouterr().out
