#!/bin/bash
# Environment bootstrap for Oxford ARC (see Submission Script Basics in the ARC user guide).
set -euo pipefail

: "${DATA:=/data/engs-df-green-ammonia/${USER}}"

ANACONDA_MODULE="${ANACONDA_MODULE:-Anaconda3/2023.09}"
CONDA_TOOLS_ENV="${CONDA_TOOLS_ENV:-/data/engs-df-green-ammonia/${USER}/envs/conda-tools}"
MICROMAMBA_BIN="${MICROMAMBA_BIN:-micromamba}"
ENV_NAME="${ENV_NAME:-green-condor-env}"
ENV_PREFIX="${ENV_PREFIX:-$DATA/envs/${ENV_NAME}}"
ENV_FILE="$(dirname "$0")/environment_arc.yaml"

module purge
module load "${ANACONDA_MODULE}"

if [[ ! -d "${CONDA_TOOLS_ENV}" ]]; then
  echo "Conda-tools environment not found at ${CONDA_TOOLS_ENV}" >&2
  exit 1
fi

source activate "${CONDA_TOOLS_ENV}"
eval "$("${MICROMAMBA_BIN}" shell hook --shell bash)"

if [[ ! -d "${ENV_PREFIX}" ]]; then
  "${MICROMAMBA_BIN}" env create -y -p "${ENV_PREFIX}" -f "${ENV_FILE}"
else
  "${MICROMAMBA_BIN}" env update -y -p "${ENV_PREFIX}" -f "${ENV_FILE}" --prune
fi

micromamba activate "${ENV_PREFIX}"

"${MICROMAMBA_BIN}" env export --name "${ENV_NAME}" > "${ENV_PREFIX}/environment-history.yml"

echo "Environment ready at ${ENV_PREFIX}"