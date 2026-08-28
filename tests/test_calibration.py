import json
import sys
import unittest
from pathlib import Path

import pandas as pd


# Add C:\SIH\heat-health-engine to Python's import path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from heat_health.calibrated_map import (
    OUTPUT_MAP_FILE,
    normalize_ward_id,
    select_peak_risk_rows,
)
from heat_health.mortality_calibration import (
    OUTPUT_FILE,
    calculate_evidence_calibration,
    classify_calibrated_risk,
)

def create_risk_row(
    danger_day=False,
    consecutive_days=0,
    wbgt=25.0,
    utci=30.0,
    extreme_hours=0,
    thermal_score=40.0,
):
    return pd.Series(
        {
            "danger_day": danger_day,
            "consecutive_danger_days": consecutive_days,
            "thermal_hazard_score": thermal_score,
            "wbgt_max_c": wbgt,
            "utci_max_c": utci,
            "extreme_hours": extreme_hours,
        }
    )


class MortalityCalibrationTests(unittest.TestCase):

    def test_safe_conditions_have_no_adjustment(self):
        row = create_risk_row()

        result = calculate_evidence_calibration(row)

        self.assertEqual(
            result["evidence_relative_risk"],
            1.0,
        )

        self.assertEqual(
            result["evidence_relative_increase_pct"],
            0.0,
        )

    def test_two_day_heatwave_uses_published_risk(self):
        row = create_risk_row(
            danger_day=True,
            consecutive_days=2,
            wbgt=31.0,
            utci=42.0,
        )

        result = calculate_evidence_calibration(row)

        self.assertEqual(
            result["evidence_relative_risk"],
            1.147,
        )

        self.assertEqual(
            result["evidence_relative_increase_pct"],
            14.7,
        )

    def test_three_day_severe_heat_is_interpolated(self):
        row = create_risk_row(
            danger_day=True,
            consecutive_days=3,
            wbgt=36.0,
            utci=48.0,
            extreme_hours=2,
            thermal_score=88.0,
        )

        result = calculate_evidence_calibration(row)

        self.assertEqual(
            result["evidence_relative_risk"],
            1.209,
        )

    def test_five_day_severe_heat_uses_maximum_evidence(self):
        row = create_risk_row(
            danger_day=True,
            consecutive_days=5,
            wbgt=37.0,
            utci=50.0,
            extreme_hours=4,
            thermal_score=92.0,
        )

        result = calculate_evidence_calibration(row)

        self.assertEqual(
            result["evidence_relative_risk"],
            1.332,
        )

        self.assertEqual(
            result["evidence_relative_increase_pct"],
            33.2,
        )

    def test_calibrated_risk_boundaries(self):
        self.assertEqual(
            classify_calibrated_risk(0),
            "Low",
        )

        self.assertEqual(
            classify_calibrated_risk(24.99),
            "Low",
        )

        self.assertEqual(
            classify_calibrated_risk(25),
            "Moderate",
        )

        self.assertEqual(
            classify_calibrated_risk(50),
            "High",
        )

        self.assertEqual(
            classify_calibrated_risk(75),
            "Extreme",
        )

        self.assertEqual(
            classify_calibrated_risk(100),
            "Extreme",
        )


class CalibratedMapTests(unittest.TestCase):

    def test_ward_id_normalization(self):
        self.assertEqual(normalize_ward_id(1), "1")
        self.assertEqual(normalize_ward_id(1.0), "1")
        self.assertEqual(normalize_ward_id("1"), "1")

        self.assertEqual(
            normalize_ward_id("UNNUMBERED_001"),
            "UNNUMBERED_001",
        )

    def test_peak_day_is_selected_for_each_ward(self):
        data = pd.DataFrame(
            [
                {
                    "ward_id": "1",
                    "forecast_date": "2026-08-28",
                    "calibrated_mortality_risk_index": 50,
                },
                {
                    "ward_id": "1",
                    "forecast_date": "2026-08-29",
                    "calibrated_mortality_risk_index": 80,
                },
                {
                    "ward_id": "2",
                    "forecast_date": "2026-08-28",
                    "calibrated_mortality_risk_index": 40,
                },
            ]
        )

        peaks = select_peak_risk_rows(data)

        self.assertEqual(len(peaks), 2)

        self.assertEqual(
            peaks.loc["1", "forecast_date"],
            "2026-08-29",
        )

        self.assertEqual(
            peaks.loc[
                "1",
                "calibrated_mortality_risk_index",
            ],
            80,
        )

    def test_calibrated_forecast_integrity(self):
        self.assertTrue(
            OUTPUT_FILE.exists(),
            f"Calibrated forecast not found: {OUTPUT_FILE}",
        )

        data = pd.read_csv(OUTPUT_FILE)

        self.assertEqual(len(data), 1450)
        self.assertEqual(data["ward_id"].nunique(), 290)
        self.assertEqual(
            data["forecast_date"].nunique(),
            5,
        )

        scores = data[
            "calibrated_mortality_risk_index"
        ]

        self.assertFalse(scores.isna().any())
        self.assertTrue(scores.between(0, 100).all())

        relative_risks = data[
            "evidence_relative_risk"
        ]

        self.assertTrue(
            relative_risks.between(
                1.0,
                1.332,
            ).all()
        )

    def test_calibrated_geojson_integrity(self):
        self.assertTrue(
            OUTPUT_MAP_FILE.exists(),
            f"Calibrated map not found: {OUTPUT_MAP_FILE}",
        )

        with OUTPUT_MAP_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            geojson = json.load(file)

        self.assertEqual(
            geojson["type"],
            "FeatureCollection",
        )

        features = geojson["features"]

        self.assertEqual(len(features), 290)

        ward_ids = []

        valid_colors = {
            "#2ECC71",
            "#F1C40F",
            "#E67E22",
            "#C0392B",
        }

        for feature in features:
            self.assertIsNotNone(
                feature.get("geometry")
            )

            properties = feature["properties"]

            ward_ids.append(
                str(properties["ward_id"])
            )

            self.assertIn(
                properties["map_color"],
                valid_colors,
            )

            self.assertIn(
                properties["risk_level"],
                {
                    "Low",
                    "Moderate",
                    "High",
                    "Extreme",
                },
            )

            self.assertGreaterEqual(
                properties["mortality_risk_index"],
                0,
            )

            self.assertLessEqual(
                properties["mortality_risk_index"],
                100,
            )

            self.assertIn(
                "base_mortality_risk_index",
                properties,
            )

            self.assertIn(
                "evidence_relative_risk",
                properties,
            )

        self.assertEqual(
            len(ward_ids),
            len(set(ward_ids)),
        )


if __name__ == "__main__":
    unittest.main()