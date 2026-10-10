"""2026-10-10: Capafy CP1 rejects SVG logos ("PNG/JPG/WebP 形式のみ対応しています"); 39 catalog
candidates had only icon.svg, so every new submission stopped as a draft and occupied a review slot."""
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[2] / "capafy" / "catalog"
# FROZEN seller (skills/capafy/FROZEN.json): only Dais changes it, so its catalog icon is left as is.
FROZEN_DIRS = {"youtube-script-writer"}


def test_every_catalog_candidate_has_a_raster_logo():
    missing = [
        d.name for d in sorted(CATALOG.iterdir())
        if d.is_dir() and d.name not in FROZEN_DIRS
        and not any((d / f"icon.{ext}").is_file() for ext in ("png", "jpg", "webp"))
    ]
    assert missing == []
