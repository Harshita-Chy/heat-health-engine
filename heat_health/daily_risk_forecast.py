from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd


HOURLY_THERMAL_CSV = Path(
    "output/delhi_ward_hourly_thermal_forecast.csv"
)

POPULATION_CSV = Path(
    "output/delhi_ward_population_exposure.csv"
)

WARD_GEOJSON = Path(
    "data/processed/delhi_wards_processed.geojson"
)

DAILY_RISK_CSV = Path(
    "output/delhi_ward_daily_risk_forecast.csv"
)

PEAK_RISK_GEOJSON = Path(
    "output/delhi_5day_peak_risk_map.geojson"
)

SUMMARY_JSON = Path(
    "output/delhi_risk_summary.json"
)


# Screening score breakpoints.
HI_POINTS = (
    (20, 0),
    (27, 10),
    (32, 30),
    (41, 60),
    (54, 90),
    (60, 100),
)

WBGT_POINTS = (
    (18, 0),
    (23, 10),
    (25, 25),
    (28, 50),
    (31, 75),
    (33, 90),
    (36, 100),
)

UTCI_POINTS = (
    (20, 0),
    (26, 10),
    (32, 35),
    (38, 60),
    (46, 90),
    (50, 100),
)


def score_values(
    values: pd.Series,
    points: tuple[tuple[float, float], ...],
) -> np.ndarray:
    """
    Convert thermal-index values to scores between 0–100.
    """

    numeric_values = pd.to_numeric(
        values,
        errors="coerce",
    ).to_numpy(dtype=float)

    if not np.isfinite(numeric_values).all():
        raise ValueError(
            "Thermal scoring received invalid values."
        )

    input_points = np.asarray(
        [point[0] for point in points],
        dtype=float,
    )

    output_points = np.asarray(
        [point[1] for point in points],
        dtype=float,
    )

    return np.interp(
        numeric_values,
        input_points,
        output_points,
        left=output_points[0],
        right=output_points[-1],
    )


def classify_risk(
    score: float,
) -> tuple[str, str, str]:
    """
    Return risk level, alert code and map colour.
    """

    if score >= 75:
        return (
            "Extreme",
            "RED",
            "#E74C3C",
        )

    if score >= 50:
        return (
            "High",
            "ORANGE",
            "#E67E22",
        )

    if score >= 25:
        return (
            "Moderate",
            "YELLOW",
            "#F1C40F",
        )

    return (
        "Low",
        "GREEN",
        "#2ECC71",
    )


def advisory_for(
    risk_level: str,
) -> str:
    """
    Return an actionable public-health intervention.
    """

    advisories = {
        "Low": (
            "Maintain routine heat surveillance; "
            "publish hydration and shade guidance."
        ),

        "Moderate": (
            "Issue targeted public messaging; place "
            "drinking-water points on standby; monitor "
            "elderly residents, children and outdoor workers."
        ),

        "High": (
            "Activate the local heat action plan; open "
            "cooling centres; shift strenuous outdoor work "
            "away from afternoon hours; alert hospitals for "
            "a possible heat-illness surge."
        ),

        "Extreme": (
            "Activate emergency heat response; extend "
            "cooling-centre hours; restrict strenuous outdoor "
            "work from 11:00-17:00; deploy medical teams and "
            "protect power and water supply continuity."
        ),
    }

    return advisories[risk_level]


def consecutive_danger_days(
    values: pd.Series,
) -> pd.Series:
    """
    Count consecutive dangerous forecast days.
    """

    running_count = 0
    result = []

    for is_dangerous in values.astype(bool):
        if is_dangerous:
            running_count += 1
        else:
            running_count = 0

        result.append(running_count)

    return pd.Series(
        result,
        index=values.index,
        dtype="int64",
    )


