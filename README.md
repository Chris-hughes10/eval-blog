# Evals Are Measurements, Not Tests

Blog post and fully reproducible companion code for **"Evals Are Measurements, Not Tests"** —
a Bayesian, code-first treatment of the statistics of small-sample LLM evals.

- The post: [Your AI Eval Isn’t a Test. It’s a Measurement.]([post/evals-are-measurements-not-tests.md](https://chris-hughes10.github.io/posts/evals-are-measurements-not-tests/))
- Every number and figure in the post is regenerated from simulated data (planted ground
  truth, so the inference can be *checked*, not just run) — no live model required.

## Layout

```
├── src/         the runnable scripts
│   ├── eval_stats.py     all worked examples + prior-sensitivity + calibration; writes the 5 figures
│   ├── cross_check.py    single-accuracy interval & calibration vs the bayes_evals reference library
│   └── paired_check.py   paired P(B>A) vs bayes_evals on the Example 3 data
├── figures/     the 5 generated PNGs embedded in the post
├── notes/       private working notes (CONTEXT.md, UNDERSTAND.md) — not for publication
├── run.sh       one-command reproduction
└── pyproject.toml / uv.lock / .python-version   pinned environment
```

## Requirements

- **Python ≥ 3.9** — the scripts use the `dict | dict` merge operator (PEP 584) and
  builtin-generic annotations (`dict[str, Any]`), both 3.9+. The pinned environment runs 3.12.
- **Pinned scientific stack** — numpy 2.4.6, scipy 1.17.1, pymc 6.0.1, pytensor 3.0.3,
  matplotlib 3.10.9, pandas 3.0.3 (on Python 3.12; the markers in `requirements.txt` resolve
  pymc/pytensor down a major version on older Pythons). The pins matter: the design-power
  table's last digit is version-sensitive across scipy releases.
- **`uv.lock` is the single source of pinned truth.** `requirements.txt` is *generated from it*
  for plain-`pip` users — never hand-edit it; regenerate with
  `uv export --no-emit-project --no-hashes --format requirements-txt > requirements.txt` whenever
  the lock changes, so the two can't silently diverge. uv users don't need it at all (`./run.sh`
  installs straight from the lock).

## Reproduce everything

Requires [uv](https://docs.astral.sh/uv/). The right Python, the scientific stack
(NumPy / SciPy / PyMC / matplotlib / pandas), and the `bayes_evals` reference library
(pinned to a specific commit) are all installed into a project-local `.venv` on first run.
The single reproduce command is:

```bash
./run.sh
```

This runs the three scripts and rewrites the five figures in `figures/`. On a given machine the
output is deterministic — every random source is seeded and sampling runs single-threaded
(`chains=4, cores=1`), so re-runs are byte-for-byte identical on a given machine.

To run a single script:

```bash
uv run python src/eval_stats.py
```

## Notes on reproducibility

- Numbers can differ in the last digit across *different* machines/BLAS for the MCMC examples
  (clustering, Examples 2–4, repeated-sampling, prior-sensitivity); the closed-form parts (Example 1,
  design-power, calibration, cross-checks) are identical everywhere.
- `uv.lock` pins exact package versions, so the environment itself won't drift.
- `bayes_evals` is the reference library from Bowyer, Aitchison & Ivanova (arXiv:2503.01747),
  installed from a pinned git commit (see `pyproject.toml`).
