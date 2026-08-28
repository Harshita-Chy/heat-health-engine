from pathlib import Path

import geopandas as gpd
import pandas as pd


# ---------------------------------------------------------
# Input and output paths
# ---------------------------------------------------------

INPUT_GEOJSON = Path("data/delhi_wards.geojson")

OUTPUT_DIRECTORY = Path("data/processed")

OUTPUT_GEOJSON = (
    OUTPUT_DIRECTORY / "delhi_wards_processed.geojson"
)

OUTPUT_CSV = (
    OUTPUT_DIRECTORY / "delhi_ward_locations.csv"
)


# ---------------------------------------------------------
# Dataset metadata
# ---------------------------------------------------------

DATASET_SOURCE = "https://bharatlas.com/view/wards_delhi"
DATASET_LICENSE = "CC-BY-SA-4.0"
DATASET_SNAPSHOT_DATE = "2026-05-26"


def clean_text(value: object) -> str:
    """
    Convert missing values to an empty string and remove
    unnecessary spaces from existing text values.
    """

    if pd.isna(value):
        return ""

    return str(value).strip()


def prepare_delhi_wards(
    input_path: Path = INPUT_GEOJSON,
    output_geojson: Path = OUTPUT_GEOJSON,
    output_csv: Path = OUTPUT_CSV,
) -> gpd.GeoDataFrame:
    """
    Read, validate and process Delhi ward boundaries.
    """

    print(f"Reading Delhi ward boundaries: {input_path}")

    # -----------------------------------------------------
    # Check input file
    # -----------------------------------------------------

    if not input_path.exists():
        raise FileNotFoundError(
            f"Boundary file not found: {input_path}\n"
            "Place delhi_wards.geojson inside the data folder."
        )

    # -----------------------------------------------------
    # Read GeoJSON
    # -----------------------------------------------------

    wards = gpd.read_file(input_path)

    print(f"Raw polygons found: {len(wards)}")

    if wards.empty:
        raise ValueError(
            "The Delhi ward GeoJSON contains no records."
        )

    # -----------------------------------------------------
    # Validate required columns
    # -----------------------------------------------------

    required_columns = {
        "Ward_No",
        "Ward_Name",
        "geometry",
    }

    missing_columns = required_columns.difference(
        wards.columns
    )

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            f"{sorted(missing_columns)}"
        )

    # -----------------------------------------------------
    # Validate geometry
    # -----------------------------------------------------

    if wards.geometry.isna().any():
        raise ValueError(
            "Some ward records do not contain geometry."
        )

    if wards.geometry.is_empty.any():
        raise ValueError(
            "Some ward records contain empty geometry."
        )

    wards = wards.copy()

    # -----------------------------------------------------
    # Clean ward IDs and ward names
    # -----------------------------------------------------

    wards["Ward_No"] = wards["Ward_No"].map(
        clean_text
    )

    wards["Ward_Name"] = wards["Ward_Name"].map(
        clean_text
    )

    # -----------------------------------------------------
    # Handle missing Ward_No
    # -----------------------------------------------------

    missing_id_mask = wards["Ward_No"].eq("")

    if missing_id_mask.any():
        missing_indices = wards.index[
            missing_id_mask
        ].tolist()

        print(
            f"Found {len(missing_indices)} "
            "polygon(s) without Ward_No."
        )

        for sequence, row_index in enumerate(
            missing_indices,
            start=1,
        ):
            generated_id = (
                f"UNNUMBERED_{sequence:03d}"
            )

            wards.at[
                row_index,
                "Ward_No",
            ] = generated_id

            print(
                f"Assigned internal ward ID: "
                f"{generated_id}"
            )

    # -----------------------------------------------------
    # Handle missing Ward_Name
    # -----------------------------------------------------

    missing_name_mask = wards["Ward_Name"].eq("")

    if missing_name_mask.any():
        missing_indices = wards.index[
            missing_name_mask
        ].tolist()

        print(
            f"Found {len(missing_indices)} "
            "polygon(s) without Ward_Name."
        )

        for row_index in missing_indices:
            ward_id = wards.at[
                row_index,
                "Ward_No",
            ]

            generated_name = (
                f"Unnamed Boundary ({ward_id})"
            )

            wards.at[
                row_index,
                "Ward_Name",
            ] = generated_name

            print(
                f"Assigned internal ward name: "
                f"{generated_name}"
            )

    # -----------------------------------------------------
    # Rename columns to project-standard names
    # -----------------------------------------------------

    wards = wards.rename(
        columns={
            "Ward_No": "ward_id",
            "Ward_Name": "ward_name",
        }
    )

    # -----------------------------------------------------
    # Confirm ward IDs are unique
    # -----------------------------------------------------

    duplicate_id_mask = wards[
        "ward_id"
    ].duplicated(keep=False)

    if duplicate_id_mask.any():
        duplicate_ids = sorted(
            wards.loc[
                duplicate_id_mask,
                "ward_id",
            ]
            .unique()
            .tolist()
        )

        raise ValueError(
            f"Duplicate ward IDs found: {duplicate_ids}"
        )

    # -----------------------------------------------------
    # Set coordinate reference system
    # -----------------------------------------------------

    if wards.crs is None:
        print(
            "CRS missing. Treating coordinates as EPSG:4326."
        )

        wards = wards.set_crs(epsg=4326)

    else:
        wards = wards.to_crs(epsg=4326)

    # -----------------------------------------------------
    # Repair invalid geometries, if present
    # -----------------------------------------------------

    invalid_geometry_mask = ~wards.geometry.is_valid

    if invalid_geometry_mask.any():
        invalid_count = int(
            invalid_geometry_mask.sum()
        )

        print(
            f"Repairing {invalid_count} invalid geometries."
        )

        repaired_geometry = (
            wards.loc[
                invalid_geometry_mask
            ]
            .geometry
            .make_valid()
        )

        wards.loc[
            invalid_geometry_mask,
            "geometry",
        ] = repaired_geometry

    if (~wards.geometry.is_valid).any():
        raise ValueError(
            "Some geometries remain invalid after repair."
        )

    # -----------------------------------------------------
    # Calculate ward areas
    # -----------------------------------------------------
    # EPSG:32643 is UTM Zone 43N, suitable for Delhi.
    # Geographic coordinates cannot calculate area correctly,
    # so geometry is temporarily projected.
    # -----------------------------------------------------

    projected_wards = wards.to_crs(epsg=32643)

    area_sq_km = (
        projected_wards.geometry.area
        / 1_000_000.0
    )

    # -----------------------------------------------------
    # Calculate ward centroids
    # -----------------------------------------------------

    projected_centroids = (
        projected_wards.geometry.centroid
    )

    centroid_locations = gpd.GeoSeries(
        projected_centroids,
        index=projected_wards.index,
        crs=projected_wards.crs,
    ).to_crs(epsg=4326)

    wards["area_sq_km"] = area_sq_km.round(4)

    wards["centroid_lat"] = (
        centroid_locations.y.round(6)
    )

    wards["centroid_lon"] = (
        centroid_locations.x.round(6)
    )

    # -----------------------------------------------------
    # Add dataset provenance
    # -----------------------------------------------------

    wards["data_source"] = DATASET_SOURCE

    wards["snapshot_date"] = (
        DATASET_SNAPSHOT_DATE
    )

    wards["license"] = DATASET_LICENSE

    # -----------------------------------------------------
    # Validate calculated output
    # -----------------------------------------------------

    if wards["area_sq_km"].isna().any():
        raise ValueError(
            "Some ward areas could not be calculated."
        )

    if (wards["area_sq_km"] <= 0).any():
        raise ValueError(
            "Some calculated ward areas are zero or negative."
        )

    if wards["centroid_lat"].isna().any():
        raise ValueError(
            "Some centroid latitudes are missing."
        )

    if wards["centroid_lon"].isna().any():
        raise ValueError(
            "Some centroid longitudes are missing."
        )

    # -----------------------------------------------------
    # Select final output columns
    # -----------------------------------------------------

    output_columns = [
        "ward_id",
        "ward_name",
        "area_sq_km",
        "centroid_lat",
        "centroid_lon",
        "data_source",
        "snapshot_date",
        "license",
        "geometry",
    ]

    wards = wards[output_columns]

    wards = wards.sort_values(
        by=[
            "ward_id",
            "ward_name",
        ]
    ).reset_index(drop=True)

    # -----------------------------------------------------
    # Create output directory
    # -----------------------------------------------------

    output_geojson.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_csv.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -----------------------------------------------------
    # Save processed GeoJSON
    # -----------------------------------------------------

    wards.to_file(
        output_geojson,
        driver="GeoJSON",
        index=False,
    )

    # -----------------------------------------------------
    # Save ward location CSV without geometry
    # -----------------------------------------------------

    ward_locations = wards.drop(
        columns="geometry"
    )

    ward_locations.to_csv(
        output_csv,
        index=False,
    )

    # -----------------------------------------------------
    # Print final results
    # -----------------------------------------------------

    print()
    print(
        f"Processed ward polygons: {len(wards)}"
    )

    print(
        "Unique ward IDs: "
        f"{wards['ward_id'].nunique()}"
    )

    print(
        "Total mapped area: "
        f"{wards['area_sq_km'].sum():.2f} sq. km"
    )

    print(
        f"Saved GeoJSON: {output_geojson}"
    )

    print(
        f"Saved ward table: {output_csv}"
    )

    return wards


def main() -> None:
    prepare_delhi_wards()


if __name__ == "__main__":
    main()