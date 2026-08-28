from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CALIBRATED_FORECAST_FILE = (
    PROJECT_ROOT
    / "output"
    / "delhi_ward_daily_calibrated_risk.csv"
)

BASE_MAP_FILE = (
    PROJECT_ROOT
    / "output"
    / "delhi_5day_peak_risk_map.geojson"
)

OUTPUT_MAP_FILE = (
    PROJECT_ROOT
    / "output"
    / "delhi_5day_peak_calibrated_risk_map.geojson"
)

HOTSPOTS_FILE = (
    PROJECT_ROOT
    / "output"
    / "delhi_calibrated_hotspots.csv"
)

SUMMARY_FILE = (
    PROJECT_ROOT
    / "output"
    / "delhi_calibrated_map_summary.json"
)

MAP_MODEL_VERSION = "calibrated-gis-map-v1"


REQUIRED_FORECAST_COLUMNS = {
    "ward_id",
    "ward_name",
    "forecast_date",
    "mortality_risk_index",
    "risk_level",
    "evidence_relative_risk",
    "evidence_relative_increase_pct",
    "calibrated_mortality_risk_index",
    "calibrated_risk_level",
    "calibrated_alert_code",
    "calibrated_map_color",
    "calibrated_recommended_action",
    "calibrated_sms_alert_required",
    "calibrated_open_cooling_centres",
    "calibrated_shift_outdoor_work_hours",
    "calibrated_hospital_surge_alert",
    "calibration_model_version",
    "calibration_confidence",
    "calibrated_risk_interpretation",
    "health_outcome_data_status",
}


def normalize_ward_id(value: Any) -> str:
    """
    Convert ward IDs into a consistent string format.

    Examples:
        1       -> "1"
        1.0     -> "1"
        "001"   -> "001"
        "UNNUMBERED_001" -> "UNNUMBERED_001"
    """

    if pd.isna(value):
        return ""

    text = str(value).strip()

    if text.endswith(".0"):
        possible_integer = text[:-2]

        if possible_integer.lstrip("-").isdigit():
            return possible_integer

    return text


def json_safe(value: Any) -> Any:
    """Convert pandas/numpy values into JSON-compatible values."""

    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass

    return value


def validate_forecast(data: pd.DataFrame) -> None:
    missing = REQUIRED_FORECAST_COLUMNS - set(data.columns)

    if missing:
        raise ValueError(
            "Calibrated forecast is missing columns: "
            + ", ".join(sorted(missing))
        )

    if data.empty:
        raise ValueError(
            "Calibrated forecast contains no rows."
        )

    data["calibrated_mortality_risk_index"] = (
        pd.to_numeric(
            data["calibrated_mortality_risk_index"],
            errors="coerce",
        )
    )

    invalid_scores = int(
        data[
            "calibrated_mortality_risk_index"
        ].isna().sum()
    )

    if invalid_scores:
        raise ValueError(
            f"{invalid_scores} rows contain invalid "
            "calibrated risk scores."
        )


def select_peak_risk_rows(
    data: pd.DataFrame,
) -> pd.DataFrame:
    """
    Select the highest calibrated risk day for every ward.
    """

    data = data.copy()

    data["_ward_key"] = data["ward_id"].apply(
        normalize_ward_id
    )

    empty_ids = int((data["_ward_key"] == "").sum())

    if empty_ids:
        raise ValueError(
            f"{empty_ids} forecast rows have empty ward IDs."
        )

    peak_indices = data.groupby(
        "_ward_key"
    )["calibrated_mortality_risk_index"].idxmax()

    peaks = data.loc[peak_indices].copy()

    duplicate_ids = peaks["_ward_key"].duplicated().sum()

    if duplicate_ids:
        raise ValueError(
            f"{duplicate_ids} duplicate peak ward IDs found."
        )

    return peaks.set_index("_ward_key", drop=False)


