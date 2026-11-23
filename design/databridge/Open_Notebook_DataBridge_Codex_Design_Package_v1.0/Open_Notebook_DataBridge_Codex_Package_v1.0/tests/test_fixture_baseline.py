"""Offline design-fixture invariants; intended to be run with standard-library unittest.

This is NOT an application integration test and cannot certify Open Notebook's behavior.
"""
from __future__ import annotations
import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'fixtures'


def read_csv(name: str):
    with (FIX / name).open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


class SyntheticFixtureTests(unittest.TestCase):
    def test_ntd_transit_trend(self):
        rows = read_csv('ntd_synthetic.csv')
        bus_a = {int(r['year']): int(r['unlinked_passenger_trips'])
                 for r in rows if r['agency_id'] == 'DEMO-A1' and r['mode'] == 'Bus'}
        self.assertEqual(bus_a[2022], 1_000_000)
        self.assertEqual(bus_a[2025], 1_250_000)
        self.assertAlmostEqual(bus_a[2025] / bus_a[2022] - 1, 0.25)
        bus_2025 = sum(int(r['unlinked_passenger_trips']) for r in rows
                       if r['mode'] == 'Bus' and r['year'] == '2025')
        self.assertEqual(bus_2025, 2_050_000)

    def test_population_denominator_only_for_verified_mapping(self):
        xwalk = {r['agency_id']: r for r in read_csv('geography_crosswalk_synthetic.csv')}
        self.assertEqual(xwalk['DEMO-A1']['join_verified'], 'true')
        self.assertEqual(xwalk['DEMO-A2']['join_verified'], 'false')
        pop = {(r['geography_id'], int(r['year'])): int(r['population'])
               for r in read_csv('census_synthetic.csv')}
        self.assertAlmostEqual(1_250_000 / pop[('DEMO-UZA-A', 2025)], 12.135922330097088)
        # There is no *trusted* agency-to-Census crosswalk for A2 in this test set.
        self.assertFalse(xwalk['DEMO-A2']['join_verified'] == 'true')

    def test_noaa_coverage_warning_needed(self):
        weather = [r for r in read_csv('noaa_synthetic.csv')
                   if r['station_id'] == 'DEMO-ST-A' and r['year'] == '2025']
        self.assertEqual(len(weather), 1)
        self.assertLess(int(weather[0]['days_observed']), 365)

    def test_explicit_synthetic_labels(self):
        for name in ['ntd_synthetic.csv', 'census_synthetic.csv',
                     'noaa_synthetic.csv', 'geography_crosswalk_synthetic.csv']:
            content = (FIX / name).read_text()
            self.assertIn('DEMO-', content)


if __name__ == '__main__':
    unittest.main()
