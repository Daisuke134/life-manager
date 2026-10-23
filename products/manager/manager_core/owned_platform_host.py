"""Exact GitHub Actions adapter for the shared owned digital cycle.

The adapter consumes the existing private checkpoint, collector, admission,
seven-path release guard and protected Pages deployment workflow. Constructing
this Python object proves no identity; only the original GitHub OIDC gateway
and trusted workflow provide platform authentication.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic

from .digital_handoff import (
    ALLOWED_PATHS, MAIN_REF, REPOSITORY, WORKFLOW, OwnedChangeContext,
    PublisherContext, commit_message, verify_readback,
)
from .owned_checkpoint import PrivateCheckpoint, SOURCE_ROOT


WORKFLOW_NAME = 'Manager Phase06 Digital Environment'
PAGES_REMOTE = f'https://github.com/{REPOSITORY}.git'
_CANONICAL_REMOTES = (PAGES_REMOTE, PAGES_REMOTE.removesuffix('.git'))
PAGES_BRANCH = 'refs/heads/gh-pages'
PAGES_WORKFLOW_ID = '307239134'
MAX_HOST_SECONDS = 600
COMMAND_TIMEOUT_SECONDS = 15
SHA_RE = re.compile(r'[0-9a-f]{40}\Z')
POSITIVE_RE = re.compile(r'[1-9][0-9]*\Z')


def is_canonical_remote(remote):
    """Accept only GitHub's exact canonical URL with or without `.git`."""
    return remote in _CANONICAL_REMOTES


class CatalogSelectionUnavailable(RuntimeError):
    """Fixed selector could not establish a safe new-candidate decision."""


