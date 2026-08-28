from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ---------------------------------------------------------
# File locations
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    PROJECT_ROOT
    / "output"
    / "delhi_ward_daily_risk_forecast.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "output"
    / "delhi_ward_daily_calibrated_risk.csv"
)

SUMMARY_FILE = (
    PROJECT_ROOT
    / "output"
    / "delhi_mortality_calibration_summary.json"
)


MODEL_VERSION = "evidence-calibrated-impact-risk-v3"

# Published Indian multi-city study coefficients.
TWO_DAY_RELATIVE_RISK = 1.147
FIVE_DAY_EXTREME_RELATIVE_RISK = 1.332


REQUIRED_COLUMNS = {
    "ward_id",
    "ward_name",
    "forecast_date",
    "thermal_hazard_score",
    "wbgt_max_c",
    "utci_max_c",
    "danger_hours",
    "extreme_hours",
    "night_temperature_min_c",
    "danger_day",
    "consecutive_danger_days",
    "mortality_risk_index",
}


NUMERIC_COLUMNS = [
    "thermal_hazard_score",
    "wbgt_max_c",
    "utci_max_c",
    "danger_hours",
    "extreme_hours",
    "night_temperature_min_c",
    "consecutive_danger_days",
    "mortality_risk_index",
]


# ---------------------------------------------------------
# Utility functions
# ---------------------------------------------------------

def to_bool(value: Any) -> bool:
    """Safely convert CSV values into Boolean values."""

    if pd.isna(value):
        return False

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    return str(value).strip().lower() in {
        "true",
        "1",
        "yes",
        "y",
    }


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------
# Evidence-based mortality calibration
# ---------------------------------------------------------

def calculate_evidence_calibration(
    row: pd.Series,
) -> pd.Series:
    """
    Calculate an evidence-based relative-risk coefficient.

    Important:
    The published coefficients were calculated at city level.
    Because Delhi ward-level mortality labels are unavailable,
    danger-day and thermal-stress conditions are used as operational
    proxies.

    The result is a relative-risk scenario, not a death-count forecast.
    """

    danger_day = to_bool(row["danger_day"])

    duration = max(
        0,
        safe_int(row["consecutive_danger_days"]),
    )

    thermal_score = safe_float(
        row["thermal_hazard_score"]
    )

    wbgt_max = safe_float(row["wbgt_max_c"])
    utci_max = safe_float(row["utci_max_c"])
    extreme_hours = safe_int(row["extreme_hours"])

    # Operational definition of severe physiological heat.
    severe_heat = (
        wbgt_max >= 35.0
        or utci_max >= 46.0
        or extreme_hours >= 1
        or thermal_score >= 85.0
    )

    # Five-day severe heat proxy.
    if severe_heat and duration >= 5:
        relative_risk = FIVE_DAY_EXTREME_RELATIVE_RISK
        basis = (
            "Indian 10-city five-day extreme-heat "
            "relative-risk proxy"
        )
        evidence_type = "Published evidence proxy"

    # Interpolate between the published two-day and
    # five-day relative-risk values.
    elif severe_heat and duration in {3, 4}:
        increase_two_day = TWO_DAY_RELATIVE_RISK - 1.0
        increase_five_day = (
            FIVE_DAY_EXTREME_RELATIVE_RISK - 1.0
        )

        interpolated_increase = (
            increase_two_day
            + ((duration - 2) / 3)
            * (increase_five_day - increase_two_day)
        )

        relative_risk = 1.0 + interpolated_increase
        basis = (
            f"Interpolated Indian multi-city evidence "
            f"for {duration}-day severe-heat proxy"
        )
        evidence_type = "Evidence interpolation"

    # Published two-consecutive-day heatwave relationship.
    elif danger_day and duration >= 2:
        relative_risk = TWO_DAY_RELATIVE_RISK
        basis = (
            "Indian 10-city two-day heatwave "
            "relative-risk proxy"
        )
        evidence_type = "Published evidence proxy"

    # A single severe day receives a conservative operational
    # adjustment. This is not presented as a published coefficient.
    elif severe_heat:
        relative_risk = 1.10
        basis = (
            "Single-day severe physiological-heat "
            "operational adjustment"
        )
        evidence_type = "Provisional operational heuristic"

    # A normal danger day receives a smaller adjustment.
    elif danger_day:
        relative_risk = 1.05
        basis = (
            "Single danger-day conservative "
            "operational adjustment"
        )
        evidence_type = "Provisional operational heuristic"

    else:
        relative_risk = 1.0
        basis = "No heat-mortality adjustment"
        evidence_type = "Baseline"

    relative_increase_pct = (
        relative_risk - 1.0
    ) * 100.0

    return pd.Series(
        {
            "evidence_relative_risk": round(
                relative_risk, 3
            ),
            "evidence_relative_increase_pct": round(
                relative_increase_pct, 2
            ),
            "calibration_basis": basis,
            "calibration_evidence_type": evidence_type,
        }
    )


