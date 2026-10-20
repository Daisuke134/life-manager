"""Offline-only project self-check."""
import json
from dataclasses import asdict
from . import __version__
from .config import DEFAULTS


def main():
    print(json.dumps({
        "product": "Manager",
        "version": __version__,
        "phase": "offline-research-and-learning",
        "runtime_defaults": asdict(DEFAULTS),
        "real_world_interventions": 0,
        "human_impact_claims": 0,
    }, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
