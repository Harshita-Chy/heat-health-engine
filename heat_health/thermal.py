"""Human thermal-stress calculation engine.

The engine calculates:

1. Heat Index
2. Wet-bulb temperature
3. Estimated globe temperature
4. Estimated mean radiant temperature
5. WBGT
6. UTCI
7. Overall thermal-stress level
"""

from math import atan, sqrt

from pythermalcomfort.models import (
    heat_index_rothfusz,
    utci,
    wbgt,
)


def validate_inputs(
    temperature_c: float,
    humidity: float,
    wind_speed: float,
    solar_radiation: float,
) -> None:
    """Validate weather inputs before calculations."""

    if not -50 <= temperature_c <= 60:
        raise ValueError("Temperature must be between -50°C and 60°C")

    if not 0 <= humidity <= 100:
        raise ValueError("Humidity must be between 0% and 100%")

    if not 0 <= wind_speed <= 75:
        raise ValueError("Wind speed cannot be negative")

    if not 0 <= solar_radiation <= 1600:
        raise ValueError("Solar radiation must be between 0 and 1600 W/m²")


def calculate_wet_bulb_temperature(
    temperature_c: float,
    humidity: float,
) -> float:
    """Estimate wet-bulb temperature using the Stull approximation."""

    humidity = max(humidity, 0.1)

    wet_bulb = (
        temperature_c
        * atan(0.151977 * sqrt(humidity + 8.313659))
        + atan(temperature_c + humidity)
        - atan(humidity - 1.676331)
        + 0.00391838
        * humidity ** 1.5
        * atan(0.023101 * humidity)
        - 4.686035
    )

    return wet_bulb


def convert_wind_height(
    wind_speed_10m: float,
    target_height: float = 1.1,
) -> float:
    """Convert 10-metre wind speed to approximately human height."""

    return wind_speed_10m * (target_height / 10.0) ** 0.14


def estimate_globe_temperature(
    temperature_c: float,
    wind_speed_10m: float,
    solar_radiation: float,
) -> float:
    """Estimate black-globe temperature.

    Solar radiation raises globe temperature, while wind provides cooling.

    This is a screening approximation, not a physical globe-thermometer
    measurement.
    """

    if solar_radiation <= 10:
        return temperature_c

    wind_at_human_height = convert_wind_height(wind_speed_10m)

    solar_temperature_gain = (
        0.020
        * solar_radiation
        / (1.0 + 0.5 * sqrt(max(wind_at_human_height, 0.1)))
    )

    # Avoid physically unrealistic values from abnormal weather inputs.
    solar_temperature_gain = min(solar_temperature_gain, 25.0)

    return temperature_c + solar_temperature_gain


def estimate_mean_radiant_temperature(
    temperature_c: float,
    globe_temperature_c: float,
    wind_speed_10m: float,
) -> float:
    """Estimate mean radiant temperature from globe temperature."""

    wind_at_human_height = max(
        convert_wind_height(wind_speed_10m),
        0.1,
    )

    emissivity = 0.95
    globe_diameter = 0.15

    globe_temperature_k = globe_temperature_c + 273.15

    convection_term = (
        1.1e8
        * wind_at_human_height ** 0.6
        / (emissivity * globe_diameter ** 0.4)
        * (globe_temperature_c - temperature_c)
    )

    radiant_temperature_k = (
        globe_temperature_k ** 4 + convection_term
    ) ** 0.25

    return radiant_temperature_k - 273.15


def classify_thermal_stress(
    wbgt_c: float,
    utci_c: float,
) -> str:
    """Classify overall human thermal stress."""

    if wbgt_c >= 33 or utci_c >= 46:
        return "Extreme"

    if wbgt_c >= 31 or utci_c >= 38:
        return "High"

    if wbgt_c >= 25 or utci_c >= 32:
        return "Moderate"

    return "Low"


def calculate_thermal_stress(
    temperature_c: float,
    humidity: float,
    wind_speed_10m: float,
    solar_radiation: float,
) -> dict:
    """Calculate all thermal-stress indices for one weather observation."""

    validate_inputs(
        temperature_c,
        humidity,
        wind_speed_10m,
        solar_radiation,
    )

    # 1. Heat Index
    heat_index_result = heat_index_rothfusz(
        tdb=temperature_c,
        rh=humidity,
        limit_inputs=False,
        round_output=False,
    )

    heat_index_c = float(heat_index_result.hi)

    # 2. Wet-bulb temperature
    wet_bulb_c = calculate_wet_bulb_temperature(
        temperature_c,
        humidity,
    )

    # 3. Globe temperature
    globe_temperature_c = estimate_globe_temperature(
        temperature_c,
        wind_speed_10m,
        solar_radiation,
    )

    # 4. Mean radiant temperature
    mean_radiant_temperature_c = estimate_mean_radiant_temperature(
        temperature_c,
        globe_temperature_c,
        wind_speed_10m,
    )

    # 5. WBGT
    if solar_radiation > 10:
        wbgt_result = wbgt(
            twb=wet_bulb_c,
            tg=globe_temperature_c,
            tdb=temperature_c,
            with_solar_load=True,
            round_output=False,
        )
    else:
        wbgt_result = wbgt(
            twb=wet_bulb_c,
            tg=globe_temperature_c,
            with_solar_load=False,
            round_output=False,
        )

    wbgt_c = float(wbgt_result.wbgt)

    # UTCI requires wind speed at 10 metres.
    valid_utci_wind = min(max(wind_speed_10m, 0.5), 17.0)

    # 6. UTCI
    utci_result = utci(
        tdb=temperature_c,
        tr=mean_radiant_temperature_c,
        v=valid_utci_wind,
        rh=humidity,
        limit_inputs=True,
        round_output=False,
    )

    utci_c = float(utci_result.utci)
    utci_category = str(utci_result.stress_category)

    # 7. Overall classification
    stress_level = classify_thermal_stress(
        wbgt_c,
        utci_c,
    )

    return {
        "temperature_c": round(temperature_c, 2),
        "relative_humidity_pct": round(humidity, 2),
        "wind_speed_10m_mps": round(wind_speed_10m, 2),
        "solar_radiation_wm2": round(solar_radiation, 2),
        "heat_index_c": round(heat_index_c, 2),
        "wet_bulb_c": round(wet_bulb_c, 2),
        "estimated_globe_temperature_c": round(
            globe_temperature_c, 2
        ),
        "estimated_mean_radiant_temperature_c": round(
            mean_radiant_temperature_c, 2
        ),
        "estimated_wbgt_c": round(wbgt_c, 2),
        "utci_c": round(utci_c, 2),
        "utci_category": utci_category,
        "thermal_stress_level": stress_level,
    }


if __name__ == "__main__":
    result = calculate_thermal_stress(
        temperature_c=40,
        humidity=70,
        wind_speed_10m=2,
        solar_radiation=800,
    )

    for key, value in result.items():
        print(f"{key}: {value}")