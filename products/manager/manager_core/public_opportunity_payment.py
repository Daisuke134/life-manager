"""Project one independently pinned public D011 opportunity snapshot."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from manager_core.models.source import Source

SOURCE_ID = "jhipster-d011-aggregate-20261023"
SNAPSHOT_URL = (
    "https://raw.githubusercontent.com/Daisuke134/life-manager/"
    "64914b52904a4a4338fdfa3f2f688cd0843a472c/"
    "products/manager/docs/research/JHIPSTER_D011_SOURCE_20261023.json"
)
SNAPSHOT_SHA256 = "0f6cc6343ca17b24c3f55061e6f38a367d3dde29cc81d0172089106723e2062e"
MAX_PACKET_BYTES = 32768


def connect_published_opportunity(packet_bytes: bytes, packet_source: Source) -> dict:
    """Return the minimal facts and limitations from the reviewed frozen packet.

    The caller supplies already acquired packet bytes. This adapter performs no
    I/O and makes no claim about recipient settlement, Manager income, or net
    benefit.
    """
    if type(packet_bytes) is not bytes or len(packet_bytes) > MAX_PACKET_BYTES:
        raise ValueError("bounded packet bytes required")
    if type(packet_source) is not Source:
        raise ValueError("actual Source provenance required")
    if packet_source.source_id != SOURCE_ID or packet_source.url != SNAPSHOT_URL:
        raise ValueError("source does not identify the reviewed aggregate snapshot")

    # Verify caller-supplied provenance, then independently enforce the
    # reviewed pin so rehashing changed facts cannot admit a replacement.
    packet_source.verify_content(packet_bytes)
    if sha256(packet_bytes).hexdigest() != SNAPSHOT_SHA256:
        raise ValueError("packet differs from independently reviewed snapshot")

    try:
        packet = json.loads(packet_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid reviewed packet encoding") from exc
    if not isinstance(packet, dict):
        raise ValueError("reviewed packet must be an object")

    payment = deepcopy(packet["platform_payment"])
    return {
        "opportunity_id": packet["opportunity_id"],
        "subject_scope": packet["subject_scope"],
        "public_artifact": deepcopy(packet["public_artifact"]),
        "platform_payment": payment,
        "public_paid_amount_minor": payment["expense_amount_minor"],
        "crosslinks": deepcopy(packet["crosslinks"]),
        "prior_posting": deepcopy(packet["prior_posting"]),
        "raw_sources": deepcopy(packet["raw_sources"]),
        "unknown_costs": deepcopy(packet["unknown_costs"]),
        "claim_limits": deepcopy(packet["claim_limits"]),
        "limitations": deepcopy(packet["limitations"]),
        "limited_rights": deepcopy(packet["limited_rights"]),
        "attribution": packet["attribution"],
        "extraction": deepcopy(packet["extraction"]),
        "packet_source": {
            "source_id": SOURCE_ID,
            "url": SNAPSHOT_URL,
            "content_sha256": SNAPSHOT_SHA256,
            "retrieved_at": packet_source.retrieved_at.isoformat(),
        },
        "proof_level": "P0",
        "action": "NO_ACTION",
        "income_status": "NOT_VERIFIED",
        "human_welfare_status": "NOT_MEASURED",
        "verified_income_increase_minor": None,
        "verified_net_benefit_minor": None,
        "chain_completeness": "INCOMPLETE_PRIOR_POSTING_UNKNOWN",
    }
