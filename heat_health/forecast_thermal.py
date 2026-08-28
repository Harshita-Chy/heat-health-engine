from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

if __package__:
    from .thermal import calculate_thermal_stress
else:
    from thermal import calculate_thermal_stress


INPUT_CSV = Path(
    "output/delhi_ward_hourly_forecast.csv"
)

OUTPUT_CSV = Path(
    "output/delhi_ward_hourly_thermal_forecast.csv"
)


WEATHER_COLUMNS = [
    "temperature_c",
    "relative_humidity_pct",
    "wind_speed_10m_mps",
    "solar_radiation_wm2",
]


THERMAL_COLUMNS = [
    "heat_index_c",
    "wet_bulb_c",
    "estimated_globe_temperature_c",
    "estimated_mean_radiant_temperature_c",
    "estimated_wbgt_c",
    "utci_c",
    "utci_category",
    "thermal_stress_level",
]


NUMERIC_THERMAL_COLUMNS = [
    "heat_index_c",
    "wet_bulb_c",
    "estimated_globe_temperature_c",
    "estimated_mean_radiant_temperature_c",
    "estimated_wbgt_c",
    "utci_c",
]


@lru_cache(maxsize=None)
def calculate_cached(
    temperature_c: float,
    relative_humidity_pct: float,
    wind_speed_10m_mps: float,
    solar_radiation_wm2: float,
) -> tuple:
    """
    Calculate thermal indices for one unique weather condition.
    """

    result = calculate_thermal_stress(
        temperature_c=temperature_c,
        humidity=relative_humidity_pct,
        wind_speed_10m=wind_speed_10m_mps,
        solar_radiation=solar_radiation_wm2,
    )

    if not isinstance(result, dict):
        raise TypeError(
            "calculate_thermal_stress() must return a dictionary."
        )

    missing_keys = [
        column
        for column in THERMAL_COLUMNS
        if column not in result
    ]

    if missing_keys:
        raise KeyError(
            "Thermal engine result is missing keys: "
            f"{missing_keys}. "
            f"Available keys: {sorted(result.keys())}"
        )

    return tuple(
        result[column]
        for column in THERMAL_COLUMNS
    )


