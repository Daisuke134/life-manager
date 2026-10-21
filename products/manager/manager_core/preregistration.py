"""F002: immutable offline preregistration DESIGN contract, not proof of field study."""
from hashlib import sha256
from hmac import compare_digest
import re


def verify_preregistration_lock(payload: bytes, expected_sha256: str) -> bool:
    if not isinstance(payload, bytes) or not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}",expected_sha256):
        raise ValueError("valid immutable SHA256 lock required")
    if not compare_digest(sha256(payload).hexdigest(),expected_sha256):
        raise ValueError("preregistration hash mismatch; new version required")
    return True


def validate_preregistration(x: dict) -> bool:
    if not isinstance(x, dict):
        raise ValueError("study must be a dictionary")
    required={"study_id","version","status","live_pilot_authorized","proof_level",
              "scenario","domain","target_candidate","hypothesis","eligibility","design",
              "assignment","primary_outcome","comparator","harms","stop_rules","publication",
              "source_urls","status_reason"}
    if set(x)!=required:
        raise ValueError("missing/unknown study fields")
    if (x["version"]!=1 or type(x["version"]) is not int or
        x["status"]!="PREREGISTERED_DESIGN_ONLY" or
        x["live_pilot_authorized"] is not False or x["proof_level"]!="P0"):
        raise ValueError("this is only a non-live research design")
    if x["domain"]!="finance" or x["target_candidate"]!="OPEN_LEDGER_SUPPORT":
        raise ValueError("wrong domain")
    for k in ("study_id","scenario","hypothesis","eligibility","publication","status_reason"):
        if not isinstance(x[k],str) or not x[k].strip():
            raise ValueError("blank study identity/description")
    d=x["design"]
    if not isinstance(d,dict):
        raise ValueError("invalid study design")
    n=d.get("n_campaigns_total")
    if (type(n) is not int or n<40 or type(d.get("n_treatment")) is not int
        or type(d.get("n_control")) is not int or
        d["n_treatment"]+d["n_control"]!=n or
        d["n_treatment"]!=d["n_control"] or
        d.get("n_is_powered") is not False or
        d.get("currency")!="USD" or
        d.get("report_negative_and_null_results") is not True):
        raise ValueError("invalid sample, no-action comparison, or unsupported power claim")
    for name in ("baseline_days","treatment_days","settlement_followup_days"):
        if type(d.get(name)) is not int or d[name]<1:
            raise ValueError("duration is required")
    a=x["assignment"]
    if (not isinstance(a,dict) or a.get("method")!="prospective_cluster_randomization"
        or a.get("no_action_arm")!="NO_ACTION" or a.get("randomized_unit")!="distinct public campaign, not individual donors"
        or a.get("ratio")!="1:1"):
        raise ValueError("randomized NO_ACTION arm required")
    o=x["primary_outcome"]
    if (not isinstance(o,dict) or o.get("name")!="incremental_net_confirmed_third_party_contributions"
        or o.get("unit")!="USD_cents_per_campaign"):
        raise ValueError("fixed primary net-contribution outcome required")
    if not all(isinstance(o.get(k),str) and o[k].strip()
               for k in ("estimand","data_source","measurement_window","missing_data")):
        raise ValueError("complete outcome and missing data required")
    c=x["comparator"]
    if not isinstance(c,dict) or c.get("type")!="concurrently randomized no-action campaigns":
        raise ValueError("explicit real comparator required")
    if not all(isinstance(c.get(k),str) and c[k].strip()
               for k in ("unit","statistical_plan","uncertainty_rule","displacement")):
        raise ValueError("comparator uncertainty required")
    if not isinstance(x["harms"],list) or len(x["harms"])<5 or not all(isinstance(v,str) and v for v in x["harms"]):
        raise ValueError("harm accounting must not be missing")
    if not isinstance(x["stop_rules"],list) or len(x["stop_rules"])<3:
        raise ValueError("stopping rules missing")
    if not isinstance(x["source_urls"],list) or not x["source_urls"] or any(
        not isinstance(v,str) or not v.startswith("https://") for v in x["source_urls"]):
        raise ValueError("source references missing")
    return True
