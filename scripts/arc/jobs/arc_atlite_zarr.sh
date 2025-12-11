#!/bin/bash
#SBATCH --job-name=atlite-zarr
#SBATCH --partition=long
#SBATCH --nodes=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=240G
#SBATCH --time=72:00:00
#SBATCH --output=slurm-%j.out
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=carlo.palazzi@eng.ox.ac.uk
## Uncomment for job arrays / latitudinal tiling
## #SBATCH --array=0-3

set -euo pipefail

: "${DATA:=/data/engs-df-green-ammonia/${USER}}"
: "${SCRATCH:=/scratch/${USER}}"

if [[ -z "${BASH_VERSION:-}" ]]; then
  echo "This script requires bash" >&2
  exit 2
fi
. /etc/profile.d/00-modulepath.sh 2>/dev/null || true
if ! command -v module >/dev/null 2>&1; then
  if [[ -f /etc/profile.d/modules.sh ]]; then
    source /etc/profile.d/modules.sh
  elif [[ -f /usr/share/Modules/init/bash ]]; then
    source /usr/share/Modules/init/bash
  fi
fi

ANACONDA_MODULE="${ANACONDA_MODULE:-Anaconda3/2023.09}"
CONDA_TOOLS_ENV="${CONDA_TOOLS_ENV:-/data/engs-df-green-ammonia/${USER}/envs/conda-tools}"
MICROMAMBA_BIN="${MICROMAMBA_BIN:-micromamba}"
ENV_PREFIX="${ENV_PREFIX:-$DATA/envs/green-condor-env}"
CUTOUT_PATH="${CUTOUT_PATH:-$DATA/green-condor/data/global_cutout_2019.nc}"
OUTPUT_ZARR="${OUTPUT_ZARR:-$SCRATCH/green-condor/global_cf_2019.zarr}"
TIME_CHUNK="${TIME_CHUNK:-168}"
Y_CHUNK="${Y_CHUNK:-180}"
X_CHUNK="${X_CHUNK:-180}"
OVERWRITE_FLAG="${OVERWRITE:-false}"

module purge
module load "${ANACONDA_MODULE}"
source activate "${CONDA_TOOLS_ENV}"
eval "$("${MICROMAMBA_BIN}" shell hook --shell bash)"
micromamba activate "${ENV_PREFIX}"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
cd "${SLURM_SUBMIT_DIR}"

mkdir -p "$(dirname "${OUTPUT_ZARR}")"

CMD=("python" "scripts/arc/run_atlite_to_zarr.py"
  "--cutout" "${CUTOUT_PATH}"
  "--output" "${OUTPUT_ZARR}"
  "--time-chunk" "${TIME_CHUNK}"
  "--target-chunk-y" "${Y_CHUNK}"
  "--target-chunk-x" "${X_CHUNK}"
)

if [[ "${OVERWRITE_FLAG}" == "true" ]]; then
  CMD+=("--overwrite")
fi

"${CMD[@]}"