# Result Layout Guide

Reviewer-facing tools now write outputs into timestamped run folders so each execution is self-contained.

By default, reviewer-facing tools use `reports/` as the shared root.

## Run Folder Pattern

Each run is created under the chosen output root with this shape:

```text
<output-root>/
  <YYYYMMDD_HHMMSS>_<run-name>/
    data/
    figures/
    exports/
    metadata/
```

## Folder Meanings

- `data/`: machine-readable JSON metrics and other primary result files
- `figures/`: plots and visual assets generated for the run
- `exports/`: reviewer-facing CSV, Markdown, and LaTeX exports when a tool produces them
- `metadata/`: run manifest information, including the start timestamp and configuration summary

## Reviewer-Facing Tools

- `tools/committee_comparative_evaluation.py`
  - Creates one timestamped run folder and then stage folders for `reduced/`, `literature/`, `solver/`, and `security/`
  - Each stage has its own `data/` and `figures/`
  - Shared cross-stage tables and narratives live under the top-level `exports/`
- `tools/evaluation_overhaul.py`
  - Stores JSON in `data/` and plots in `figures/`
- `tools/security_experiments.py`
  - Stores aggregate JSON in `data/` and experiment plots in `figures/`
- `tools/throughput_evaluation.py`
  - Stores throughput metrics JSON in `data/` and comparison figures in `figures/`
- `tools/suitability_timing_benchmark.py`
  - Stores timing metrics JSON in `data/` and the benchmark figure in `figures/`

## Reviewer-Facing Tests

Artifact-producing reviewer tests use the same `reports/` root and create timestamped `test_*` run folders with the same layout.