"""Combine thermal hazard and ward vulnerability into a risk index."""

import argparse
from pathlib import Path

import pandas as pd


DAILY_REQUIRED_COLUMNS = [
    "date",
    "heat_index_max_c",
    "wbgt_max_c",
    "utci_max_c",
    "consecutive_danger_days",
    "danger_hours",
]

WARD_REQUIRED_COLUMNS = [
    "ward_id",
    "ward_name",
    "demographic_vulnerability_score",
    "population_exposure_score",
]


def validate_columns(
    data: pd.DataFrame,
    required_columns: list[str],
    dataset_name: str,
) -> None:
    """Check whether a dataset contains all required columns."""

    missing_columns = [
        column
        for column in required_columns
        if column not in data.columns
    ]

    if missing_columns:
        raise ValueError(
            f"{dataset_name} is missing columns: "
            f"{missing_columns}"
        )


def piecewise_score(
    value: float,
    breakpoints: list[tuple[float, float]],
) -> float:
    """Convert an index value to a score using linear interpolation."""

    if value <= breakpoints[0][0]:
        return breakpoints[0][1]

    for index in range(len(breakpoints) - 1):
        x_start, y_start = breakpoints[index]
        x_end, y_end = breakpoints[index + 1]

        if value <= x_end:
            fraction = (
                (value - x_start)
                / (x_end - x_start)
            )

            return (
                y_start
                + fraction * (y_end - y_start)
            )

    return breakpoints[-1][1]


def calculate_thermal_hazard_score(
    heat_index_c: float,
    wbgt_c: float,
    utci_c: float,
) -> float:
    """Convert Heat Index, WBGT and UTCI into a 0–100 score."""

    heat_index_score = piecewise_score(
        heat_index_c,
        [
            (20, 0),
            (27, 10),
            (32, 30),
            (39, 55),
            (51, 85),
            (60, 100),
        ],
    )

    wbgt_score = piecewise_score(
        wbgt_c,
        [
            (18, 0),
            (23, 15),
            (25, 30),
            (28, 50),
            (31, 75),
            (33, 90),
            (36, 100),
        ],
    )

    utci_score = piecewise_score(
        utci_c,
        [
            (20, 0),
            (26, 10),
            (32, 35),
            (38, 60),
            (46, 90),
            (50, 100),
        ],
    )

    combined_score = (
        0.15 * heat_index_score
        + 0.50 * wbgt_score
        + 0.35 * utci_score
    )

    return round(
        min(max(combined_score, 0), 100),
        2,
    )


def calculate_duration_score(
    consecutive_danger_days: int,
) -> float:
    """Convert consecutive dangerous days to a 0–100 score."""

    return round(
        min(
            consecutive_danger_days / 3 * 100,
            100,
        ),
        2,
    )


def classify_risk(score: float) -> tuple[str, str]:
    """Return risk level and colour."""

    if score >= 75:
        return "Extreme", "Red"

    if score >= 50:
        return "High", "Orange"

    if score >= 25:
        return "Moderate", "Yellow"

    return "Low", "Green"


def get_advisory(risk_level: str) -> str:
    """Return an automatic public-health recommendation."""

    advisories = {
        "Low": (
            "Continue monitoring and publish routine "
            "hydration guidance."
        ),
        "Moderate": (
            "Notify local health centres, increase water "
            "access and check vulnerable residents."
        ),
        "High": (
            "Prepare cooling centres, shift outdoor work "
            "hours and increase hospital readiness."
        ),
        "Extreme": (
            "Activate the Heat Action Plan, open cooling "
            "centres and restrict peak-hour outdoor work."
        ),
    }

    return advisories[risk_level]


