import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
ENTRYPOINT = ROOT / "skills/earn/line-sticker/line-sticker-factory.sh"


class FactoryWrapperIdleTimeout(unittest.TestCase):
    def run_factory_wrapper(self, *, inherited_timeout: str | None) -> str:
        with tempfile.TemporaryDirectory(dir=ENTRYPOINT.parent) as tmp:
            root = Path(tmp)
            state = root / "state"
            state.mkdir()
            (state / ".env").write_text("FAL_KEY=test\nGEMINI_API_KEY=test\n", encoding="utf-8")

            output = root / "timeout.txt"
            fake_python = root / "python"
            fake_python.write_text(
                "#!/bin/sh\n"
                "printf '%s' \"${AGENT_BROWSER_IDLE_TIMEOUT_MS:-unset}\" > \"$CAPTURE\"\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            env = os.environ.copy()
            env.pop("AGENT_BROWSER_IDLE_TIMEOUT_MS", None)
            if inherited_timeout is not None:
                env["AGENT_BROWSER_IDLE_TIMEOUT_MS"] = inherited_timeout
            env.update({
                "CAPTURE": str(output),
                "LIFE_MANAGER_PYTHON": str(fake_python),
                "LIFE_MANAGER_REPO": str(ROOT),
                "LIFE_MANAGER_STATE_HOME": str(state),
            })
            result = subprocess.run(
                ["bash", str(ENTRYPOINT)], env=env, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return output.read_text(encoding="utf-8")

    def test_launchd_environment_gets_fifteen_minute_default(self) -> None:
        self.assertEqual(self.run_factory_wrapper(inherited_timeout=None), "900000")

    def test_explicit_timeout_override_is_preserved(self) -> None:
        self.assertEqual(self.run_factory_wrapper(inherited_timeout="1200000"), "1200000")


if __name__ == "__main__":
    unittest.main()
