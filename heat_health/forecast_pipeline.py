"""Run the complete Delhi operational heat-health forecast pipeline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "output"

PIPELINE_SUMMARY_FILE = (
    OUTPUT_DIRECTORY / "forecast_pipeline_summary.json"
)


PIPELINE_STEPS = [
    {
        "name": "Download ward-level weather forecast",
        "module": "heat_health.ward_forecast",
        "network_required": True,
        "outputs": [
            OUTPUT_DIRECTORY
            / "delhi_ward_hourly_forecast.csv",
        ],
    },
    {
        "name": "Calculate hourly thermal indices",
        "module": "heat_health.forecast_thermal",
        "network_required": False,
        "outputs": [
            OUTPUT_DIRECTORY
            / "delhi_ward_hourly_thermal_forecast.csv",
        ],
    },
    {
        "name": "Generate daily ward risk forecast",
        "module": "heat_health.daily_risk_forecast",
        "network_required": False,
        "outputs": [
            OUTPUT_DIRECTORY
            / "delhi_ward_daily_risk_forecast.csv",
            OUTPUT_DIRECTORY
            / "delhi_5day_peak_risk_map.geojson",
            OUTPUT_DIRECTORY
            / "delhi_risk_summary.json",
        ],
    },
    {
        "name": "Apply mortality-risk calibration",
        "module": "heat_health.mortality_calibration",
        "network_required": False,
        "outputs": [
            OUTPUT_DIRECTORY
            / "delhi_ward_daily_calibrated_risk.csv",
            OUTPUT_DIRECTORY
            / "delhi_mortality_calibration_summary.json",
        ],
    },
    {
        "name": "Generate calibrated GIS products",
        "module": "heat_health.calibrated_map",
        "network_required": False,
        "outputs": [
            OUTPUT_DIRECTORY
            / "delhi_5day_peak_calibrated_risk_map.geojson",
            OUTPUT_DIRECTORY
            / "delhi_calibrated_hotspots.csv",
            OUTPUT_DIRECTORY
            / "delhi_calibrated_map_summary.json",
        ],
    },
]


def utc_now() -> str:
    """Return the current UTC time in ISO format."""

    return datetime.now(timezone.utc).isoformat()


def validate_outputs(paths: list[Path]) -> None:
    """Verify that a pipeline step created non-empty output files."""

    missing_files = [
        path
        for path in paths
        if not path.exists() or path.stat().st_size == 0
    ]

    if missing_files:
        formatted_files = ", ".join(
            str(path.relative_to(PROJECT_ROOT))
            for path in missing_files
        )

        raise FileNotFoundError(
            f"Expected output files were not created: "
            f"{formatted_files}"
        )


def run_module(module_name: str) -> None:
    """Execute one project module using the active Python environment."""

    command = [
        sys.executable,
        "-m",
        module_name,
    ]

    subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
    )


def write_summary(summary: dict[str, Any]) -> None:
    """Save a machine-readable pipeline execution summary."""

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    PIPELINE_SUMMARY_FILE.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def run_pipeline(skip_fetch: bool = False) -> None:
    """Execute every operational forecast step in order."""

    pipeline_started = time.perf_counter()

    summary: dict[str, Any] = {
        "pipeline_version": "delhi-operational-pipeline-v1",
        "started_at_utc": utc_now(),
        "completed_at_utc": None,
        "status": "running",
        "skip_fetch": skip_fetch,
        "steps": [],
    }

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 68)
    print("DELHI HEAT-HEALTH OPERATIONAL FORECAST PIPELINE")
    print("=" * 68)
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Python: {sys.executable}")

    try:
        for step_number, step in enumerate(
            PIPELINE_STEPS,
            start=1,
        ):
            step_name = str(step["name"])
            module_name = str(step["module"])
            outputs = list(step["outputs"])
            network_required = bool(
                step["network_required"]
            )

            print("\n" + "-" * 68)
            print(
                f"STEP {step_number}/{len(PIPELINE_STEPS)}: "
                f"{step_name}"
            )
            print("-" * 68)

            step_summary: dict[str, Any] = {
                "step": step_number,
                "name": step_name,
                "module": module_name,
                "started_at_utc": utc_now(),
                "completed_at_utc": None,
                "duration_seconds": None,
                "status": "running",
                "outputs": [
                    str(path.relative_to(PROJECT_ROOT))
                    for path in outputs
                ],
            }

            summary["steps"].append(step_summary)
            write_summary(summary)

            step_started = time.perf_counter()

            if skip_fetch and network_required:
                print(
                    "Weather download skipped; validating "
                    "existing forecast file."
                )

                validate_outputs(outputs)
                step_summary["status"] = "skipped_existing_output"

            else:
                run_module(module_name)
                validate_outputs(outputs)
                step_summary["status"] = "completed"

            step_summary["duration_seconds"] = round(
                time.perf_counter() - step_started,
                2,
            )

            step_summary["completed_at_utc"] = utc_now()

            print(
                f"Completed in "
                f"{step_summary['duration_seconds']} seconds."
            )

            for output_path in outputs:
                print(
                    "Verified:",
                    output_path.relative_to(PROJECT_ROOT),
                )

            write_summary(summary)

        summary["status"] = "completed"
        summary["completed_at_utc"] = utc_now()
        summary["duration_seconds"] = round(
            time.perf_counter() - pipeline_started,
            2,
        )

        write_summary(summary)

        print("\n" + "=" * 68)
        print("PIPELINE COMPLETED SUCCESSFULLY")
        print("=" * 68)
        print(
            f"Total duration: "
            f"{summary['duration_seconds']} seconds"
        )
        print(
            "Summary:",
            PIPELINE_SUMMARY_FILE.relative_to(PROJECT_ROOT),
        )
        print(
            "The backend will read the refreshed outputs "
            "automatically."
        )

    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        ValueError,
    ) as error:
        summary["status"] = "failed"
        summary["completed_at_utc"] = utc_now()
        summary["duration_seconds"] = round(
            time.perf_counter() - pipeline_started,
            2,
        )
        summary["error"] = str(error)

        if summary["steps"]:
            current_step = summary["steps"][-1]
            current_step["status"] = "failed"
            current_step["completed_at_utc"] = utc_now()
            current_step["error"] = str(error)

        write_summary(summary)

        print("\n" + "=" * 68)
        print("PIPELINE FAILED")
        print("=" * 68)
        print(error)
        print(
            "Failure summary:",
            PIPELINE_SUMMARY_FILE.relative_to(PROJECT_ROOT),
        )

        raise SystemExit(1) from error


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate Delhi heat-health forecasts, "
            "mortality risk and GIS outputs."
        )
    )

    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help=(
            "Use the existing ward weather forecast instead "
            "of downloading fresh weather data."
        ),
    )

    arguments = parser.parse_args()

    run_pipeline(
        skip_fetch=arguments.skip_fetch,
    )


if __name__ == "__main__":
    main()