import hashlib
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from job_search_loop.browser_agent import runtime
from job_search_loop.browser_agent.contracts import ObservationV1, VisibleControlV1


class ValidationRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_field_feedback_preserves_the_active_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pdf=root/'resume.pdf';pdf.write_bytes(b'%PDF-1.4 fixture')
            submit=VisibleControlV1('button','button','submit','Submit Application',False,'ref:submit')
            before=ObservationV1(1,'https://jobs.ashbyhq.com/fixture/job/application','Role at Brand',
                'Brand Role resume.pdf',(submit,),(),(),root/'before.png','f'*64,'a'*64)
            after=ObservationV1(1,before.url,before.title,'Phone number is required',(submit,),
                ('Phone number is required',),(),root/'after.png','f'*64,'b'*64,(),('Phone number',))
            handle=Mock(row_run_id='row-one',page_marker='row-marker',generation=1)
            cursor=Mock(handle=handle,checkpoint=None)
            session=Mock(close_owned=AsyncMock());session.page.return_value=Mock(wait_for_timeout=AsyncMock())
            evidence=Mock();evidence.read_chain.return_value=();evidence.append.return_value=Mock(evidence_sha256='e'*64)
            checkpoints=Mock();checkpoints.save.return_value=Mock(checkpoint_sha256='c'*64)
            builder=Mock(build=AsyncMock(side_effect=(before,after)))
            row={'application_id':'row-one','company':'Brand','title':'Role','canonical_url':'https://jobs.ashbyhq.com/fixture/job'}
            ledger=Mock();ledger.claim_submission.return_value=Mock(intent_id='intent-one',fence=1)
            executor=Mock(execute_final=AsyncMock(return_value=Mock(receipt_sha256='d'*64)))
            verifier=Mock(verify=AsyncMock(return_value=Mock()))
            review=Mock(receipt_sha256='c'*64,observation_sha256=before.content_sha256)
            with patch.object(runtime,'_context',new=AsyncMock(return_value=(row,session,checkpoints,evidence,cursor,builder))), \
                 patch.object(runtime,'_routed_resume',return_value={'resume_path':str(pdf),'resume_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}), \
                 patch.object(runtime,'ResumeVerifier',return_value=verifier), patch.object(runtime,'verify_final_review',return_value=review), \
                 patch.object(runtime,'Ledger',return_value=ledger), patch.object(runtime,'SubmissionFence'), \
                 patch.object(runtime,'ActionExecutor',return_value=executor), patch.object(runtime,'_path_env',return_value=root), \
                 patch.object(runtime,'_exclusive_terminal_effect',side_effect=nullcontext), patch.object(runtime,'_check_terminal_failure_marker'), \
                 patch.object(runtime,'_wake_budget',return_value=40), patch.object(runtime,'send_hourly_outcomes',return_value={'message_id':'fake'}) as report, \
                 patch.object(runtime,'_mark_wake_completed') as completed:
                result=await runtime.finalize()
            self.assertEqual(result['status'],'action_rejected')
            self.assertEqual(result['reason'],'provider_field_validation_rejection')
            self.assertIn('Phone number is required',result['observation']['validation'])
            session.close_owned.assert_not_awaited();completed.assert_not_called();report.assert_not_called()
            self.assertEqual(checkpoints.save.call_args.args[0].remaining_steps,40)
