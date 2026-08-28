from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from heat_health.mortality_calibration import (
    calculate_evidence_calibration,
    classify_calibrated_risk,
)


INPUT_FILE = (
    PROJECT_ROOT
    / "output"
    / "delhi_daily_heat_features.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "output"
    / "delhi_may_2024_backtest.csv"
)

SUMMARY_FILE = (
    PROJECT_ROOT
    / "output"
    / "delhi_may_2024_backtest_summary.json"
)

CHART_FILE = (
    PROJECT_ROOT
    / "output"
    / "delhi_may_2024_backtest.png"
)

MODEL_VERSION = "historical-stress-validation-v1"


REQUIRED_COLUMNS = {
    "date",
    "temperature_max_c",
    "temperature_min_c",
    "humidity_mean_pct",
    "wbgt_max_c",
    "utci_max_c",
    "danger_hours",
    "extreme_hours",
    "night_temperature_min_c",
    "is_dangerous_day",
    "consecutive_danger_days",
}


NUMERIC_COLUMNS = [
    "temperature_max_c",
    "temperature_min_c",
    "humidity_mean_pct",
    "wbgt_max_c",
    "utci_max_c",
    "danger_hours",
    "extreme_hours",
    "night_temperature_min_c",
    "consecutive_danger_days",
]


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def normalized_score(
    value: float,
    lower_bound: float,
    upper_bound: float,
) -> float:
    if upper_bound <= lower_bound:
        raise ValueError(
            "Upper score bound must be greater than lower bound."
        )

    score = (
        (value - lower_bound)
        / (upper_bound - lower_bound)
        * 100.0
    )

    return round(clamp(score, 0.0, 100.0), 2)


def to_bool(value: Any) -> bool:
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


