# Quantum-Enhanced Solana-Style Blockchain

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

A high-performance blockchain implementation featuring **Solana-style architecture** with quantum-annealing-based consensus, Proof of History (PoH), parallel execution (Sealevel), and efficient block propagation (Turbine).

> **Note**: This is a research artifact submitted for anonymous peer review. All identifying information has been removed.

---

## Key Features

- **Quantum Annealing Consensus** — QUBO-based leader selection via simulated annealing (D-Wave compatible), with health-aware scoring, frequency penalty, and Byzantine fault tolerance.
- **Gulf Stream** — Transaction forwarding direct to upcoming leaders (current + next 3).
- **Proof of History** — 5 000 ticks/sec cryptographic clock for verifiable ordering.
- **Sealevel** — Parallel transaction execution with 8-thread processing.
- **Turbine** — Erasure-coded block propagation with shred distribution.
- **Full Evaluation Suite** — Baseline comparisons, ablation studies, security experiments, and timing benchmarks (see [Reproducing the Evaluation](#reproducing-the-evaluation)).

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
cd proofwithquantumannealing/blockchain

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

All evaluation scripts live under `blockchain/tools/` and write results (JSON metrics + PNG figures) to `blockchain/reports/`. **No running nodes are required** for the offline evaluations — they instantiate the consensus engine directly.

### 1. Main Evaluation (Baselines + Ablations)

Compares quantum annealing against 9 baselines across 100–1000 nodes and 1000+ rounds. Produces PQI, agreement rate, security, and solver-time charts plus a full ablation heatmap.

```bash
cd blockchain
python tools/evaluation_overhaul.py
# Output: reports/evaluation_overhaul_*.json
#         reports/eval_pqi_*.png
#         reports/eval_agreement_*.png
#         reports/eval_security_*.png
#         reports/eval_solver_time_*.png
#         reports/ablation_heatmap_*.png
```

### 2. Security Experiments

Three targeted attack scenarios: probe manipulation, infrastructure gaming, and score-racing / fairness-bound verification.

```bash
python tools/security_experiments.py
# Output: reports/security_experiments_*.json
#         reports/security_probe_manipulation_*.png
#         reports/security_infra_gaming_*.png
#         reports/security_score_racing_*.png
```

### 3. Proposer-Selection Timing Benchmark

Measures wall-clock selection latency for quantum (SA-QUBO), classical greedy, argmax, and VRF-weighted strategies as node count scales from 5 to 100+.

```bash
python tools/suitability_timing_benchmark.py
# Output: reports/suitability_timing_*_metrics.json
#         reports/suitability_timing_*_timing_comparison.png
```

### 4. Consensus Baseline Comparison

Controlled simulation (20 nodes, 300 rounds) computing PQI, missed-slot rate, p95 block time, Nakamoto coefficient, and attacker proposer share for 6 strategies.

```bash
python tools/consensus_baseline_evaluation.py
# Output: reports/ (comparison graphs)
```

### 5. Throughput and Finality Evaluation

Measures TPS, block production time, and finality across strategies (50 nodes, 100 blocks, 500 tx/block).

```bash
python tools/throughput_evaluation.py
# Output: reports/ (JSON metrics + comparison graphs)
```

### 6. Live Network Tests (requires running nodes)

```bash
# Start 5 nodes first
./start_nodes.sh 5

# Transaction performance (consensus time, throughput)
python tests/test_performance_metrics.py

# Full Solana-style validator verification and voting
python tests/test_solana_validation.py

# Gulf Stream + PoH + Turbine end-to-end
python tests/test_gulf_stream_transactions.py

# Load test (100 concurrent transactions)
python clients/send_100_transactions.py
```

> **Tip**: Run the offline evaluations (1–5) first — they are deterministic and do not require network setup.

---

## Project Structure

```
blockchain/
├── run_node.py                  # Node entry point
├── start_nodes.sh               # Multi-node launcher
├── requirements.txt             # Pinned Python dependencies
├── Dockerfile                   # Container image
│
├── blockchain/                  # Core library
│   ├── node.py                  # Node orchestrator (P2P, gossip, TPU, slots)
│   ├── blockchain.py            # Chain state, genesis, validation
│   ├── block.py                 # Block data structure
│   ├── poh_sequencer.py         # Proof of History
│   ├── sealevel_executor.py     # Parallel transaction execution
│   ├── turbine_protocol.py      # Block propagation
│   ├── fast_gulf_stream.py      # Transaction forwarding to leaders
│   ├── slot_producer.py         # Slot-based block production
│   ├── consensus/               # PoH, Sealevel, Turbine, TPU, leader schedule
│   ├── quantum_consensus/       # Quantum annealing leader selection (QUBO)
│   ├── transaction/             # Transaction, wallet (ECDSA P-256), pool
│   ├── p2p/                     # Socket communication, peer discovery, mempool
│   └── utils/                   # Logging, serialization helpers
│
├── api/                         # FastAPI REST API
│   └── api_v1/                  # Blockchain, transaction, leader endpoints
│
├── gossip_protocol/             # CRDS-based gossip (Solana-style)
│
├── tools/                       # Evaluation and operations
│   ├── evaluation_overhaul.py          # Main evaluation harness
│   ├── security_experiments.py         # Attack scenario experiments
│   ├── suitability_timing_benchmark.py # Selection latency benchmark
│   ├── consensus_baseline_evaluation.py# Strategy comparison
│   ├── throughput_evaluation.py        # TPS and finality evaluation
│   ├── leader_monitor.py              # Real-time leader monitoring
│   ├── comprehensive_metrics.py       # Live performance report
│   └── bootstrap_network.py           # Network bootstrapping
│
├── tests/                       # Integration and unit tests
│   ├── test_solana_validation.py
│   ├── test_performance_metrics.py
│   ├── test_gulf_stream_*.py
│   └── validation_tests/        # Leader schedule and gossip verification
│
├── clients/                     # Transaction submission scripts
│   ├── simple_transaction_example.py
│   ├── test_sample_transaction.py
│   └── send_100_transactions.py
│
├── reports/                     # Evaluation outputs (JSON + PNG)
├── genesis_config/              # Genesis block and bootstrap keys
├── keys/                        # ECDSA node keys (generated)
├── configs/                     # Tuning configs (TPS optimization)
├── monitoring/                  # Health checks and metrics exporters
├── scripts/                     # Key generation, status checks
└── docs/                        # Internal development docs
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

## Performance Benchmarks

Measured on a 5-node cluster (single machine):

| Metric | Value |
|--------|-------|
| Transaction submission rate | 272+ TPS |
| PoH tick rate | 5 000 / sec |
| Consensus (leader selection + block) | 2–15 s |
| Leader selection startup | 2–3 s |
| Sealevel parallel threads | 8 |
| Leader API response | < 50 ms |

---

## License

This project is licensed under the MIT License.

> **Disclaimer**: This is a research and demonstration project. Not intended for production use.