class GitHubActionsCycleHost:
    """The only live adapter accepted by ``run_owned_cycle``.

    ``checkpoint`` must already own a fresh restored private SQLite file.
    Candidate objects and source audit are optional so recovery can run when no
    new candidate is available. They are read only after pending rows recover.
    """

    def __init__(self, checkpoint, checkout, source_audit_path, *,
                 context=None, assessment=None, scope=None):
        if type(checkpoint) is not PrivateCheckpoint:
            raise TypeError('exact private checkpoint session required')
        if context is not None and type(context) is not OwnedChangeContext:
            raise TypeError('typed owned change context required')
        from .candidate_verification import TechnicalAssessment
        from .authority import OwnedDigitalScope
        if assessment is not None and type(assessment) is not TechnicalAssessment:
            raise TypeError('typed technical assessment required')
        if scope is not None and type(scope) is not OwnedDigitalScope:
            raise TypeError('typed owned digital scope required')
        if source_audit_path is not None and not isinstance(source_audit_path, (str, os.PathLike)):
            raise TypeError('source audit path required')
        if not isinstance(checkout, (str, os.PathLike)):
            raise TypeError('canonical gh-pages checkout path required')
        self.checkpoint = checkpoint
        self.checkout = Path(checkout).absolute()
        self.source_audit_path = (Path(source_audit_path).absolute()
                                  if source_audit_path is not None else None)
        self.context = context
        self.assessment = assessment
        self.scope = scope
        self._started_at = monotonic()

    def prepare_candidate(self, now):
        """Return fixed typed candidate data after the shared recovery gates.

        A complete prebound tuple is retained for the existing unit contracts.
        Otherwise selection is imported lazily and can only use committed code,
        the existing Pages checkout, and the actual runner identity.
        """
        from .candidate_verification import TechnicalAssessment
        from .authority import OwnedDigitalScope
        if self.context is not None or self.assessment is not None or self.scope is not None:
            if (self.context is not None and type(self.context) is not OwnedChangeContext) or \
                    (self.assessment is not None and type(self.assessment) is not TechnicalAssessment) or \
                    (self.scope is not None and type(self.scope) is not OwnedDigitalScope):
                raise PermissionError('owned candidate unavailable')
            if self.context is not None and self.assessment is not None and self.scope is not None:
                return self.context, self.assessment, self.scope
            raise PermissionError('incomplete owned candidate binding')
        from .owned_catalog_planner import plan_catalog_change
        env = os.environ
        run_id, source_sha = env.get('GITHUB_RUN_ID'), env.get('GITHUB_SHA')
        planning = self.checkpoint.db.parent / 'planning'
        self.source_audit_path = planning / 'source-audit.json'
        try:
            selected = plan_catalog_change(self.checkout, planning, source_sha, now, run_id=run_id)
        except Exception:
            # Mismatch/audit/browser uncertainty blocks a new send but leaves
            # the already-restored journal available to the cycle owner.
            raise CatalogSelectionUnavailable('fixed catalog selection unavailable') from None
        if selected is None:
            return None, None, None
        if type(selected) is not tuple or len(selected) != 3:
            raise CatalogSelectionUnavailable('fixed catalog selection unavailable')
        context, assessment, scope = selected
        if (type(context) is not OwnedChangeContext or type(assessment) is not TechnicalAssessment or
                type(scope) is not OwnedDigitalScope):
            raise CatalogSelectionUnavailable('fixed catalog selection unavailable')
        self.context, self.assessment, self.scope = context, assessment, scope
        return context, assessment, scope

    def _environment(self, *, require_release=False):
        env = os.environ
        run_id, attempt = env.get('GITHUB_RUN_ID'), env.get('GITHUB_RUN_ATTEMPT')
        sha, workflow_sha = env.get('GITHUB_SHA'), env.get('GITHUB_WORKFLOW_SHA')
        if (env.get('GITHUB_REPOSITORY') != REPOSITORY or
                env.get('GITHUB_REF') != MAIN_REF or
                env.get('GITHUB_WORKFLOW_REF') != f'{REPOSITORY}/{WORKFLOW}@{MAIN_REF}' or
                env.get('GITHUB_WORKFLOW') != WORKFLOW_NAME or
                env.get('GITHUB_EVENT_NAME') not in ('schedule', 'workflow_dispatch') or
                env.get('RUNNER_ENVIRONMENT') != 'github-hosted' or
                (require_release and env.get('MANAGER_RELEASE_ENABLED') != 'true') or
                not isinstance(run_id, str) or not POSITIVE_RE.fullmatch(run_id) or
                not isinstance(attempt, str) or not POSITIVE_RE.fullmatch(attempt) or
                not isinstance(sha, str) or not SHA_RE.fullmatch(sha) or
                workflow_sha != sha):
            raise PermissionError('GitHub Actions platform admission failed')
        if (self.checkpoint.owner != f'{run_id}:{attempt}:{self.checkpoint.nonce}' or
                self.checkpoint.broken or self.checkpoint.db is None):
            raise PermissionError('private checkpoint session is unavailable')
        return env

    def assert_session(self, state_store):
        """Validate real runner identity and the exact restored private DB."""
        from .owned_cycle import CycleStore
        if type(state_store) is not CycleStore:
            raise PermissionError('exact private cycle store required')
        env = self._environment()
        db_path = Path(self.checkpoint.db).absolute()
        if db_path.resolve() != Path(state_store.db).resolve() or db_path.name != 'cycle.sqlite':
            raise PermissionError('cycle store is not bound to the private checkpoint')
        if any(path.is_symlink() for path in (db_path, *db_path.parents)):
            raise PermissionError('private checkpoint path is not canonical')
        try:
            if db_path.parent.stat().st_mode & 0o077 or db_path.stat().st_mode & 0o077:
                raise PermissionError('private checkpoint permissions are too broad')
        except OSError:
            raise PermissionError('private checkpoint is unavailable') from None
        root = SOURCE_ROOT.resolve()
        if db_path.resolve() == root or root in db_path.resolve().parents:
            raise PermissionError('private checkpoint must stay outside source checkout')
        if monotonic() - self._started_at > MAX_HOST_SECONDS:
            raise PermissionError('platform host lifetime exceeded')
        from scripts import phase06_kernel_release
        try:
            source_sha = phase06_kernel_release.source_checkout_commit()
        except Exception:
            raise PermissionError('canonical source checkout unavailable') from None
        if source_sha != env['GITHUB_SHA']:
            raise PermissionError('source checkout does not match workflow SHA')

    def _run_cli(self, argv, *, input_data=None, timeout=COMMAND_TIMEOUT_SECONDS):
        """Run a fixed argv with bounded time and sanitized failures."""
        try:
            completed = subprocess.run(
                argv, input=input_data, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=min(timeout or COMMAND_TIMEOUT_SECONDS, COMMAND_TIMEOUT_SECONDS),
                check=False,
            )
        except Exception:
            raise RuntimeError('bounded platform command failed') from None
        if completed.returncode != 0:
            raise RuntimeError('bounded platform command failed')
        return completed.stdout.strip()

    def _run_cli_bytes(self, argv, *, timeout=COMMAND_TIMEOUT_SECONDS):
        """Read exact Git object bytes without exposing command errors."""
        try:
            completed = subprocess.run(
                argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=min(timeout or COMMAND_TIMEOUT_SECONDS, COMMAND_TIMEOUT_SECONDS),
                check=False,
            )
        except Exception:
            raise RuntimeError('bounded platform command failed') from None
        if completed.returncode != 0:
            raise RuntimeError('bounded platform command failed')
        return completed.stdout

    def _git(self, *args):
        return self._run_cli(['git', '-C', str(self.checkout), *args])

    def _git_blob(self, commit, path):
        if type(commit) is not str or not SHA_RE.fullmatch(commit) or path not in ALLOWED_PATHS:
            raise ValueError('fixed committed Manager path required')
        return self._run_cli_bytes([
            'git', '-C', str(self.checkout), 'show', f'{commit}:{path}',
        ])

    def _validate_commit_tree(self, commit, expected_parent, expected_tree,
                              expected_paths, packet):
        """Validate the exact object tree before moving the branch ref."""
        try:
            if (not SHA_RE.fullmatch(commit) or not SHA_RE.fullmatch(expected_tree) or
                    self._git('rev-parse', f'{commit}^') != expected_parent or
                    self._git('rev-parse', f'{commit}^{{tree}}') != expected_tree):
                raise ValueError('commit parent or tree changed')
            names = set(self._git(
                'diff-tree', '--no-commit-id', '--name-only', '-r', '-z', commit,
            ).split('\x00')) - {''}
            if names != expected_paths or not names <= set(ALLOWED_PATHS):
                raise ValueError('committed path set differs from admission')
            message = self._git('show', '-s', '--format=%B', commit)
            if message != commit_message(packet):
                raise ValueError('committed message differs from intent')
            manifest = json.loads(self._git_blob(commit, 'manager-support/manifest.json'))
            if manifest != packet['candidate']:
                raise ValueError('committed manifest differs from candidate')
            bodies = {
                name: self._git_blob(commit, f'manager-support/{name}')
                for name in manifest['files']
            }
            verify_readback(manifest, bodies)
        except Exception:
            raise PermissionError('committed Manager tree differs from admitted candidate') from None

    def _assert_checkout_identity(self, *, clean):
        try:
            top = Path(self._git('rev-parse', '--show-toplevel')).resolve()
            branch = self._git('symbolic-ref', '--quiet', 'HEAD')
            fetch_url = self._git('remote', 'get-url', 'origin')
            push_url = self._git('remote', 'get-url', '--push', 'origin')
            status = self._git('status', '--porcelain=v1', '--untracked-files=all')
        except Exception:
            raise PermissionError('canonical gh-pages checkout unavailable') from None
        source = SOURCE_ROOT.resolve()
        if (top != self.checkout.resolve() or top == source or top in source.parents or
                source in top.parents or branch != PAGES_BRANCH or
                not is_canonical_remote(fetch_url) or not is_canonical_remote(push_url) or
                (clean and status)):
            raise PermissionError('canonical clean gh-pages checkout required')

    def _fetch_remote_parent(self):
        self._git('fetch', '--no-tags', 'origin', PAGES_BRANCH)
        remote_parent = self._git('rev-parse', 'FETCH_HEAD')
        if not SHA_RE.fullmatch(remote_parent):
            raise PermissionError('canonical gh-pages parent unavailable')
        return remote_parent

    def current_parent(self):
        """Read the clean checkout and require its exact remote parent."""
        self._assert_checkout_identity(clean=True)
        local_parent = self._git('rev-parse', 'HEAD')
        remote_parent = self._fetch_remote_parent()
        if not SHA_RE.fullmatch(local_parent) or remote_parent != local_parent:
            raise PermissionError('gh-pages parent moved; reconcile only')
        return local_parent

    def manifest(self):
        from .digital_environment import verify_bundle
        bundle = self.checkout / 'manager-support'
        try:
            manifest = json.loads((bundle / 'manifest.json').read_text())
            verify_bundle(bundle, manifest)
            return manifest
        except Exception:
            raise PermissionError('canonical Manager bundle unavailable') from None

    def occurrence(self, key, journal):
        from .owned_public_collector import collect_owned_occurrence
        return collect_owned_occurrence(key, journal)

    def observe_delivery(self, packet, receipt_ref, key, journal):
        from .owned_public_collector import collect_owned_delivery
        if key != packet.get('effect_key'):
            raise ValueError('saved platform occurrence required')
        record = journal.record(key)
        if record is None or record.receipt_ref != receipt_ref:
            raise ValueError('saved platform occurrence required')
        return collect_owned_delivery(key, journal)

    def observe_current_delivery(self, journal):
        from .owned_public_collector import collect_current_owned_delivery
        return collect_current_owned_delivery(journal,self._now())

    def _rollback_window(self, packet):
        from .outbox import validate_owned_rollback
        env=self._environment(require_release=True)
        created=validate_owned_rollback(packet)
        now=self._now()
        expires=datetime.fromisoformat(packet['expires_at'])
        if (env.get('GITHUB_EVENT_NAME')!='workflow_dispatch' or
                packet['controller_sha']!=env['GITHUB_SHA'] or
                not created<=now<expires or
                monotonic()-self._started_at>MAX_HOST_SECONDS):
            raise PermissionError('trusted bounded rollback control required')
        return env

    def _validate_rollback_commit(self, commit, expected_parent, expected_tree,
                                  expected_paths, packet, expected_bodies):
        from .outbox import owned_rollback_commit_message
        from .digital_environment import verify_readback
        try:
            if (not SHA_RE.fullmatch(commit) or not SHA_RE.fullmatch(expected_tree) or
                    self._git('rev-parse',f'{commit}^')!=expected_parent or
                    self._git('rev-parse',f'{commit}^{{tree}}')!=expected_tree):
                raise ValueError('rollback parent or tree changed')
            names=set(self._git('diff-tree','--no-commit-id','--name-only','-r','-z',commit).split('\x00'))-{''}
            if names!=expected_paths or not names<=set(ALLOWED_PATHS):
                raise ValueError('rollback path set widened')
            if self._git('show','-s','--format=%B',commit)!=owned_rollback_commit_message(packet):
                raise ValueError('rollback message changed')
            manifest_raw=self._git_blob(commit,'manager-support/manifest.json')
            manifest=json.loads(manifest_raw)
            bodies={'manager-support/'+name:self._git_blob(commit,'manager-support/'+name)
                    for name in manifest['files']}
            if (manifest!=packet['baseline'] or set(expected_bodies)!=set(ALLOWED_PATHS) or
                    manifest_raw!=expected_bodies['manager-support/manifest.json'] or
                    bodies!={name:raw for name,raw in expected_bodies.items()
                             if name!='manager-support/manifest.json'}):
                raise ValueError('rollback bytes differ from immutable parent')
            verify_readback(manifest,{name.removeprefix('manager-support/'):raw
                                      for name,raw in bodies.items()})
        except Exception:
            raise PermissionError('rollback commit differs from exact saved parent bytes') from None

    def send_owned_rollback(self, state_store, journal, packet):
        """Restore only exact parent bytes with a non-force gh-pages CAS push."""
        from .outbox import owned_rollback_commit_message
        from .reconcile import OwnedOccurrenceEvidence
        from .digital_environment import verify_readback
        from .owned_public_collector import collect_owned_occurrence
        self.assert_session(state_store)
        env=self._rollback_window(packet)
        self._assert_checkout_identity(clean=True)
        if self.current_parent()!=packet['candidate_commit']:
            raise PermissionError('rollback target moved; reconcile only')
        if self.manifest()!=packet['candidate']:
            raise PermissionError('latest candidate bundle changed; reconcile only')
        evidence=collect_owned_occurrence(packet['candidate_effect_key'],journal,self._now())
        relative_paths={name.removeprefix('manager-support/') for name in ALLOWED_PATHS}
        if (type(evidence) is not OwnedOccurrenceEvidence or
                evidence.receipt.get('sha')!=packet['candidate_commit'] or
                evidence.parent_commit!=packet['parent_commit'] or
                evidence.committed_manifest!=packet['candidate'] or
                evidence.parent_manifest!=packet['baseline'] or
                set(evidence.parent_bodies)!=relative_paths or
                set(evidence.committed_bodies)!=relative_paths):
            raise PermissionError('exact saved candidate and immutable parent unavailable')
        verify_readback(packet['baseline'],{
            name:raw for name,raw in evidence.parent_bodies.items()
            if name!='manifest.json'})
        if json.loads(evidence.parent_bodies['manifest.json'])!=packet['baseline']:
            raise PermissionError('immutable rollback baseline manifest changed')
        if (packet['candidate_effect_key']!=journal.latest_present_record().key or
                journal.latest_present_record().receipt_ref!=packet['candidate_commit']):
            raise PermissionError('rollback is not the latest saved candidate receipt')

        repository_parent_bodies={
            'manager-support/'+name:raw for name,raw in evidence.parent_bodies.items()}
        repository_candidate_bodies={
            'manager-support/'+name:raw for name,raw in evidence.committed_bodies.items()}
        if (set(repository_parent_bodies)!=set(ALLOWED_PATHS) or
                set(repository_candidate_bodies)!=set(ALLOWED_PATHS)):
            raise PermissionError('rollback path conversion widened')
        for name,raw in repository_parent_bodies.items():
            destination=self.checkout/name
            if (destination.is_symlink() or not destination.is_file() or
                    destination.parent.is_symlink()):
                raise PermissionError('tracked rollback path is not a regular file')
            destination.write_bytes(raw)
        self._git('add','--',*ALLOWED_PATHS)
        expected_paths={name for name in ALLOWED_PATHS
                        if repository_candidate_bodies[name]!=repository_parent_bodies[name]}
        staged=set(self._git('diff','--cached','--name-only','-z').split('\x00'))-{''}
        if not expected_paths or staged!=expected_paths:
            raise PermissionError('staged rollback paths differ from saved baseline')
        tree=self._git('write-tree')
        for name,raw in repository_parent_bodies.items():
            indexed=self._run_cli_bytes(['git','-C',str(self.checkout),'show',':'+name])
            if indexed!=raw:
                raise PermissionError('staged rollback bytes differ from immutable baseline')
        message=owned_rollback_commit_message(packet)
        with TemporaryDirectory(prefix='manager-owned-rollback-') as tmp:
            message_path=Path(tmp)/'message.txt';message_path.write_text(message+'\n')
            commit=self._git('-c','core.hooksPath=/dev/null','-c','user.name=github-actions[bot]',
                '-c','user.email=41898282+github-actions[bot]@users.noreply.github.com',
                'commit-tree',tree,'-p',packet['candidate_commit'],'-F',str(message_path))
        self._validate_rollback_commit(commit,packet['candidate_commit'],tree,
                                       expected_paths,packet,repository_parent_bodies)
        self._rollback_window(packet)
        if self._git('rev-parse','HEAD')!=packet['candidate_commit']:
            raise PermissionError('rollback local parent moved')
        self._git('-c','core.hooksPath=/dev/null','update-ref','refs/heads/gh-pages',
                  commit,packet['candidate_commit'])
        if self._git('rev-parse','HEAD')!=commit:
            raise PermissionError('rollback local ref did not advance')
        self._assert_checkout_identity(clean=True)
        self._rollback_window(packet)
        if self._fetch_remote_parent()!=packet['candidate_commit']:
            raise PermissionError('rollback remote CAS parent moved; reconcile only')
        self._rollback_window(packet)
        self._run_cli(['git','-c','core.hooksPath=/dev/null','-C',str(self.checkout),
                       'push','origin',f'HEAD:{PAGES_BRANCH}'])
        self._rollback_window(packet)
        self._run_cli(['gh','api','--method','POST',
            f'repos/{REPOSITORY}/actions/workflows/{PAGES_WORKFLOW_ID}/dispatches',
            '--input','-'],input_data=json.dumps({'ref':'gh-pages'},separators=(',',':')))
        return commit

    def reconcile_pending_rollbacks(self, state_store):
        """Read-only recovery; an old rollback reservation never reacquires send permission."""
        from .owned_public_collector import collect_owned_rollback,collect_owned_rollback_delivery
        records=state_store.journal.pending_rollbacks(limit=100)
        if not records:return None
        result=None
        for row in records:
            current=state_store.journal.rollback_record(row.key)
            if current.status!='PRESENT':
                evidence=collect_owned_rollback(row.key,state_store.journal,self._now())
                if evidence is not None:
                    state_store.journal._rollback_present(row.key,evidence.receipt['sha'])
                    current=state_store.journal.rollback_record(row.key)
            if current.status=='PRESENT' and current.delivery_status!='VERIFIED':
                delivery=collect_owned_rollback_delivery(row.key,state_store.journal,self._now())
                state_store.journal.save_rollback_delivery(row.key,delivery)
                current=state_store.journal.rollback_record(row.key)
            if current.status=='PRESENT':
                result={'status':'ROLLBACK_RECONCILED','writes':0,
                        'receipt_ref':current.receipt_ref,
                        'rollback_delivery_status':current.delivery_status}
            else:
                result={'status':'UNKNOWN','writes':None,
                        'reason':'ROLLBACK_RECONCILIATION_PENDING'}
        return result

    def rollback_latest_owned(self, state_store):
        """Explicit owner-only rollback of the exact current saved candidate."""
        from .outbox import plan_owned_rollback
        from .reconcile import OwnedOccurrenceEvidence
        from .owned_public_collector import (collect_owned_occurrence,
            collect_owned_rollback,collect_owned_rollback_delivery)
        from .digital_environment import verify_readback
        if not state_store.stopped():
            return {'status':'CONTROL_STOP_REQUIRED','writes':0}
        env=self._environment(require_release=True)
        if env.get('GITHUB_EVENT_NAME')!='workflow_dispatch':
            raise PermissionError('explicit workflow dispatch required')
        prior=self.reconcile_pending_rollbacks(state_store)
        if prior is not None:
            return prior
        self.assert_session(state_store)
        self._assert_checkout_identity(clean=True)
        current=self.current_parent()
        record=state_store.journal.latest_present_record()
        if record is None or record.receipt_ref!=current:
            return {'status':'ROLLBACK_BLOCKED','writes':0,'reason':'LATEST_RECEIPT_NOT_CURRENT'}
        original=json.loads(record.packet_json)
        if (original.get('schema')!='manager.digital-handoff.v2' or
                self.manifest()!=original['candidate']):
            return {'status':'ROLLBACK_BLOCKED','writes':0,'reason':'CANDIDATE_BINDING_CHANGED'}
        evidence=collect_owned_occurrence(record.key,state_store.journal,self._now())
        relative_paths={name.removeprefix('manager-support/') for name in ALLOWED_PATHS}
        if (type(evidence) is not OwnedOccurrenceEvidence or
                evidence.receipt.get('sha')!=record.receipt_ref or
                evidence.parent_commit!=record.expected_parent or
                evidence.committed_manifest!=original['candidate'] or
                evidence.parent_manifest!=original['baseline'] or
                set(evidence.parent_bodies)!=relative_paths or
                set(evidence.committed_bodies)!=relative_paths):
            return {'status':'ROLLBACK_BLOCKED','writes':0,'reason':'IMMUTABLE_PARENT_UNAVAILABLE'}
        verify_readback(original['baseline'],{
            name:raw for name,raw in evidence.parent_bodies.items()
            if name!='manifest.json'})
        if json.loads(evidence.parent_bodies['manifest.json'])!=original['baseline']:
            return {'status':'ROLLBACK_BLOCKED','writes':0,'reason':'IMMUTABLE_PARENT_CHANGED'}
        packet=plan_owned_rollback(original,record.receipt_ref,record.expected_parent,
                                   self._now(),controller_sha=env['GITHUB_SHA'])
        reserved=state_store.journal.reserve_rollback(packet,self._now())
        if not reserved.dispatch:
            return {'status':'UNKNOWN','writes':None,'reason':'ROLLBACK_ALREADY_RESERVED'}
        # The gateway ACK is mandatory before any external push or deployment dispatch.
        self.checkpoint.save()
        commit=self.send_owned_rollback(state_store,state_store.journal,packet)
        proof=collect_owned_rollback(packet['effect_key'],state_store.journal,self._now())
        if proof is None or proof.receipt.get('sha')!=commit:
            return {'status':'UNKNOWN','writes':None,'reason':'ROLLBACK_RECEIPT_PENDING'}
        state_store.journal._rollback_present(packet['effect_key'],commit)
        delivery=collect_owned_rollback_delivery(packet['effect_key'],state_store.journal,self._now())
        state_store.journal.save_rollback_delivery(packet['effect_key'],delivery)
        return {'status':'ROLLBACK_SUBMITTED','writes':1,'receipt_ref':commit,
                'rollback_delivery_status':delivery['status']}

    def _send_window(self, packet, expected_parent):
        env = self._environment(require_release=True)
        if monotonic() - self._started_at > MAX_HOST_SECONDS:
            raise PermissionError('platform host lifetime exceeded')
        now = self._now()
        created = datetime.fromisoformat(packet['created_at'])
        expires = datetime.fromisoformat(packet['expires_at'])
        if now.tzinfo is None or not created <= now < expires:
            raise PermissionError('owned release lease expired')
        if (packet.get('repository') != env['GITHUB_REPOSITORY'] or
                packet.get('ref') != env['GITHUB_REF'] or
                packet.get('workflow') != WORKFLOW or
                packet.get('schema') != 'manager.digital-handoff.v2' or
                packet.get('candidate', {}).get('source_commit') != env['GITHUB_SHA'] or
                not SHA_RE.fullmatch(expected_parent)):
            raise PermissionError('owned platform send binding changed')

    def send_owned(self, state_store, context, assessment, scope, prepared,
                   packet, expected_parent):
        """Run original admission, scoped commit, non-force push and one dispatch."""
        self.assert_session(state_store)
        self._send_window(packet, expected_parent)
        if self.current_parent() != expected_parent:
            raise PermissionError('gh-pages parent moved; reconcile only')
        if self.manifest() != packet['baseline']:
            raise PermissionError('gh-pages baseline changed; reconcile only')

        # This is the existing privileged publisher admission and seven-path
        # release guard. It rechecks source, audit, candidate and live scope.
        from scripts import phase06_kernel_release
        if self.source_audit_path is None:
            raise PermissionError('fresh source audit required')
        with TemporaryDirectory(prefix='manager-owned-admit-') as output:
            result = phase06_kernel_release.admit_owned(
                context, assessment, scope, prepared, self.checkout,
                self.source_audit_path, Path(output) / 'admission.json',
                self._now(),
            )
        if (result.get('status') != 'ADMITTED_MANAGER_PREFIX_ONLY' or
                result.get('dispatch_deployment') is not True):
            raise PermissionError('original publisher admission did not authorize a send')
        changed = result.get('changed_files')
        if (not isinstance(changed, list) or not changed or
                len(set(changed)) != len(changed) or not set(changed) <= set(ALLOWED_PATHS)):
            raise PermissionError('exact scoped changes required')

        self._git('add', '--', *ALLOWED_PATHS)
        staged_text = self._git('diff', '--cached', '--name-only', '-z')
        staged = set(staged_text.split('\x00')) - {''}
        if not staged or not staged <= set(ALLOWED_PATHS) or staged != set(changed):
            raise PermissionError('staged paths differ from original admission')
        if self._git('rev-parse', 'HEAD') != expected_parent:
            raise PermissionError('gh-pages parent moved before commit')

        message = commit_message(packet)
        with TemporaryDirectory(prefix='manager-owned-commit-') as tmp:
            message_path = Path(tmp) / 'message.txt'
            message_path.write_text(message + '\n')
            tree = self._git('write-tree')
            if not SHA_RE.fullmatch(tree):
                raise PermissionError('exact staged tree required')
            commit = self._git(
                '-c', 'core.hooksPath=/dev/null',
                '-c', 'user.name=github-actions[bot]',
                '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                'commit-tree', tree, '-p', expected_parent, '-F', str(message_path),
            )
        self._validate_commit_tree(commit, expected_parent, tree, staged, packet)
        # update-ref is a local compare-and-swap. Suppress reference hooks for
        # this mutation without changing any repository or global config.
        self._git('-c', 'core.hooksPath=/dev/null', 'update-ref',
                  'refs/heads/gh-pages', commit, expected_parent)
        if self._git('rev-parse', 'HEAD') != commit:
            raise PermissionError('gh-pages ref did not advance to exact commit')
        self._assert_checkout_identity(clean=True)
        self._send_window(packet, expected_parent)
        if self._fetch_remote_parent() != expected_parent:
            raise PermissionError('gh-pages parent moved; reconcile only')
        # Fetch itself may cross either the packet lease or host lifetime.
        # This is the final gate immediately before the irreversible push.
        self._send_window(packet, expected_parent)
        # Non-force CAS push. Any response loss stays UNKNOWN and is reconciled.
        self._run_cli(['git', '-c', 'core.hooksPath=/dev/null',
                       '-C', str(self.checkout), 'push', 'origin',
                       f'HEAD:{PAGES_BRANCH}'])
        self._send_window(packet, expected_parent)
        # Only the existing protected workflow owns Pages deployment.
        self._run_cli([
            'gh', 'api', '--method', 'POST',
            f'repos/{REPOSITORY}/actions/workflows/{PAGES_WORKFLOW_ID}/dispatches',
            '--input', '-',
        ], input_data=json.dumps({'ref': 'gh-pages'}, separators=(',', ':')))
        return commit

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    def release_enabled(self):
        return os.environ.get('MANAGER_RELEASE_ENABLED') == 'true'

    def publisher_context(self):
        env = self._environment(require_release=True)
        return PublisherContext(env['GITHUB_REPOSITORY'], env['GITHUB_REF'], WORKFLOW,
                               env['GITHUB_SHA'], env['GITHUB_RUN_ID'],
                               workflow_commit=env['GITHUB_WORKFLOW_SHA'])
