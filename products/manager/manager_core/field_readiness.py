"""External permission evidence discovery, NOT an authorization or effect executor.

Even a fully populated checklist cannot issue an authority grant. Only an
independently validated issuer, legal rights and provider-specific scoped
credentials could eventually authorize a separate, reviewed live adapter.
The Phase05 kernel still forbids every real-world effect.
"""
from typing import Mapping


REQUIREMENTS={
    "finance":(
        "fiscal_host_or_operator_ref",
        "legal_entity_and_country_ref",
        "funding_custody_ref",
        "scoped_grant_ref",
        "grant_verified_by_operator_ref",
        "budget_currency_and_max_ref",
        "target_campaigns_and_rights_ref",
        "revocation_check_ref",
        "participant_consent_ref",
        "independent_receipt_source_ref",
        "external_preregistration_ref",
        "harm_displacement_plan_ref",
    ),
    "environment":(
        "site_owner_ref",
        "room_access_and_safety_ref",
        "permission_for_portable_actuation_ref",
        "independent_sensor_ref",
        "sensor_public_api_provenance_ref",
        "calibration_ref",
        "electricity_noise_measurement_ref",
        "stop_and_rollback_ref",
        "occupant_consent_ref",
        "independent_trial_review_ref",
    ),
}


def examine_authority_packet(bundle: Mapping) -> dict:
    if not isinstance(bundle,Mapping) or bundle.get("schema")!="manager.phase06.authority-readiness.v1":
        raise ValueError("proper Manager-only external readiness packet required")
    result={}
    for domain,fields in REQUIREMENTS.items():
        part=bundle.get(domain)
        if not isinstance(part,Mapping):
            raise ValueError("each domain needs its own external evidence")
        missing=tuple(field for field in fields
                      if not isinstance(part.get(field),str) or not part[field].strip())
        result[domain]={
            "status": "MISSING_EXTERNAL_EVIDENCE" if missing
                      else "AWAITING_INDEPENDENT_VALIDATION",
            "missing": list(missing),
            "can_execute": False,
            "action": "NO_ACTION",
            "verified_beneficiary_effect": "NOT_MEASURED"
        }
    return result
