#!/usr/bin/env python3
"""Print safe public missing-evidence report; NEVER unblocks real effects."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.field_readiness import examine_authority_packet


def main():
    source=Path(__file__).resolve().parents[1]/"pilot/PHASE06_AUTHORITY_READINESS.json"
    data=json.loads(source.read_text(encoding="utf-8"))
    print(json.dumps(examine_authority_packet(data),indent=2,sort_keys=True))
    print("F004 and F007 are NOT authorized; no payments or physical actuation performed.")


if __name__=="__main__":
    main()
