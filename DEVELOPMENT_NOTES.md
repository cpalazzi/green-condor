# Development notes

## Starting point

- `green-lory` holds the strongest current implementation for weather ingestion and the ammonia workflow.
- `green-caribou-paper` holds the stronger mathematical framing and analysis.
- `pypsa-earth-green-auklet` holds broader power-system structure and data conventions.
- `green-condor` now serves as the integration workspace where those threads are unified into a single interactive tool.

## Archive record

The legacy `green-condor` weather archive now lives at:

- `/Users/carlopalazzi/programming/pypsa_models/green-lory/data/weather_data/archive/green-condor_global_cutout_2019/`

That archive contains:

- `global_cutout_2019.nc`
- `001_get_weather.ipynb`
- `README.green-condor.md`
- `scripts/` containing the ARC environment and batch workflow

The archive remains local and untracked because it sits under `green-lory/data/`.

## Working assumptions

- Keep heavy datasets outside this repo and reference them by path or symlink.
- Build the simulation core in Python so we can reuse the existing scientific stack.
- Use Phaser as the default frontend because the current target is a browser-first 2D pixel-art globe/map rather than a full 3D engine.
- Treat the frontend as a control and visualization layer, not as the place where heavy weather processing happens.
- Start with deterministic scenario playback and coarse heuristics before attempting large-scale optimisation in the UI loop.

## Target product

An interactive global energy modelling tool where a user can:

- inspect resource quality, land availability, and infrastructure constraints on a pixel-art globe or projected world map;
- place demand points with time series;
- place or remove generation, storage, ammonia, conversion, and transmission assets;
- run a scenario and see system costs, energy balances, trade flows, and emissions implications;
- compare multiple world-building choices without dropping into raw notebooks.

## Proposed architecture

### 1. Data layer

- Global weather and derived resource layers from `green-lory`
- Static geographic layers from `pypsa-earth-green-auklet`
- Economic and technology assumptions distilled from `green-caribou-paper` and other model inputs
- Cached, pre-derived frontend tiles and scenario payloads produced from the Python backend

### 2. Model kernel layer

- Resource kernel: weather to capacity factors
- Siting kernel: land, bathymetry, exclusions, and distance constraints
- Conversion kernel: electrolysis, ammonia, storage, and reconversion chains
- Network kernel: transmission and shipping abstractions
- Accounting kernel: capex, opex, dispatch summaries, and objective metrics

### 3. Interface layer

- Phaser scene graph for the map, sprites, links, and overlays
- HTML/TypeScript side panels for scenario editing, time-series charts, and inspection
- interaction modes for place, connect, run, compare, and inspect

## Weather data strategy

### Principle

- Do not stream full raw weather cubes into the browser.
- Stream only what the frontend needs for interaction: precomputed summaries, tiles, sampled time series, and scenario results.
- Keep raw weather access in Python services or preprocessing jobs.

### Preferred deployment path

- Primary public source: Google Cloud public ARCO ERA5 Zarr.
- Primary access pattern: backend or worker jobs open Zarr directly from public cloud and derive energy-specific products.
- Browser payloads should be reduced products such as:
  - capacity-factor tiles by technology and month
  - point or region time series for selected coordinates
  - scenario-ready aggregates for transmission, storage, and conversion logic

### Why Google first

- Google Cloud documents ARCO ERA5 as a public dataset with hourly atmospheric, land, and oceanic variables from 1979 to present.
- The ARCO ERA5 repository documents concrete anonymous Zarr access patterns, stable bucket naming, monthly stable updates, and separate analysis-ready (`ar/`) versus cloud-optimized (`co/`) stores.
- This makes it the cleanest target for an MVP backend.

### AWS role

- Keep AWS as a supported secondary source rather than the default.
- AWS has public ERA5 options too, including the AWS Registry ERA5 listing and a separate `planette-era5` Zarr archive.
- Those sources do not look as cleanly documented for our intended analysis-ready workflow as Google ARCO ERA5, so they should be supported through adapters rather than treated as the canonical first implementation.
- We should treat AWS support as an adapter layer, not as the canonical source for the first build.

### Consequence for our stack

- Backend weather adapters should hide source details behind one interface:
  - `get_weather_timeseries(lat, lon, variables, window)`
  - `get_resource_summary(cell_ids, techs, window)`
  - `build_capacity_factor_cube(bounds, tech, window)`
