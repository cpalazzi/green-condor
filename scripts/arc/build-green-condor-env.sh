#!/bin/bash
# Environment bootstrap for Oxford ARC (see Submission Script Basics in the ARC user guide).
set -euo pipefail

MODULE_NAME="${MINICONDA_MODULE:-Miniconda3/23.5.2-0}"
ENV_NAME="${ENV_NAME:-green-condor-env}"
ENV_PREFIX="${ENV_PREFIX:-$DATA/conda-envs/${ENV_NAME}}"
ENV_FILE="$(dirname "$0")/environment_arc.yaml"

module purge
module load "${MODULE_NAME}"

source "$(conda info --base)/etc/profile.d/conda.sh"

if [[ ! -d "${ENV_PREFIX}" ]]; then
  conda env create -p "${ENV_PREFIX}" -f "${ENV_FILE}"
else
  conda env update -p "${ENV_PREFIX}" -f "${ENV_FILE}" --prune
fi

conda activate "${ENV_PREFIX}"

conda env export --from-history > "${ENV_PREFIX}/environment-history.yml"

echo "Environment ready at ${ENV_PREFIX}"