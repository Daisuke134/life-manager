from pathlib import Path
import json
import os
import subprocess
import textwrap
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


class OwnedWorkflowContractTests(unittest.TestCase):
    def _publish_script(self):
        workflow = (ROOT / '.github/workflows/manager-phase06-service.yml').read_text()
        lines = workflow.splitlines()
        try:
            step = next(i for i, line in enumerate(lines)
                        if line.startswith('      - name: Restore,'))
            run = next(i for i in range(step + 1, len(lines))
                       if lines[i] == '        run: |')
        except StopIteration:
            self.fail('owned writer run block must remain extractable')
        script = []
        for line in lines[run + 1:]:
            if not line.startswith('          '):
                break
            script.append(line[10:])
        return '\n'.join(script) + '\n'

    def _run_publish_script(self, operation, *, cli_status=0):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        fake_bin = root / 'bin'
        fake_bin.mkdir()
        log = root / 'cli-call.json'
        summary_called = root / 'summary-called'
        fake_python = fake_bin / 'python'
        fake_python.write_text(textwrap.dedent('''\
            #!/usr/bin/env python3
            import json, os, pathlib, sys
            if len(sys.argv) > 1 and sys.argv[1] == 'scripts/run_owned_digital_cycle.py':
                pathlib.Path(os.environ['CLI_CALL_LOG']).write_text(json.dumps(sys.argv[1:]))
                raise SystemExit(int(os.environ.get('MOCK_CLI_STATUS', '0')))
            if len(sys.argv) > 1 and sys.argv[1] == '-':
                sys.stdin.read()
                pathlib.Path(os.environ['SUMMARY_CALLED']).touch()
                summary = pathlib.Path(os.environ['RUNNER_TEMP']) / 'manager-public-summary.json'
                summary.write_text(json.dumps({'status': 'NO_ACTION'}))
                with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                    output.write('status=NO_ACTION\\n')
                raise SystemExit(0)
            raise SystemExit(97)
        '''))
        fake_python.chmod(0o755)
        output = root / 'github-output'
        workspace = root / 'workspace'
        workspace.mkdir()
        env = os.environ.copy()
        env.update({
            'PATH': str(fake_bin) + os.pathsep + env.get('PATH', ''),
            'MANAGER_OPERATION': operation,
            'RUNNER_TEMP': str(root),
            'GITHUB_WORKSPACE': str(workspace),
            'GITHUB_OUTPUT': str(output),
            'CLI_CALL_LOG': str(log),
            'SUMMARY_CALLED': str(summary_called),
            'MOCK_CLI_STATUS': str(cli_status),
        })
        return subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', self._publish_script()],
                              cwd=ROOT, env=env, text=True, capture_output=True), root

    def test_main_owner_is_single_cli_writer_and_private_artifacts_stay_private(self):
        workflow = (ROOT / '.github/workflows/manager-phase06-service.yml').read_text()
        self.assertIn('schedule:', workflow)
        self.assertIn('refs/heads/main', workflow)
        self.assertIn('group: manager-pages-prefix-writer', workflow)
        self.assertIn("if: github.repository == 'Daisuke134/life-manager' && github.ref == 'refs/heads/main' && (github.event_name == 'schedule' || github.event_name == 'workflow_dispatch')", workflow)
        self.assertEqual(workflow.count('python scripts/run_owned_digital_cycle.py "$MANAGER_OPERATION"'), 1)
        self.assertNotRegex(workflow, r'(?m)^\s+git push origin HEAD:gh-pages\s*$')
        self.assertIn('GH_TOKEN: ${{ github.token }}', workflow)
        self.assertIn('persist-credentials: false', workflow)
        self.assertIn('id-token: write', workflow)
        self.assertIn('contents: write', workflow)
        self.assertIn('actions: write', workflow)
        from manager_core.owned_platform_host import PAGES_WORKFLOW_ID
        self.assertEqual(PAGES_WORKFLOW_ID, '307239134')
        self.assertIn('manager-public-summary.json', workflow)
        self.assertNotIn('cycle.sqlite', workflow)
        self.assertNotIn('nonce', workflow)
        self.assertNotIn('source-audit.json', workflow)
        self.assertNotIn('verify-live', workflow)

    def test_each_dispatch_operation_reaches_one_cli_call_with_the_shared_roots(self):
        workflow = (ROOT / '.github/workflows/manager-phase06-service.yml').read_text()
        self.assertIn(
            "MANAGER_OPERATION: ${{ github.event_name == 'schedule' && 'run-once' || github.event.inputs.operation || 'run-once' }}",
            workflow)
        self.assertIn('        default: run-once\n        type: choice', workflow)
        self.assertIn(
            '        options:\n          - run-once\n          - stop\n          - rollback\n          - resume',
            workflow)
        for operation in ('run-once', 'stop', 'rollback', 'resume'):
            with self.subTest(operation=operation):
                result, root = self._run_publish_script(operation)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads((root / 'cli-call.json').read_text()), [
                    'scripts/run_owned_digital_cycle.py', operation,
                    '--state-store', str(root / 'manager-owned-state'),
                    '--pages-checkout', str(root / 'workspace/pages'),
                ])
                self.assertTrue((root / 'summary-called').exists())
                self.assertIn('status=NO_ACTION', (root / 'github-output').read_text())

    def test_unknown_operation_is_rejected_before_cli_or_summary_side_effects(self):
        for operation in ('', 'STOP', 'run-once; touch pwned', 'rollback --receipt sha'):
            with self.subTest(operation=operation):
                result, root = self._run_publish_script(operation)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse((root / 'cli-call.json').exists())
                self.assertFalse((root / 'summary-called').exists())

    def test_unknown_cli_exit_two_survives_tee_and_success_still_writes_summary(self):
        result, root = self._run_publish_script('rollback', cli_status=2)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((root / 'summary-called').exists())
        result, root = self._run_publish_script('run-once', cli_status=0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((root / 'summary-called').exists())

    def test_legacy_research_writer_gate_is_removed(self):
        workflow = (ROOT / '.github/workflows/manager-phase06-service.yml').read_text()
        self.assertNotIn('research/manager-product-r006-20261020', workflow)
        self.assertIn('  publish-owned-prefix:', workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)

    def test_existing_artifact_step_uploads_only_summary_and_two_proof_outputs(self):
        workflow = (ROOT / '.github/workflows/manager-phase06-service.yml').read_text()
        lines = workflow.splitlines()
        start = lines.index('      - name: Publish only the allowlisted public summary')
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].startswith('      - name: ')), len(lines))
        step = lines[start:end]
        self.assertEqual(sum(line.strip() == 'uses: actions/upload-artifact@v4' for line in step), 1)
        path_line = next(i for i, line in enumerate(step) if line.strip() == 'path: |')
        paths = []
        for line in step[path_line + 1:]:
            if not line.startswith('            '):
                break
            paths.append(line.strip())
        self.assertEqual(paths, [
            '${{ runner.temp }}/manager-public-summary.json',
            '${{ runner.temp }}/manager-kernel-proof/kernel-public-proof.json',
            '${{ runner.temp }}/manager-kernel-proof/proof-explorer.html',
        ])
        self.assertNotIn('cycle.sqlite', '\n'.join(paths))
        self.assertNotIn('packet', '\n'.join(paths))
        self.assertNotIn('nonce', '\n'.join(paths))


if __name__ == '__main__':
    unittest.main()
