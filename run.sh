#!/usr/bin/env bash
# Reproduce every result and figure in "Evals Are Measurements, Not Tests".
#
# Usage:  ./run.sh
#
# Requires uv (https://docs.astral.sh/uv/). Everything else — the right Python,
# the scientific stack, and the bayes_evals reference library — is installed by
# uv into a project-local .venv on first run.
set -euo pipefail
cd "$(dirname "$0")"

# Unset conda/venv vars so uv always resolves to THIS project's .venv,
# never an ambient conda environment.
unset VIRTUAL_ENV CONDA_PREFIX 2>/dev/null || true

echo ">> Syncing environment (uv) ..."
uv sync

echo
echo ">> [1/3] eval_stats.py  — all worked examples + regenerates the five figures"
uv run python src/eval_stats.py

echo
echo ">> [2/3] cross_check.py  — single-accuracy interval & calibration vs bayes_evals"
uv run python src/cross_check.py

echo
echo ">> [3/3] paired_check.py — paired P(B>A) vs bayes_evals on the Example 3 data"
uv run python src/paired_check.py

echo
echo ">> Done. Figures written:"
ls -1 figures/*.png
