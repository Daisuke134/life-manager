"""K009: provider lookup never implies permission to retry a possibly sent effect."""
from dataclasses import dataclass
from .outbox import DurableOutbox


@dataclass(frozen=True)
class ReconcileResult:
    status: str
    receipt_ref: str | None


class Reconciler:
    def __init__(self,outbox: DurableOutbox):
        self.outbox=outbox

    def reconcile(self,key,provider) -> ReconcileResult:
        record=self.outbox.record(key)
        if record is None:
            raise ValueError("effect intent not reserved")
        if record.status in ("PRESENT","ABSENT"):
            return ReconcileResult(record.status,record.receipt_ref)
        try:
            status,ref=provider.lookup(key)
        except Exception:
            status,ref="UNKNOWN",None
        if status not in ("PRESENT","ABSENT","UNKNOWN") or (status=="PRESENT" and not ref):
            status,ref="UNKNOWN",None
        if status in ("PRESENT","ABSENT"):
            self.outbox._set_status(key,status,ref if status=="PRESENT" else None)
        return ReconcileResult(status,ref if status=="PRESENT" else None)


@dataclass(frozen=True)
class OwnedOccurrenceEvidence:
    """Collector output; fixture dictionaries alone are not authenticated proof."""
    receipt: dict
    committed_manifest: dict
    committed_bodies: dict
    parent_commit: str
    parent_manifest: dict
    parent_bodies: dict


def reconcile_owned(journal,key,read_occurrence,observed_at):
    """Read-only exact occurrence reconciliation; no absence authorizes retry.

    Production collector must fetch exact public GitHub commit/parent/file GETs
    using the existing collector. Offline collectors prove only contract logic.
    Transient missing data, branch lag and errors all stay UNKNOWN.
    """
    import json
    from .digital_handoff import validate_commit_receipt
    record=journal.record(key)
    if record is None:raise ValueError('owned intent not reserved')
    if record.status=='PRESENT':return ReconcileResult('PRESENT',record.receipt_ref)
    try:
        evidence=read_occurrence(key)
        if type(evidence) is not OwnedOccurrenceEvidence:return ReconcileResult('UNKNOWN',None)
        if evidence.parent_commit!=record.expected_parent:return ReconcileResult('UNKNOWN',None)
        validate_commit_receipt(json.loads(record.packet_json),evidence.receipt,evidence.committed_manifest,
            observed_at,committed_bodies=evidence.committed_bodies,parent_commit=evidence.parent_commit,
            parent_manifest=evidence.parent_manifest,parent_bodies=evidence.parent_bodies)
        ref=evidence.receipt['sha'];journal._present(key,ref)
        return ReconcileResult('PRESENT',ref)
    except Exception:
        return ReconcileResult('UNKNOWN',None)


def reconcile_pending_owned(journal,read_occurrence,observed_at):
    """Recover one bounded batch from saved bindings, without fresh authority.

    Callers must keep dispatch blocked while any pending records remain,
    including records beyond this batch. Missing evidence is never absence.
    """
    batch=journal.recovery_batch('occurrence')
    results=tuple(reconcile_owned(journal,record.key,read_occurrence,observed_at)
                  for record in batch)
    journal.complete_recovery_batch('occurrence',batch)
    return results
