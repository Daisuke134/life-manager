"""Real SQLite snapshots; an injected gateway never proves live cloud authority."""
import base64
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from manager_core.owned_cycle import CycleStore
from test_digital_handoff import NOW, manifest


def snapshot(root):
    store = CycleStore(root)
    from manager_core.digital_handoff import plan_release, PublisherContext, REPOSITORY, SOURCE_REF, WORKFLOW
    packet = plan_release(manifest('a'*40, 'old'), manifest('b'*40, 'new'), NOW)
    store.journal.reserve(packet, PublisherContext(REPOSITORY, SOURCE_REF, WORKFLOW, 'b'*40, '123'),
                          packet['baseline'], packet['candidate'], 'c'*40, NOW)
    return store.db.read_bytes(), packet


class MemoryGateway:
    def __init__(self, raw):
        self.value = dict(revision=0, sha256=sha256(raw).hexdigest(),
                          snapshot=base64.b64encode(raw).decode(), owner=None)
        self.calls = []
        self.lose_ack = False

    def __call__(self, payload):
        self.calls.append(payload['operation'])
        owner = '123:1:' + payload['nonce']
        if payload['operation'] == 'acquire':
            if self.value['owner'] is not None: raise OSError('busy')
            self.value['owner'] = owner
        elif payload['operation'] == 'checkpoint':
            if self.value['owner'] != owner or payload['revision'] != self.value['revision']:
                raise OSError('CAS rejected')
            self.value.update(revision=self.value['revision']+1, sha256=payload['sha256'], snapshot=payload['snapshot'])
            if self.lose_ack: raise OSError('response lost after remote commit')
        elif payload['operation'] == 'release':
            if self.value['owner'] != owner: raise OSError('wrong owner')
            self.value['owner'] = None
        return deepcopy(self.value)


