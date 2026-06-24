from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
import pandas as pd

from aes.populate import populate_caiso_inputs
from aes.schemas import validate_input_dir
from aes.watttime_v3 import normalize_moer_to_aes_schema, aggregate_moer_hourly, LB_PER_MWH_TO_G_PER_KWH
from aes.caiso_oasis import normalize_lmp_to_aes_schema
from aes.dispatch import run_dispatch
from aes.monte_carlo import run_monte_carlo


class TestAESCore(unittest.TestCase):
    def test_moer_conversion_and_hourly_aggregation(self):
        raw = pd.DataFrame({
            "point_time": ["2026-01-01T08:00:00Z", "2026-01-01T08:05:00Z"],
            "value": [1000.0, 1100.0],
        })
        aes = normalize_moer_to_aes_schema(raw)
        self.assertAlmostEqual(aes["moer_g_co2e_kwh"].iloc[0], 1000.0 * LB_PER_MWH_TO_G_PER_KWH)
        hourly = aggregate_moer_hourly(aes)
        self.assertEqual(len(hourly), 1)

    def test_lmp_conversion(self):
        raw = pd.DataFrame({
            "INTERVALSTARTTIME_GMT": ["2026-01-01T08:00:00Z"],
            "LMP_PRC": [100.0],
        })
        aes = normalize_lmp_to_aes_schema(raw)
        self.assertAlmostEqual(aes["price_usd_kwh"].iloc[0], 0.1)

    def test_full_demo_pipeline(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            populate_caiso_inputs(td/"raw", td/"processed", demo=True)
            report = validate_input_dir(td/"processed")
            self.assertTrue(report["ok"], report)
            dispatch = run_dispatch(td/"processed", td/"outputs")
            self.assertEqual(len(dispatch), 168)
            summary, conv = run_monte_carlo(td/"processed", td/"outputs", n=1000)
            self.assertTrue((td/"outputs"/"monte_carlo_summary.csv").exists())
            self.assertGreater(len(summary), 0)
            self.assertGreater(len(conv), 0)


if __name__ == "__main__":
    unittest.main()
