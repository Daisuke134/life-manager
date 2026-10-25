"""scripts/ledger-check.sh: fail closed, key = platform:id across every owner/account.

2026-10-26: the Lancers loop (keiodaisuke) sent proposal 28079351 to project 5620321 while another account
already held 28078288 for the same project. The old script swallowed a failed pull and matched by substring.
"""
import os
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "ledger-check.sh"
HEADER = "| 日付 | 種別 | 内容 | key | owner | status | 備考 |\n|---|---|---|---|---|---|---|\n"


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def _repo(tmp_path, rows=""):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    (work / "scripts").mkdir()
    shutil.copy(SCRIPT, work / "scripts" / "ledger-check.sh")
    (work / "ledger").mkdir()
    (work / "ledger" / "APPLICATIONS.md").write_text(HEADER + rows)
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "init")
    _git(work, "push", "-q", "-u", "origin", "HEAD:main")
    return work, origin


def _run(work, key):
    return subprocess.run(["bash", str(work / "scripts" / "ledger-check.sh"), key],
                          capture_output=True, text=True)


def _row(key, owner="参謀", status="applied"):
    return f"| 2026-10-26 | gig | Lancers x | {key} | {owner} | {status} | n |\n"


def test_free_when_the_key_is_absent_and_the_ledger_is_fresh(tmp_path):
    work, _ = _repo(tmp_path, _row("lancers:111"))
    result = _run(work, "lancers:222")
    assert result.returncode == 0 and "FREE" in result.stdout


def test_busy_for_the_same_platform_id_whatever_the_owner(tmp_path):
    work, _ = _repo(tmp_path, _row("lancers:5620321", owner="参謀"))
    result = _run(work, "lancers:5620321")
    assert result.returncode == 1 and "BUSY" in result.stderr


def test_a_longer_id_does_not_collide_by_substring(tmp_path):
    work, _ = _repo(tmp_path, _row("lancers:56203219"))
    assert _run(work, "lancers:5620321").returncode == 0


def test_unknown_send_result_blocks_until_reconciled(tmp_path):
    work, _ = _repo(tmp_path, _row("lancers:777", status="unknown"))
    result = _run(work, "lancers:777")
    assert result.returncode == 1 and "BUSY" in result.stderr


def test_pull_failure_never_returns_free(tmp_path):
    work, origin = _repo(tmp_path, _row("lancers:111"))
    shutil.rmtree(origin)
    result = _run(work, "lancers:222")
    assert result.returncode == 3 and "FREE" not in result.stdout


def test_unreadable_ledger_never_returns_free(tmp_path):
    work, _ = _repo(tmp_path, _row("lancers:111"))
    (work / "ledger" / "APPLICATIONS.md").unlink()
    _git(work, "commit", "-aqm", "rm")
    _git(work, "push", "-q", "origin", "HEAD:main")
    result = _run(work, "lancers:222")
    assert result.returncode == 3 and "FREE" not in result.stdout