class OwnedCheckpointTests(unittest.TestCase):
    def api(self):
        from manager_core.owned_checkpoint import PrivateCheckpoint, CheckpointUnavailable
        return PrivateCheckpoint, CheckpointUnavailable

    def test_restore_preserves_unknown_reservation_and_never_replays_dispatch(self):
        api, _ = self.api()
        with TemporaryDirectory() as tmp:
            root = Path(tmp); raw, packet = snapshot(root/'seed')
            gateway = MemoryGateway(raw)
            checkpoint = api(gateway, run_id='123', run_attempt='1')
            db = checkpoint.acquire(root/'run')
            store = CycleStore(db.parent)
            record = store.journal.record(packet['effect_key'])
            self.assertEqual(record.status, 'DISPATCHING')
            self.assertEqual(record.expected_parent, 'c'*40)
            self.assertFalse(record.dispatch)
            self.assertEqual(db.stat().st_mode & 0o777, 0o600)
            self.assertEqual(db.parent.stat().st_mode & 0o777, 0o700)
            store.stop()
            result = checkpoint.save()
            self.assertEqual(set(result), {'revision', 'sha256'})
            checkpoint.release()
            next_run = api(gateway, run_id='123', run_attempt='1')
            db2 = next_run.acquire(root/'next')
            self.assertTrue(CycleStore(db2.parent).stopped())
            self.assertFalse(CycleStore(db2.parent).journal.record(packet['effect_key']).dispatch)

    def test_corrupt_missing_mismatched_or_wrong_schema_store_never_becomes_blank_state(self):
        api, error = self.api()
        with TemporaryDirectory() as tmp:
            root = Path(tmp); raw, _ = snapshot(root/'seed')
            for kind in ('missing', 'digest', 'sqlite', 'schema', 'owner', 'revision', 'fields'):
                gateway = MemoryGateway(raw)
                if kind == 'missing':
                    def transport(payload): raise OSError('missing state')
                else:
                    def transport(payload, gateway=gateway, kind=kind):
                        result = gateway(payload)
                        if kind == 'digest': result['sha256'] = 'f'*64
                        if kind in ('sqlite', 'schema'):
                            if kind == 'sqlite': data = b'not a database'
                            else:
                                with sqlite3.connect(root/'other.sqlite') as db:
                                    db.execute('CREATE TABLE unrelated(x)')
                                data = (root/'other.sqlite').read_bytes()
                            result.update(sha256=sha256(data).hexdigest(), snapshot=base64.b64encode(data).decode())
                        if kind == 'owner': result['owner'] = 'another:owner'
                        if kind == 'revision': result['revision'] = True
                        if kind == 'fields': result['unexpected'] = True
                        return result
                destination = root/kind
                with self.subTest(kind=kind), self.assertRaises(error):
                    api(transport, run_id='123', run_attempt='1').acquire(destination)
                self.assertFalse((destination/'cycle.sqlite').exists())

    def test_lost_checkpoint_ack_poison_session_and_preserves_remote_unknown(self):
        api, error = self.api()
        with TemporaryDirectory() as tmp:
            root = Path(tmp); raw, packet = snapshot(root/'seed'); gateway = MemoryGateway(raw)
            checkpoint = api(gateway, run_id='123', run_attempt='1')
            checkpoint.acquire(root/'run'); gateway.lose_ack = True
            with self.assertRaises(error): checkpoint.save()
            before = list(gateway.calls)
            with self.assertRaises(error): checkpoint.save()
            with self.assertRaises(error): checkpoint.release()
            self.assertEqual(gateway.calls, before)
            self.assertEqual(gateway.value['revision'], 1)
            gateway.value['owner'] = None  # fixture lease expiry, never a production reset
            restored = api(gateway, run_id='123', run_attempt='1').acquire(root/'retry')
            self.assertEqual(CycleStore(restored.parent).journal.record(packet['effect_key']).status, 'DISPATCHING')

    def test_rejects_old_cache_source_directory_symlink_and_conflicting_revision(self):
        api, error = self.api()
        with TemporaryDirectory() as tmp:
            root = Path(tmp); raw, _ = snapshot(root/'seed'); gateway = MemoryGateway(raw)
            for destination in (root/'seed', Path(__file__).parents[1]/'output/private-state-test'):
                before = list(gateway.calls)
                with self.assertRaises(error): api(gateway, run_id='123', run_attempt='1').acquire(destination)
                self.assertEqual(gateway.calls, before)
            (root/'link').symlink_to(root/'seed', target_is_directory=True)
            with self.assertRaises(error): api(gateway, run_id='123', run_attempt='1').acquire(root/'link')
            checkpoint = api(gateway, run_id='123', run_attempt='1'); checkpoint.acquire(root/'run')
            gateway.value['revision'] += 1
            with self.assertRaises(error): checkpoint.save()

    def test_busy_owner_cannot_restore_or_clear_other_owner(self):
        api, error = self.api()
        with TemporaryDirectory() as tmp:
            root = Path(tmp); raw, _ = snapshot(root/'seed'); gateway = MemoryGateway(raw)
            first = api(gateway, run_id='123', run_attempt='1'); first.acquire(root/'first')
            owner = gateway.value['owner']
            second = api(gateway, run_id='123', run_attempt='1')
            with self.assertRaises(error): second.acquire(root/'second')
            with self.assertRaises(error): second.release()
            self.assertEqual(gateway.value['owner'], owner)

    def test_snapshot_contains_committed_wal_changes_and_does_not_create_missing_database(self):
        from manager_core.owned_checkpoint import _database_bytes
        with TemporaryDirectory() as tmp:
            root = Path(tmp); raw, _ = snapshot(root/'seed')
            db_path = root/'seed/cycle.sqlite'
            with sqlite3.connect(db_path) as writer:
                writer.execute('PRAGMA journal_mode=WAL')
                writer.execute('UPDATE control SET stopped=1'); writer.commit()
                # Keep the connection open so the committed change is in WAL.
                gateway = MemoryGateway(_database_bytes(db_path))
                api, _ = self.api()
                restored = api(gateway, run_id='123', run_attempt='1').acquire(root/'run')
                self.assertTrue(CycleStore(restored.parent).stopped())
            missing = root/'missing.sqlite'
            with self.assertRaises((OSError, sqlite3.Error, ValueError)):
                _database_bytes(missing)
            self.assertFalse(missing.exists())


if __name__ == '__main__': unittest.main()
