import json
import subprocess
from pathlib import Path

import pytest
from job_search_loop import mercor_paid_snapshot as paid
from job_search_loop.mercor_reply_snapshot import _direct_capture_expression


@pytest.mark.parametrize("first_email,expected_fetches", [("other@example.test", 0), ("owner@example.test", 1)])
def test_only_matching_first_token_identity_fetches(first_email, expected_fetches):
    expression = _direct_capture_expression(['contracts'], expected_email='owner@example.test')
    harness = '''let fetched=0;
const records=[{value:{email:'other@example.test',stsTokenManager:{accessToken:'fake'}}},
 {value:{email:'owner@example.test',stsTokenManager:{accessToken:'fake2'}}}];
global.indexedDB={open:()=>{const req={};queueMicrotask(()=>{req.result={
 objectStoreNames:{contains:()=>true},close:()=>{},transaction:()=>({objectStore:()=>({getAll:()=>{
 const get={result:records};queueMicrotask(()=>get.onsuccess());return get;}})})};req.onsuccess();});return req;}};
global.document={querySelectorAll:()=>[]};global.fetch=async()=>{fetched++;return {ok:true,json:async()=>[]};};
'''
    harness = harness.replace('other@example.test', first_email)
    script = harness + '(' + expression + ').then(value=>console.log(JSON.stringify({value:JSON.parse(value),fetched})))'
    result = subprocess.run(['node', '-e', script], text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == {'value': {'contracts': []} if expected_fetches else {}, 'fetched': expected_fetches}


class Page:
    def __init__(self, payload):
        self.payload = payload
        self.closed = False
        self.url = 'https://work.mercor.com/home?tab=contracts'
    def goto(self, *args, **kwargs):
        assert args[0] == self.url
    def evaluate(self, expression):
        assert 'https://aws.api.mercor.com/work/jobs' in expression
        assert 'owner@example.test' in expression
        return json.dumps(self.payload)
    def close(self):
        self.closed = True


def test_failed_capture_preserves_previous_snapshot_and_closes_own_page(tmp_path):
    output = tmp_path/'snapshot.json'
    output.write_text('old observation')
    page = Page({})
    with pytest.raises(RuntimeError, match='mercor_paid_contract_capture_unavailable'):
        paid.capture(page, expected_email='owner@example.test', output=output)
    assert output.read_text() == 'old observation'
    assert page.closed


def test_empty_official_response_is_fresh_private_snapshot(tmp_path):
    output = tmp_path/'snapshot.json'
    page = Page({'contracts': []})
    paid.capture(page, expected_email='owner@example.test', output=output)
    value = json.loads(output.read_text())
    assert value['contracts'] == []
    assert value['version'] == 1
    assert value['observed_at']
    assert output.stat().st_mode & 0o777 == 0o600
    assert page.closed


def test_paid_owner_has_own_observation_before_kernel():
    root = Path(__file__).resolve().parents[3]
    owner = (root/'skills/earn/mercor/scripts/paid-owner').read_text()
    assert owner.index('job_search_loop.mercor_paid_snapshot') < owner.index('scripts/paid_kernel.py')
    assert '$STATE_ROOT/paid-official-snapshot.json' in owner
    assert '$STATE_ROOT/reply/official-snapshot.json' not in owner


def test_capture_failure_never_enters_paid_kernel(tmp_path):
    root = Path(__file__).resolve().parents[3]
    source = root/'skills/earn/mercor/scripts/paid-owner'
    owner = tmp_path/'skills/earn/mercor/scripts/paid-owner'
    owner.parent.mkdir(parents=True)
    owner.write_text(source.read_text())
    wrapper = tmp_path/'skills/browser/with-browser.sh'
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text('#!/bin/bash\nexit 75\n')
    interpreter = tmp_path/'python'
    interpreter.write_text('#!/bin/bash\ntouch "$KERNEL_CALLED"\n')
    interpreter.chmod(0o700)
    hint = tmp_path/'hint.json'
    called = tmp_path/'kernel-called'
    import os
    result = subprocess.run(['bash', str(owner)], env={**os.environ,
        'LIFE_MANAGER_STATE_ROOT':str(tmp_path/'state'), 'LIFE_MANAGER_PYTHON':str(interpreter),
        'LIFE_MANAGER_RESULT_HINT_PATH':str(hint), 'KERNEL_CALLED':str(called)}, capture_output=True)
    assert result.returncode == 75
    assert not called.exists()
    assert json.loads(hint.read_text()) == {'status':'pre_effect_failure','effect':0}
