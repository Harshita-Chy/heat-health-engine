import json
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd


class PipelineOutputTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.weather_path = Path(
            "output/delhi_ward_hourly_forecast.csv"
        )

        cls.thermal_path = Path(
            "output/delhi_ward_hourly_thermal_forecast.csv"
        )

        cls.population_path = Path(
            "output/delhi_ward_population_exposure.csv"
        )

        cls.daily_path = Path(
            "output/delhi_ward_daily_risk_forecast.csv"
        )

        cls.map_path = Path(
            "output/delhi_5day_peak_risk_map.geojson"
        )

        cls.summary_path = Path(
            "output/delhi_risk_summary.json"
        )

        required_files = [
            cls.weather_path,
            cls.thermal_path,
            cls.population_path,
            cls.daily_path,
            cls.map_path,
            cls.summary_path,
        ]

        missing_files = [
            str(path)
            for path in required_files
            if not path.exists()
        ]

        if missing_files:
            raise FileNotFoundError(
                "Generate pipeline outputs before testing. "
                f"Missing files: {missing_files}"
            )

        cls.weather = pd.read_csv(
            cls.weather_path,
            dtype={"ward_id": "string"},
        )

        cls.thermal = pd.read_csv(
            cls.thermal_path,
            dtype={"ward_id": "string"},
        )

        cls.population = pd.read_csv(
            cls.population_path,
            dtype={"ward_id": "string"},
        )

        cls.daily = pd.read_csv(
            cls.daily_path,
            dtype={"ward_id": "string"},
        )

        cls.risk_map = gpd.read_file(
            cls.map_path
        )

        cls.risk_map["ward_id"] = cls.risk_map[
            "ward_id"
        ].astype("string")

        with cls.summary_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            cls.summary = json.load(file)

    def test_expected_row_counts(self):
        ward_count = 290
        forecast_days = 5
        hours_per_day = 24

        expected_hourly_rows = (
            ward_count
            * forecast_days
            * hours_per_day
        )

        expected_daily_rows = (
            ward_count
            * forecast_days
        )

        self.assertEqual(
            self.weather["ward_id"].nunique(),
            ward_count,
        )

        self.assertEqual(
            len(self.weather),
            expected_hourly_rows,
        )

        self.assertEqual(
            len(self.thermal),
            expected_hourly_rows,
        )

        self.assertEqual(
            len(self.daily),
            expected_daily_rows,
        )

        self.assertEqual(
            len(self.risk_map),
            ward_count,
        )

        self.assertEqual(
            self.daily["forecast_date"].nunique(),
            forecast_days,
        )

    def test_unique_ward_time_records(self):
        weather_duplicates = self.weather.duplicated(
            [
                "ward_id",
                "forecast_time_ist",
            ]
        )

        thermal_duplicates = self.thermal.duplicated(
            [
                "ward_id",
                "forecast_time_ist",
            ]
        )

        daily_duplicates = self.daily.duplicated(
            [
                "ward_id",
                "forecast_date",
            ]
        )

        self.assertFalse(
            weather_duplicates.any()
        )

        self.assertFalse(
            thermal_duplicates.any()
        )

        self.assertFalse(
            daily_duplicates.any()
        )

        self.assertEqual(
            self.population["ward_id"].nunique(),
            290,
        )

        self.assertEqual(
            self.risk_map["ward_id"].nunique(),
            290,
        )

    def test_weather_values_are_physical(self):
        self.assertTrue(
            self.weather["temperature_c"].between(
                -20,
                60,
            ).all()
        )

        self.assertTrue(
            self.weather[
                "relative_humidity_pct"
            ].between(
                0,
                100,
            ).all()
        )

        self.assertTrue(
            (
                self.weather[
                    "wind_speed_10m_mps"
                ] >= 0
            ).all()
        )

        self.assertTrue(
            (
                self.weather[
                    "solar_radiation_wm2"
                ] >= 0
            ).all()
        )

        self.assertTrue(
            (
                self.weather[
                    "solar_radiation_wm2"
                ] <= 1600
            ).all()
        )

    def test_thermal_results_are_complete(self):
        required_columns = [
            "heat_index_c",
            "wet_bulb_c",
            "estimated_globe_temperature_c",
            "estimated_mean_radiant_temperature_c",
            "estimated_wbgt_c",
            "utci_c",
            "utci_category",
            "thermal_stress_level",
        ]

        self.assertTrue(
            set(required_columns).issubset(
                self.thermal.columns
            )
        )

        self.assertFalse(
            self.thermal[
                required_columns
            ].isna().any().any()
        )

        self.assertTrue(
            self.thermal[
                "estimated_wbgt_c"
            ].between(
                -30,
                70,
            ).all()
        )

        self.assertTrue(
            self.thermal["utci_c"].between(
                -60,
                80,
            ).all()
        )

        self.assertTrue(
            self.thermal["heat_index_c"].between(
                -30,
                100,
            ).all()
        )

    def test_population_exposure_is_valid(self):
        required_columns = [
            "population_estimate_2020",
            "population_density_per_sq_km",
            "exposure_score",
        ]

        self.assertFalse(
            self.population[
                required_columns
            ].isna().any().any()
        )

        self.assertTrue(
            (
                self.population[
                    "population_estimate_2020"
                ] > 0
            ).all()
        )

        self.assertTrue(
            (
                self.population[
                    "population_density_per_sq_km"
                ] > 0
            ).all()
        )

        self.assertTrue(
            self.population[
                "exposure_score"
            ].between(
                0,
                100,
            ).all()
        )

        total_population = self.population[
            "population_estimate_2020"
        ].sum()

        self.assertGreater(
            total_population,
            10_000_000,
        )

        self.assertLess(
            total_population,
            30_000_000,
        )

    def test_risk_formula_is_correct(self):
        required_columns = [
            "thermal_hazard_score",
            "exposure_score",
            "heat_duration_score",
            "mortality_risk_index",
        ]

        self.assertFalse(
            self.daily[
                required_columns
            ].isna().any().any()
        )

        expected_risk = (
            self.daily["thermal_hazard_score"]
            * (
                0.70
                + 0.20
                * self.daily["exposure_score"]
                / 100.0
                + 0.10
                * self.daily["heat_duration_score"]
                / 100.0
            )
        ).clip(
            0,
            100,
        )

        np.testing.assert_allclose(
            self.daily[
                "mortality_risk_index"
            ].to_numpy(dtype=float),
            expected_risk.to_numpy(dtype=float),
            atol=0.02,
        )

        self.assertTrue(
            self.daily[
                "thermal_hazard_score"
            ].between(
                0,
                100,
            ).all()
        )

        self.assertTrue(
            self.daily[
                "mortality_risk_index"
            ].between(
                0,
                100,
            ).all()
        )

    def test_risk_labels_and_triggers(self):
        def expected_level(score):
            if score >= 75:
                return "Extreme"

            if score >= 50:
                return "High"

            if score >= 25:
                return "Moderate"

            return "Low"

        expected_levels = self.daily[
            "mortality_risk_index"
        ].map(expected_level)

        self.assertTrue(
            (
                self.daily["risk_level"]
                == expected_levels
            ).all()
        )

        alert_rows = self.daily[
            "risk_level"
        ].isin(
            [
                "High",
                "Extreme",
            ]
        )

        non_alert_rows = ~alert_rows

        trigger_columns = [
            "sms_alert_required",
            "open_cooling_centres",
            "shift_outdoor_work_hours",
            "hospital_surge_alert",
        ]

        for column in trigger_columns:
            normalized_values = (
                self.daily[column]
                .astype(str)
                .str.lower()
                .eq("true")
            )

            self.assertTrue(
                normalized_values[
                    alert_rows
                ].all()
            )

            self.assertFalse(
                normalized_values[
                    non_alert_rows
                ].any()
            )

    def test_peak_risk_map_matches_daily_data(self):
        daily_peak = (
            self.daily.groupby(
                "ward_id"
            )["mortality_risk_index"]
            .max()
            .sort_index()
        )

        map_peak = (
            self.risk_map.set_index(
                "ward_id"
            )["mortality_risk_index"]
            .astype(float)
            .sort_index()
        )

        self.assertEqual(
            list(daily_peak.index),
            list(map_peak.index),
        )

        np.testing.assert_allclose(
            daily_peak.to_numpy(dtype=float),
            map_peak.to_numpy(dtype=float),
            atol=0.02,
        )

        self.assertIsNotNone(
            self.risk_map.crs
        )

        self.assertEqual(
            self.risk_map.crs.to_epsg(),
            4326,
        )

    def test_summary_matches_daily_output(self):
        self.assertEqual(
            self.summary["wards"],
            290,
        )

        expected_dates = sorted(
            self.daily[
                "forecast_date"
            ].astype(str).unique().tolist()
        )

        self.assertEqual(
            self.summary["forecast_dates"],
            expected_dates,
        )

        self.assertAlmostEqual(
            float(
                self.summary[
                    "maximum_risk_index"
                ]
            ),
            float(
                self.daily[
                    "mortality_risk_index"
                ].max()
            ),
            places=2,
        )


if __name__ == "__main__":
    unittest.main()