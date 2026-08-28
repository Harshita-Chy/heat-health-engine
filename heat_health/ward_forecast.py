from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


WARD_LOCATIONS = Path(
    "data/processed/delhi_ward_locations.csv"
)

OUTPUT_CSV = Path(
    "output/delhi_ward_hourly_forecast.csv"
)

API_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "shortwave_radiation",
)

FORECAST_DAYS = 5
BATCH_SIZE = 50
MAX_RETRIES = 3


def create_batches(
    dataframe: pd.DataFrame,
    batch_size: int,
):
    """
    Divide ward locations into smaller API batches.
    """

    for start in range(
        0,
        len(dataframe),
        batch_size,
    ):
        yield dataframe.iloc[
            start : start + batch_size
        ]


def fetch_batch(
    batch: pd.DataFrame,
) -> list[dict]:
    """
    Fetch hourly forecasts for one group of ward coordinates.
    """

    latitude_values = ",".join(
        batch["centroid_lat"].map(
            lambda value: f"{value:.6f}"
        )
    )

    longitude_values = ",".join(
        batch["centroid_lon"].map(
            lambda value: f"{value:.6f}"
        )
    )

    parameters = {
        "latitude": latitude_values,
        "longitude": longitude_values,
        "hourly": ",".join(HOURLY_VARIABLES),
        "forecast_days": FORECAST_DAYS,
        "timezone": "Asia/Kolkata",
        "temperature_unit": "celsius",
        "wind_speed_unit": "ms",
        "timeformat": "iso8601",
    }

    query_string = urlencode(
        parameters,
        safe=",/",
    )

    request_url = (
        f"{API_URL}?{query_string}"
    )

    request = Request(
        request_url,
        headers={
            "User-Agent":
                "SIH-Heat-Health-Engine/1.0"
        },
    )

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):
        try:
            with urlopen(
                request,
                timeout=60,
            ) as response:
                payload = json.load(response)

            if (
                isinstance(payload, dict)
                and payload.get("error")
            ):
                raise ValueError(
                    "Open-Meteo API error: "
                    f"{payload.get('reason')}"
                )

            if isinstance(payload, dict):
                payload = [payload]

            if not isinstance(payload, list):
                raise ValueError(
                    "Open-Meteo returned an invalid response."
                )

            if len(payload) != len(batch):
                raise ValueError(
                    "Open-Meteo returned "
                    f"{len(payload)} locations for a "
                    f"batch containing {len(batch)} wards."
                )

            return payload

        except (
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as error:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    "Open-Meteo request failed after "
                    f"{MAX_RETRIES} attempts: {error}"
                ) from error

            wait_seconds = 2 ** (attempt - 1)

            print(
                f"Request failed: {error}"
            )

            print(
                f"Retrying in {wait_seconds} seconds..."
            )

            time.sleep(wait_seconds)

    raise RuntimeError(
        "Forecast request ended unexpectedly."
    )


def convert_response_to_rows(
    ward: pd.Series,
    location_response: dict,
    generated_at_utc: str,
) -> list[dict]:
    """
    Convert one ward's API response into tabular rows.
    """

    hourly_data = location_response.get(
        "hourly"
    )

    if not isinstance(hourly_data, dict):
        raise ValueError(
            "Hourly forecast is missing for ward "
            f"{ward['ward_id']}."
        )

    required_fields = {
        "time",
        *HOURLY_VARIABLES,
    }

    missing_fields = required_fields.difference(
        hourly_data
    )

    if missing_fields:
        raise ValueError(
            f"Forecast for ward {ward['ward_id']} "
            f"is missing: {sorted(missing_fields)}"
        )

    array_lengths = {
        len(hourly_data[field])
        for field in required_fields
    }

    if len(array_lengths) != 1:
        raise ValueError(
            "Forecast arrays have different lengths "
            f"for ward {ward['ward_id']}."
        )

    rows = []

    for index, forecast_time in enumerate(
        hourly_data["time"]
    ):
        row = {
            "ward_id": str(ward["ward_id"]),
            "ward_name": ward["ward_name"],

            "centroid_lat": float(
                ward["centroid_lat"]
            ),

            "centroid_lon": float(
                ward["centroid_lon"]
            ),

            "model_latitude":
                location_response.get("latitude"),

            "model_longitude":
                location_response.get("longitude"),

            "model_elevation_m":
                location_response.get("elevation"),

            "forecast_time_ist": forecast_time,

            "temperature_c":
                hourly_data[
                    "temperature_2m"
                ][index],

            "relative_humidity_pct":
                hourly_data[
                    "relative_humidity_2m"
                ][index],

            "wind_speed_10m_mps":
                hourly_data[
                    "wind_speed_10m"
                ][index],

            "solar_radiation_wm2":
                hourly_data[
                    "shortwave_radiation"
                ][index],

            "forecast_generated_utc":
                generated_at_utc,

            "weather_source":
                "Open-Meteo Forecast API",

            "weather_license":
                "CC-BY-4.0",
        }

        rows.append(row)

    return rows


