"""Regressions raised by independent review; no production safety gate relaxed."""
from datetime import datetime as RealDatetime, timezone
import ast
import importlib.util
import inspect
from pathlib import Path
import textwrap
from unittest.mock import patch
import unittest

ROOT=Path(__file__).resolve().parents[1]

class LaterUtc(RealDatetime):
    @classmethod
    def now(cls,tz=None):
        return cls(2030,1,1,tzinfo=timezone.utc)

class ReviewRegressions(unittest.TestCase):
    def test_one_existing_pages_deployment_authority_not_stale_full_site_upload(self):
        workflow=(ROOT.parents[1]/'.github/workflows/manager-phase06-service.yml').read_text()
        self.assertNotIn('uses: actions/deploy-pages@',workflow)
        self.assertNotIn('uses: actions/upload-pages-artifact@',workflow)
        self.assertIn('workflow_dispatch',workflow)
        self.assertIn("if: github.repository == 'Daisuke134/life-manager' && github.ref == 'refs/heads/main' && (github.event_name == 'schedule' || github.event_name == 'workflow_dispatch')",workflow)
        self.assertIn('group: manager-pages-prefix-writer',workflow)
        self.assertIn('actions: write',workflow)
        self.assertIn('GH_TOKEN: ${{ github.token }}',workflow)
        self.assertEqual(workflow.count('python scripts/run_owned_digital_cycle.py "$MANAGER_OPERATION"'),1)
        self.assertIn(
            'case "$MANAGER_OPERATION" in\n'
            '            run-once|stop|rollback|resume) ;;\n'
            '            *) echo "invalid manager operation" >&2; exit 2 ;;\n'
            '          esac',
            workflow)
        self.assertNotRegex(workflow,r'(?m)^\s+git push\b')

        from manager_core.owned_platform_host import (
            GitHubActionsCycleHost, PAGES_BRANCH, PAGES_WORKFLOW_ID,
        )
        from manager_core import owned_cycle

        self.assertEqual(PAGES_WORKFLOW_ID,'307239134')
        send_source=inspect.getsource(GitHubActionsCycleHost.send_owned)
        send_tree=ast.parse(textwrap.dedent(send_source))
        calls=[node for node in ast.walk(send_tree) if isinstance(node,ast.Call)]
        cas_calls=[node for node in calls
                   if isinstance(node.func,ast.Attribute) and node.func.attr=='_git'
                   and any(isinstance(arg,ast.Constant) and arg.value=='update-ref'
                           for arg in node.args)]
        self.assertEqual(len(cas_calls),1)
        self.assertTrue(any(isinstance(node,ast.Name) and node.id=='expected_parent'
                            for node in ast.walk(cas_calls[0])))

        push_calls=[]
        for node in calls:
            if not (isinstance(node.func,ast.Attribute) and node.func.attr=='_run_cli'
                    and node.args and isinstance(node.args[0],ast.List)):
                continue
            constants=[item.value for item in ast.walk(node.args[0])
                       if isinstance(item,ast.Constant) and isinstance(item.value,str)]
            if 'push' in constants and 'origin' in constants:
                push_calls.append((node,constants))
        self.assertEqual(len(push_calls),1)
        push_node,push_constants=push_calls[0]
        self.assertNotIn('--force',push_constants)
        self.assertTrue(any(isinstance(node,ast.Name) and node.id=='PAGES_BRANCH'
                            for node in ast.walk(push_node)))
        self.assertIn('PAGES_WORKFLOW_ID',send_source)
        self.assertIn('refs/heads/gh-pages',PAGES_BRANCH)

        collector_tree=ast.parse(textwrap.dedent(
            inspect.getsource(GitHubActionsCycleHost.observe_delivery)))
        self.assertTrue(any(isinstance(node,ast.Name) and node.id=='collect_owned_delivery'
                            for node in ast.walk(collector_tree)))
        cycle_tree=ast.parse(textwrap.dedent(
            inspect.getsource(owned_cycle._observe_owned_delivery)))
        self.assertTrue(any(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                            and node.func.attr=='observe_delivery'
                            for node in ast.walk(cycle_tree)))

    def test_fixture_suite_works_in_2030_while_production_stale_catalog_is_rejected(self):
        from manager_core import digital_environment as impl
        import json
        catalog=json.loads((ROOT/'public_goods/service/catalog.json').read_text())
        with patch.object(impl,'datetime',LaterUtc):
            with self.assertRaises(ValueError): impl.validate_catalog(catalog)
        for name in ('test_phase06_service_execution','test_phase06_release_guard'):
            path=ROOT/'tests'/f'{name}.py'
            spec=importlib.util.spec_from_file_location(name+'_clock_regression',path)
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            suite=unittest.defaultTestLoader.loadTestsFromModule(mod)
            result=unittest.TestResult()
            with patch.object(impl,'datetime',LaterUtc):
                suite.run(result)
            self.assertTrue(result.wasSuccessful(),f'{name}: {result.failures!r} {result.errors!r}')

if __name__=='__main__': unittest.main()
