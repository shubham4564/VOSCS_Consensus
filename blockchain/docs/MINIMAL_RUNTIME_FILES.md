# Minimal runtime files (node + transactions)

This repo contains many diagnostics/tests/docs. This document lists the **smallest practical set of files** you need to:
1) run one or more nodes, and 2) submit signed transactions via the HTTP API.

## 1) Dependencies (required)

- `requirements/prod.txt`
  - Install with: `pip install -r requirements/prod.txt`
  - Contains runtime deps (FastAPI/Uvicorn, crypto, jsonpickle, p2pnetwork).

## 2) Node runtime (required)

These are required to start a node process and serve the REST API:

- Entrypoints
  - `run_node.py` (starts a node, starts P2P + API)
  - `start_nodes.sh` (optional helper to start many nodes)

- Python packages/modules (keep as-is)
  - `blockchain/` (core node + chain + consensus + p2p + tx types)
  - `api/` (FastAPI app + routes used by `run_node.py`)
  - `gossip_protocol/` (gossip implementation imported by `blockchain/blockchain.py`)
  - `fast_gulf_stream.py` (imported by `blockchain/node.py`)

### Safe-to-ignore inside runtime packages

These are not required at runtime and can be removed if you are making a minimal distribution:

- `blockchain/**/__pycache__/`
- `blockchain/**/*.backup_*`
- `blockchain/**/test_*.py` (only if you are sure you don’t run them)

## 3) Genesis + keys (required)

The chain bootstraps from a shared genesis file:

- Required
  - `genesis_config/genesis.json` (loaded by `blockchain/blockchain.py`)

- Required for the provided multi-node scripts
  - `keys/genesis_private_key.pem` (used by `start_nodes.sh` for node 1)

- Required if you want the included transaction test harness to sign transactions
  - `genesis_config/bootstrap_validator_private_key.pem`
  - (Optionally) `genesis_config/faucet_private_key.pem`, `genesis_config/bootstrap_vote_private_key.pem`

Notes:
- You **can** run with different keys, but then you must update scripts/config accordingly.
- `start_nodes.sh` will try `keys/nodeN_private_key.pem` for nodes 2..N and fall back if missing.

## 4) Transaction submission (required for the included demo)

To submit signed transactions using the existing harness:

- `clients/test_sample_transaction.py`

This script:
- loads keys from `genesis_config/`
- creates and signs transactions
- POSTs them to `http://localhost:11000/api/v1/transaction/create/`

If you prefer a smaller example, you can also use:
- `clients/simple_transaction_example.py` (client-side example)

## 5) What is *not* required (optional)

The following are useful, but not needed just to run nodes + submit transactions:

- Docs / reports
  - `*.md`
  - `*_REPORT*.json`, `*_metrics_*.json`

- Diagnostics / sync tools
  - `tools/sync_checker.py`, `tools/direct_sync_tool.py`, `tools/emergency_sync_tool.py`, `tools/block_sync_diagnosis.py`, etc.

- Stress tests / benchmarks
  - `tools/real_transaction_stress_test.py`, `tools/enhanced_stress_test.py`, `tests/simple_load_test.py`, etc.

- Tests
  - `test_*.py`
  - `tests/validation_tests/`

- Operational artifacts
  - `logs/` (generated at runtime)

## 6) Minimal commands

### Start a single node

```bash
pip install -r requirements/prod.txt

# from the repo's blockchain/ folder
python run_node.py --ip 0.0.0.0 --node_port 10000 --api_port 11000 --key_file keys/genesis_private_key.pem
```

## 7) Minimal runtime folder (ready-made)

If you want everything already arranged into a small runnable directory, use:

- `minimal_runtime/`

It contains only the runtime code + genesis + minimal keys + a transaction client.

```bash
cd minimal_runtime
pip install -r requirements/prod.txt
./start_nodes.sh 4
python clients/test_sample_transaction.py --count 3
```

### Submit a few transactions

```bash
# in another terminal (same folder)
python clients/test_sample_transaction.py --count 3
```
