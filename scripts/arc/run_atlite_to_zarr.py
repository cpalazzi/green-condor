#!/usr/bin/env python3
"""Headless driver that converts an atlite cutout into a multi-layer Zarr store."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import atlite
import geopandas as gpd
import geodatasets
import xarray as xr
from shapely.ops import unary_union

DEFAULT_TIME_CHUNK = 168
DEFAULT_SPATIAL_CHUNK = 180

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
        capacity_factor=True,
        per_unit=True,
    )
    cf_wind_off = cutout.wind(
        turbine=WIND_OFFSHORE,
        capacity_factor=True,
        per_unit=True,
    )
    cf_wind = xr.where(onshore_mask, cf_wind_on, cf_wind_off).rename("cf_wind")
    cf_wind = cf_wind.chunk({"time": chunk_t, "y": chunk_y, "x": chunk_x})

    cf_solar = cutout.pv(
        panel=SOLAR_PANEL,
        orientation="latitude_optimal",
        tracking=None,
        capacity_factor=True,
        per_unit=True,
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
    ds.attrs.update({"tool": "green-condor", "source": Path(cf_wind.encoding.get("source", "cutout"))})
    return ds


def main() -> None:
    args = parse_args()

    cutout_path = Path(args.cutout)
    if not cutout_path.exists():
        raise FileNotFoundError(cutout_path)

    cutout = atlite.Cutout(path=cutout_path)
    if not args.skip_prepare:
        cutout.prepare(features=REQUIRED_FEATURES, monthly_requests=True)

    mask = build_onshore_mask(cutout, args.target_chunk_y, args.target_chunk_x)
    cf_wind, cf_solar = compute_capacity_factors(
        cutout,
        mask,
        args.time_chunk,
        args.target_chunk_y,
        args.target_chunk_x,
    )
    dataset = assemble_dataset(cf_wind, cf_solar, mask)

    output_path = Path(args.output)
    if output_path.exists():
        if args.overwrite:
            import shutil

            shutil.rmtree(output_path)
        else:
            raise FileExistsError(output_path)

    dataset.to_zarr(output_path, mode="w", consolidated=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
