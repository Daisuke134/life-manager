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
