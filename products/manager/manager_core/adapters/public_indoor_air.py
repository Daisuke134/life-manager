"""Privacy-minimized third-party indoor observations, not a live actuation grant.

Reads only a fixed AirGradient opt-in indoor Map API endpoint. Public data
access is NOT unrestricted reuse rights and says nothing about who performed
an intervention, whether a building improved, or whether a resident benefited.
Raw location identifiers/coordinates are never retained or returned.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
from math import isfinite
from urllib.request import Request, urlopen


API_URL = "https://map-data.airgradient.com/map/api/v1/indoor/measurements/current?pagesize=2&page=1"


class IndoorAirUnverified(ValueError):
    """Missing, untrustworthy, out-of-date or unparseable external observation."""


@dataclass(frozen=True)
class IndoorAirAggregate:
    provider: str
    source_url: str
    observed_at: datetime
    sample_count: int
    missing_count: int
    mean_pm25_ug_m3: float
    content_sha256: str
    privacy_class: str = "public_opt_in_aggregate"
    data_rights: str = "REVIEW_BEFORE_REUSE"
    field_intervention_status: str = "NOT_MEASURED"
    proof_level: str = "P0"


class PublicIndoorAirObservations:
    """Network use is read-only GET. No configurable URL, key or sensor identity."""

    def __init__(self, *, opener=None):
        self._open = opener if opener is not None else urlopen

    def read(self, *, at: datetime) -> IndoorAirAggregate:
        if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone-aware read time required")
        request = Request(API_URL, method="GET", headers={
            "Accept": "application/json",
            "User-Agent": "Manager-Research-Indoor-ReadOnly/0.1"
        })
        try:
            with self._open(request, timeout=12) as response:
                raw=response.read(65537)
            if not isinstance(raw,bytes) or len(raw)>65536:
                raise IndoorAirUnverified("bounded provider JSON required")
            parsed=json.loads(raw)
            if not isinstance(parsed,dict):
                raise IndoorAirUnverified("wrong data type")
            rows=parsed["data"]
            if (not isinstance(rows,list) or not rows or len(rows)>2
                or type(parsed.get("total")) is not int or parsed["total"]<len(rows)
                or parsed.get("page") != 1 or parsed.get("pagesize") != 2):
                raise IndoorAirUnverified("invalid sampling frame")
            observations=[]
            missing=0
            for row in rows:
                if not isinstance(row,dict):
                    raise IndoorAirUnverified("invalid monitoring object")
                source=row.get("dataSource")
                if source != "AirGradient":
                    raise IndoorAirUnverified("unattributed or unrecognized indoor data source")
                stamp=datetime.fromisoformat(row["measuredAt"].replace("Z","+00:00"))
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise IndoorAirUnverified("timezone-free reading")
                if stamp>at+timedelta(minutes=10):
                    raise IndoorAirUnverified("future dated provider sample")
                if stamp<at-timedelta(hours=48):
                    continue  # stale not equivalent to an acceptable zero
                pm=row.get("pm25")
                if pm is None:
                    missing+=1
                    continue
                if type(pm) not in (int,float) or not isfinite(pm) or not 0<=pm<=1000:
                    raise IndoorAirUnverified("invalid PM2.5 observation")
                observations.append((str(source),stamp,float(pm)))
            if not observations:
                raise IndoorAirUnverified("no fresh nonmissing PM2.5 readings")
            digest_input=json.dumps(sorted(
                (source,stamp.isoformat(),value) for source,stamp,value in observations
            ),separators=(",",":"),ensure_ascii=False).encode()
            return IndoorAirAggregate(
                provider="AirGradient",
                source_url=API_URL,
                observed_at=max(x[1] for x in observations),
                sample_count=len(observations),
                missing_count=missing,
                mean_pm25_ug_m3=round(sum(x[2] for x in observations)/len(observations),4),
                content_sha256=sha256(digest_input).hexdigest()
            )
        except IndoorAirUnverified:
            raise
        except Exception:
            # No raw response or private identifiers in errors.
            raise IndoorAirUnverified("external indoor air response UNKNOWN") from None
