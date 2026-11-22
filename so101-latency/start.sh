#!/usr/bin/env bash
set -eo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
conda_init="${SO101_CONDA_INIT:-$HOME/miniforge3/etc/profile.d/conda.sh}"
if [[ ! -r "$conda_init" ]]; then
    echo "Conda setup not found at $conda_init. Set SO101_CONDA_INIT to conda.sh." >&2
    exit 1
fi
source "$conda_init"
conda activate "${SO101_CONDA_ENV:-lerobot}"
cd "$script_dir"
exec python measure_latency.py "$@"
