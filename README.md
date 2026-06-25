# green-condor

Fresh coordination workspace for a global energy modelling tool with a Phaser front end.

This repository is intentionally thin. The active source material now lives in symlinked sibling projects:

- `green-lory/`: weather fetching, ammonia model, and related notebooks.
- `green-caribou-paper/`: filtered symlink view of the paper repo and mathematical model, without its nested `pypsa-earth-green-auklet` link.
- `pypsa-earth-green-auklet/`: PyPSA-Earth-based system model scaffolding.

## Purpose of this repo now

`green-condor` should become the integration layer where we:

1. distill reusable model kernels from the linked projects;
2. define common data contracts for geography, weather, technologies, and scenarios;
3. prototype an interactive global energy modelling interface in Phaser.

The current default assumption is:

- Python for the model core
- Phaser for the interactive front end
- browser-first deployment, with server-side preprocessing where needed

See `DEVELOPMENT_NOTES.md` for the archive record, data strategy, and delivery plan.