def create_feature_properties(
    row: pd.Series,
) -> dict[str, Any]:
    """
    Create map properties using the calibrated peak-risk row.

    Existing dashboard-compatible fields such as risk_level,
    map_color and alert_code are updated to their calibrated values.
    Original values are preserved with a base_ prefix.
    """

    properties = {
        str(column): json_safe(value)
        for column, value in row.items()
        if column != "_ward_key"
    }

    # Preserve the original provisional results.
    properties["base_mortality_risk_index"] = (
        properties.get("mortality_risk_index")
    )

    properties["base_risk_level"] = (
        properties.get("risk_level")
    )

    properties["base_alert_code"] = (
        properties.get("alert_code")
    )

    properties["base_map_color"] = (
        properties.get("map_color")
    )

    # Replace dashboard-facing fields with calibrated results.
    properties["mortality_risk_index"] = (
        properties[
            "calibrated_mortality_risk_index"
        ]
    )

    properties["risk_level"] = properties[
        "calibrated_risk_level"
    ]

    properties["alert_code"] = properties[
        "calibrated_alert_code"
    ]

    properties["map_color"] = properties[
        "calibrated_map_color"
    ]

    properties["recommended_action"] = properties[
        "calibrated_recommended_action"
    ]

    properties["sms_alert_required"] = properties[
        "calibrated_sms_alert_required"
    ]

    properties["open_cooling_centres"] = properties[
        "calibrated_open_cooling_centres"
    ]

    properties["shift_outdoor_work_hours"] = properties[
        "calibrated_shift_outdoor_work_hours"
    ]

    properties["hospital_surge_alert"] = properties[
        "calibrated_hospital_surge_alert"
    ]

    properties["model_version"] = properties[
        "calibration_model_version"
    ]

    properties["risk_interpretation"] = properties[
        "calibrated_risk_interpretation"
    ]

    properties["vulnerability_data_status"] = properties[
        "health_outcome_data_status"
    ]

    properties["map_model_version"] = MAP_MODEL_VERSION

    properties["peak_selection_basis"] = (
        "Maximum calibrated mortality risk index "
        "during the five-day forecast"
    )

    return properties


def build_calibrated_map() -> None:
    if not CALIBRATED_FORECAST_FILE.exists():
        raise FileNotFoundError(
            "Calibrated forecast not found: "
            f"{CALIBRATED_FORECAST_FILE}"
        )

    if not BASE_MAP_FILE.exists():
        raise FileNotFoundError(
            f"Base GeoJSON map not found: {BASE_MAP_FILE}"
        )

    print(
        "Reading calibrated forecast: "
        f"{CALIBRATED_FORECAST_FILE}"
    )

    forecast = pd.read_csv(
        CALIBRATED_FORECAST_FILE,
        dtype={"ward_id": "string"},
    )

    validate_forecast(forecast)

    peak_rows = select_peak_risk_rows(forecast)

    print(f"Peak ward rows selected: {len(peak_rows):,}")

    print(f"Reading base map: {BASE_MAP_FILE}")

    with BASE_MAP_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        geojson = json.load(file)

    if geojson.get("type") != "FeatureCollection":
        raise ValueError(
            "The base map is not a GeoJSON FeatureCollection."
        )

    features = geojson.get("features")

    if not isinstance(features, list):
        raise ValueError(
            "GeoJSON does not contain a valid features list."
        )

    matched_ids: set[str] = set()
    unmatched_map_ids: list[str] = []

    for feature in features:
        old_properties = feature.get("properties") or {}

        ward_key = normalize_ward_id(
            old_properties.get("ward_id")
        )

        if not ward_key:
            unmatched_map_ids.append(
                "EMPTY_WARD_ID"
            )
            continue

        if ward_key not in peak_rows.index:
            unmatched_map_ids.append(ward_key)
            continue

        peak_row = peak_rows.loc[ward_key]

        feature["properties"] = (
            create_feature_properties(peak_row)
        )

        matched_ids.add(ward_key)

    forecast_ids = set(peak_rows.index)

    forecast_without_geometry = sorted(
        forecast_ids - matched_ids
    )

    if unmatched_map_ids or forecast_without_geometry:
        raise ValueError(
            "Ward join failed. "
            f"Map wards without forecast: "
            f"{unmatched_map_ids[:10]}; "
            f"forecast wards without geometry: "
            f"{forecast_without_geometry[:10]}"
        )

    geojson["name"] = (
        "Delhi Five-Day Peak Calibrated "
        "Heat-Health Risk"
    )

    geojson["model_version"] = MAP_MODEL_VERSION

    geojson["generated_at_utc"] = datetime.now(
        timezone.utc
    ).isoformat()

    geojson["description"] = (
        "Each feature represents the highest calibrated "
        "heat-health risk forecast for that ward during "
        "the five-day forecast period."
    )

    OUTPUT_MAP_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_MAP_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            geojson,
            file,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    save_hotspots(peak_rows)
    save_summary(peak_rows, len(features))

    print()
    print(f"Map features: {len(features):,}")
    print(f"Matched wards: {len(matched_ids):,}")
    print(
        "Maximum calibrated risk: "
        f"{peak_rows['calibrated_mortality_risk_index'].max():.2f}"
    )
    print(f"Saved calibrated map: {OUTPUT_MAP_FILE}")
    print(f"Saved hotspot table: {HOTSPOTS_FILE}")
    print(f"Saved map summary: {SUMMARY_FILE}")


