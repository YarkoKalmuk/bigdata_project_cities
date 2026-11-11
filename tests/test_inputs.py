"""Input metadata tests use local fixtures and never download or inspect a city."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from airbnb.inputs import load_sources, resolve_snapshot, resolve_source


SYNTHETIC = {
    'synthetic_city': {
        'snapshot_date': '2026-01-02',
        'source_url': 'https://data.insideairbnb.com/example/synthetic_city/2026-01-02/data/listings.csv.gz',
        'centre_latitude': 0,
        'centre_longitude': 0,
    }
}


class InputTests(unittest.TestCase):
    def test_new_configured_city_resolves_without_code_changes(self):
        result = resolve_snapshot(SYNTHETIC, 'workspace', 'synthetic_city', '')
        path, url = resolve_source(result)
        self.assertEqual(result.snapshot_date, '2026-01-02')
        self.assertEqual(result.centre, (0.0, 0.0))
        self.assertEqual(path, '/Volumes/workspace/airbnb_bronze/raw_files/synthetic_city/2026-01-02/listings.csv.gz')
        self.assertEqual(url, SYNTHETIC['synthetic_city']['source_url'])

    def test_external_manifest_is_runtime_input(self):
        path = '/Volumes/workspace/airbnb_bronze/raw_files/config/synthetic.json'
        with patch.object(Path, 'read_text', return_value=json.dumps(SYNTHETIC)) as read:
            loaded = load_sources(Path.cwd(), 'workspace', path)
        self.assertEqual(loaded, SYNTHETIC)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(resolve_snapshot(loaded, 'workspace', 'synthetic_city', '').city, 'synthetic_city')

    def test_rejects_unconfigured_city_and_snapshot_mismatch(self):
        for city, snapshot in [('unknown', ''), ('synthetic_city', '2026-01-03')]:
            with self.assertRaises(ValueError):
                resolve_snapshot(SYNTHETIC, 'workspace', city, snapshot)

    def test_rejects_bad_identifiers_and_noncanonical_dates(self):
        for catalog, city, snapshot in [("a`", 'synthetic_city', ''), ('workspace', "x' OR true", ''), ('workspace', 'synthetic_city', '20260102')]:
            with self.assertRaises(ValueError):
                resolve_snapshot(SYNTHETIC, catalog, city, snapshot)

    def test_rejects_manifest_outside_input_volume(self):
        for path in ['/tmp/config.json', '/Volumes/other/airbnb_bronze/raw_files/config/data.json', '/Volumes/workspace/airbnb_bronze/raw_files/config/../data.json']:
            with self.assertRaises(ValueError):
                load_sources(Path.cwd(), 'workspace', path)

    def test_missing_centre_is_supported_but_partial_or_nonfinite_is_not(self):
        bare = {'synthetic_city': {'snapshot_date': '2026-01-02'}}
        self.assertIsNone(resolve_snapshot(bare, 'workspace', 'synthetic_city', '').centre)
        for extra in [{'centre_latitude': 1}, {'centre_latitude': float('nan'), 'centre_longitude': 0}]:
            with self.assertRaises(ValueError):
                resolve_snapshot({'synthetic_city': dict(bare['synthetic_city'], **extra)}, 'workspace', 'synthetic_city', '')

    def test_rejects_source_from_another_city_or_date(self):
        snapshot = resolve_snapshot(SYNTHETIC, 'workspace', 'synthetic_city', '')
        for url in ['https://data.insideairbnb.com/example/other/2026-01-02/data/listings.csv.gz', 'https://data.insideairbnb.com/example/synthetic_city/2026-01-03/data/listings.csv.gz']:
            with self.assertRaises(ValueError):
                resolve_source(snapshot, source_url=url)

    def test_all_pipeline_parameter_cells_support_runtime_manifest(self):
        # Execute actual notebook parameter cells with a synthetic manifest. No
        # Spark action, source read or download occurs in these cells.
        from types import SimpleNamespace
        from test_bronze_parameters import Widgets
        for filename in ('01_ingest_bronze.py', '02_prepare_silver.py', '03_build_gold.py'):
            code = (Path('notebooks') / filename).read_text().split('# COMMAND ----------')[1]
            widgets = Widgets(city='synthetic_city', snapshot_date='2026-01-02', sources_config_path='/Volumes/workspace/airbnb_bronze/raw_files/config/synthetic.json')
            with patch('airbnb.inputs.load_sources', return_value=SYNTHETIC):
                scope = {'dbutils': SimpleNamespace(widgets=widgets)}
                exec(compile(code, filename, 'exec'), scope)
            self.assertEqual(scope['city'], 'synthetic_city')
            self.assertEqual(scope['snapshot_date'], '2026-01-02')
