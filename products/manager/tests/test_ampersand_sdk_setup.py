"""Focused setup checks for the optional Ampersand SDK adapter."""
from __future__ import annotations

import importlib.util
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

FIXTURE_API_KEY = "hak_" + ("a" * 12)


class AmpersandClientSetupTests(unittest.TestCase):
    def _fake_openai(self):
        module = ModuleType("openai")
        module.OpenAI = Mock(name="OpenAI")
        return module

    def test_exact_supported_version_keeps_existing_client_arguments(self):
        from manager_core import ampersand_api

        openai = self._fake_openai()
        with patch("importlib.metadata.version", return_value="3.24.0"), \
                patch.dict("sys.modules", {"openai": openai}):
            client = ampersand_api.make_client(
                FIXTURE_API_KEY, timeout=37)

        self.assertIs(client, openai.OpenAI.return_value)
        openai.OpenAI.assert_called_once_with(
            base_url=ampersand_api.BASE_URL,
            api_key=FIXTURE_API_KEY,
            max_retries=0,
            timeout=37,
        )

    def test_incompatible_version_fails_safely_before_client_construction(self):
        from manager_core import ampersand_api

        openai = self._fake_openai()
        for unsupported in ("3.23.9", "3.24.1", "3.24.0+local-private"):
            with self.subTest(version=unsupported):
                with patch("importlib.metadata.version", return_value=unsupported), \
                        patch.dict("sys.modules", {"openai": openai}):
                    with self.assertRaises(ampersand_api.SessionFailure) as raised:
                        ampersand_api.make_client(FIXTURE_API_KEY)

                self.assertEqual(
                    str(raised.exception),
                    "openai==3.24.0 is required for live inference",
                )
                self.assertNotIn(unsupported, str(raised.exception))
                openai.OpenAI.assert_not_called()

    def test_missing_distribution_fails_safely_before_client_construction(self):
        from manager_core import ampersand_api

        openai = self._fake_openai()
        missing = PackageNotFoundError("private /path/package-metadata-detail")
        with patch("importlib.metadata.version", side_effect=missing), \
                patch.dict("sys.modules", {"openai": openai}):
            with self.assertRaises(ampersand_api.SessionFailure) as raised:
                ampersand_api.make_client(FIXTURE_API_KEY)

        self.assertEqual(
            str(raised.exception),
            "openai==3.24.0 is required for live inference",
        )
        self.assertNotIn("private /path", str(raised.exception))
        openai.OpenAI.assert_not_called()

    def test_invalid_inputs_fail_before_sdk_metadata_lookup(self):
        from manager_core import ampersand_api

        with patch("importlib.metadata.version") as version:
            with self.assertRaises(ValueError):
                ampersand_api.make_client("bad")
            with self.assertRaises(ValueError):
                ampersand_api.make_client(FIXTURE_API_KEY, timeout=181)

        version.assert_not_called()

    def test_importing_adapter_does_not_query_or_import_optional_sdk(self):
        from manager_core import ampersand_api

        probe_name = "manager_core._ampersand_optional_import_probe"
        spec = importlib.util.spec_from_file_location(
            probe_name, ampersand_api.__file__)
        probe = importlib.util.module_from_spec(spec)
        import sys

        sys.modules[probe_name] = probe
        with patch("importlib.metadata.version") as version, \
                patch.dict("sys.modules", {"openai": None}):
            try:
                spec.loader.exec_module(probe)
            finally:
                sys.modules.pop(probe_name, None)

        version.assert_not_called()

    def test_optional_requirement_matches_the_checked_sdk_version(self):
        from manager_core import ampersand_api

        requirement = (Path(__file__).resolve().parents[1] /
                       "requirements-ampersand.txt").read_text().strip()
        self.assertEqual(requirement, f"openai=={ampersand_api.OPENAI_SDK_VERSION}")


if __name__ == "__main__":
    unittest.main()
