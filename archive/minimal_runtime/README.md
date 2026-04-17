# minimal_runtime

This folder is a **self-contained minimal runtime** for running the blockchain nodes and submitting transactions, extracted from the main repo without changing the original layout.

## What’s inside

- `run_node.py` – single-node entrypoint (starts P2P + API)
- `start_nodes.sh` – helper to start a small local cluster (uses `keys/`)
- `blockchain/` – core node/chain implementation
- `api/` – FastAPI REST API
- `gossip_protocol/` – gossip implementation imported by the chain
- `fast_gulf_stream.py` – UDP forwarder imported by `blockchain/node.py`
- `requirements/prod.txt` – runtime dependencies
- `genesis_config/` – `genesis.json` + validator/faucet/vote private keys
- `keys/` – minimal node keys for 4 nodes (node1 genesis + node2-4)
- `clients/test_sample_transaction.py` – submits signed transactions via the REST API

## Install deps

```bash
cd minimal_runtime
pip install -r requirements/prod.txt
```

## Run a 4-node cluster

```bash
cd minimal_runtime
./start_nodes.sh 4
```

APIs will be on `11000-11003`.

## Submit transactions

```bash
cd minimal_runtime
python clients/test_sample_transaction.py --count 3
```

## Notes

- The node code loads the genesis file via the relative path `genesis_config/genesis.json`, so **run commands from this folder**.
- If you want more than 4 nodes, add more `keys/nodeN_private_key.pem` files into `keys/`.
