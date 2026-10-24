import subprocess
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "codex-limit-fallback-env.sh"
ROOT = Path(__file__).resolve().parents[4]
CUTOFF = 1793415600  # 2026-10-31 12:00 JST


def _run(tmp_path, *, now: int, with_config: bool = True) -> str:
    repo = tmp_path / "repo"
    (repo / "runtime/agent-runner").mkdir(parents=True, exist_ok=True)
    if with_config:
        (repo / "runtime/agent-runner/config.codex-limit-fallback.json").write_text("{}")
    script = (
        f'date() {{ if [ "$1" = "-u" ]; then echo {now}; else command date "$@"; fi; }}\n'
        f'source "{HELPER}"\n'
        f'capafy_use_codex_limit_fallback "{repo}"\n'
        'printf "%s" "${AGENT_RUNNER_CONFIG:-}"\n'
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True,
                          env={"PATH": "/usr/bin:/bin"}).stdout


def test_fallback_config_is_used_before_the_cutoff(tmp_path) -> None:
    assert _run(tmp_path, now=CUTOFF - 1).endswith("runtime/agent-runner/config.codex-limit-fallback.json")


def test_default_config_applies_again_at_and_after_the_cutoff(tmp_path) -> None:
    assert _run(tmp_path, now=CUTOFF) == ""
    assert _run(tmp_path, now=CUTOFF + 86400) == ""


def test_missing_fallback_file_leaves_the_default_untouched(tmp_path) -> None:
    assert _run(tmp_path, now=CUTOFF - 1, with_config=False) == ""


def test_both_capafy_loops_source_the_helper_and_the_cutoff_matches_codex_return() -> None:
    loops = [HELPER.parent / "capafy-distribute-daily.sh", HELPER.parent / "capafy-reel-daily.sh",
             ROOT / "skills/self/capafy-loop/capafy-loop-daily.sh"]
    for path in loops:
        text = path.read_text()
        assert "codex-limit-fallback-env.sh" in text and "capafy_use_codex_limit_fallback" in text, path.name
    assert (ROOT / "runtime/agent-runner/config.codex-limit-fallback.json").exists()
