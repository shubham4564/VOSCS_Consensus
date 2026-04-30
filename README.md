# Verifiable Optimization based Blockchain Consensus

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

A research artifact for **verifiable optimization-based blockchain consensus** with Solana-style ordering, execution, and propagation components.

> **Note**: This is a research artifact submitted for anonymous peer review. All identifying information has been removed.

---

## Key Features

- **Quantum Annealing Consensus** — QUBO-based leader selection via simulated annealing (D-Wave compatible), with health-aware scoring, frequency penalty, and Byzantine fault tolerance.
- **Gulf Stream** — Transaction forwarding direct to upcoming leaders (current + next 3).
- **Proof of History** — 5 000 ticks/sec cryptographic clock for verifiable ordering.
- **Sealevel** — Parallel transaction execution with 8-thread processing.
- **Turbine** — Erasure-coded block propagation with shred distribution.
- **Full Evaluation Suite** — Baseline comparisons, ablation studies, security experiments, curated paper figures, and throughput/finality benchmarks (see [Reproducing the Evaluation](#reproducing-the-evaluation)).

---

## Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.8 | 3.9+ |
| RAM | 4 GB | 8 GB (multi-node) |
| OS | Linux / macOS / WSL2 | Ubuntu 22.04+ |

All Python dependencies are pinned in `blockchain/requirements.txt`.

---

## Quick Start

```bash
# 1. Clone and enter the project
git clone <repository-url>
cd <repository-root>/blockchain

# 2. Create a virtual environment (recommended)
python -m venv venv && source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Generate cryptographic keys (ECDSA P-256)
chmod +x scripts/generate_keys.sh
./scripts/generate_keys.sh

# 5. Start a 5-node network
./start_nodes.sh 5

# 6. Verify all nodes are healthy
for port in 11000 11001 11002 11003 11004; do
  echo -n "Node $port: "
  curl -s http://localhost:$port/api/v1/health/ | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "UNREACHABLE"
done

# 7. Submit a test transaction
python clients/simple_transaction_example.py

# 8. Monitor leader selection
python tools/leader_monitor.py
```

---

## Reproducing the Evaluation

All reviewer-facing evaluation tools live under `blockchain/tools/` and write timestamped run folders under `blockchain/reports/`. Offline evaluation does **not** require running validator nodes.

### Reviewer Setup

From the repository root:

```bash
cd blockchain
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Recommended End-to-End Reproduction

For a single command that reproduces the committee comparison stack and emits a manifest plus reviewer-facing exports, run:

```bash
cd blockchain
python tools/committee_comparative_evaluation.py --output-dir reports/reviewer_eval
```

This command creates a timestamped run directory of the form:

```text
reports/reviewer_eval/
  <YYYYMMDD_HHMMSS>_committee_comparative_evaluation/
    reduced/
    literature/
    solver/
    committee_ablation/
    measurement_overhead/
    security/
    exports/
    metadata/
```

The most important reviewer-facing files are:

- `metadata/comparative_manifest.json`
- `metadata/comparative_summary.md`
- `exports/` CSV, Markdown, and LaTeX summary files
- stage-specific JSON and figures under each stage's `data/` and `figures/`

### Verifying That The Comparative Run Completed

```bash
cd blockchain
latest_run="$(ls -dt reports/reviewer_eval/*committee_comparative_evaluation | head -n 1)"
test -f "$latest_run/metadata/comparative_manifest.json"
test -f "$latest_run/metadata/comparative_summary.md"
find "$latest_run" -maxdepth 2 -type d | sort
ls "$latest_run/exports"
```

If the run completed correctly, the `test -f` checks succeed silently, the directory listing shows the expected stage folders, and `exports/` contains reviewer-facing tables and summaries.

### Generating The Curated Figure Bundle

The attached `reports/figure/` tree is produced by `tools/generate_evaluation_figures.py`. This is the fastest way to regenerate the paper-style figures from the archived evaluation outputs already included in the artifact under `reports/ccs_eval_old/`, `reports/ccs_eval/`, and `reports/old/`.

```bash
cd blockchain
python tools/generate_evaluation_figures.py --output-dir reports/figure
```

This command writes a curated figure bundle of the form:

```text
reports/figure/
  figure_manifest.json
  ablation/
  baselines/
  long_horizon/
  scaling/
  security/
  solver/
```

`figure_manifest.json` records the generated figure paths and the raw JSON sources used for each plot, so it is the main provenance file for the attached `reports/figure/` outputs.

To verify that the figure bundle was generated correctly:

```bash
cd blockchain
test -f reports/figure/figure_manifest.json
find reports/figure -maxdepth 2 -type f | sort
```

If you have fresh raw evaluation outputs in a non-default directory, add that directory to the scan roots. **This is necessary when pointing the figure generator at a fresh reviewer run**, since the default scan roots do not include `reports/reviewer_eval`:

```bash
cd blockchain
python tools/generate_evaluation_figures.py \
  --report-roots reports/reviewer_eval reports/ccs_eval_old reports/ccs_eval reports/old \
  --output-dir reports/figure
```

### Reproducing Individual Evaluation Components

Run the components in this order so that `generate_evaluation_figures.py` can collect all outputs in a single pass.

**1. Main strategy comparison and ablation harness:**

```bash
cd blockchain
python tools/evaluation_overhaul.py \
  --output-dir reports/eval_main \
  --strategy-preset literature
```

**2. Committee security experiments:**

```bash
cd blockchain
python tools/security_experiments.py \
  --output-dir reports/eval_security \
  --experiments probe_manipulation infra_gaming score_racing \
                attacker_sweep correlated_failure block_withholding
```

> `witness_collusion` is already run as part of `committee_comparative_evaluation.py` (Step 4 above). Add it here only if you want a standalone run.

**3. Selection timing benchmark:**

```bash
cd blockchain
python tools/suitability_timing_benchmark.py
```

**4. Throughput and finality evaluation:**

```bash
cd blockchain
python tools/throughput_evaluation.py
```

**5. Generate curated paper figures (run last, after all components above):**

```bash
cd blockchain
python tools/generate_evaluation_figures.py \
  --report-roots reports/reviewer_eval reports/eval_main reports/eval_security \
  --output-dir reports/figure
```

### Reproducing the Measurement Overhead Table

The measurement overhead table (probe traffic, VOSCS optimization time, greedy optimization time, and lightweight optimization time across node counts) is produced by calling `run_measurement_overhead_study` directly, since the CLI of `committee_comparative_evaluation.py` does not expose `--measurement-overhead-nodes`. Run the following inline script from `blockchain/`:

```bash
cd blockchain
python - <<'EOF'
import sys, os
sys.path.insert(0, os.path.abspath("."))

from tools.evaluation_overhaul import (
    SimulationConfig,
    run_measurement_overhead_study,
    save_measurement_overhead_results,
)
from blockchain.utils.result_layout import create_run_layout

cfg = SimulationConfig(
    num_nodes=200,
    num_rounds=100,
    seed=42,
    attacker_fraction=0.2,
    committee_k=7,
    metadata_profile="clustered_attackers",
    output_dir="reports/overhead_N50_100_150_200",
)

run_layout = create_run_layout(cfg.output_dir, "measurement_overhead")

overhead_metrics = run_measurement_overhead_study(
    cfg,
    node_counts=[50, 100, 150, 200],
    num_rounds=100,
    window_rounds=25,
)

out_json = save_measurement_overhead_results(overhead_metrics, run_layout.data_dir)
print(f"Results written to: {out_json}")
EOF
```

Parameters match the table caption: 100 rounds, 25-round measurement window. Replace `node_counts` with `[40, 100, 200]` to reproduce the originally published N=40/100/200 rows. Output lands in:

```text
reports/overhead_N50_100_150_200/
  <YYYYMMDD_HHMMSS>_measurement_overhead/
    data/
      measurement_overhead_<timestamp>.json
```

The JSON key `measurement_overhead` contains one record per node count with fields for probe traffic (MB), VOSCS solver time (ms), greedy time (ms), and lightweight time (ms).

To reproduce the attached throughput run with the same main parameters (`100` nodes, `100` blocks, `500` transactions per block, attacker fraction `0.2`, seed `42`), run:

```bash
cd blockchain
python tools/throughput_evaluation.py \
  --nodes 100 \
  --blocks 100 \
  --txs-per-block 500 \
  --attackers 0.2 \
  --seed 42 \
  --output-dir reports
```

This creates a timestamped run directory of the form:

```text
reports/
  <YYYYMMDD_HHMMSS>_throughput_evaluation/
    data/
      throughput_metrics.json
    figures/
      block_finality.png
      throughput.png
      throughput_block_time.png
      throughput_comparison.png
      throughput_finality.png
      throughput_throughput.png
    exports/
    metadata/
      run_manifest.json
```

The primary reviewer-facing files are:

- `data/throughput_metrics.json` for per-strategy TPS, block-time, finality, and attacker-share metrics
- `figures/` for the generated throughput and latency plots
- `metadata/run_manifest.json` for the exact run configuration and output layout

To verify the latest throughput run:

```bash
cd blockchain
latest_run="$(ls -dt reports/*throughput_evaluation | head -n 1)"
test -f "$latest_run/data/throughput_metrics.json"
test -f "$latest_run/metadata/run_manifest.json"
find "$latest_run/figures" -maxdepth 1 -type f | sort
```

Add `--real --wallets 20 --sequential` if you want to run the same benchmark with real signed transactions instead of the default simulated transaction workload.

### Verifying With Reviewer-Facing Tests

The reviewer-facing pytest checks are kept at the top level of `blockchain/tests/`.

```bash
cd blockchain
python -m pytest tests/test_committee_comparative_evaluation.py -q
python -m pytest tests/test_security_committee_experiments.py -q
python -m pytest tests/test_committee_selection.py -q
```

These tests verify that the comparative runner, committee security experiments, and committee selection logic all produce the expected artifacts and invariants.

### Result Layout

Reviewer-facing runs use a common directory layout:

```text
<output-root>/
  <YYYYMMDD_HHMMSS>_<run-name>/
    data/
    figures/
    exports/
    metadata/
```

- `data/` stores primary JSON artifacts
- `figures/` stores generated plots
- `exports/` stores CSV, Markdown, and LaTeX summaries
- `metadata/` stores the run manifest and configuration summary

---

## Project Structure

```
.
├── README.md
├── README.md.bak
├── docker-compose.yml
├── archive/
└── blockchain/
  ├── Dockerfile
  ├── requirements.txt
  ├── run_node.py
  ├── start_nodes.sh
  ├── api/
  ├── blockchain/
  ├── clients/
  ├── configs/
  ├── docs/
  ├── genesis_config/
  ├── gossip_protocol/
  ├── keys/
  ├── logs/
  ├── monitoring/
  ├── reports/
  ├── scripts/
  ├── tests/
  └── tools/
```

---

## Running a Multi-Node Network

### Native (recommended for evaluation)

```bash
cd blockchain

# Start N nodes (default 10; override with argument)
./start_nodes.sh 5

# Nodes bind to:
#   P2P:    ports 10000-10004
#   API:    ports 11000-11004
#   TPU:    ports 13000-13004 (UDP, Gulf Stream)
#   Gossip: ports 12000-12004

# Stop all nodes
pkill -f 'run_node.py'
```

### Docker

```bash
# Build image
cd blockchain && docker build -t quantum-blockchain .

# Run 3-node cluster
cd .. && docker-compose up -d
# Nodes: localhost:8050 (node1), :8051 (node2), :8052 (node3)
```

---

## API Reference

All endpoints are served at `http://localhost:<api_port>/api/v1/`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health/` | Node health status |
| GET | `/blockchain/` | Full chain state |
| GET | `/blockchain/leader/current/` | Current leader, slot, time remaining |
| GET | `/blockchain/leader/upcoming/` | Next leaders in schedule |
| GET | `/blockchain/leader/quantum-selection/` | Quantum consensus details |
| GET | `/blockchain/leader/schedule/` | Complete leader schedule |
| GET | `/blockchain/mempool/` | Mempool statistics |
| GET | `/transaction/transaction_pool/` | Pending transactions |
| POST | `/transaction/create/` | Submit a signed transaction |

Interactive API docs: `http://localhost:11000/api/v1/docs/`

---

## Configuration

Key parameters and where to find them:

| Parameter | Default | Location |
|-----------|---------|----------|
| Slot duration | 0.45 s | `genesis_config/genesis.json` |
| Ticks per slot | 64 | `genesis_config/genesis.json` |
| PoH ticks/sec | 5 000 | `blockchain/consensus/proof_of_history.py` |
| Sealevel threads | 8 | `blockchain/consensus/sealevel.py` |
| Quantum annealing time | 10 ms | `configs/tps_optimization_config.json` |
| Leader advance | 30 s | `configs/tps_optimization_config.json` |
| Gulf Stream buffer | 200 slots | `genesis_config/genesis.json` |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError` | `pip install -r requirements.txt` inside `blockchain/` |
| Port already in use | `pkill -f 'run_node.py'` then restart |
| No leader selected | Wait 2–3 s after startup; check `python tools/leader_monitor.py` |
| Key file not found | Run `./scripts/generate_keys.sh` |
| Transaction not in block | Verify leader is active: `curl localhost:11000/api/v1/blockchain/leader/current/` |
| Remote ports unreachable | Forward API ports (11000–11004) via SSH or VS Code Ports panel |

Debug mode:
```bash
LOG_LEVEL=DEBUG python run_node.py --ip 0.0.0.0 --node_port 10000 --api_port 11000
tail -f logs/node1.log
```

---

## License

This project is licensed under the MIT License.