- Derived outputs should be cached locally or in object storage so repeated runs do not hammer public stores.

## Product slices

### Slice A: map sandbox

- Render the world map in Phaser.
- Show demand points, production points, transmission links, and storage nodes.
- Support selecting nodes and links and inspecting their state.

### Slice B: scenario semantics

- Define a common scenario JSON schema.
- Support demand profiles, technology configs, transmission configs, and storage configs.
- Load and save scenarios without notebooks.

### Slice C: simulation kernel

- Run a simplified hourly simulation for one scenario.
- Produce time-series outputs and summary metrics.
- Defer full optimisation until the data contracts are stable.

### Slice D: resource backend

- Expose weather- and resource-derived products through a thin API or job runner.
- Allow switching between local cache, archived local files, and public-cloud ERA5-backed derivation.

## Phase plan

### Phase 0: inventory and contracts

- Identify the canonical files and notebooks in each linked project.
- Pull out the minimum shared input/output contracts.
- Write down where the current methods disagree.
- Decide which existing calculations are authoritative for:
  - weather ingestion
  - technology parameters
  - ammonia chain logic
  - transmission/network abstractions

### Phase 1: define the common schema

- Choose the base spatial unit: grid cell, region, or hybrid.
- Define canonical weather, technology, and scenario schemas.
- Decide what stays time-series rich and what gets aggregated.
- Define the frontend-facing entities:
  - demand node
  - production node
  - conversion node
  - storage node
  - transmission edge

### Phase 2: build a thin Python core

- Wrap the reusable kernels behind a small package API.
- Make one reproducible end-to-end scenario run from inputs to summary outputs.
- Keep outputs engine-friendly: JSON for metadata, Parquet/Zarr for arrays.
- Add a weather-source abstraction with:
  - local archived files
  - local derived caches
  - public GCS ARCO ERA5
  - optional AWS adapter later

### Phase 3: build the first Phaser prototype

- Render a pixel-art globe or projected world map in Phaser.
- Load one scenario, one set of resource overlays, and one summary panel.
- Support a minimal edit-run-view loop.
- Keep charts and forms outside the canvas where that is simpler.

### Phase 4: extend scope carefully

- Add transmission and trade interactions.
- Add ammonia chain detail where it changes system behaviour materially.
- Add scenario comparison, save/load, and calibration workflows.

## Immediate next tasks

### This week

- Inventory reusable code in the three linked projects.
- Decide the MVP spatial abstraction.
- Define one narrow end-to-end use case for the first interactive prototype.
- Decide the first backend weather variables we actually need.

### Next build step

- Create a small Python package in `green-condor` for shared contracts and adapters.
- Add a Phaser app shell with one map scene and one side-panel layout.
- Implement one weather-backed example scenario end to end.

### First demonstrator

- One region or small global subset
- Demand nodes with hourly demand profiles
- Wind, solar, storage, and one conversion chain
- Transmission links between a small number of nodes
- Run button producing hourly balance and headline cost metrics

## Open questions

- What is the MVP resolution: global regions, coarse grid cells, or a mixed representation?
- Should the first web build call Python through a local service, serverless jobs, or precomputed files?
- Which outputs need optimisation, and which can use fast heuristics in the first version?
- How much of the ammonia detail belongs in the MVP versus a later advanced mode?
- Do we want a true spherical globe, or a stylized projected map that reads as a globe?
- Which ERA5-derived variables should be canonical for wind, solar, and demand shaping?

## Source notes for public weather access

- Google Cloud public datasets list ARCO ERA5 as a public dataset with data from 1979 to present:
  - <https://cloud.google.com/storage/docs/public-datasets>
- The ARCO ERA5 repository documents anonymous Zarr access, bucket layout, update cadence, and sample paths:
  - <https://github.com/google-research/arco-era5>
- ECMWF describes its Data Stores ARCO data lake as Zarr-based:
  - <https://www.ecmwf.int/en/newsletter/183/news/dawn-new-era-explorer>
- AWS public ERA5 entries relevant to adapters:
  - <https://registry.opendata.aws/ecmwf-era5/>
  - <https://registry.opendata.aws/planette_era5_reanalysis/>
