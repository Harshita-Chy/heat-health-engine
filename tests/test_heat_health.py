"""Automated tests for the heat-health engine."""

import unittest

import pandas as pd

from heat_health.risk_engine import (
    calculate_duration_score,
    calculate_thermal_hazard_score,
    classify_risk,
)
from heat_health.thermal import (
    calculate_thermal_stress,
)
from heat_health.ward_vulnerability import (
    normalize_score,
)


class ThermalEngineTests(unittest.TestCase):
    """Test the scientific thermal-stress calculations."""

    def test_humid_heat_is_more_dangerous(self):
        """Same temperature with more humidity should be riskier."""

        dry_heat = calculate_thermal_stress(
            temperature_c=40,
            humidity=20,
            wind_speed_10m=2,
            solar_radiation=800,
        )

        humid_heat = calculate_thermal_stress(
            temperature_c=40,
            humidity=70,
            wind_speed_10m=2,
            solar_radiation=800,
        )

        self.assertGreater(
            humid_heat["heat_index_c"],
            dry_heat["heat_index_c"],
        )

        self.assertGreater(
            humid_heat["estimated_wbgt_c"],
            dry_heat["estimated_wbgt_c"],
        )

    def test_solar_radiation_increases_wbgt(self):
        """Direct sunlight should raise outdoor WBGT."""

        shaded = calculate_thermal_stress(
            temperature_c=38,
            humidity=50,
            wind_speed_10m=2,
            solar_radiation=0,
        )

        direct_sun = calculate_thermal_stress(
            temperature_c=38,
            humidity=50,
            wind_speed_10m=2,
            solar_radiation=800,
        )

        self.assertGreater(
            direct_sun["estimated_globe_temperature_c"],
            shaded["estimated_globe_temperature_c"],
        )

        self.assertGreater(
            direct_sun["estimated_wbgt_c"],
            shaded["estimated_wbgt_c"],
        )

    def test_invalid_humidity_is_rejected(self):
        """Humidity above 100% should generate an error."""

        with self.assertRaises(ValueError):
            calculate_thermal_stress(
                temperature_c=40,
                humidity=120,
                wind_speed_10m=2,
                solar_radiation=800,
            )

    def test_invalid_solar_radiation_is_rejected(self):
        """Negative solar radiation should generate an error."""

        with self.assertRaises(ValueError):
            calculate_thermal_stress(
                temperature_c=40,
                humidity=50,
                wind_speed_10m=2,
                solar_radiation=-10,
            )


class RiskEngineTests(unittest.TestCase):
    """Test hazard scoring and risk classification."""

    def test_extreme_conditions_have_higher_score(self):
        moderate_score = calculate_thermal_hazard_score(
            heat_index_c=32,
            wbgt_c=26,
            utci_c=34,
        )

        extreme_score = calculate_thermal_hazard_score(
            heat_index_c=55,
            wbgt_c=35,
            utci_c=49,
        )

        self.assertGreater(
            extreme_score,
            moderate_score,
        )

    def test_duration_score_is_limited_to_100(self):
        score = calculate_duration_score(
            consecutive_danger_days=10
        )

        self.assertEqual(score, 100)

    def test_risk_classification_boundaries(self):
        self.assertEqual(
            classify_risk(10),
            ("Low", "Green"),
        )

        self.assertEqual(
            classify_risk(30),
            ("Moderate", "Yellow"),
        )

        self.assertEqual(
            classify_risk(60),
            ("High", "Orange"),
        )

        self.assertEqual(
            classify_risk(85),
            ("Extreme", "Red"),
        )


class VulnerabilityEngineTests(unittest.TestCase):
    """Test ward-indicator normalization."""

    def test_higher_value_produces_higher_score(self):
        values = pd.Series([10, 20, 30])

        scores = normalize_score(
            values,
            higher_is_worse=True,
        )

        self.assertEqual(scores.iloc[0], 0)
        self.assertEqual(scores.iloc[1], 50)
        self.assertEqual(scores.iloc[2], 100)

    def test_healthcare_score_is_reversed(self):
        hospital_availability = pd.Series(
            [1, 2, 3]
        )

        deficiency_scores = normalize_score(
            hospital_availability,
            higher_is_worse=False,
        )

        self.assertEqual(
            deficiency_scores.iloc[0],
            100,
        )

        self.assertEqual(
            deficiency_scores.iloc[2],
            0,
        )


if __name__ == "__main__":
    unittest.main()