from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class OwnedWorkflowContractTests(unittest.TestCase):
    def test_main_owner_is_single_cli_writer_and_private_artifacts_stay_private(self):
        workflow = (ROOT / '.github/workflows/manager-phase06-service.yml').read_text()
        self.assertIn('schedule:', workflow)
        self.assertIn('refs/heads/main', workflow)
        self.assertIn('group: manager-pages-prefix-writer', workflow)
        self.assertIn("if: github.repository == 'Daisuke134/life-manager' && github.ref == 'refs/heads/main' && (github.event_name == 'schedule' || github.event_name == 'workflow_dispatch')", workflow)
        self.assertEqual(workflow.count('run_owned_digital_cycle.py run-once'), 1)
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

    def test_legacy_research_writer_gate_is_removed(self):
        workflow = (ROOT / '.github/workflows/manager-phase06-service.yml').read_text()
        self.assertNotIn('research/manager-product-r006-20261020', workflow)
        self.assertIn('  publish-owned-prefix:', workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)


if __name__ == '__main__':
    unittest.main()
