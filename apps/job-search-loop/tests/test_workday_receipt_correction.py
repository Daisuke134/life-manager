import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
import test_submission_confirmation as fixtures

from job_search_loop.browser_agent.completion import verify_completion_ui
from job_search_loop.ledger import Ledger
from job_search_loop.submission_confirmation import reconcile_confirmation_threads


class WorkdayReceiptCorrectionTests(unittest.TestCase):
    def test_success_alert_without_parent_name_waits_for_receipt(self):
        observation = Mock(content_sha256='b'*64, visible_text='Your application has been submitted',
            validation_text=('Your application has been submitted',), blocking_validation_text=())
        review = Mock(observation_sha256='a'*64, receipt_sha256='c'*64)
        result = verify_completion_ui(company='Parent', role='Role', review=review,
            observation=observation, require_receipt=True)
        self.assertEqual(result.outcome, 'submit_unknown')
        self.assertEqual(result.evidence_class, 'exact_completion_ui_pending_receipt')

    def test_generic_alert_is_not_a_definite_provider_rejection(self):
        observation = Mock(content_sha256='b'*64, visible_text='Provider notification',
            validation_text=('Notification',), blocking_validation_text=())
        result = verify_completion_ui(company='Parent', role='Role',
            review=Mock(observation_sha256='a'*64, receipt_sha256='c'*64),
            observation=observation, require_receipt=True)
        self.assertEqual(result.outcome, 'submit_unknown')

    def test_official_receipts_correct_false_negative_slots_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);ids=[]
            for company in ('First Brand', 'Second Brand'):
                ledger, app, intent = fixtures.SubmissionConfirmationTests()._unknown_submission(
                    root, company=company, title=company+' Role',
                    url='https://fixture.wd1.myworkdayjobs.com/jobs/job/'+company.replace(' ','-'), outcome='not_submitted')
                ids.append((app,intent));ledger.close()
            ledger = Ledger(root/'ledger.sqlite3')
            received=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()
            for index,(app,intent) in enumerate(ids):
                kwargs=dict(intent_id=intent, message_id='receipt-'+str(index), thread_id='thread-'+str(index),
                    evidence_sha256=str(index+1)*64, received_at=received)
                self.assertEqual(ledger.reconcile_submission_confirmation(**kwargs),'reconciled')
                self.assertEqual(ledger.reconcile_submission_confirmation(**kwargs),'duplicate')
            rows=ledger.connection.execute('select slot,application_id,status from daily_slots order by slot').fetchall()
            self.assertEqual([(r[0],r[2]) for r in rows],[(1,'submitted'),(2,'submitted')])
            self.assertEqual(len(ledger.pending_materials_ready_applications()),0)
            self.assertEqual(len(ledger.retryable_applications()),0)
            ledger.close()

    def test_generic_subject_uses_exact_official_hiring_brand_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ledger,app,intent=fixtures.SubmissionConfirmationTests()._unknown_submission(root,
                company='Parent', title='Agent Product Engineer',
                url='https://fixture.wd1.myworkdayjobs.com/jobs/job/role_R1')
            ledger.close();received=datetime.now(timezone.utc)+timedelta(minutes=1)
            payload={'thread':{'id':'thread-one','messages':[{'id':'message-one','threadId':'thread-one',
                'internalDate':int(received.timestamp()*1000), 'headers':{
                    'from':'Hiring Brand <notifications@myworkday.com>',
                    'to':'candidate@example.test','subject':'採用についてのメッセージ'},
                'body':'候補者 様 , Hiring Brand の Agent Product Engineer の職務にご応募いただき、ありがとうございました。'}]}}
            result=reconcile_confirmation_threads(ledger_path=root/'ledger.sqlite3',
                threads=[{'id':'thread-one','from':'notifications@myworkday.com','subject':'採用についてのメッセージ'}],
                thread_loader=lambda _id:payload, seen_state=root/'seen.json', expected_recipient='candidate@example.test',
                official_posting_loader=lambda candidate:{'jobPostingInfo':{'title':'Agent Product Engineer',
                    'jobDescription':'Hiring Brand builds agent software.', 'logoImage':{'alt':'Hiring Brand Logo'}}, 'hiringOrganization':{'name':'Hiring Brand KK'}})
            self.assertEqual(len(result['reconciled']),1)

    def test_wrong_role_cannot_correct_a_false_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ledger,app,intent=fixtures.SubmissionConfirmationTests()._unknown_submission(root,
                company='Fixture Company', title='Agent Product Engineer',
                url='https://fixture.wd1.myworkdayjobs.com/jobs/job/role_R1', outcome='not_submitted')
            ledger.close();received=datetime.now(timezone.utc)+timedelta(minutes=1)
            payload={'thread':{'id':'thread-wrong','messages':[{'id':'message-wrong','threadId':'thread-wrong',
                'internalDate':int(received.timestamp()*1000), 'headers':{'from':'notifications@myworkday.com',
                    'to':'candidate@example.test','subject':'Application received'},
                'body':'Thank you for applying to Warehouse Manager at Fixture Company.'}]}}
            result=reconcile_confirmation_threads(ledger_path=root/'ledger.sqlite3',
                threads=[{'id':'thread-wrong','from':'notifications@myworkday.com','subject':'Application received'}],
                thread_loader=lambda _id:payload, seen_state=root/'seen.json', expected_recipient='candidate@example.test')
            self.assertEqual(result['reconciled'],[])

    def test_a_vendor_mentioned_in_the_description_is_not_the_hiring_brand(self):
        from job_search_loop.submission_confirmation import _workday_hiring_receipt_matches
        message={'sender':'notifications@myworkday.com','recipient':'candidate@example.test',
                 'body':'候補者 様 , Employer Alpha の Agent Product Engineer の職務にご応募いただき、ありがとうございました。'}
        candidate={'canonical_url':'https://fixture.wd1.myworkdayjobs.com/jobs/job/role_R1','title':'Agent Product Engineer'}
        posting={'jobPostingInfo':{'title':'Agent Product Engineer','jobDescription':'Our customers include Employer Alpha.',
                    'logoImage':{'alt':'Parent Beta Logo'}},'hiringOrganization':{'name':'Parent Beta'}}
        self.assertFalse(_workday_hiring_receipt_matches(message,candidate,'candidate@example.test',lambda _c:posting))

    def test_one_posting_readback_failure_does_not_stop_another_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for company,title in [('Parent','Agent Product Engineer'),('Other Brand','Other Role')]:
                ledger,app,intent=fixtures.SubmissionConfirmationTests()._unknown_submission(root,
                    company=company,title=title,url='https://fixture.wd1.myworkdayjobs.com/jobs/job/'+title.replace(' ','-'))
                ledger.close()
            received=datetime.now(timezone.utc)+timedelta(minutes=1)
            messages=[]
            for index,(sender,body) in enumerate([('Hiring Brand','候補者 様 , Hiring Brand の Agent Product Engineer の職務にご応募いただき、ありがとうございました。'),
                                                 ('Other Brand','Thank you for applying to Other Role at Other Brand.')]):
                messages.append({'id':'message-'+str(index),'threadId':'thread-readbacks',
                    'internalDate':int(received.timestamp()*1000),'headers':{'from':sender+' <notifications@myworkday.com>',
                    'to':'candidate@example.test','subject':'採用についてのメッセージ'},'body':body})
            def unavailable(_candidate):raise OSError('fixture posting unavailable')
            result=reconcile_confirmation_threads(ledger_path=root/'ledger.sqlite3',
                threads=[{'id':'thread-readbacks','from':'notifications@myworkday.com','subject':'採用についてのメッセージ'}],
                thread_loader=lambda _id:{'thread':{'id':'thread-readbacks','messages':messages}},
                seen_state=root/'seen.json', expected_recipient='candidate@example.test',official_posting_loader=unavailable)
            self.assertEqual(len(result['reconciled']),1)
            self.assertEqual(result['reconciled'][0]['message_id'],'message-1')
