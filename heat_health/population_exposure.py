from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.mask import mask
from rasterio.transform import array_bounds
from rasterio.warp import (
    Resampling,
    calculate_default_transform,
    reproject,
)
from shapely.geometry import mapping


# ---------------------------------------------------------
# File paths
# ---------------------------------------------------------

WARD_GEOJSON = Path(
    "data/processed/delhi_wards_processed.geojson"
)

POPULATION_RASTER = Path(
    "data/population/ind_pd_2020_1km.tif"
)

OUTPUT_CSV = Path(
    "output/delhi_ward_population_exposure.csv"
)

OUTPUT_GEOJSON = Path(
    "data/processed/delhi_wards_with_population.geojson"
)


# ---------------------------------------------------------
# Processing settings
# ---------------------------------------------------------

TARGET_CRS = "EPSG:32643"
TARGET_RESOLUTION_METERS = 100

WORLDPOP_SOURCE = (
    "https://hub.worldpop.org/geodata/summary?id=41746"
)

WORLDPOP_LICENSE = "CC-BY-4.0"
POPULATION_YEAR = 2020


def robust_score(values: pd.Series) -> pd.Series:
    """
    Convert values into scores between 0 and 100.

    The 5th and 95th percentiles are used to reduce the
    influence of unusually small or large wards.
    """

    numeric_values = pd.to_numeric(
        values,
        errors="coerce",
    ).astype(float)

    if numeric_values.isna().any():
        raise ValueError(
            "Exposure scoring received missing values."
        )

    lower_limit = float(
        numeric_values.quantile(0.05)
    )

    upper_limit = float(
        numeric_values.quantile(0.95)
    )

    if np.isclose(lower_limit, upper_limit):
        return pd.Series(
            50.0,
            index=numeric_values.index,
        )

    clipped_values = numeric_values.clip(
        lower=lower_limit,
        upper=upper_limit,
    )

    scores = (
        (clipped_values - lower_limit)
        / (upper_limit - lower_limit)
        * 100.0
    )

    return scores.clip(0, 100)


def build_delhi_density_grid(
    wards: gpd.GeoDataFrame,
    raster_path: Path,
) -> tuple[np.ndarray, rasterio.Affine]:
    """
    Crop the India WorldPop raster to Delhi and reproject
    it to a 100-metre Delhi calculation grid.
    """

    with rasterio.open(raster_path) as source:
        if source.crs is None:
            raise ValueError(
                "Population raster does not have a CRS."
            )

        if source.count != 1:
            raise ValueError(
                "Expected a single-band WorldPop raster."
            )

        wards_in_raster_crs = wards.to_crs(
            source.crs
        )

        delhi_geometry = (
            wards_in_raster_crs
            .geometry
            .union_all()
        )

        clipped_data, clipped_transform = mask(
            source,
            [mapping(delhi_geometry)],
            crop=True,
            filled=True,
            nodata=source.nodata,
        )

        source_density = clipped_data[0].astype(
            np.float32
        )

        source_nodata = source.nodata

        if source_nodata is None:
            source_nodata = -99999.0

            source_density[
                ~np.isfinite(source_density)
            ] = source_nodata

        source_height, source_width = (
            source_density.shape
        )

        left, bottom, right, top = array_bounds(
            source_height,
            source_width,
            clipped_transform,
        )

        (
            destination_transform,
            destination_width,
            destination_height,
        ) = calculate_default_transform(
            source.crs,
            TARGET_CRS,
            source_width,
            source_height,
            left,
            bottom,
            right,
            top,
            resolution=TARGET_RESOLUTION_METERS,
        )

        destination_density = np.full(
            (
                destination_height,
                destination_width,
            ),
            np.nan,
            dtype=np.float32,
        )

        reproject(
            source=source_density,
            destination=destination_density,
            src_transform=clipped_transform,
            src_crs=source.crs,
            src_nodata=source_nodata,
            dst_transform=destination_transform,
            dst_crs=TARGET_CRS,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )

    destination_density[
        destination_density < 0
    ] = np.nan

    return (
        destination_density,
        destination_transform,
    )


