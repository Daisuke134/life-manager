#!/usr/bin/env python3
"""Y002: observe the actual public site, compare an identical proposal, abstain.

No publishing authority or provider write is used. The captured result drives
the demo video; it is a visualization of this execution, not fabricated output.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.audit import AuditTrail
from manager_core.kernel import ManagerKernel
from phase06_kernel_release import live_snapshot, write_json, PUBLIC_BASE


def main():
    baseline,bodies=live_snapshot()
    now=datetime.now(timezone.utc)
    with TemporaryDirectory() as tmp:
        kernel=ManagerKernel(None,None,AuditTrail(Path(tmp)/'demo.sqlite'))
        packet=kernel.prepare_digital_release('public-no-action-demo',baseline,baseline,now)
        result={'schema':'manager.public-demo.v1','captured_at':now.isoformat(),
                'public_url':PUBLIC_BASE,'source_commit':baseline['source_commit'],
                'observed_pages':len(bodies),'source':'ACTUAL_PUBLIC_HTTPS_READBACK',
                'candidate':'Republish the identical public artifact',
                'alternative':'NO_ACTION','decision':packet['decision'],
                'changed_pages':packet['changed_pages'],'external_writes':0,
                'human_outcome':'NOT_MEASURED','causal_effect_verified':False,
                'effect_key':packet['effect_key'],'manifest':baseline,
                'trace_valid':kernel.audit.verify_chain('public-no-action-demo'),
                'trace':kernel.audit.trace('public-no-action-demo'),
                'limitation':'Real public observation; deterministic software decision; no new field intervention, beneficiary measurement, or causal trial.'}
    target=Path(__file__).resolve().parents[1]/'docs/demos/manager-public-no-action-20261022.json'
    write_json(target,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