# ---------------------------------------------------------
# Risk classification and advisories
# ---------------------------------------------------------

def classify_calibrated_risk(score: float) -> str:
    if score < 25:
        return "Low"

    if score < 50:
        return "Moderate"

    if score < 75:
        return "High"

    return "Extreme"


def alert_properties(level: str) -> dict[str, Any]:
    properties = {
        "Low": {
            "code": "GREEN",
            "color": "#2ECC71",
            "action": (
                "Continue routine heat surveillance and "
                "publish general hydration guidance."
            ),
            "sms": False,
            "cooling_centres": False,
            "shift_work": False,
            "hospital_alert": False,
        },
        "Moderate": {
            "code": "YELLOW",
            "color": "#F1C40F",
            "action": (
                "Issue preventive advisories, monitor "
                "vulnerable residents and ensure drinking "
                "water availability."
            ),
            "sms": False,
            "cooling_centres": False,
            "shift_work": False,
            "hospital_alert": False,
        },
        "High": {
            "code": "ORANGE",
            "color": "#E67E22",
            "action": (
                "Activate the local heat action plan; open "
                "cooling centres; shift strenuous outdoor "
                "work away from afternoon hours; alert "
                "hospitals for a possible heat-illness surge."
            ),
            "sms": True,
            "cooling_centres": True,
            "shift_work": True,
            "hospital_alert": True,
        },
        "Extreme": {
            "code": "RED",
            "color": "#C0392B",
            "action": (
                "Activate emergency heat response; expand "
                "cooling centres and ambulance readiness; "
                "suspend strenuous outdoor work; issue "
                "regional alerts and initiate hospital "
                "surge protocols."
            ),
            "sms": True,
            "cooling_centres": True,
            "shift_work": True,
            "hospital_alert": True,
        },
    }

    return properties[level]


# ---------------------------------------------------------
# Main processing pipeline
# ---------------------------------------------------------

def validate_input(data: pd.DataFrame) -> None:
    missing_columns = REQUIRED_COLUMNS - set(data.columns)

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            "The input forecast is missing required "
            f"columns: {missing_text}"
        )

    if data.empty:
        raise ValueError(
            "The input forecast file contains no rows."
        )