def calculate_ward_risk(
    daily_file: str,
    ward_file: str,
    output_file: str,
) -> pd.DataFrame:
    """Generate one heat-health risk record per ward per day."""

    print(f"Reading daily heat data: {daily_file}")
    daily = pd.read_csv(daily_file)

    print(f"Reading ward vulnerability data: {ward_file}")
    wards = pd.read_csv(ward_file)

    validate_columns(
        daily,
        DAILY_REQUIRED_COLUMNS,
        "Daily heat dataset",
    )

    validate_columns(
        wards,
        WARD_REQUIRED_COLUMNS,
        "Ward vulnerability dataset",
    )

    daily["thermal_hazard_score"] = daily.apply(
        lambda row: calculate_thermal_hazard_score(
            heat_index_c=float(row["heat_index_max_c"]),
            wbgt_c=float(row["wbgt_max_c"]),
            utci_c=float(row["utci_max_c"]),
        ),
        axis=1,
    )

    daily["heat_duration_score"] = daily[
        "consecutive_danger_days"
    ].apply(calculate_duration_score)

    # Combine every Delhi day with every Delhi ward.
    ward_daily_risk = daily.merge(
        wards,
        how="cross",
    )

    def calculate_single_risk(row: pd.Series) -> float:
        """Calculate risk while ensuring heat hazard remains necessary."""

        vulnerability = (
            float(
                row[
                    "demographic_vulnerability_score"
                ]
            )
            / 100
        )

        exposure = (
            float(
                row["population_exposure_score"]
            )
            / 100
        )

        duration = (
            float(row["heat_duration_score"])
            / 100
        )

        amplification = (
            0.55
            + 0.20 * vulnerability
            + 0.15 * exposure
            + 0.10 * duration
        )

        score = (
            float(row["thermal_hazard_score"])
            * amplification
        )

        return round(
            min(max(score, 0), 100),
            2,
        )

    ward_daily_risk["mortality_risk_index"] = (
        ward_daily_risk.apply(
            calculate_single_risk,
            axis=1,
        )
    )

    classifications = (
        ward_daily_risk[
            "mortality_risk_index"
        ]
        .apply(classify_risk)
    )

    ward_daily_risk["risk_level"] = (
        classifications.apply(
            lambda result: result[0]
        )
    )

    ward_daily_risk["alert_colour"] = (
        classifications.apply(
            lambda result: result[1]
        )
    )

    ward_daily_risk["recommended_action"] = (
        ward_daily_risk["risk_level"]
        .apply(get_advisory)
    )

    ward_daily_risk["risk_rank_within_city"] = (
        ward_daily_risk
        .groupby("date")[
            "mortality_risk_index"
        ]
        .rank(
            method="dense",
            ascending=False,
        )
        .astype(int)
    )

    # Important metadata prevents this score from being
    # misrepresented as an exact death forecast.
    ward_daily_risk["model_version"] = (
        "provisional-rule-based-v1"
    )

    ward_daily_risk["risk_interpretation"] = (
        "Impact-risk ranking, not a predicted death count"
    )

    ward_daily_risk.sort_values(
        by=[
            "date",
            "mortality_risk_index",
        ],
        ascending=[
            True,
            False,
        ],
        inplace=True,
    )

    output_path = Path(output_file)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ward_daily_risk.to_csv(
        output_path,
        index=False,
    )

    print("\nRisk calculation completed.")
    print(
        f"Generated {len(ward_daily_risk)} "
        "ward-day risk records."
    )
    print(f"Output: {output_path.resolve()}")

    return ward_daily_risk


def print_summary(
    risk_data: pd.DataFrame,
) -> None:
    """Print risk distribution and highest-risk records."""

    print("\nRisk-level distribution:")

    print(
        risk_data["risk_level"]
        .value_counts()
    )

    print("\nTop 10 highest-risk ward-day records:")

    display_columns = [
        "date",
        "ward_id",
        "ward_name",
        "thermal_hazard_score",
        "demographic_vulnerability_score",
        "population_exposure_score",
        "mortality_risk_index",
        "risk_level",
        "alert_colour",
    ]

    top_records = risk_data.nlargest(
        10,
        "mortality_risk_index",
    )

    print(
        top_records[display_columns]
        .to_string(index=False)
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate ward-level heat-health risk"
        )
    )

    parser.add_argument(
        "--daily",
        default=(
            "output/"
            "delhi_daily_heat_features.csv"
        ),
    )

    parser.add_argument(
        "--wards",
        default=(
            "output/"
            "delhi_ward_vulnerability.csv"
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            "output/"
            "delhi_ward_daily_risk.csv"
        ),
    )

    arguments = parser.parse_args()

    risk_data = calculate_ward_risk(
        daily_file=arguments.daily,
        ward_file=arguments.wards,
        output_file=arguments.output,
    )

    print_summary(risk_data)


if __name__ == "__main__":
    main()