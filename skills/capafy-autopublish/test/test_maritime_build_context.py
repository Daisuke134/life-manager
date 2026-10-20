import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

MODULE = Path(__file__).resolve().parents[3] / 'apps/life-manager/maritime/build-context.py'

class MaritimeBuildContextTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.is_file(), 'build-context.py must build a sanitized immutable source archive')
        spec = importlib.util.spec_from_file_location('maritime_build_context', MODULE)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'; self.repo.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Fixture'); self.git('config', 'user.email', 'fixture@example.invalid')
        docker = self.repo / 'apps/life-manager/maritime/Dockerfile'; docker.parent.mkdir(parents=True)
        docker.write_text('FROM node:22-bookworm-slim\nCMD ["node", "apps/life-manager/maritime/server.js"]\n')
        server = docker.parent / 'server.js'; server.write_text('immutable release server\n')
        for name in ['.env', 'credentials/account.json', 'runtime/state/private.json', '.codex/auth.json', '.worktrees/other/file', 'memory/private.md']:
            target = self.repo / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_text('fake-private-content')
        self.git('add', '-A'); self.git('-c', 'commit.gpgSign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '-m', 'fixture')
        self.sha = self.git('rev-parse', 'HEAD').strip()
        self.git('update-ref', 'refs/remotes/origin/main', self.sha)
        server.write_text('uncommitted content must never ship\n')
        (self.repo / 'untracked.txt').write_text('must never ship')
        self.output = self.root / 'maritime.zip'
    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, capture_output=True, text=True, check=True,
            env={'PATH': os.environ['PATH'], 'HOME': str(self.root), 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1'}).stdout
    def test_zip_contains_only_tracked_release_and_root_dockerfile(self):
        receipt = self.module.build_context(self.repo, self.sha, self.output)
        with zipfile.ZipFile(self.output) as archive:
            names = set(archive.namelist())
            self.assertEqual(names, {'Dockerfile', 'apps/life-manager/maritime/Dockerfile', 'apps/life-manager/maritime/server.js'})
            self.assertEqual(archive.read('Dockerfile'), archive.read('apps/life-manager/maritime/Dockerfile'))
            self.assertEqual(archive.read('apps/life-manager/maritime/server.js'), b'immutable release server\n')
        self.assertFalse((self.repo / 'Dockerfile').exists())
        self.assertEqual(receipt['sourceSha'], self.sha)
        self.assertEqual(receipt['fileCount'], 3)
        self.assertEqual(len(receipt['archiveSha256']), 64)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
    def test_unmerged_or_non_sha_release_is_rejected(self):
        target = self.repo / 'next.js'; target.write_text('branch-only\n'); self.git('add', 'next.js')
        self.git('-c', 'commit.gpgSign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '-m', 'branch fixture')
        other = self.git('rev-parse', 'HEAD').strip()
        for sha in [other, 'main', 'a' * 40]:
            with self.assertRaisesRegex(ValueError, 'release'):
                self.module.build_context(self.repo, sha, self.output)
        self.assertFalse(self.output.exists())
    def test_existing_archive_is_never_overwritten(self):
        self.output.write_text('keep existing archive')
        with self.assertRaises(FileExistsError):self.module.build_context(self.repo, self.sha, self.output)
        self.assertEqual(self.output.read_text(), 'keep existing archive')
    def test_archive_exceeding_platform_limit_is_not_left_as_a_valid_upload(self):
        self.module.MAX_UNPACKED_BYTES = 1
        with self.assertRaisesRegex(ValueError, 'limit'):
            self.module.build_context(self.repo, self.sha, self.output)
        self.assertFalse(self.output.exists())

if __name__ == '__main__':unittest.main()
