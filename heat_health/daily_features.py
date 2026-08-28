"""Generate daily heat-health features from hourly thermal data."""

import argparse
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = [
    "timestamp_local",
    "temperature_c",
    "relative_humidity_pct",
    "wind_speed_10m_mps",
    "solar_radiation_wm2",
    "heat_index_c",
    "wet_bulb_c",
    "estimated_wbgt_c",
    "utci_c",
]


def validate_hourly_data(hourly: pd.DataFrame) -> None:
    """Check whether required thermal columns exist."""

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in hourly.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Hourly dataset is missing columns: {missing_columns}"
        )


def classify_daily_heat_risk(
    wbgt_max: float,
    utci_max: float,
) -> str:
    """Classify the maximum daily thermal risk."""

    if wbgt_max >= 33 or utci_max >= 46:
        return "Extreme"

    if wbgt_max >= 31 or utci_max >= 38:
        return "High"

    if wbgt_max >= 25 or utci_max >= 32:
        return "Moderate"

    return "Low"


def calculate_consecutive_danger_days(
    dangerous_days: pd.Series,
) -> list[int]:
    """Count consecutive high/extreme heat days."""

    consecutive_days = []
    running_count = 0

    for is_dangerous in dangerous_days:
        if is_dangerous:
            running_count += 1
        else:
            running_count = 0

        consecutive_days.append(running_count)

    return consecutive_days


def generate_daily_features(
    input_file: str,
    output_file: str,
) -> pd.DataFrame:
    """Aggregate hourly thermal observations into daily features."""

    print(f"Reading hourly data: {input_file}")

    hourly = pd.read_csv(input_file)

    validate_hourly_data(hourly)

    # Parse timestamp and ensure it uses Indian Standard Time.
    hourly["timestamp_local"] = (
        pd.to_datetime(
            hourly["timestamp_local"],
            utc=True,
            errors="coerce",
        )
        .dt.tz_convert("Asia/Kolkata")
    )

    hourly.dropna(
        subset=["timestamp_local"],
        inplace=True,
    )

    hourly["date"] = hourly["timestamp_local"].dt.date
    hourly["hour"] = hourly["timestamp_local"].dt.hour

    # A dangerous hour occurs when either index enters a high-risk range.
    hourly["is_danger_hour"] = (
        (hourly["estimated_wbgt_c"] >= 31)
        | (hourly["utci_c"] >= 38)
    )

    hourly["is_extreme_hour"] = (
        (hourly["estimated_wbgt_c"] >= 33)
        | (hourly["utci_c"] >= 46)
    )

    # Nighttime is defined here as 10 PM through 6 AM.
    hourly["is_night_hour"] = (
        (hourly["hour"] >= 22)
        | (hourly["hour"] <= 6)
    )

    daily = (
        hourly.groupby("date", as_index=False)
        .agg(
            hours_available=("timestamp_local", "count"),

            temperature_max_c=("temperature_c", "max"),
            temperature_min_c=("temperature_c", "min"),
            temperature_mean_c=("temperature_c", "mean"),

            humidity_max_pct=(
                "relative_humidity_pct",
                "max",
            ),
            humidity_mean_pct=(
                "relative_humidity_pct",
                "mean",
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

            wet_bulb_max_c=(
                "wet_bulb_c",
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

            utci_mean_c=(
                "utci_c",
                "mean",
            ),

            danger_hours=(
                "is_danger_hour",
                "sum",
            ),

            extreme_hours=(
                "is_extreme_hour",
                "sum",
            ),
        )
    )

    # Calculate minimum nighttime temperature separately.
    nighttime_data = hourly[
        hourly["is_night_hour"]
    ]

    nighttime_minimum = (
        nighttime_data.groupby("date")["temperature_c"]
        .min()
    )

    daily["night_temperature_min_c"] = (
        daily["date"].map(nighttime_minimum)
    )

    # UTC-to-IST conversion creates partial first and last dates.
    incomplete_days = daily[
        daily["hours_available"] != 24
    ]

    if not incomplete_days.empty:
        print(
            "\nRemoving incomplete local dates:",
            incomplete_days["date"].tolist(),
        )

    daily = daily[
        daily["hours_available"] == 24
    ].copy()

    daily.reset_index(
        drop=True,
        inplace=True,
    )

    daily["daily_heat_level"] = daily.apply(
        lambda row: classify_daily_heat_risk(
            wbgt_max=row["wbgt_max_c"],
            utci_max=row["utci_max_c"],
        ),
        axis=1,
    )

    daily["is_dangerous_day"] = (
        (daily["wbgt_max_c"] >= 31)
        | (daily["utci_max_c"] >= 38)
    )

    daily["consecutive_danger_days"] = (
        calculate_consecutive_danger_days(
            daily["is_dangerous_day"]
        )
    )

    # Lagged and rolling features for the future model.
    daily["previous_day_wbgt_c"] = (
        daily["wbgt_max_c"].shift(1)
    )

    daily["previous_day_utci_c"] = (
        daily["utci_max_c"].shift(1)
    )

    daily["wbgt_3day_mean_c"] = (
        daily["wbgt_max_c"]
        .rolling(
            window=3,
            min_periods=1,
        )
        .mean()
    )

    daily["utci_3day_mean_c"] = (
        daily["utci_max_c"]
        .rolling(
            window=3,
            min_periods=1,
        )
        .mean()
    )

    numeric_columns = daily.select_dtypes(
        include="number"
    ).columns

    daily[numeric_columns] = daily[
        numeric_columns
    ].round(2)

    output_path = Path(output_file)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    daily.to_csv(
        output_path,
        index=False,
    )

    print("\nDaily feature generation completed.")
    print(f"Saved {len(daily)} complete daily records.")
    print(f"Output: {output_path.resolve()}")

    return daily


def print_daily_summary(
    daily: pd.DataFrame,
) -> None:
    """Display important daily results."""

    print("\nDaily heat-level distribution:")

    print(
        daily["daily_heat_level"]
        .value_counts()
    )

    print("\nMost dangerous day:")

    most_dangerous_index = (
        daily["wbgt_max_c"].idxmax()
    )

    columns_to_display = [
        "date",
        "temperature_max_c",
        "humidity_mean_pct",
        "heat_index_max_c",
        "wbgt_max_c",
        "utci_max_c",
        "danger_hours",
        "extreme_hours",
        "daily_heat_level",
    ]

    print(
        daily.loc[
            most_dangerous_index,
            columns_to_display,
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate daily heat-health features"
    )

    parser.add_argument(
        "--input",
        default=(
            "output/"
            "delhi_hourly_thermal_indices.csv"
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            "output/"
            "delhi_daily_heat_features.csv"
        ),
    )

    arguments = parser.parse_args()

    daily = generate_daily_features(
        input_file=arguments.input,
        output_file=arguments.output,
    )

    print_daily_summary(daily)


if __name__ == "__main__":
    main()