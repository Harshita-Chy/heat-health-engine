"""Validate the complete Delhi heat-health system before a demonstration."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "output"

FORECAST_FILE = (
    OUTPUT_DIRECTORY
    / "delhi_ward_daily_calibrated_risk.csv"
)

MAP_FILE = (
    OUTPUT_DIRECTORY
    / "delhi_5day_peak_calibrated_risk_map.geojson"
)

PIPELINE_SUMMARY_FILE = (
    OUTPUT_DIRECTORY
    / "forecast_pipeline_summary.json"
)

MODEL_FILE = (
    PROJECT_ROOT
    / "models"
    / "mortality_model_v1.json"
)

FRONTEND_BUILD_FILE = (
    PROJECT_ROOT
    / "frontend"
    / "dist"
    / "index.html"
)

REPORT_FILE = (
    OUTPUT_DIRECTORY
    / "system_check_report.json"
)


def normalize_ward_id(value: object) -> str:
    text = str(value).strip()

    if text.endswith(".0"):
        return text[:-2]

    return text


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


def api_get(
    api_url: str,
    endpoint: str,
    parameters: dict[str, str] | None = None,
) -> dict[str, Any]:
    url = f"{api_url.rstrip('/')}{endpoint}"

    if parameters:
        url = f"{url}?{urlencode(parameters)}"

    with urlopen(url, timeout=15) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate model, GIS, API and frontend outputs."
    )

    parser.add_argument(
        "--api-url",
        default="http://localhost:5000",
        help="Node backend address",
    )

    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Check local files without checking the backend API",
    )

    arguments = parser.parse_args()

    checks: list[dict[str, Any]] = []

    def record(
        name: str,
        passed: bool,
        details: str,
    ) -> None:
        status = "PASS" if passed else "FAIL"

        print(f"[{status}] {name}: {details}")

        checks.append(
            {
                "name": name,
                "passed": passed,
                "details": details,
            }
        )

    print("=" * 68)
    print("DELHI HEAT-HEALTH SYSTEM CHECK")
    print("=" * 68)

    required_files = [
        FORECAST_FILE,
        MAP_FILE,
        PIPELINE_SUMMARY_FILE,
        MODEL_FILE,
        FRONTEND_BUILD_FILE,
    ]

    missing_files = [
        path
        for path in required_files
        if not path.exists() or path.stat().st_size == 0
    ]

    record(
        "Required files",
        not missing_files,
        (
            "All required files are available"
            if not missing_files
            else "Missing: "
            + ", ".join(str(path) for path in missing_files)
        ),
    )

    forecast_rows: list[dict[str, str]] = []
    forecast_dates: list[str] = []
    ward_ids: set[str] = set()

    try:
        forecast_rows = load_csv(FORECAST_FILE)

        forecast_dates = sorted(
            {
                row["forecast_date"]
                for row in forecast_rows
            }
        )

        ward_ids = {
            normalize_ward_id(row["ward_id"])
            for row in forecast_rows
        }

        record(
            "Forecast dimensions",
            (
                len(forecast_rows) == 1450
                and len(ward_ids) == 290
                and len(forecast_dates) == 5
            ),
            (
                f"{len(forecast_rows)} rows, "
                f"{len(ward_ids)} wards, "
                f"{len(forecast_dates)} days"
            ),
        )

        date_counts = Counter(
            row["forecast_date"]
            for row in forecast_rows
        )

        record(
            "Daily ward coverage",
            all(
                date_counts[date] == 290
                for date in forecast_dates
            ),
            str(dict(date_counts)),
        )

        risk_values = [
            float(
                row["calibrated_mortality_risk_index"]
            )
            for row in forecast_rows
        ]

        record(
            "Risk index validity",
            all(0 <= value <= 100 for value in risk_values),
            (
                f"Range {min(risk_values):.2f} "
                f"to {max(risk_values):.2f}"
            ),
        )

    except Exception as error:
        record(
            "Forecast data",
            False,
            str(error),
        )

    try:
        map_data = load_json(MAP_FILE)
        features = map_data.get("features", [])

        map_ward_ids = {
            normalize_ward_id(
                feature.get("properties", {}).get(
                    "ward_id",
                    "",
                )
            )
            for feature in features
        }

        valid_geometries = all(
            feature.get("geometry")
            and feature["geometry"].get("coordinates")
            for feature in features
        )

        record(
            "GIS features",
            (
                len(features) == 290
                and len(map_ward_ids) == 290
                and valid_geometries
            ),
            (
                f"{len(features)} features, "
                f"{len(map_ward_ids)} unique ward IDs"
            ),
        )

        if ward_ids:
            record(
                "Forecast-to-map join",
                ward_ids == map_ward_ids,
                (
                    f"{len(ward_ids & map_ward_ids)} "
                    f"of {len(ward_ids)} wards matched"
                ),
            )

    except Exception as error:
        record(
            "GIS map",
            False,
            str(error),
        )

    try:
        pipeline_summary = load_json(
            PIPELINE_SUMMARY_FILE
        )

        record(
            "Pipeline status",
            pipeline_summary.get("status") == "completed",
            (
                f"Status: "
                f"{pipeline_summary.get('status', 'unknown')}"
            ),
        )

    except Exception as error:
        record(
            "Pipeline summary",
            False,
            str(error),
        )

    if not arguments.skip_api:
        try:
            health = api_get(
                arguments.api_url,
                "/api/health",
            )

            record(
                "Backend health",
                (
                    health.get("success") is True
                    and health.get("status") == "ready"
                ),
                f"Status: {health.get('status', 'unknown')}",
            )

        except Exception as error:
            record(
                "Backend health",
                False,
                str(error),
            )

        if forecast_dates:
            selected_date = forecast_dates[0]

            try:
                daily = api_get(
                    arguments.api_url,
                    "/api/forecast/daily",
                    {"date": selected_date},
                )

                daily_rows = daily.get("data", [])

                record(
                    "Daily forecast API",
                    (
                        daily.get("success") is True
                        and len(daily_rows) == 290
                        and all(
                            row.get("forecast_date")
                            == selected_date
                            for row in daily_rows
                        )
                    ),
                    (
                        f"{len(daily_rows)} wards for "
                        f"{selected_date}"
                    ),
                )

            except Exception as error:
                record(
                    "Daily forecast API",
                    False,
                    str(error),
                )

            if ward_ids:
                sample_ward = sorted(ward_ids)[0]

                try:
                    ward = api_get(
                        arguments.api_url,
                        f"/api/wards/{sample_ward}",
                    )

                    ward_forecast = (
                        ward.get("data", {})
                        .get("forecast", [])
                    )

                    record(
                        "Ward forecast API",
                        (
                            ward.get("success") is True
                            and len(ward_forecast) == 5
                        ),
                        (
                            f"{len(ward_forecast)} days for "
                            f"ward {sample_ward}"
                        ),
                    )

                except Exception as error:
                    record(
                        "Ward forecast API",
                        False,
                        str(error),
                    )

                try:
                    alert = api_get(
                        arguments.api_url,
                        "/api/alerts/preview",
                        {
                            "ward_id": sample_ward,
                            "date": selected_date,
                        },
                    )

                    alert_data = alert.get("data", {})

                    record(
                        "Alert preview API",
                        (
                            alert.get("success") is True
                            and bool(
                                alert_data
                                .get("messages", {})
                                .get("sms")
                            )
                            and bool(
                                alert_data
                                .get(
                                    "administrative_triggers"
                                )
                            )
                        ),
                        (
                            f"Ward {sample_ward}, "
                            f"date {selected_date}"
                        ),
                    )

                except Exception as error:
                    record(
                        "Alert preview API",
                        False,
                        str(error),
                    )

    passed_checks = sum(
        check["passed"]
        for check in checks
    )

    failed_checks = len(checks) - passed_checks

    report = {
        "generated_at_utc": (
            datetime.now(timezone.utc).isoformat()
        ),
        "overall_status": (
            "passed"
            if failed_checks == 0
            else "failed"
        ),
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "checks": checks,
    }

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_FILE.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 68)
    print(
        f"SYSTEM CHECK: "
        f"{passed_checks} passed, "
        f"{failed_checks} failed"
    )
    print("=" * 68)
    print(
        "Report:",
        REPORT_FILE.relative_to(PROJECT_ROOT),
    )

    if failed_checks:
        raise SystemExit(1)


if __name__ == "__main__":
    main()