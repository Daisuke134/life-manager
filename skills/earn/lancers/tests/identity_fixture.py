"""Synthetic local-user input for isolated Lancers tests."""
import json
from pathlib import Path


PROFILE = {
    "version": 1,
    "candidate": {"name": "別の利用者"},
    "facts": [{"id": "automation", "claim": "業務自動化を実装できる", "evidence": "本人の検証記録"}],
}
PROVIDER = {"account_id": "other-seller"}


def write_identity(home: Path) -> tuple[Path, Path]:
    paths = (home / ".config/anicca/job-search/profile.json",
             home / ".config/anicca/lancers/public-profile.json")
    for path, value in zip(paths, (PROFILE, PROVIDER)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return paths