def build_daily_risk_forecast(
    hourly_path: Path = HOURLY_THERMAL_CSV,
    population_path: Path = POPULATION_CSV,
    ward_geojson_path: Path = WARD_GEOJSON,
    daily_output: Path = DAILY_RISK_CSV,
    map_output: Path = PEAK_RISK_GEOJSON,
    summary_output: Path = SUMMARY_JSON,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """
    Build daily ward-level heat-health risk forecasts.
    """

    # -----------------------------------------------------
    # Validate input files
    # -----------------------------------------------------

    required_files = (
        hourly_path,
        population_path,
        ward_geojson_path,
    )

    for path in required_files:
        if not path.exists():
            raise FileNotFoundError(
                f"Required input file not found: {path}"
            )

    # -----------------------------------------------------
    # Read inputs
    # -----------------------------------------------------

    hourly = pd.read_csv(
        hourly_path,
        dtype={
            "ward_id": "string",
        },
    )

    population = pd.read_csv(
        population_path,
        dtype={
            "ward_id": "string",
        },
    )

    hourly_required = {
        "ward_id",
        "ward_name",
        "forecast_time_ist",
        "temperature_c",
        "relative_humidity_pct",
        "wind_speed_10m_mps",
        "solar_radiation_wm2",
        "heat_index_c",
        "estimated_wbgt_c",
        "utci_c",
    }

    population_required = {
        "ward_id",
        "population_estimate_2020",
        "population_density_per_sq_km",
        "exposure_score",
    }

    missing_hourly = hourly_required.difference(
        hourly.columns
    )

    missing_population = (
        population_required.difference(
            population.columns
        )
    )

    if missing_hourly:
        raise ValueError(
            "Hourly thermal file is missing: "
            f"{sorted(missing_hourly)}"
        )

    if missing_population:
        raise ValueError(
            "Population file is missing: "
            f"{sorted(missing_population)}"
        )

    if hourly.empty:
        raise ValueError(
            "Hourly thermal input is empty."
        )

    if population.empty:
        raise ValueError(
            "Population input is empty."
        )

    if population["ward_id"].duplicated().any():
        raise ValueError(
            "Population input contains duplicate ward IDs."
        )

    # -----------------------------------------------------
    # Validate and prepare hourly data
    # -----------------------------------------------------

    hourly["forecast_datetime_ist"] = pd.to_datetime(
        hourly["forecast_time_ist"],
        errors="coerce",
    )

    if hourly[
        "forecast_datetime_ist"
    ].isna().any():
        raise ValueError(
            "Some forecast timestamps could not be parsed."
        )

    numeric_columns = [
        "temperature_c",
        "relative_humidity_pct",
        "wind_speed_10m_mps",
        "solar_radiation_wm2",
        "heat_index_c",
        "estimated_wbgt_c",
        "utci_c",
    ]

    hourly[numeric_columns] = hourly[
        numeric_columns
    ].apply(
        pd.to_numeric,
        errors="coerce",
    )

    if hourly[
        numeric_columns
    ].isna().any().any():
        raise ValueError(
            "Hourly thermal input contains invalid values."
        )

    duplicate_hourly = hourly.duplicated(
        [
            "ward_id",
            "forecast_time_ist",
        ]
    )

    if duplicate_hourly.any():
        raise ValueError(
            "Hourly input contains duplicate ward/time rows."
        )

    hourly["forecast_date"] = (
        hourly["forecast_datetime_ist"]
        .dt.strftime("%Y-%m-%d")
    )

    hourly["forecast_hour"] = (
        hourly["forecast_datetime_ist"]
        .dt.hour
    )

    # -----------------------------------------------------
    # Calculate thermal hazard score
    # -----------------------------------------------------

    hourly["heat_index_score"] = score_values(
        hourly["heat_index_c"],
        HI_POINTS,
    )

    hourly["wbgt_score"] = score_values(
        hourly["estimated_wbgt_c"],
        WBGT_POINTS,
    )

    hourly["utci_score"] = score_values(
        hourly["utci_c"],
        UTCI_POINTS,
    )

    hourly["thermal_hazard_score"] = (
        0.15 * hourly["heat_index_score"]
        + 0.50 * hourly["wbgt_score"]
        + 0.35 * hourly["utci_score"]
    ).clip(0, 100)

    hourly["danger_hour"] = (
        (hourly["estimated_wbgt_c"] >= 28)
        | (hourly["utci_c"] >= 38)
    )

    hourly["extreme_hour"] = (
        (hourly["estimated_wbgt_c"] >= 31)
        | (hourly["utci_c"] >= 46)
    )

    # -----------------------------------------------------
    # Confirm 24 hours exist for every ward/day
    # -----------------------------------------------------

    group_columns = [
        "ward_id",
        "ward_name",
        "forecast_date",
    ]

    hours_per_day = hourly.groupby(
        group_columns,
        observed=True,
    ).size()

    invalid_groups = hours_per_day[
        ~hours_per_day.eq(24)
    ]

    if not invalid_groups.empty:
        raise ValueError(
            "Every ward/day must contain 24 hourly "
            "records. Invalid groups:\n"
            + invalid_groups.head(20).to_string()
        )

    # -----------------------------------------------------
    # Daily aggregation
    # -----------------------------------------------------

    daily = hourly.groupby(
        group_columns,
        as_index=False,
        observed=True,
    ).agg(
        temperature_max_c=(
            "temperature_c",
            "max",
        ),

        temperature_min_c=(
            "temperature_c",
            "min",
        ),

        temperature_mean_c=(
            "temperature_c",
            "mean",
        ),

        humidity_mean_pct=(
            "relative_humidity_pct",
            "mean",
        ),

        humidity_max_pct=(
            "relative_humidity_pct",
            "max",
        ),

        wind_mean_mps=(
            "wind_speed_10m_mps",
            "mean",
        ),

        solar_max_wm2=(
            "solar_radiation_wm2",
            "max",
        ),

        heat_index_max_c=(
            "heat_index_c",
            "max",
        ),

        wbgt_max_c=(
            "estimated_wbgt_c",
            "max",
        ),

        wbgt_mean_c=(
            "estimated_wbgt_c",
            "mean",
        ),

        utci_max_c=(
            "utci_c",
            "max",
        ),

        thermal_hazard_score=(
            "thermal_hazard_score",
            "max",
        ),

        danger_hours=(
            "danger_hour",
            "sum",
        ),

        extreme_hours=(
            "extreme_hour",
            "sum",
        ),
    )

    # -----------------------------------------------------
    # Night-time temperature
    # -----------------------------------------------------

    night_hours = hourly.loc[
        (hourly["forecast_hour"] <= 6)
        | (hourly["forecast_hour"] >= 22)
    ]

    night_minimum = night_hours.groupby(
        group_columns,
        as_index=False,
        observed=True,
    ).agg(
        night_temperature_min_c=(
            "temperature_c",
            "min",
        )
    )

    daily = daily.merge(
        night_minimum,
        on=group_columns,
        how="left",
        validate="one_to_one",
    )

    # -----------------------------------------------------
    # Peak-risk forecast time
    # -----------------------------------------------------

    peak_indices = hourly.groupby(
        group_columns,
        observed=True,
    )["thermal_hazard_score"].idxmax()

    peak_times = hourly.loc[
        peak_indices,
        group_columns
        + ["forecast_time_ist"],
    ].rename(
        columns={
            "forecast_time_ist":
                "peak_risk_time_ist"
        }
    )

    daily = daily.merge(
        peak_times,
        on=group_columns,
        how="left",
        validate="one_to_one",
    )

    # -----------------------------------------------------
    # Join population exposure
    # -----------------------------------------------------

    population_columns = [
        "ward_id",
        "population_estimate_2020",
        "population_density_per_sq_km",
        "exposure_score",
    ]

    daily = daily.merge(
        population[population_columns],
        on="ward_id",
        how="left",
        validate="many_to_one",
    )

    if daily[
        population_columns[1:]
    ].isna().any().any():
        missing_ward_ids = daily.loc[
            daily["exposure_score"].isna(),
            "ward_id",
        ].unique().tolist()

        raise ValueError(
            "Population exposure is missing for wards: "
            f"{missing_ward_ids}"
        )

    # -----------------------------------------------------
    # Calculate duration and persistence
    # -----------------------------------------------------

    daily = daily.sort_values(
        [
            "ward_id",
            "forecast_date",
        ]
    ).reset_index(drop=True)

    daily["danger_day"] = (
        (daily["thermal_hazard_score"] >= 50)
        | (daily["danger_hours"] >= 3)
    )

    daily[
        "consecutive_danger_days"
    ] = daily.groupby(
        "ward_id",
        sort=False,
        group_keys=False,
    )["danger_day"].transform(
        consecutive_danger_days
    )

    daily["heat_duration_score"] = (
        daily["consecutive_danger_days"]
        / 3.0
        * 100.0
    ).clip(0, 100)

    # -----------------------------------------------------
    # Provisional Mortality Risk Index
    # -----------------------------------------------------
    #
    # Thermal hazard is the main factor.
    # Population exposure and duration amplify that hazard.
    #
    # This remains an operational relative-risk index until
    # calibrated using hospitalization or mortality labels.
    # -----------------------------------------------------

    daily["mortality_risk_index"] = (
        daily["thermal_hazard_score"]
        * (
            0.70
            + 0.20
            * daily["exposure_score"]
            / 100.0
            + 0.10
            * daily["heat_duration_score"]
            / 100.0
        )
    ).clip(0, 100)

    # -----------------------------------------------------
    # Risk classifications
    # -----------------------------------------------------

    classifications = daily[
        "mortality_risk_index"
    ].map(classify_risk)

    daily["risk_level"] = classifications.map(
        lambda result: result[0]
    )

    daily["alert_code"] = classifications.map(
        lambda result: result[1]
    )

    daily["map_color"] = classifications.map(
        lambda result: result[2]
    )

    daily["recommended_action"] = daily[
        "risk_level"
    ].map(advisory_for)

    # -----------------------------------------------------
    # Automated administrative triggers
    # -----------------------------------------------------

    alert_levels = [
        "High",
        "Extreme",
    ]

    daily["sms_alert_required"] = daily[
        "risk_level"
    ].isin(alert_levels)

    daily["open_cooling_centres"] = daily[
        "risk_level"
    ].isin(alert_levels)

    daily[
        "shift_outdoor_work_hours"
    ] = daily["risk_level"].isin(
        alert_levels
    )

    daily["hospital_surge_alert"] = daily[
        "risk_level"
    ].isin(alert_levels)

    # -----------------------------------------------------
    # Transparency information
    # -----------------------------------------------------

    daily["model_version"] = (
        "provisional-impact-risk-v2"
    )

    daily["risk_interpretation"] = (
        "Relative heat-health impact ranking; "
        "not a predicted death count"
    )

    daily["vulnerability_data_status"] = (
        "WorldPop exposure included; demographic and "
        "health-outcome calibration pending"
    )

    numeric_output_columns = daily.select_dtypes(
        include="number"
    ).columns

    daily[
        numeric_output_columns
    ] = daily[
        numeric_output_columns
    ].round(2)

    # -----------------------------------------------------
    # Save daily CSV
    # -----------------------------------------------------

    daily_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    map_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    daily.to_csv(
        daily_output,
        index=False,
    )

    # -----------------------------------------------------
    # Create five-day peak-risk GIS map
    # -----------------------------------------------------

    peak_row_indices = daily.groupby(
        "ward_id"
    )["mortality_risk_index"].idxmax()

    peak_risk = daily.loc[
        peak_row_indices
    ].copy()

    wards = gpd.read_file(
        ward_geojson_path
    )

    if "ward_id" not in wards.columns:
        raise ValueError(
            "Ward GeoJSON does not contain ward_id."
        )

    wards["ward_id"] = wards[
        "ward_id"
    ].astype("string")

    map_attributes = peak_risk.drop(
        columns=[
            "ward_name",
        ]
    )

    risk_map = wards[
        [
            "ward_id",
            "ward_name",
            "geometry",
        ]
    ].merge(
        map_attributes,
        on="ward_id",
        how="left",
        validate="one_to_one",
    )

    if risk_map[
        "mortality_risk_index"
    ].isna().any():
        raise ValueError(
            "Some polygons could not be joined "
            "to risk results."
        )

    risk_map.to_file(
        map_output,
        driver="GeoJSON",
        index=False,
    )

    # -----------------------------------------------------
    # Create API/dashboard summary
    # -----------------------------------------------------

    risk_level_order = [
        "Low",
        "Moderate",
        "High",
        "Extreme",
    ]

    daily_counts = (
        daily.groupby(
            [
                "forecast_date",
                "risk_level",
            ],
            observed=True,
        )
        .size()
        .unstack(fill_value=0)
        .reindex(
            columns=risk_level_order,
            fill_value=0,
        )
    )

    summary = {
        "model_version":
            "provisional-impact-risk-v2",

        "interpretation":
            "Relative heat-health impact ranking; "
            "not a predicted death count",

        "wards":
            int(daily["ward_id"].nunique()),

        "forecast_dates":
            sorted(
                daily[
                    "forecast_date"
                ].unique().tolist()
            ),

        "maximum_risk_index":
            round(
                float(
                    daily[
                        "mortality_risk_index"
                    ].max()
                ),
                2,
            ),

        "daily_risk_level_counts": {
            date: {
                level: int(value)
                for level, value in row.items()
            }
            for date, row in daily_counts.to_dict(
                orient="index"
            ).items()
        },
    }

    with summary_output.open(
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            summary,
            output_file,
            indent=2,
        )

    print()

    print(
        f"Ward-day risk rows: {len(daily):,}"
    )

    print(
        f"Wards: {daily['ward_id'].nunique()}"
    )

    print(
        "Forecast days: "
        f"{daily['forecast_date'].nunique()}"
    )

    print(
        "Maximum provisional risk: "
        f"{daily['mortality_risk_index'].max():.2f}"
    )

    print(
        f"Saved daily risk: {daily_output}"
    )

    print(
        f"Saved five-day peak map: {map_output}"
    )

    print(
        f"Saved summary: {summary_output}"
    )

    return daily, risk_map


def main() -> None:
    build_daily_risk_forecast()


if __name__ == "__main__":
    main()