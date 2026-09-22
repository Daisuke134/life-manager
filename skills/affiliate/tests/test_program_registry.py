import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "program_registry.py"
SPEC = importlib.util.spec_from_file_location("affiliate_program_registry", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReadbackPage:
    def __init__(self, observed):
        self.observed = observed
        self.navigations = []
        self.ui_reads = 0

    def goto(self, url, **_kwargs):
        self.navigations.append(url)

    def evaluate(self, _script):
        return self.observed

    def get_by_text(self, *_args, **_kwargs):
        self.ui_reads += 1
        raise AssertionError("official readback must stop before link-form UI")


def fake_playwright(page):
    class Playwright:
        def __enter__(self):
            browser = types.SimpleNamespace(
                contexts=[types.SimpleNamespace(pages=[page])],
            )
            self.chromium = types.SimpleNamespace(
                connect_over_cdp=lambda _url: browser,
            )
            return self

        def __exit__(self, *_args):
            return False

    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = Playwright
    playwright = types.ModuleType("playwright")
    playwright.sync_api = sync_api
    return patch.dict(sys.modules, {
        "playwright": playwright,
        "playwright.sync_api": sync_api,
    })


class ProgramRegistryTest(unittest.TestCase):
    def test_partnerstack_unauthorized_stops_before_link_form_or_effect(self):
        for http_status in (401, 403):
            with self.subTest(http_status=http_status):
                page = ReadbackPage({
                    "state": "AUTH_REQUIRED",
                    "partnership_http": http_status,
                    "ensure_http": None,
                    "items": [],
                })

                with tempfile.TemporaryDirectory() as temporary:
                    state = Path(temporary) / "state"
                    private = Path(temporary) / "credentials.md"
                    private.write_text(
                        "## ElevenLabs\n- Login: owner@example.com\n- Password: secret\n",
                        encoding="utf-8",
                    )
                    private.chmod(0o600)
                    with fake_playwright(page):
                        receipt = MODULE.elevenlabs_link_action(
                            state, 9324, private, "campaign-one", create=True,
                            title="Campaign one", description="A decision guide.",
                        )

                    self.assertEqual(receipt["state"], "AUTH_REQUIRED")
                    self.assertEqual(receipt["reason"], "PARTNERSTACK_AUTH_REQUIRED")
                    self.assertEqual(receipt["provider_http_status"], http_status)
                    self.assertFalse(receipt["provider_effect_started"])
                    self.assertFalse(receipt["changed"])
                    self.assertEqual(page.ui_reads, 0)
                    self.assertEqual(
                        page.navigations,
                        [MODULE.ELEVENLABS_LINKS, MODULE.ELEVENLABS_HOME],
                    )
                    stored = json.loads((
                        state / "program-links" / "campaign-one.json"
                    ).read_text(encoding="utf-8"))
                    self.assertEqual(stored, receipt)
                    self.assertTrue({
                        "schema_version", "receipt_type", "provider", "state",
                        "reason", "placement", "provider_http_status",
                        "provider_effect_started", "changed", "observed_at",
                    }.issuperset(stored))

    def test_existing_partnerstack_link_verifies_without_link_form(self):
        page = ReadbackPage({
            "state": "READY",
            "partnership_http": 200,
            "ensure_http": 200,
            "items": [{
                "key": "link-key-1",
                "tracking_custom_link_id": "tracking-1",
                "slug": "campaign-one",
                "url": "https://try.elevenlabs.io/campaign-one",
                "dest": "https://elevenlabs.io",
            }],
        })

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            private = Path(temporary) / "credentials.md"
            private.write_text(
                "## ElevenLabs\n- Login: owner@example.com\n- Password: secret\n",
                encoding="utf-8",
            )
            private.chmod(0o600)
            with fake_playwright(page):
                receipt = MODULE.elevenlabs_link_action(
                    state, 9324, private, "campaign-one", create=True,
                    title="Campaign one", description="A decision guide.",
                )

            self.assertEqual(receipt["state"], "VERIFIED")
            self.assertTrue(receipt["deduplicated"])
            self.assertEqual(receipt["provider_link_key"], "link-key-1")
            self.assertEqual(page.ui_reads, 0)
            self.assertIn(
                "- Placement 27f8a68166e22555 affiliate link: "
                "https://try.elevenlabs.io/campaign-one",
                private.read_text(encoding="utf-8"),
            )

    def test_store_login_replaces_only_login_and_keeps_private_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "credentials.md"
            path.write_text(
                "## Impact\n- Login: broken-description\n- Password: keep-secret\n"
                "\n## Other\n- Login: untouched@example.com\n",
                encoding="utf-8",
            )
            path.chmod(0o600)
            result = MODULE.store_login("Impact", path, "owner@example.com")
            text = path.read_text(encoding="utf-8")
            self.assertEqual(result["private_markdown_login_state"], "VERIFIED_NONEMPTY")
            self.assertIn("- Login: owner@example.com", text)
            self.assertIn("- Password: keep-secret", text)
            self.assertIn("- Login: untouched@example.com", text)
            self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_network_section_inherits_login_but_not_password(self):
        source = "## ElevenLabs\n- Login: owner@example.com\n- Password: original\n"
        result = MODULE.ensure_credential_section(
            source, "PartnerStack", "ElevenLabs",
            "keychain://ai.anicca.affiliate.provider.partnerstack/elevenlabs",
        )
        partner = result.split("## PartnerStack", 1)[1]
        self.assertIn("- Login: owner@example.com", partner)
        self.assertIn("- Password: \n", partner)
        self.assertNotIn("original", partner)

    def test_store_link_adds_only_private_affiliate_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "credentials.md"
            path.write_text(
                "## ElevenLabs\n- Login: owner@example.com\n- Password: keep-secret\n",
                encoding="utf-8",
            )
            path.chmod(0o600)
            link = "https://example.test/private-referral"
            result = MODULE.store_link(
                "ElevenLabs", "ElevenAgents affiliate link", path, link,
            )
            text = path.read_text(encoding="utf-8")
            self.assertEqual(result["private_markdown_link_state"], "VERIFIED_NONEMPTY")
            self.assertNotIn(link, str(result))
            self.assertIn(f"- ElevenAgents affiliate link: {link}", text)
            self.assertIn("- Password: keep-secret", text)
            self.assertEqual(path.stat().st_mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
