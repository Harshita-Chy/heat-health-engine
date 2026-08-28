"""Download hourly Delhi weather data from NASA POWER."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


NASA_POWER_URL = (
    "https://power.larc.nasa.gov/api/temporal/hourly/point"
)

WEATHER_PARAMETERS = [
    "T2M",                  # Temperature at 2 metres
    "RH2M",                 # Relative humidity
    "WS10M",                # Wind speed at 10 metres
    "ALLSKY_SFC_SW_DWN",    # Solar radiation
    "T2MDEW",               # Dew-point temperature
    "PS",                   # Surface pressure
]


def download_nasa_weather(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Download and clean hourly weather data."""

    query_parameters = {
        "parameters": ",".join(WEATHER_PARAMETERS),
        "community": "RE",
        "longitude": longitude,
        "latitude": latitude,
        "start": start_date,
        "end": end_date,
        "format": "JSON",
        "time-standard": "UTC",
    }

    url = f"{NASA_POWER_URL}?{urlencode(query_parameters)}"

    print("Downloading weather data...")
    print(f"Latitude: {latitude}")
    print(f"Longitude: {longitude}")
    print(f"Period: {start_date} to {end_date}")

    request = Request(
        url,
        headers={
            "User-Agent": "SIH-Heat-Health-Prototype/1.0"
        },
    )

    try:
        with urlopen(request, timeout=120) as response:
            response_text = response.read().decode("utf-8")
    except Exception as error:
        raise RuntimeError(
            f"Unable to download NASA POWER data: {error}"
        ) from error

    api_data = json.loads(response_text)

    if "properties" not in api_data:
        raise RuntimeError(
            f"NASA POWER returned an invalid response: {api_data}"
        )

    parameter_data = api_data["properties"]["parameter"]

    weather = pd.DataFrame(parameter_data)

    weather.index.name = "timestamp_code"
    weather.reset_index(inplace=True)

    required_columns = [
        "T2M",
        "RH2M",
        "WS10M",
        "ALLSKY_SFC_SW_DWN",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in weather.columns
    ]

    if missing_columns:
        raise RuntimeError(
            f"NASA response is missing columns: {missing_columns}"
        )

    # Convert weather columns into numeric values.
    for column in WEATHER_PARAMETERS:
        if column in weather.columns:
            weather[column] = pd.to_numeric(
                weather[column],
                errors="coerce",
            )

            # NASA uses values close to -999 for missing observations.
            weather.loc[
                weather[column] <= -900,
                column,
            ] = pd.NA

    # NASA timestamp format: YYYYMMDDHH
    weather["timestamp_utc"] = pd.to_datetime(
        weather["timestamp_code"],
        format="%Y%m%d%H",
        utc=True,
        errors="coerce",
    )

    # Convert UTC into Indian Standard Time.
    weather["timestamp_local"] = (
        weather["timestamp_utc"]
        .dt.tz_convert("Asia/Kolkata")
    )

    weather.rename(
        columns={
            "T2M": "temperature_c",
            "RH2M": "relative_humidity_pct",
            "WS10M": "wind_speed_10m_mps",
            "ALLSKY_SFC_SW_DWN": "solar_radiation_wm2",
            "T2MDEW": "dew_point_c",
            "PS": "surface_pressure_kpa",
        },
        inplace=True,
    )

    final_columns = [
        "timestamp_utc",
        "timestamp_local",
        "temperature_c",
        "relative_humidity_pct",
        "wind_speed_10m_mps",
        "solar_radiation_wm2",
        "dew_point_c",
        "surface_pressure_kpa",
    ]

    weather = weather[final_columns]

    weather.dropna(
        subset=[
            "timestamp_utc",
            "temperature_c",
            "relative_humidity_pct",
            "wind_speed_10m_mps",
            "solar_radiation_wm2",
        ],
        inplace=True,
    )

    weather.drop_duplicates(
        subset=["timestamp_utc"],
        inplace=True,
    )

    weather.sort_values(
        by="timestamp_utc",
        inplace=True,
    )

    weather.reset_index(
        drop=True,
        inplace=True,
    )

    return weather


def save_weather_data(
    weather: pd.DataFrame,
    output_file: str,
) -> None:
    """Save cleaned weather data as CSV."""

    output_path = Path(output_file)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    weather.to_csv(
        output_path,
        index=False,
    )

    print(f"\nSaved {len(weather)} hourly records.")
    print(f"File: {output_path.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download NASA POWER weather data"
    )

    parser.add_argument(
        "--latitude",
        type=float,
        default=28.6139,
        help="Location latitude",
    )

    parser.add_argument(
        "--longitude",
        type=float,
        default=77.2090,
        help="Location longitude",
    )

    parser.add_argument(
        "--start",
        default="20240501",
        help="Start date in YYYYMMDD format",
    )

    parser.add_argument(
        "--end",
        default="20240531",
        help="End date in YYYYMMDD format",
    )

    parser.add_argument(
        "--output",
        default="data/delhi_weather_may_2024.csv",
        help="Output CSV file",
    )

    arguments = parser.parse_args()

    weather = download_nasa_weather(
        latitude=arguments.latitude,
        longitude=arguments.longitude,
        start_date=arguments.start,
        end_date=arguments.end,
    )

    save_weather_data(
        weather,
        arguments.output,
    )

    print("\nFirst five records:")
    print(weather.head().to_string(index=False))


if __name__ == "__main__":
    main()