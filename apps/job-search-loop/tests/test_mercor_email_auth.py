import json

import pytest

from job_search_loop import mercor_email_auth
from job_search_loop.mercor_email_auth import application_email, extract_action_url


def test_extracts_only_official_mercor_firebase_action_link():
    link = (
        "https://mercor-prod-firebase.firebaseapp.com/__/auth/action?"
        "mode=signIn&oobCode=private&continueUrl=https%3A%2F%2Fwork.mercor.com"
    )
    assert extract_action_url({"body": f"Continue to Mercor → ( {link} )"}) == link


@pytest.mark.parametrize("body", ["", "https://evil.example/auth/action?mode=signIn"])
def test_rejects_missing_or_unofficial_action_link(body):
    with pytest.raises(ValueError, match="mercor_magic_link_not_found"):
        extract_action_url({"body": body})


def test_reads_application_email_from_private_profile(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"candidate": {"application_email": "candidate@example.com"}}))
    assert application_email(profile) == "candidate@example.com"


def test_email_login_navigates_to_exact_official_login_before_filling():
    source = mercor_email_auth.Path(mercor_email_auth.__file__).read_text()
    navigate = '"Page.navigate", {"url": "https://work.mercor.com/login"}'
    fill = "document.querySelector('input[type=\"email\"][name=\"email\"]')"
    assert navigate in source
    assert source.index(navigate) < source.index(fill)


def test_magic_link_readback_uses_only_the_profile_gmail_account(monkeypatch):
    account = "another-owner@fixture.invalid"
    calls = []
    link = "https://mercor-prod-firebase.firebaseapp.com/__/auth/action?mode=signIn&oobCode=fixture"

    def read(command, **options):
        calls.append(command)
        assert command[command.index("--account") + 1] == account
        if "search" in command:
            return json.dumps({"messages": [{"id": "fixture-message"}]})
        return json.dumps({"message": {"internalDate": "2000000"}, "body": link})

    monkeypatch.setattr(mercor_email_auth.subprocess, "check_output", read)
    assert mercor_email_auth.newest_action_url(1000, account=account) == link
    assert len(calls) == 2


def test_magic_link_readback_uses_the_same_selected_gog_as_reply(monkeypatch):
    monkeypatch.setenv("JOB_SEARCH_GOG", "/synthetic-owner/tools/gog")
    commands = []
    link = "https://mercor-prod-firebase.firebaseapp.com/__/auth/action?mode=signIn&oobCode=fixture"

    def read(command, **options):
        commands.append(command)
        assert command[0] == "/synthetic-owner/tools/gog"
        return (json.dumps({"messages": [{"id": "fixture-message"}]}) if "search" in command else
                json.dumps({"message": {"internalDate": "2000000"}, "body": link}))

    monkeypatch.setattr(mercor_email_auth.subprocess, "check_output", read)
    assert mercor_email_auth.newest_action_url(1000, account="owner@fixture.invalid") == link
    assert len(commands) == 2


def test_email_login_cli_passes_the_profile_account_to_magic_link_readback(tmp_path, monkeypatch, capsys):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"candidate": {"application_email": "another-owner@fixture.invalid"}}))
    observed = []

    async def request(ws, email):
        observed.append(("request", email))

    def newest(epoch, *, account):
        observed.append(("read", account))
        return "fixture-link"

    async def authenticate(ws, link):
        return {"status": "authenticated"}

    monkeypatch.setattr(mercor_email_auth, "request_email_login", request)
    monkeypatch.setattr(mercor_email_auth, "newest_action_url", newest)
    monkeypatch.setattr(mercor_email_auth, "authenticate", authenticate)
    assert mercor_email_auth.main(["--ws", "ws://localhost/fixture", "--after-epoch", "1000",
                                  "--profile", str(profile), "--output", str(tmp_path / "output.json")]) == 0
    assert observed == [("request", "another-owner@fixture.invalid"), ("read", "another-owner@fixture.invalid")]
    assert "another-owner@fixture.invalid" not in capsys.readouterr().out
