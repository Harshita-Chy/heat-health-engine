"""Process hourly weather data through the thermal-stress engine."""

import argparse
from pathlib import Path

import pandas as pd

from heat_health.thermal import calculate_thermal_stress


REQUIRED_COLUMNS = [
    "timestamp_local",
    "temperature_c",
    "relative_humidity_pct",
    "wind_speed_10m_mps",
    "solar_radiation_wm2",
]

THERMAL_OUTPUT_COLUMNS = [
    "heat_index_c",
    "wet_bulb_c",
    "estimated_globe_temperature_c",
    "estimated_mean_radiant_temperature_c",
    "estimated_wbgt_c",
    "utci_c",
    "utci_category",
    "thermal_stress_level",
]


def validate_weather_data(weather: pd.DataFrame) -> None:
    """Check whether all required columns are present."""

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in weather.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Weather dataset is missing columns: {missing_columns}"
        )


def process_weather_data(
    input_file: str,
    output_file: str,
) -> pd.DataFrame:
    """Calculate thermal indices for every hourly observation."""

    print(f"Reading: {input_file}")

    weather = pd.read_csv(input_file)

    validate_weather_data(weather)

    print(f"Found {len(weather)} hourly weather records.")
    print("Calculating thermal indices...")

    thermal_results = []

    for index, row in weather.iterrows():
        try:
            result = calculate_thermal_stress(
                temperature_c=float(row["temperature_c"]),
                humidity=float(row["relative_humidity_pct"]),
                wind_speed_10m=float(
                    row["wind_speed_10m_mps"]
                ),
                solar_radiation=float(
                    row["solar_radiation_wm2"]
                ),
            )

            thermal_results.append(
                {
                    column: result[column]
                    for column in THERMAL_OUTPUT_COLUMNS
                }
            )

        except (ValueError, TypeError) as error:
            print(
                f"Warning: Could not process row {index}: {error}"
            )

            thermal_results.append(
                {
                    column: pd.NA
                    for column in THERMAL_OUTPUT_COLUMNS
                }
            )

        if (index + 1) % 100 == 0:
            print(
                f"Processed {index + 1}/{len(weather)} records"
            )

    thermal_frame = pd.DataFrame(thermal_results)

    processed_weather = pd.concat(
        [
            weather.reset_index(drop=True),
            thermal_frame,
        ],
        axis=1,
    )

    output_path = Path(output_file)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    processed_weather.to_csv(
        output_path,
        index=False,
    )

    print("\nProcessing completed.")
    print(f"Saved {len(processed_weather)} records.")
    print(f"Output: {output_path.resolve()}")

    return processed_weather


def print_summary(processed_weather: pd.DataFrame) -> None:
    """Print a basic thermal-stress summary."""

    print("\nThermal-stress summary:")

    stress_counts = (
        processed_weather["thermal_stress_level"]
        .value_counts(dropna=False)
    )

    print(stress_counts)

    print("\nMaximum calculated values:")

    print(
        "Maximum temperature:",
        round(processed_weather["temperature_c"].max(), 2),
        "°C",
    )

    print(
        "Maximum Heat Index:",
        round(processed_weather["heat_index_c"].max(), 2),
        "°C",
    )

    print(
        "Maximum WBGT:",
        round(processed_weather["estimated_wbgt_c"].max(), 2),
        "°C",
    )

    print(
        "Maximum UTCI:",
        round(processed_weather["utci_c"].max(), 2),
        "°C",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate hourly thermal-stress indices"
    )

    parser.add_argument(
        "--input",
        default="data/delhi_weather_may_2024.csv",
        help="NASA POWER weather CSV",
    )

    parser.add_argument(
        "--output",
        default="output/delhi_hourly_thermal_indices.csv",
        help="Processed output CSV",
    )

    arguments = parser.parse_args()

    processed_weather = process_weather_data(
        input_file=arguments.input,
        output_file=arguments.output,
    )

    print_summary(processed_weather)


if __name__ == "__main__":
    main()