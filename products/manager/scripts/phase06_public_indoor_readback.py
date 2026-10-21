#!/usr/bin/env python3
"""Independent opt-in public indoor air readback; NOT an indoor intervention."""
from datetime import datetime,timezone
from pathlib import Path
from dataclasses import asdict
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.adapters.public_indoor_air import PublicIndoorAirObservations,IndoorAirUnverified


def main():
    try:
        obs=PublicIndoorAirObservations().read(at=datetime.now(timezone.utc))
    except IndoorAirUnverified as err:
        raise SystemExit(f"F007_READ_ONLY_PROVIDER_UNKNOWN: {err}") from None
    values=asdict(obs)
    values["observed_at"]=obs.observed_at.isoformat()
    print(json.dumps(values,sort_keys=True,indent=2))
    print("NO_ACTION: independent opt-in data is not evidence of an authorized site or intervention.")


if __name__=="__main__":
    main()