def validate_input(
    forecast: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate the ward weather forecast.
    """

    required_columns = {
        "ward_id",
        "ward_name",
        "forecast_time_ist",
        *WEATHER_COLUMNS,
    }

    missing_columns = required_columns.difference(
        forecast.columns
    )

    if missing_columns:
        raise ValueError(
            "Forecast file is missing columns: "
            f"{sorted(missing_columns)}"
        )

    if forecast.empty:
        raise ValueError(
            "Forecast file contains no rows."
        )

    forecast = forecast.copy()

    for column in WEATHER_COLUMNS:
        forecast[column] = pd.to_numeric(
            forecast[column],
            errors="coerce",
        )

    invalid_rows = forecast[
        WEATHER_COLUMNS
    ].isna().any(axis=1)

    if invalid_rows.any():
        raise ValueError(
            f"Forecast contains {int(invalid_rows.sum())} "
            "rows with invalid weather values."
        )

    if not forecast[
        "relative_humidity_pct"
    ].between(0, 100).all():
        raise ValueError(
            "Humidity must be between 0 and 100."
        )

    if (
        forecast["wind_speed_10m_mps"] < 0
    ).any():
        raise ValueError(
            "Wind speed cannot be negative."
        )

    if (
        forecast["solar_radiation_wm2"] < 0
    ).any():
        raise ValueError(
            "Solar radiation cannot be negative."
        )

    duplicate_rows = forecast.duplicated(
        [
            "ward_id",
            "forecast_time_ist",
        ]
    )

    if duplicate_rows.any():
        raise ValueError(
            "Forecast contains duplicate ward/time records."
        )

    return forecast


def generate_thermal_forecast(
    input_csv: Path = INPUT_CSV,
    output_csv: Path = OUTPUT_CSV,
) -> pd.DataFrame:
    """
    Calculate hourly thermal indices for all Delhi wards.
    """

    if not input_csv.exists():
        raise FileNotFoundError(
            f"Input forecast not found: {input_csv}"
        )

    print(
        f"Reading forecast: {input_csv}"
    )

    forecast = pd.read_csv(
        input_csv,
        dtype={
            "ward_id": "string",
        },
    )

    forecast = validate_input(
        forecast
    )

    total_rows = len(forecast)

    print(
        f"Forecast rows: {total_rows:,}"
    )

    print(
        f"Wards: {forecast['ward_id'].nunique()}"
    )

    thermal_results = []

    for row_number, row in enumerate(
        forecast.itertuples(index=False),
        start=1,
    ):
        temperature = float(
            row.temperature_c
        )

        humidity = float(
            row.relative_humidity_pct
        )

        wind_speed = float(
            row.wind_speed_10m_mps
        )

        solar_radiation = max(
            0.0,
            float(row.solar_radiation_wm2),
        )

        try:
            result = calculate_cached(
                temperature,
                humidity,
                wind_speed,
                solar_radiation,
            )

        except Exception as error:
            raise RuntimeError(
                "Thermal calculation failed for "
                f"ward {row.ward_id} at "
                f"{row.forecast_time_ist}.\n"
                f"Temperature: {temperature}\n"
                f"Humidity: {humidity}\n"
                f"Wind: {wind_speed}\n"
                f"Solar radiation: {solar_radiation}\n"
                f"Error: {error}"
            ) from error

        thermal_results.append(
            result
        )

        if row_number % 5000 == 0:
            print(
                f"Processed {row_number:,}/"
                f"{total_rows:,} rows..."
            )

    thermal_dataframe = pd.DataFrame(
        thermal_results,
        columns=THERMAL_COLUMNS,
    )

    for column in NUMERIC_THERMAL_COLUMNS:
        thermal_dataframe[column] = pd.to_numeric(
            thermal_dataframe[column],
            errors="coerce",
        )

    missing_results = thermal_dataframe[
        NUMERIC_THERMAL_COLUMNS
    ].isna().sum()

    missing_results = missing_results[
        missing_results > 0
    ]

    if not missing_results.empty:
        raise ValueError(
            "Thermal engine produced missing results: "
            f"{missing_results.to_dict()}"
        )

    if thermal_dataframe[
        [
            "utci_category",
            "thermal_stress_level",
        ]
    ].isna().any().any():
        raise ValueError(
            "Thermal engine produced missing categories."
        )

    thermal_dataframe[
        NUMERIC_THERMAL_COLUMNS
    ] = thermal_dataframe[
        NUMERIC_THERMAL_COLUMNS
    ].round(2)

    final_output = pd.concat(
        [
            forecast.reset_index(drop=True),
            thermal_dataframe.reset_index(drop=True),
        ],
        axis=1,
    )

    if len(final_output) != total_rows:
        raise ValueError(
            "Output row count does not match input row count."
        )

    if final_output.duplicated(
        [
            "ward_id",
            "forecast_time_ist",
        ]
    ).any():
        raise ValueError(
            "Output contains duplicate records."
        )

    output_csv.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    final_output.to_csv(
        output_csv,
        index=False,
    )

    cache_info = calculate_cached.cache_info()

    print()
    print(
        f"Completed rows: {len(final_output):,}"
    )

    print(
        "Unique weather combinations: "
        f"{cache_info.misses:,}"
    )

    print(
        "Cached repeated combinations: "
        f"{cache_info.hits:,}"
    )

    print(
        "Heat Index range: "
        f"{final_output['heat_index_c'].min():.2f} "
        "to "
        f"{final_output['heat_index_c'].max():.2f} C"
    )

    print(
        "WBGT range: "
        f"{final_output['estimated_wbgt_c'].min():.2f} "
        "to "
        f"{final_output['estimated_wbgt_c'].max():.2f} C"
    )

    print(
        "UTCI range: "
        f"{final_output['utci_c'].min():.2f} "
        "to "
        f"{final_output['utci_c'].max():.2f} C"
    )

    print(
        f"Saved: {output_csv}"
    )

    return final_output


def main() -> None:
    generate_thermal_forecast()


if __name__ == "__main__":
    main()