def calculate_population_exposure(
    ward_geojson: Path = WARD_GEOJSON,
    population_raster: Path = POPULATION_RASTER,
    output_csv: Path = OUTPUT_CSV,
    output_geojson: Path = OUTPUT_GEOJSON,
) -> gpd.GeoDataFrame:
    """
    Estimate population and population exposure for every
    Delhi ward.
    """

    # -----------------------------------------------------
    # Validate files
    # -----------------------------------------------------

    if not ward_geojson.exists():
        raise FileNotFoundError(
            "Processed ward file not found: "
            f"{ward_geojson}"
        )

    if not population_raster.exists():
        raise FileNotFoundError(
            "WorldPop raster not found: "
            f"{population_raster}"
        )

    # -----------------------------------------------------
    # Read ward polygons
    # -----------------------------------------------------

    wards = gpd.read_file(ward_geojson)

    required_columns = {
        "ward_id",
        "ward_name",
        "area_sq_km",
        "geometry",
    }

    missing_columns = required_columns.difference(
        wards.columns
    )

    if missing_columns:
        raise ValueError(
            "Processed ward file is missing columns: "
            f"{sorted(missing_columns)}"
        )

    if wards.empty:
        raise ValueError(
            "Processed ward file contains no wards."
        )

    if wards["ward_id"].duplicated().any():
        raise ValueError(
            "Processed ward file contains duplicate IDs."
        )

    print(
        f"Reading {len(wards)} processed Delhi wards."
    )

    print(
        "Preparing WorldPop density grid for Delhi..."
    )

    # -----------------------------------------------------
    # Prepare population density grid
    # -----------------------------------------------------

    (
        density_grid,
        density_transform,
    ) = build_delhi_density_grid(
        wards,
        population_raster,
    )

    wards_projected = wards.to_crs(
        TARGET_CRS
    )

    pixel_area_sq_km = abs(
        density_transform.a * density_transform.e
        - density_transform.b * density_transform.d
    ) / 1_000_000.0

    population_estimates = []
    valid_pixel_counts = []

    # -----------------------------------------------------
    # Calculate population inside every ward
    # -----------------------------------------------------

    for ward_geometry in wards_projected.geometry:
        inside_ward = geometry_mask(
            [mapping(ward_geometry)],
            out_shape=density_grid.shape,
            transform=density_transform,
            invert=True,
            all_touched=False,
        )

        valid_pixels = (
            inside_ward
            & np.isfinite(density_grid)
        )

        valid_count = int(
            valid_pixels.sum()
        )

        if valid_count == 0:
            population_estimates.append(0.0)
            valid_pixel_counts.append(0)
            continue

        estimated_population = float(
            np.sum(
                density_grid[valid_pixels],
                dtype=np.float64,
            )
            * pixel_area_sq_km
        )

        population_estimates.append(
            max(0.0, estimated_population)
        )

        valid_pixel_counts.append(
            valid_count
        )

    # -----------------------------------------------------
    # Create population features
    # -----------------------------------------------------

    wards["population_estimate_2020"] = np.rint(
        population_estimates
    ).astype("int64")

    ward_areas = pd.to_numeric(
        wards["area_sq_km"],
        errors="coerce",
    )

    wards[
        "population_density_per_sq_km"
    ] = (
        wards["population_estimate_2020"]
        / ward_areas
    ).round(2)

    # -----------------------------------------------------
    # Create exposure scores
    # -----------------------------------------------------

    wards["population_score"] = robust_score(
        wards["population_estimate_2020"]
    ).round(2)

    wards[
        "population_density_score"
    ] = robust_score(
        wards["population_density_per_sq_km"]
    ).round(2)

    # Density is more important for heat exposure because
    # it represents population concentration.
    wards["exposure_score"] = (
        0.40 * wards["population_score"]
        + 0.60
        * wards["population_density_score"]
    ).round(2)

    # -----------------------------------------------------
    # Add metadata
    # -----------------------------------------------------

    wards[
        "population_raster_valid_pixels"
    ] = valid_pixel_counts

    wards["population_year"] = POPULATION_YEAR

    wards[
        "population_source"
    ] = WORLDPOP_SOURCE

    wards[
        "population_license"
    ] = WORLDPOP_LICENSE

    wards["population_method"] = (
        "WorldPop 1km density reprojected to 100m; "
        "density integrated over ward area"
    )

    # -----------------------------------------------------
    # Final validation
    # -----------------------------------------------------

    zero_population = (
        wards["population_estimate_2020"] <= 0
    )

    if zero_population.any():
        failed_wards = wards.loc[
            zero_population,
            [
                "ward_id",
                "ward_name",
            ],
        ]

        raise ValueError(
            "Population could not be estimated for:\n"
            + failed_wards.to_string(index=False)
        )

    if not wards["exposure_score"].between(
        0,
        100,
    ).all():
        raise ValueError(
            "Exposure scores must remain between 0 and 100."
        )

    # -----------------------------------------------------
    # Save results
    # -----------------------------------------------------

    output_geojson.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_csv.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    wards.to_file(
        output_geojson,
        driver="GeoJSON",
        index=False,
    )

    wards.drop(
        columns="geometry"
    ).to_csv(
        output_csv,
        index=False,
    )

    # -----------------------------------------------------
    # Print summary
    # -----------------------------------------------------

    total_population = int(
        wards["population_estimate_2020"].sum()
    )

    print()
    print(
        f"Processed wards: {len(wards)}"
    )

    print(
        "Estimated Delhi population "
        f"({POPULATION_YEAR}): "
        f"{total_population:,}"
    )

    print(
        "Minimum ward estimate: "
        f"{wards['population_estimate_2020'].min():,}"
    )

    print(
        "Maximum ward estimate: "
        f"{wards['population_estimate_2020'].max():,}"
    )

    print(
        f"Saved population table: {output_csv}"
    )

    print(
        f"Saved population GeoJSON: "
        f"{output_geojson}"
    )

    return wards


def main() -> None:
    calculate_population_exposure()


if __name__ == "__main__":
    main()