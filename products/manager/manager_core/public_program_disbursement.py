"""Connect one independently pinned public D003 aggregate snapshot."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from manager_core.models.source import Source

SOURCE_ID = "givedirectly-d003-aggregate-20261023"
SNAPSHOT_URL = (
    "https://raw.githubusercontent.com/Daisuke134/life-manager/"
    "71c42c559ba416a85e60f10ba510298b4ceea44c/"
    "products/manager/docs/research/GIVEDIRECTLY_D003_SOURCE_20261023.json"
)
SNAPSHOT_SHA256 = "b76f8bbfb6e5a51094e35a3639a40bd0d4638c789fa1d2769a939cd88d2d6989"
MAX_PACKET_BYTES = 32768


def connect_published_program(packet_bytes: bytes, packet_source: Source) -> dict:
    """Return separate published outflows and implementer-reported outcomes.

    The caller supplies bytes already acquired from the public immutable
    snapshot. This function performs no I/O and does not authenticate payment
    settlement or reported welfare outcomes.
    """
    if type(packet_bytes) is not bytes or len(packet_bytes) > MAX_PACKET_BYTES:
        raise ValueError("bounded packet bytes required")
    if type(packet_source) is not Source:
        raise ValueError("actual Source provenance required")
    if packet_source.source_id != SOURCE_ID or packet_source.url != SNAPSHOT_URL:
        raise ValueError("source does not identify the reviewed aggregate snapshot")

    # Verify the supplied Source record, then enforce the immutable reviewed pin
    # independently so a caller cannot bless changed bytes with a new hash.
    packet_source.verify_content(packet_bytes)
    if sha256(packet_bytes).hexdigest() != SNAPSHOT_SHA256:
        raise ValueError("packet differs from independently reviewed snapshot")

    try:
        packet = json.loads(packet_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid reviewed packet encoding") from exc
    if not isinstance(packet, dict):
        raise ValueError("reviewed packet must be an object")

    disbursements = deepcopy(packet["disbursements"])
    rows = disbursements["rows"]
    total = sum(row["amount_minor"] for row in rows)
    disbursements["published_disbursement_total_minor"] = total

    return {
        "program_id": packet["activity_id"],
        "disbursements": disbursements,
        "beneficiary_aggregate": deepcopy(packet["beneficiary_aggregate"]),
        "source_relation": {
            "connection": deepcopy(packet["connection"]),
            "activity_report_document_link": deepcopy(packet["activity_report_document_link"]),
            "raw_sources": deepcopy(packet["raw_sources"]),
        },
        "packet_source": {
            "source_id": SOURCE_ID,
            "url": SNAPSHOT_URL,
            "content_sha256": SNAPSHOT_SHA256,
            "retrieved_at": packet_source.retrieved_at.isoformat(),
        },
        "unresolved_accounting": deepcopy(packet["unresolved_accounting"]),
        "claim_limits": deepcopy(packet["claim_limits"]),
        "limited_rights": deepcopy(packet["limited_rights"]),
        "attribution": packet["attribution"],
        "extraction": deepcopy(packet["extraction"]),
        "proof_level": "P0",
        "action": "NO_ACTION",
        "human_welfare_status": "NOT_MEASURED",
        "measurement_authentication": "NOT_VERIFIED",
        "verified_income_increase_minor": None,
        "verified_net_benefit_minor": None,
    }