def validate_input(data: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(data.columns)

    if missing:
        raise ValueError(
            "Historical feature file is missing columns: "
            + ", ".join(sorted(missing))
        )

    if data.empty:
        raise ValueError(
            "Historical feature file contains no rows."
        )


def calculate_daily_scores(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()

    # Temperature-only comparison.
    result["temperature_only_warning"] = (
        result["temperature_max_c"] >= 40.0
    )

    result["temperature_only_score"] = (
        result["temperature_max_c"].apply(
            lambda value: normalized_score(
                value,
                35.0,
                48.0,
            )
        )
    )

    result["wbgt_score"] = (
        result["wbgt_max_c"].apply(
            lambda value: normalized_score(
                value,
                23.0,
                35.0,
            )
        )
    )

    result["utci_score"] = (
        result["utci_max_c"].apply(
            lambda value: normalized_score(
                value,
                32.0,
                50.0,
            )
        )
    )

    result["warm_night_score"] = (
        result["night_temperature_min_c"].apply(
            lambda value: normalized_score(
                value,
                22.0,
                32.0,
            )
        )
    )

    result["danger_hour_score"] = (
        result["danger_hours"].apply(
            lambda value: round(
                clamp(
                    value / 24.0 * 100.0,
                    0.0,
                    100.0,
                ),
                2,
            )
        )
    )

    result["duration_score"] = (
        result["consecutive_danger_days"].apply(
            lambda value: round(
                clamp(
                    value / 5.0 * 100.0,
                    0.0,
                    100.0,
                ),
                2,
            )
        )
    )

    # Comprehensive physiological hazard score.
    result["historical_thermal_hazard_score"] = (
        0.10 * result["temperature_only_score"]
        + 0.25 * result["wbgt_score"]
        + 0.25 * result["utci_score"]
        + 0.15 * result["warm_night_score"]
        + 0.15 * result["danger_hour_score"]
        + 0.10 * result["duration_score"]
    ).clip(lower=0, upper=100).round(2)

    result["comprehensive_warning"] = (
        result["is_dangerous_day"].apply(to_bool)
    )

    calibration = result.apply(
        calculate_historical_calibration,
        axis=1,
    )

    result = pd.concat(
        [
            result.reset_index(drop=True),
            calibration.reset_index(drop=True),
        ],
        axis=1,
    )

    result["historical_calibrated_risk_index"] = (
        result["historical_thermal_hazard_score"]
        * result["evidence_relative_risk"]
    ).clip(lower=0, upper=100).round(2)

    result["historical_risk_level"] = (
        result["historical_calibrated_risk_index"].apply(
            classify_calibrated_risk
        )
    )

    result["temperature_threshold_missed_event"] = (
        result["comprehensive_warning"]
        & ~result["temperature_only_warning"]
    )

    result["backtest_model_version"] = MODEL_VERSION

    return result


def calculate_historical_calibration(
    row: pd.Series,
) -> pd.Series:
    proxy_row = pd.Series(
        {
            "danger_day": row["comprehensive_warning"],
            "consecutive_danger_days": (
                row["consecutive_danger_days"]
            ),
            "thermal_hazard_score": (
                row["historical_thermal_hazard_score"]
            ),
            "wbgt_max_c": row["wbgt_max_c"],
            "utci_max_c": row["utci_max_c"],
            "extreme_hours": row["extreme_hours"],
        }
    )

    return calculate_evidence_calibration(proxy_row)


def get_date_of_maximum(
    data: pd.DataFrame,
    column: str,
) -> str:
    index = data[column].idxmax()

    return data.loc[index, "date"].strftime("%Y-%m-%d")


def safe_record(record: dict[str, Any]) -> dict[str, Any]:
    cleaned = {}

    for key, value in record.items():
        if isinstance(value, pd.Timestamp):
            cleaned[key] = value.strftime("%Y-%m-%d")
        elif hasattr(value, "item"):
            cleaned[key] = value.item()
        elif pd.isna(value):
            cleaned[key] = None
        else:
            cleaned[key] = value

    return cleaned


def create_summary(data: pd.DataFrame) -> dict[str, Any]:
    risk_counts = (
        data["historical_risk_level"]
        .value_counts()
        .to_dict()
    )

    risk_counts = {
        str(level): int(count)
        for level, count in risk_counts.items()
    }

    correlation_columns = [
        "temperature_max_c",
        "humidity_mean_pct",
        "wbgt_max_c",
        "utci_max_c",
        "night_temperature_min_c",
        "historical_thermal_hazard_score",
        "historical_calibrated_risk_index",
    ]

    correlation_matrix = (
        data[correlation_columns]
        .corr()
        .round(3)
        .to_dict()
    )

    cleaned_correlations = {}

    for outer_key, values in correlation_matrix.items():
        cleaned_correlations[outer_key] = {
            inner_key: (
                None
                if pd.isna(value)
                else float(value)
            )
            for inner_key, value in values.items()
        }

    top_days = (
        data[
            [
                "date",
                "temperature_max_c",
                "humidity_mean_pct",
                "wbgt_max_c",
                "utci_max_c",
                "danger_hours",
                "extreme_hours",
                "consecutive_danger_days",
                "historical_thermal_hazard_score",
                "evidence_relative_risk",
                "historical_calibrated_risk_index",
                "historical_risk_level",
            ]
        ]
        .sort_values(
            by="historical_calibrated_risk_index",
            ascending=False,
        )
        .head(10)
        .to_dict(orient="records")
    )

    top_days = [
        safe_record(record)
        for record in top_days
    ]

    return {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "model_version": MODEL_VERSION,
        "validation_scope": (
            "Historical heat-stress detection validation. "
            "This is not mortality-count accuracy testing "
            "because daily Delhi mortality labels are unavailable."
        ),
        "period": {
            "start": data["date"].min().strftime("%Y-%m-%d"),
            "end": data["date"].max().strftime("%Y-%m-%d"),
            "days": int(len(data)),
        },
        "event_detection": {
            "temperature_only_warning_days": int(
                data["temperature_only_warning"].sum()
            ),
            "comprehensive_warning_days": int(
                data["comprehensive_warning"].sum()
            ),
            "dangerous_days_missed_by_40c_threshold": int(
                data[
                    "temperature_threshold_missed_event"
                ].sum()
            ),
        },
        "maximum_dates": {
            "highest_temperature": get_date_of_maximum(
                data,
                "temperature_max_c",
            ),
            "highest_wbgt": get_date_of_maximum(
                data,
                "wbgt_max_c",
            ),
            "highest_utci": get_date_of_maximum(
                data,
                "utci_max_c",
            ),
            "highest_calibrated_risk": get_date_of_maximum(
                data,
                "historical_calibrated_risk_index",
            ),
        },
        "maximum_values": {
            "temperature_max_c": round(
                float(data["temperature_max_c"].max()),
                2,
            ),
            "wbgt_max_c": round(
                float(data["wbgt_max_c"].max()),
                2,
            ),
            "utci_max_c": round(
                float(data["utci_max_c"].max()),
                2,
            ),
            "calibrated_risk_index": round(
                float(
                    data[
                        "historical_calibrated_risk_index"
                    ].max()
                ),
                2,
            ),
        },
        "historical_risk_level_counts": risk_counts,
        "correlation_matrix": cleaned_correlations,
        "top_10_risk_days": top_days,
        "limitations": [
            (
                "No daily mortality or hospitalization "
                "labels were available."
            ),
            (
                "The test validates event detection and "
                "ranking, not predicted death counts."
            ),
            (
                "Published city-level relative risks are "
                "used as provisional calibration factors."
            ),
        ],
    }


def create_chart(data: pd.DataFrame) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print(
            "Matplotlib is not installed; chart generation skipped."
        )
        return False

    figure, axes = plt.subplots(
        2,
        1,
        figsize=(13, 8),
        sharex=True,
    )

    axes[0].plot(
        data["date"],
        data["temperature_max_c"],
        color="#E74C3C",
        linewidth=2,
        label="Maximum temperature",
    )

    axes[0].axhline(
        40,
        color="#7F8C8D",
        linestyle="--",
        label="40°C threshold",
    )

    axes[0].set_ylabel("Temperature (°C)")
    axes[0].set_title(
        "Delhi Historical Heat-Stress Validation — May 2024"
    )
    axes[0].legend()
    axes[0].grid(alpha=0.25)

    axes[1].plot(
        data["date"],
        data["temperature_only_score"],
        color="#3498DB",
        linewidth=1.8,
        label="Temperature-only score",
    )

    axes[1].plot(
        data["date"],
        data["historical_calibrated_risk_index"],
        color="#C0392B",
        linewidth=2.2,
        label="Comprehensive calibrated risk",
    )

    axes[1].axhline(
        50,
        color="#F39C12",
        linestyle="--",
        alpha=0.8,
        label="High-risk boundary",
    )

    axes[1].axhline(
        75,
        color="#922B21",
        linestyle="--",
        alpha=0.8,
        label="Extreme-risk boundary",
    )

    axes[1].set_ylabel("Risk score (0–100)")
    axes[1].set_xlabel("Date")
    axes[1].legend()
    axes[1].grid(alpha=0.25)

    figure.autofmt_xdate()
    figure.tight_layout()

    figure.savefig(
        CHART_FILE,
        dpi=180,
        bbox_inches="tight",
    )

    plt.close(figure)

    return True


def run_backtest() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Historical features not found: {INPUT_FILE}"
        )

    print(f"Reading historical features: {INPUT_FILE}")

    data = pd.read_csv(INPUT_FILE)

    validate_input(data)

    data["date"] = pd.to_datetime(
        data["date"],
        errors="coerce",
    )

    if data["date"].isna().any():
        raise ValueError(
            "Historical data contains invalid dates."
        )

    for column in NUMERIC_COLUMNS:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )

    invalid_numeric_rows = int(
        data[NUMERIC_COLUMNS]
        .isna()
        .any(axis=1)
        .sum()
    )

    if invalid_numeric_rows:
        raise ValueError(
            f"{invalid_numeric_rows} rows contain invalid "
            "required numeric values."
        )

    data = data.sort_values("date").reset_index(drop=True)

    results = calculate_daily_scores(data)

    results.to_csv(
        OUTPUT_FILE,
        index=False,
        date_format="%Y-%m-%d",
    )

    summary = create_summary(results)

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

    chart_created = create_chart(results)

    print()
    print(f"Historical days tested: {len(results)}")
    print(
        "Temperature-only warning days: "
        f"{results['temperature_only_warning'].sum()}"
    )
    print(
        "Comprehensive warning days: "
        f"{results['comprehensive_warning'].sum()}"
    )
    print(
        "Dangerous days missed by 40°C threshold: "
        f"{results['temperature_threshold_missed_event'].sum()}"
    )
    print(
        "Maximum calibrated historical risk: "
        f"{results['historical_calibrated_risk_index'].max():.2f}"
    )
    print(f"Saved results: {OUTPUT_FILE}")
    print(f"Saved summary: {SUMMARY_FILE}")

    if chart_created:
        print(f"Saved chart: {CHART_FILE}")


def main() -> None:
    run_backtest()


if __name__ == "__main__":
    main()