def fetch_ward_forecasts(
    ward_locations: Path = WARD_LOCATIONS,
    output_csv: Path = OUTPUT_CSV,
) -> pd.DataFrame:
    """
    Fetch and save five-day hourly forecasts for every ward.
    """

    if not ward_locations.exists():
        raise FileNotFoundError(
            f"Ward location file not found: "
            f"{ward_locations}"
        )

    wards = pd.read_csv(
        ward_locations,
        dtype={
            "ward_id": "string",
        },
    )

    required_columns = {
        "ward_id",
        "ward_name",
        "centroid_lat",
        "centroid_lon",
    }

    missing_columns = required_columns.difference(
        wards.columns
    )

    if missing_columns:
        raise ValueError(
            "Ward location file is missing: "
            f"{sorted(missing_columns)}"
        )

    if wards.empty:
        raise ValueError(
            "Ward location file contains no records."
        )

    if wards["ward_id"].duplicated().any():
        raise ValueError(
            "Ward location file contains duplicate IDs."
        )

    coordinate_columns = [
        "centroid_lat",
        "centroid_lon",
    ]

    for column in coordinate_columns:
        wards[column] = pd.to_numeric(
            wards[column],
            errors="coerce",
        )

    if wards[
        coordinate_columns
    ].isna().any().any():
        raise ValueError(
            "Some ward coordinates are missing or invalid."
        )

    generated_at_utc = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )

    all_forecast_rows = []

    total_batches = (
        len(wards) + BATCH_SIZE - 1
    ) // BATCH_SIZE

    for batch_number, batch in enumerate(
        create_batches(
            wards,
            BATCH_SIZE,
        ),
        start=1,
    ):
        print(
            f"Fetching batch "
            f"{batch_number}/{total_batches} "
            f"({len(batch)} wards)..."
        )

        api_response = fetch_batch(batch)

        for (
            (_, ward),
            location_response,
        ) in zip(
            batch.iterrows(),
            api_response,
        ):
            ward_rows = convert_response_to_rows(
                ward,
                location_response,
                generated_at_utc,
            )

            all_forecast_rows.extend(
                ward_rows
            )

        if batch_number < total_batches:
            time.sleep(0.25)

    forecasts = pd.DataFrame(
        all_forecast_rows
    )

    numeric_columns = [
        "temperature_c",
        "relative_humidity_pct",
        "wind_speed_10m_mps",
        "solar_radiation_wm2",
    ]

    forecasts[numeric_columns] = forecasts[
        numeric_columns
    ].apply(
        pd.to_numeric,
        errors="coerce",
    )

    missing_weather = forecasts[
        numeric_columns
    ].isna().any(axis=1)

    if missing_weather.any():
        raise ValueError(
            "Forecast contains "
            f"{int(missing_weather.sum())} rows "
            "with missing weather values."
        )

    if not forecasts[
        "relative_humidity_pct"
    ].between(0, 100).all():
        raise ValueError(
            "Forecast contains invalid humidity values."
        )

    if (
        forecasts["wind_speed_10m_mps"] < 0
    ).any():
        raise ValueError(
            "Forecast contains negative wind speed."
        )

    if (
        forecasts["solar_radiation_wm2"] < 0
    ).any():
        raise ValueError(
            "Forecast contains negative solar radiation."
        )

    expected_rows = (
        len(wards)
        * FORECAST_DAYS
        * 24
    )

    if len(forecasts) != expected_rows:
        raise ValueError(
            f"Expected {expected_rows} forecast rows, "
            f"received {len(forecasts)}."
        )

    duplicate_records = forecasts.duplicated(
        [
            "ward_id",
            "forecast_time_ist",
        ]
    )

    if duplicate_records.any():
        raise ValueError(
            "Forecast contains duplicate ward/time records."
        )

    forecasts = forecasts.sort_values(
        [
            "forecast_time_ist",
            "ward_id",
        ]
    ).reset_index(drop=True)

    output_csv.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    forecasts.to_csv(
        output_csv,
        index=False,
    )

    print()
    print(
        f"Wards: "
        f"{forecasts['ward_id'].nunique()}"
    )

    print(
        "Forecast hours per ward: "
        f"{FORECAST_DAYS * 24}"
    )

    print(
        f"Total forecast rows: "
        f"{len(forecasts):,}"
    )

    print(
        f"From: "
        f"{forecasts['forecast_time_ist'].min()}"
    )

    print(
        f"To: "
        f"{forecasts['forecast_time_ist'].max()}"
    )

    print(
        f"Saved: {output_csv}"
    )

    return forecasts


def main() -> None:
    fetch_ward_forecasts()


if __name__ == "__main__":
    main()