# green-condor workflows

This repository hosts lightweight notebooks for generating hourly renewable resource datasets that can feed Calliope or PyPSA-style power system models. The plan is to keep each stage isolated and reproducible:

1. **Power dataset (current notebook: `001_get_weather.ipynb`)** – prepare ERA5 cutouts with atlite, compute hourly capacity-factor (CF) cubes for wind (on/offshore) and solar at grid-cell resolution, and store them efficiently (Zarr/GeoParquet).
2. **Land-use & siting constraints (future notebook)** – derive land/sea masks, slope, bathymetry, protected-area exclusions, and distance-to-shore layers. Output standardized GeoParquet files for later joins.
3. **Model integration (future notebook)** – transform the CF dataset plus siting layers into Calliope or PyPSA inputs (per-region availability profiles, generator definitions, cost assumptions) to estimate LCOE/LCOH/LCOA.

## Power dataset workflow

The power notebook now contains reusable utilities for:

- Declaring technology specs (`TECH_SPECS`) for wind onshore/offshore and solar PV, including turbine/panel parameters and land masks.
- Building 1 kW layouts per grid cell (`unit_layout`) and evaluating hourly CFs via `atlite.Cutout.wind` / `.pv`.
- Concatenating multiple technology CFs into an `xarray.Dataset` with a `technology` dimension (`build_cf_dataset`).
- Chunking and persisting the dataset to Zarr (`store_cf_zarr`) so downstream tools can stream time-slices without loading everything into memory.
- Exporting GeoParquet/CSV summaries (`outputs/sample_region_cf.geo.parquet`, `sample_region_cf_summary.csv`) for the sample test region.

### How to run

1. Execute the cutout preparation cell (already configured for global 2019 ERA5 at 0.25°).
2. Run the sample-region cells to sanity-check outputs and populate `outputs/sample_region_cf.*` artifacts.
3. Set `run_full = True` in the utilities cell once you are ready for the global evaluation, optionally bringing up a Dask client sized to your machine.
4. After completion, you will have `outputs/global_2019_cf.zarr` with hourly CF per technology and grid cell.

### TODO

- [ ] Add a notebook cell that aggregates CFs over arbitrary polygons (countries, EEZ, ISO regions) and writes region-level averages for Calliope/PyPSA inputs.
- [ ] Encode compression (e.g., Zarr + Zstd) and metadata (attrs describing turbines/panels) before writing the global dataset.
- [ ] Provide helper scripts to convert the Zarr CF dataset into per-technology Parquet/CSV tables consumable by Calliope (`timeseries_data_path`) and PyPSA (`generators_p_set`).
- [ ] Mirror the Dask/Zarr pattern in the forthcoming land-use notebook so constraints align 1:1 with grid cells.

Feel free to extend the README as future notebooks come online.