def build_calibrated_forecast() -> pd.DataFrame:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Required input file not found: {INPUT_FILE}"
        )

    print(f"Reading risk forecast: {INPUT_FILE}")

    data = pd.read_csv(INPUT_FILE)

    validate_input(data)

    for column in NUMERIC_COLUMNS:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )

    if data["mortality_risk_index"].isna().any():
        bad_rows = int(
            data["mortality_risk_index"].isna().sum()
        )

        raise ValueError(
            f"{bad_rows} rows have an invalid "
            "mortality_risk_index."
        )

    calibration = data.apply(
        calculate_evidence_calibration,
        axis=1,
    )

    data = pd.concat(
        [
            data.reset_index(drop=True),
            calibration.reset_index(drop=True),
        ],
        axis=1,
    )

    # Apply the evidence coefficient to the existing
    # provisional 0-100 risk index.
    data["calibrated_mortality_risk_index"] = (
        data["mortality_risk_index"]
        * data["evidence_relative_risk"]
    ).clip(lower=0, upper=100).round(2)

    data["calibrated_risk_level"] = (
        data["calibrated_mortality_risk_index"].apply(
            classify_calibrated_risk
        )
    )

    alert_data = data["calibrated_risk_level"].apply(
        alert_properties
    )

    data["calibrated_alert_code"] = alert_data.apply(
        lambda value: value["code"]
    )

    data["calibrated_map_color"] = alert_data.apply(
        lambda value: value["color"]
    )

    data["calibrated_recommended_action"] = (
        alert_data.apply(
            lambda value: value["action"]
        )
    )

    data["calibrated_sms_alert_required"] = (
        alert_data.apply(
            lambda value: value["sms"]
        )
    )

    data["calibrated_open_cooling_centres"] = (
        alert_data.apply(
            lambda value: value["cooling_centres"]
        )
    )

    data["calibrated_shift_outdoor_work_hours"] = (
        alert_data.apply(
            lambda value: value["shift_work"]
        )
    )

    data["calibrated_hospital_surge_alert"] = (
        alert_data.apply(
            lambda value: value["hospital_alert"]
        )
    )

    data["calibration_model_version"] = MODEL_VERSION

    data["calibration_confidence"] = (
        "Provisional: published city-level evidence; "
        "Delhi ward health-outcome labels unavailable"
    )

    data["calibrated_risk_interpretation"] = (
        "Relative ward-level heat-health impact ranking. "
        "The evidence percentage is a scenario coefficient, "
        "not a predicted number of deaths."
    )

    data["health_outcome_data_status"] = (
        "Awaiting authorized Delhi IHIP or hospital "
        "outcome data"
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    create_summary(data)

    print()
    print(f"Calibrated rows: {len(data):,}")
    print(
        f"Wards: {data['ward_id'].nunique():,}"
    )
    print(
        "Forecast days: "
        f"{data['forecast_date'].nunique():,}"
    )
    print(
        "Maximum calibrated MRI: "
        f"{data['calibrated_mortality_risk_index'].max():.2f}"
    )
    print(
        "Maximum evidence increase: "
        f"{data['evidence_relative_increase_pct'].max():.2f}%"
    )
    print(f"Saved calibrated risk: {OUTPUT_FILE}")
    print(f"Saved calibration summary: {SUMMARY_FILE}")

    return data


def create_summary(data: pd.DataFrame) -> None:
    risk_counts = (
        data["calibrated_risk_level"]
        .value_counts()
        .to_dict()
    )

    risk_counts = {
        str(level): int(count)
        for level, count in risk_counts.items()
    }

    summary = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "model_version": MODEL_VERSION,
        "input_file": str(INPUT_FILE),
        "output_file": str(OUTPUT_FILE),
        "rows": int(len(data)),
        "wards": int(data["ward_id"].nunique()),
        "forecast_days": int(
            data["forecast_date"].nunique()
        ),
        "maximum_original_mri": round(
            float(data["mortality_risk_index"].max()),
            2,
        ),
        "maximum_calibrated_mri": round(
            float(
                data[
                    "calibrated_mortality_risk_index"
                ].max()
            ),
            2,
        ),
        "maximum_evidence_relative_increase_pct": round(
            float(
                data[
                    "evidence_relative_increase_pct"
                ].max()
            ),
            2,
        ),
        "calibrated_risk_level_counts": risk_counts,
        "published_evidence": {
            "study_scope": (
                "Ten Indian cities, including Delhi"
            ),
            "two_day_relative_risk": (
                TWO_DAY_RELATIVE_RISK
            ),
            "five_day_extreme_relative_risk": (
                FIVE_DAY_EXTREME_RELATIVE_RISK
            ),
            "reference": (
                "de Bont et al., Environment "
                "International, 2024"
            ),
        },
        "limitations": [
            (
                "No Delhi ward-level mortality or "
                "hospitalization labels were used."
            ),
            (
                "Published city-level relationships are "
                "mapped using operational heat proxies."
            ),
            (
                "Outputs are relative impact rankings and "
                "must not be interpreted as predicted "
                "death counts."
            ),
        ],
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
    build_calibrated_forecast()


if __name__ == "__main__":
    main()