def save_hotspots(peak_rows: pd.DataFrame) -> None:
    hotspot_columns = [
        "ward_id",
        "ward_name",
        "forecast_date",
        "temperature_max_c",
        "humidity_mean_pct",
        "wbgt_max_c",
        "utci_max_c",
        "thermal_hazard_score",
        "danger_hours",
        "extreme_hours",
        "consecutive_danger_days",
        "population_estimate_2020",
        "mortality_risk_index",
        "evidence_relative_risk",
        "evidence_relative_increase_pct",
        "calibrated_mortality_risk_index",
        "calibrated_risk_level",
        "calibrated_alert_code",
        "calibrated_recommended_action",
    ]

    available_columns = [
        column
        for column in hotspot_columns
        if column in peak_rows.columns
    ]

    hotspots = (
        peak_rows[available_columns]
        .sort_values(
            by="calibrated_mortality_risk_index",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    hotspots.to_csv(
        HOTSPOTS_FILE,
        index=False,
    )


def save_summary(
    peak_rows: pd.DataFrame,
    feature_count: int,
) -> None:
    risk_counts = (
        peak_rows["calibrated_risk_level"]
        .value_counts()
        .to_dict()
    )

    risk_counts = {
        str(level): int(count)
        for level, count in risk_counts.items()
    }

    top_columns = [
        "ward_id",
        "ward_name",
        "forecast_date",
        "calibrated_mortality_risk_index",
        "calibrated_risk_level",
        "evidence_relative_increase_pct",
    ]

    top_wards = (
        peak_rows[top_columns]
        .sort_values(
            by="calibrated_mortality_risk_index",
            ascending=False,
        )
        .head(10)
    )

    top_wards_records = []

    for record in top_wards.to_dict(
        orient="records"
    ):
        top_wards_records.append(
            {
                key: json_safe(value)
                for key, value in record.items()
            }
        )

    summary = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "map_model_version": MAP_MODEL_VERSION,
        "forecast_wards": int(len(peak_rows)),
        "geojson_features": int(feature_count),
        "maximum_calibrated_risk": round(
            float(
                peak_rows[
                    "calibrated_mortality_risk_index"
                ].max()
            ),
            2,
        ),
        "minimum_calibrated_risk": round(
            float(
                peak_rows[
                    "calibrated_mortality_risk_index"
                ].min()
            ),
            2,
        ),
        "risk_level_counts": risk_counts,
        "top_10_risk_wards": top_wards_records,
        "interpretation": (
            "Relative heat-health impact ranking; "
            "not a predicted death count."
        ),
    }

    with SUMMARY_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            summary,
            file,
            indent=2,
            ensure_ascii=False,
        )


def main() -> None:
    build_calibrated_map()


if __name__ == "__main__":
    main()