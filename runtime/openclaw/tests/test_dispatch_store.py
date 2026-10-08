import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('dispatch_store', Path(__file__).parents[1] / 'dispatch_store.py')
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)

def record(**patch):
    return dict(version=2, owner_id='writer', occurrence_id='wake:001', task_id='draft',
                session_key='agent:manager:lm:session', upstream_run_id=None, claim_ref=None,
                request_digest='a'*64, phase='prepared', **patch)

def race(root, q):
    try:
        v=record(); v['phase']='dispatching'
        store.save_dispatch(Path(root), v, expected_phase='prepared')
        q.put('sent')
    except ValueError:
        q.put('held')

class DispatchTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()/'dispatch'
    def test_missing_and_tuple_identity_matches_node(self):
        self.assertIsNone(store.load_dispatch(self.root,'writer','wake:001','draft'))
        p=store.save_dispatch(self.root,record(),expected_phase=None)
        digest=subprocess.check_output(['node','--input-type=module','-e',
          "import {tupleDigest} from './runtime/openclaw/protocol.mjs'; console.log(tupleDigest(['writer','wake:001','draft']))"],text=True).strip()
        self.assertEqual(p.stem,digest)
        self.assertNotEqual(store.dispatch_key('a:b','c','d'),store.dispatch_key('a','b:c','d'))
        self.assertEqual(p.stat().st_mode & 0o777,0o600)
    def test_competing_processes_admit_only_one_send(self):
        store.save_dispatch(self.root,record(),expected_phase=None)
        ctx=multiprocessing.get_context('fork'); q=ctx.Queue()
        children=[ctx.Process(target=race,args=(str(self.root),q)) for _ in range(2)]
        for p in children:p.start()
        for p in children:p.join(5); self.assertEqual(p.exitcode,0)
        self.assertEqual(sorted(q.get(timeout=2) for _ in children),['held','sent'])
        q.close(); q.join_thread()
    def test_unknown_terminal_and_modified_request_cannot_reenter_send(self):
        store.save_dispatch(self.root,record(),expected_phase=None)
        v=record();v['phase']='dispatching';store.save_dispatch(self.root,v,expected_phase='prepared')
        v['phase']='unknown';store.save_dispatch(self.root,v,expected_phase='dispatching')
        v['phase']='prepared'
        with self.assertRaises(ValueError):store.save_dispatch(self.root,v,expected_phase='unknown')
        v['phase']='terminal';store.save_dispatch(self.root,v,expected_phase='unknown')
        v['request_digest']='b'*64
        with self.assertRaises(ValueError):store.save_dispatch(self.root,v,expected_phase='terminal')
    def test_corrupt_foreign_symlink_or_world_readable_records_fail_closed(self):
        p=store.save_dispatch(self.root,record(),expected_phase=None)
        os.chmod(p,0o644)
        with self.assertRaises(ValueError):store.load_dispatch(self.root,'writer','wake:001','draft')
        os.chmod(p,0o600);p.write_text('{broken')
        with self.assertRaises(ValueError):store.load_dispatch(self.root,'writer','wake:001','draft')
        bad=record();bad['owner_id']='foreign';p.write_text(json.dumps(bad))
        with self.assertRaises(ValueError):store.load_dispatch(self.root,'writer','wake:001','draft')
        p.unlink();target=Path(self.temp.name)/'target';target.write_text('{}');p.symlink_to(target)
        with self.assertRaises(ValueError):store.load_dispatch(self.root,'writer','wake:001','draft')
    def test_symlink_root_never_writes_outside_private_dispatch(self):
        target=Path(self.temp.name)/'other';target.mkdir();self.root.symlink_to(target)
        with self.assertRaises(ValueError):store.save_dispatch(self.root,record(),expected_phase=None)
        self.assertEqual(list(target.iterdir()),[])

if __name__=='__main__':unittest.main()
