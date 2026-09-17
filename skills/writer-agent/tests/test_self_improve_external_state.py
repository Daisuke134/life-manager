import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
WRAPPER = ROOT / "scripts" / "article-selfimprove-verify.sh"


def test_self_improve_verify_forwards_external_state_root(tmp_path: Path) -> None:
    skill_dir = tmp_path / "release" / "skills" / "writer-agent"
    state_dir = tmp_path / "state"
    skill_dir.joinpath("scripts").mkdir(parents=True)
    recorder = skill_dir / "scripts" / "self_improve_control.py"
    recorder.write_text(
        "import json, os, sys\n"
        "open(os.environ['ARGS_FILE'], 'w').write(json.dumps(sys.argv[1:]))\n"
        "print('{\"missing_count\":0}')\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "ARTICLE_SKILL_DIR": str(skill_dir),
        "ARTICLE_STATE_DIR": str(state_dir),
        "ARGS_FILE": str(tmp_path / "args.json"),
    }

    result = subprocess.run(
        ["bash", str(WRAPPER)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(Path(env["ARGS_FILE"]).read_text(encoding="utf-8")) == [
        "verify",
        "--skill-dir",
        str(skill_dir),
        "--state-dir",
        str(state_dir),
    ]
