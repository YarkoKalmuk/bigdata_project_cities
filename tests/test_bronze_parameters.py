"""Exercise the notebook parameter cell without reading datasets."""
from pathlib import Path
from types import SimpleNamespace
import unittest


class Widgets:
    def __init__(self, **values):
        self.values = values

    def text(self, key, default):
        self.values.setdefault(key, default)

    def dropdown(self, key, default, choices):
        self.text(key, default)

    def get(self, key):
        return self.values[key]


class BronzeParametersTests(unittest.TestCase):
    def run_cell(self, **values):
        code = Path('notebooks/01_ingest_bronze.py').read_text().split('# COMMAND ----------')[1]
        scope = {'dbutils': SimpleNamespace(widgets=Widgets(**values))}
        exec(compile(code, 'bronze-parameter-cell', 'exec'), scope)
        return scope

    def test_florence_uses_selected_city_and_widget_url(self):
        url = 'https://data.insideairbnb.com/italy/toscana/florence/2026-09-19/data/listings.csv.gz'
        values = self.run_cell(city='florence', catalog='team_catalog', source_url=url)
        self.assertEqual(values['source_url'], url)
        self.assertEqual(values['source_path'], '/Volumes/team_catalog/airbnb_bronze/raw_files/florence/2026-09-19/listings.csv.gz')

    def test_milan_defaults_to_recorded_source(self):
        values = self.run_cell()
        self.assertIn('/milan/', values['source_url'])
        self.assertIn('/milan/', values['source_path'])

    def test_stale_milan_path_cannot_load_as_florence(self):
        with self.assertRaisesRegex(ValueError, 'Upload the original file'):
            self.run_cell(city='florence', source_path='/Volumes/workspace/airbnb_bronze/raw_files/milan/2026-09-19/listings.csv.gz')
