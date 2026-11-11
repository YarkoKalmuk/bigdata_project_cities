"""Check the runnable Job graph and parameter contract without a workspace."""
import ast
import json
from pathlib import Path
import unittest


class JobDefinitionTests(unittest.TestCase):
    def test_job_pins_an_immutable_commit(self):
        source = json.loads(Path('jobs/airbnb_etl.job.json').read_text())['git_source']
        self.assertRegex(source['git_commit'], r'^[0-9a-f]{40}$')
        self.assertNotIn('git_branch', source)
        self.assertNotIn('git_tag', source)

    def test_graph_uses_real_notebooks_and_fail_closed_dependencies(self):
        job = json.loads(Path('jobs/airbnb_etl.job.json').read_text())
        self.assertEqual(job['max_concurrent_runs'], 1)
        self.assertNotIn('schedule', job)
        self.assertNotIn('job_clusters', job)
        self.assertEqual([t['task_key'] for t in job['tasks']], ['bronze', 'silver', 'gold', 'validate'])
        previous = None
        for task in job['tasks']:
            self.assertEqual(task['notebook_task']['source'], 'GIT')
            self.assertEqual(task.get('depends_on', []), [] if previous is None else [{'task_key': previous}])
            self.assertNotIn('existing_cluster_id', task)
            self.assertNotIn('new_cluster', task)
            self.assertEqual(task.get('run_if', 'ALL_SUCCESS'), 'ALL_SUCCESS')
            path = Path(task['notebook_task']['notebook_path'])
            self.assertTrue(path.is_file())
            self.assertIn('environment_version = "6"', path.read_text())
            ast.parse(path.read_text())
            previous = task['task_key']

    def test_parameters_have_no_city_specific_path_or_url(self):
        job = json.loads(Path('jobs/airbnb_etl.job.json').read_text())
        params = {p['name']: p['default'] for p in job['parameters']}
        self.assertEqual(set(params), {'catalog', 'city', 'snapshot_date', 'source_path', 'source_url', 'sources_config_path'})
        self.assertEqual(params['sources_config_path'], '')
        self.assertEqual(params['source_path'], '')
        self.assertEqual(params['source_url'], '')
        self.assertEqual(job['tasks'][-1]['notebook_task']['base_parameters']['job_run_id'], '{{job.run_id}}')
