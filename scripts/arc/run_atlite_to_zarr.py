#!/usr/bin/env python3
"""Headless driver that converts an atlite cutout into a multi-layer Zarr store."""

from __future__ import annotations

import argparse
import gc
import sys
from pathlib import Path

import atlite
import geopandas as gpd
import geodatasets
import numpy as np
import xarray as xr
import zarr
from shapely.ops import unary_union

DEFAULT_TIME_CHUNK = 168
DEFAULT_SPATIAL_CHUNK = 180
DEFAULT_LAT_TILES = 1
DEFAULT_LAT_ROWS = 0

WIND_ONSHORE = "Vestas_V112_3MW"
WIND_OFFSHORE = "NREL_ReferenceTurbine_5MW_offshore"
SOLAR_PANEL = "CSi"
REQUIRED_FEATURES = ["influx", "wind", "temperature", "height"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutout", required=True, help="Path to the prepared atlite cutout (NetCDF).")
    parser.add_argument("--output", required=True, help="Target Zarr store path.")
    parser.add_argument("--time-chunk", type=int, default=DEFAULT_TIME_CHUNK, help="Dask chunk size along time.")
    parser.add_argument("--target-chunk-y", type=int, default=DEFAULT_SPATIAL_CHUNK, help="Chunk size along latitude.")
    parser.add_argument("--target-chunk-x", type=int, default=DEFAULT_SPATIAL_CHUNK, help="Chunk size along longitude.")
    parser.add_argument("--overwrite", action="store_true", help="Delete any existing Zarr store before writing.")
    parser.add_argument("--skip-prepare", action="store_true", help="Assume the cutout already contains all required features.")
    parser.add_argument(
        "--lat-tiles",
        type=int,
        default=DEFAULT_LAT_TILES,
        help="Split the latitude dimension into this many sequential tiles to reduce peak memory.",
    )
    parser.add_argument(
        "--lat-rows-per-tile",
        type=int,
        default=DEFAULT_LAT_ROWS,
        help="Explicitly set the number of latitude rows per tile. Overrides --lat-tiles when > 0.",
    )
    parser.add_argument(
        "--lat-step-deg",
        type=float,
        default=None,
        help="If provided, derive tile height in degrees (e.g. 0.25 for single-row tiles).",
    )
    parser.add_argument(
        "--prepare-per-tile",
        action="store_true",
        help="If set, run cutout.prepare separately for each latitude tile instead of once globally.",
    )
    parser.add_argument(
        "--tile-start-index",
        type=int,
        default=0,
        help="Zero-based index of the first latitude tile to process.",
    )
    parser.add_argument(
        "--tile-count",
        type=int,
        default=0,
        help="If >0, only process this many tiles starting from --tile-start-index.",
    )
    return parser.parse_args()


def build_onshore_mask(cutout: atlite.Cutout, chunk_y: int, chunk_x: int) -> xr.DataArray:
    land_geom = unary_union(gpd.read_file(geodatasets.get_path("naturalearth_land")).geometry)
    grid = cutout.grid.reset_index(drop=True)
    grid["is_onshore"] = grid.geometry.centroid.within(land_geom)
    mask_table = (
        grid.set_index(["y", "x"])["is_onshore"]
        .unstack("x")
        .reindex(index=cutout.coords["y"], columns=cutout.coords["x"])
        .fillna(False)
    )
    return xr.DataArray(
        mask_table.values.astype(bool),
        coords={"y": cutout.coords["y"], "x": cutout.coords["x"]},
        dims=("y", "x"),
        name="is_onshore",
    ).chunk({"y": chunk_y, "x": chunk_x})


def compute_capacity_factors(
    cutout: atlite.Cutout,
    onshore_mask: xr.DataArray,
    chunk_t: int,
    chunk_y: int,
    chunk_x: int,
) -> tuple[xr.DataArray, xr.DataArray]:
    cf_wind_on = cutout.wind(
        turbine=WIND_ONSHORE,
        capacity_factor_timeseries=True,
    ).rename("cf_wind_on")
    cf_wind_off = cutout.wind(
        turbine=WIND_OFFSHORE,
        capacity_factor_timeseries=True,
    ).rename("cf_wind_off")
    cf_wind = xr.where(onshore_mask, cf_wind_on, cf_wind_off).rename("cf_wind")
    cf_wind = cf_wind.chunk({"time": chunk_t, "y": chunk_y, "x": chunk_x})

    cf_solar = cutout.pv(
        panel=SOLAR_PANEL,
        orientation="latitude_optimal",
        tracking=None,
        capacity_factor_timeseries=True,
    ).rename("cf_solar")
    cf_solar = cf_solar.where(onshore_mask, 0.0)
    cf_solar = cf_solar.chunk({"time": chunk_t, "y": chunk_y, "x": chunk_x})

    return cf_wind, cf_solar


def assemble_dataset(cf_wind: xr.DataArray, cf_solar: xr.DataArray, mask: xr.DataArray) -> xr.Dataset:
    ds = xr.Dataset(
        data_vars={
            "cf_wind": cf_wind.astype("float32"),
            "cf_solar": cf_solar.astype("float32"),
            "is_onshore": mask.astype("int8"),
        }
    )
    ds["cf_wind"].attrs.update(
        {
            "long_name": "Wind capacity factor",
            "onshore_turbine": WIND_ONSHORE,
            "offshore_turbine": WIND_OFFSHORE,
        }
    )
    ds["cf_solar"].attrs.update({"long_name": "Solar PV capacity factor", "panel": SOLAR_PANEL})
    ds["is_onshore"].attrs.update({"long_name": "1 if the grid cell centroid lies on land"})

    ds.attrs.update(
        {
            "tool": "green-condor",
            "generation_note": (
                "Capacity factors computed with atlite using "
                f"{WIND_ONSHORE}/{WIND_OFFSHORE} turbines and {SOLAR_PANEL} panels."
            ),
        }
    )
    source_attr = cf_wind.encoding.get("source")
    if source_attr:
        ds.attrs["cutout_source"] = str(source_attr)
    return ds


def build_latitude_slices(
    cutout: atlite.Cutout,
    tile_count: int,
    rows_per_tile: int,
    step_deg: float | None,
) -> list[tuple[float, float]]:
    y_values = cutout.data.coords["y"].values
    if y_values.size == 0:
        return []

    effective_rows = rows_per_tile if rows_per_tile > 0 else 0
    if step_deg is not None:
        if step_deg <= 0:
            raise ValueError("lat-step-deg must be > 0")
        if y_values.size == 1:
            effective_rows = 1
        else:
            cell_height = abs(float(y_values[1] - y_values[0]))
            if cell_height == 0:
                raise ValueError("Cannot infer latitude resolution from cutout coordinates")
            effective_rows = max(1, int(round(step_deg / cell_height)))

    if effective_rows > 0:
        slices: list[tuple[float, float]] = []
        for start in range(0, y_values.size, effective_rows):
            chunk = y_values[start : start + effective_rows]
            slices.append((float(chunk[0]), float(chunk[-1])))
        return slices

    if tile_count < 1:
        raise ValueError("lat-tiles must be >= 1")

    chunks = np.array_split(y_values, tile_count)
    slices = []
    for chunk in chunks:
        if chunk.size == 0:
            continue
        slices.append((float(chunk[0]), float(chunk[-1])))
    return slices


def main() -> None:
    args = parse_args()

    cutout_path = Path(args.cutout)
    if not cutout_path.exists():
        raise FileNotFoundError(cutout_path)

    cutout = atlite.Cutout(path=cutout_path)
    if args.skip_prepare:
        print("Skipping cutout.prepare per --skip-prepare flag.", file=sys.stderr, flush=True)
    elif args.prepare_per_tile:
        print(
            "Will run cutout.prepare independently for each latitude tile.",
            file=sys.stderr,
            flush=True,
        )
    else:
        print("Preparing entire cutout before tiling...", file=sys.stderr, flush=True)
        cutout.prepare(features=REQUIRED_FEATURES, monthly_requests=True)
        print("Finished preparing entire cutout.", file=sys.stderr, flush=True)

    output_path = Path(args.output)
    if output_path.exists():
        if args.overwrite:
            import shutil

            shutil.rmtree(output_path)
        else:
            raise FileExistsError(output_path)

    lat_slices = build_latitude_slices(cutout, args.lat_tiles, args.lat_rows_per_tile, args.lat_step_deg)
    total_tiles = len(lat_slices)
    if total_tiles == 0:
        print("No latitude tiles detected for the current cutout.", file=sys.stderr)
        return

    start_idx = args.tile_start_index
    if start_idx < 0 or start_idx >= total_tiles:
        raise ValueError(f"tile-start-index {start_idx} is outside [0, {total_tiles - 1}]")

    lat_slices = lat_slices[start_idx:]
    if args.tile_count > 0:
        lat_slices = lat_slices[: args.tile_count]

    if not lat_slices:
        print("Tile selection resulted in zero latitude tiles to process.", file=sys.stderr)
        return

    selection_size = len(lat_slices)
    global_offset = start_idx
    full_mask = build_onshore_mask(cutout, args.target_chunk_y, args.target_chunk_x)
    prepare_each_tile = args.prepare_per_tile and not args.skip_prepare
    for local_idx, (y_start, y_stop) in enumerate(lat_slices, start=1):
        global_idx = global_offset + local_idx
        print(
            f"Processing latitude tile {global_idx}/{total_tiles} "
            f"(batch tile {local_idx}/{selection_size}): "
            f"y in [{y_start:.2f}, {y_stop:.2f}]",
            file=sys.stderr,
            flush=True,
        )
        tile_cutout = cutout.sel(y=slice(y_start, y_stop))
        if prepare_each_tile:
            print(
                f"Preparing features for batch tile {local_idx}/{selection_size}...",
                file=sys.stderr,
                flush=True,
            )
            tile_cutout.prepare(features=REQUIRED_FEATURES, monthly_requests=True)
        mask = full_mask.sel(y=slice(y_start, y_stop))
        cf_wind, cf_solar = compute_capacity_factors(
            tile_cutout,
            mask,
            args.time_chunk,
            args.target_chunk_y,
            args.target_chunk_x,
        )
        dataset = assemble_dataset(cf_wind, cf_solar, mask)

        mode = "w" if local_idx == 1 else "a"
        to_zarr_kwargs: dict[str, object] = {"mode": mode, "consolidated": False}
        if mode == "a":
            to_zarr_kwargs["append_dim"] = "y"
        dataset.to_zarr(output_path, **to_zarr_kwargs)

        del dataset, mask, cf_wind, cf_solar
        gc.collect()

    zarr.consolidate_metadata(str(output_path))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
