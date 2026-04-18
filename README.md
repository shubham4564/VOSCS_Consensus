#  Quantum-Enhanced Solana-Style Blockchain

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

A high-performance blockchain implementation featuring **Solana-style architecture** with quantum consensus, Proof of History (PoH), parallel execution (Sealevel), and efficient block propagation (Turbine).

##  **Key Features**

### ** Quantum Consensus**
- **Quantum annealing-based leader selection** for deterministic consensus
- **2-second slot intervals** with continuous leader scheduling
- **Byzantine fault tolerance** with quantum-enhanced security
- **Health-based voting system** prioritizing healthy nodes over stake weights

### ** Solana-Style Architecture**
- ** Gulf Stream**: Direct transaction forwarding to upcoming leaders
- ** Proof of History**: 5,000 ticks/second cryptographic clock for verifiable ordering
- ** Sealevel**: Parallel transaction execution with 8-thread processing
- ** Turbine**: Efficient block propagation with erasure coding and shred distribution

### ** Enhanced Logging & Monitoring**
- **Component-specific logs**: Separate files for PoH, Sealevel, Turbine, consensus, transactions
- **Performance metrics**: Real-time TPS monitoring and latency analysis
- **Real-time monitoring**: Live log tailing and component analysis
- **JSON-structured logs**: Machine-readable for automated analysis

##  **Prerequisites**

### **System Requirements**
- **Python 3.8+** (3.9+ recommended)
- **4GB+ RAM** (8GB recommended for multi-node setups)
- **Linux/macOS** (Windows with WSL2)

### **Python Dependencies**
All dependencies are listed in `blockchain/requirements.txt`:
```
# Core blockchain / networking
cryptography==41.0.5
p2pnetwork==1.2
jsonpickle==3.0.2

# Web API
fastapi==0.104.1
uvicorn==0.23.2
starlette==0.27.0
pydantic==2.11.7

# Quantum annealing
dimod==0.12.20
dwave-samplers==1.6.0

# HTTP / async
aiohttp==3.12.14
requests==2.32.4

# Numerics / plotting
numpy==2.3.1
matplotlib==3.10.3

# Observability
psutil==7.0.0
python-json-logger==2.0.7
```

##  **Installation**

### **1. Clone Repository**
```bash
git clone https://github.com/[anonymous]/proofwithquantumannealing.git
cd proofwithquantumannealing/blockchain
```

### **2. Install Dependencies**
```bash
# Using pip (recommended)
pip install -r requirements.txt

# Or using conda
conda create -n blockchain python=3.9
conda activate blockchain
pip install -r requirements.txt
```

### **3. Generate Cryptographic Keys**
```bash
# Generate keys for nodes (genesis + node keys)
chmod +x scripts/generate_keys.sh
./scripts/generate_keys.sh

# Verify key generation
ls keys/
# Should show: genesis_private_key.pem, genesis_public_key.pem, node*_private_key.pem, etc.
```

##  **Quick Start**

### **1. Start Blockchain Network**  **AUTO LEADER SELECTION**
```bash
# Start 5 nodes (ports 10000-10004 for P2P, 11000-11004 for API)
./start_nodes.sh

# Expected output:
#  Starting 5 blockchain nodes...
#  All 5 nodes started!
#  Node ports: 10000-10004
#  API ports: 11000-11004
#  Logs: tail -f logs/node1.log

# NEW: Leader selection now starts automatically!
#  Leaders are selected within 2-3 seconds of network startup
#  No need to wait for transactions to trigger leader selection
#  Continuous leader schedule updates every 30 seconds
```

### **2. Verify Node Status & Leader Selection**  **ENHANCED**
```bash
# Check if nodes are responding
curl http://localhost:11000/api/v1/blockchain/ | jq

# Should return blockchain status with blocks array

# Monitor leader selection (NEW!)
curl http://localhost:11000/api/v1/blockchain/leader/current/ | jq

# Expected response showing active leader:
{
  "current_leader": "node_10001",
  "current_slot": 5,
  "leader_valid": true,
  "next_leader": "node_10002",
  "next_slot": 6,
  "time_until_next_slot": 1.8
}

# Use monitoring tools for continuous tracking
python tools/leader_monitor.py --once
```

### **3. Run Transaction Test**
```bash
# NEW: Interactive transaction example (recommended for beginners)
python clients/simple_transaction_example.py

# Simple transaction flow test
python clients/test_sample_transaction.py

# Comprehensive Solana-style flow test
python tests/test_solana_validation.py

# Performance analysis test
python tests/test_performance_metrics.py
```

##  **Sending Transactions & Testing**

### ** Transaction Basics**

#### **1. Understanding Transactions**
The blockchain supports several transaction types:
- **TRANSFER**: Send tokens between accounts
- **EXCHANGE**: Initial funding/exchange transactions
- **Custom types**: Extensible for future use cases

#### **2. Transaction Structure**
```python
# Basic transaction components
{
    "sender_public_key": "-----BEGIN PUBLIC KEY-----...",
    "receiver_public_key": "-----BEGIN PUBLIC KEY-----...", 
    "amount": 10.0,
    "type": "TRANSFER",
    "timestamp": 1640995200,
    "signature": "base64_encoded_signature"
}
```

### ** Creating and Sending Transactions**

#### **Option 1: Using Python Scripts (Recommended)**

**Simple Transaction Test:**
```bash
# NEW: Interactive transaction example with detailed output
python clients/simple_transaction_example.py

# Basic transaction flow test
python clients/test_sample_transaction.py

# Expected output from simple_transaction_example.py:
#  SIMPLE TRANSACTION EXAMPLE
#  Node is healthy and responsive
#  Genesis keys loaded successfully  
#  Transaction created and signed
#  Transaction submitted successfully!
#  New block(s) created - transaction likely included!
```

**Custom Transaction Script:**
```python
#!/usr/bin/env python3
from blockchain.transaction.transaction import Transaction
from blockchain.transaction.wallet import Wallet
from blockchain.utils.helpers import BlockchainUtils
import requests

# 1. Load or create wallet
wallet = Wallet()
# OR load existing keys:
# with open('keys/genesis_private_key.pem', 'r') as f:
#     wallet.from_key(f.read())

# 2. Create transaction
transaction = Transaction(
    sender_public_key=wallet.public_key_string(),
    receiver_public_key="<recipient_public_key>",
    amount=25.0,
    type="TRANSFER"
)

# 3. Sign transaction
signature = wallet.sign(transaction.payload())
transaction.sign(signature)

# 4. Submit to blockchain
encoded_tx = BlockchainUtils.encode(transaction)
response = requests.post(
    "http://localhost:11000/api/v1/transaction/create/",
    json={"transaction": encoded_tx}
)

print(f"Transaction result: {response.status_code}")
```

#### **Option 2: Using API Directly**

**API Transaction Submission:**
```bash
# Create and encode transaction (use Python helper)
python -c "
from blockchain.transaction.transaction import Transaction
from blockchain.transaction.wallet import Wallet  
from blockchain.utils.helpers import BlockchainUtils

# Load genesis keys
with open('keys/genesis_private_key.pem', 'r') as f:
    private_key = f.read()
with open('keys/genesis_public_key.pem', 'r') as f:
    public_key = f.read()

wallet = Wallet()
wallet.from_key(private_key)

# Create self-transfer for testing
tx = Transaction(public_key, public_key, 10.0, 'TRANSFER')
signature = wallet.sign(tx.payload())
tx.sign(signature)

encoded = BlockchainUtils.encode(tx)
print('ENCODED_TRANSACTION:')
print(encoded)
" > encoded_tx.txt

# Extract the encoded transaction
ENCODED_TX=$(grep -A1 "ENCODED_TRANSACTION:" encoded_tx.txt | tail -1)

# Submit via API
curl -X POST http://localhost:11000/api/v1/transaction/create/ \
  -H "Content-Type: application/json" \
  -d "{\"transaction\": \"$ENCODED_TX\"}"

# Clean up
rm encoded_tx.txt
```

**Alternative: Quick Test Script**
```bash
# Use the built-in transaction test
python clients/test_sample_transaction.py

# Or test with multiple nodes
python clients/test_sample_transaction.py --node-port 11001
```

### ** Comprehensive Testing Guide**

#### **Test Categories**

**1. Basic Connectivity Tests**
```bash
# Test node health
curl http://localhost:11000/api/v1/health/
curl http://localhost:11001/api/v1/health/
curl http://localhost:11002/api/v1/health/

# Test blockchain status
curl http://localhost:11000/api/v1/blockchain/ | jq '.blocks | length'
```

**2. Transaction Flow Tests**
```bash
# Single transaction test
python clients/test_sample_transaction.py

# Multiple transaction test
python clients/send_100_transactions.py

# Gulf Stream transaction forwarding test
python tests/test_gulf_stream_transactions.py
```

**3. Performance & Load Tests**
```bash
# Performance metrics
python tests/test_performance_metrics.py

# Comprehensive performance analysis
python tools/comprehensive_metrics.py
```

**4. Solana Component Tests**
```bash
# Turbine integration test
python tests/simple_turbine_test.py

# Solana validation test (complete compliance)
python tests/test_solana_validation.py

# Gulf Stream forwarding tests
python tests/test_gulf_stream_fix.py
python tests/test_gulf_stream_4_leaders.py
```

#### **Transaction Testing Patterns**

**Pattern 1: Simple Self-Transfer**
```python
# Test basic transaction mechanics
transaction = Transaction(
    sender_public_key=my_public_key,
    receiver_public_key=my_public_key,  # Self-send
    amount=10.0,
    type="TRANSFER"
)
```

**Pattern 2: Multi-Node Transfer**
```python
# Test cross-node transactions
# Load different node keys for sender/receiver
with open('keys/node2_public_key.pem', 'r') as f:
    receiver_key = f.read()
    
transaction = Transaction(
    sender_public_key=genesis_public_key,
    receiver_public_key=receiver_key,
    amount=50.0,
    type="TRANSFER"
)
```

**Pattern 3: High-Volume Testing**
```python
# Test multiple rapid transactions
for i in range(20):
    tx = Transaction(
        sender_public_key=wallet.public_key_string(),
        receiver_public_key=target_key,
        amount=float(i + 1),
        type="TRANSFER"
    )
    # Sign and submit...
```

#### **Monitoring Transaction Processing**

**Real-time Transaction Monitoring:**
```bash
# Tail node logs (start_nodes.sh writes logs/nodeN.log)
tail -f logs/node1.log
```

**Check Transaction Pool:**
```bash
# View pending transactions
curl http://localhost:11000/api/v1/transaction/transaction_pool/ | jq

# View mempool statistics
curl http://localhost:11000/api/v1/blockchain/mempool/ | jq
```

**Verify Transaction Inclusion:**
```bash
# Check if transactions made it into blocks
curl http://localhost:11000/api/v1/blockchain/ | jq '.blocks[-1].transactions'

# Count total transactions across all blocks
curl http://localhost:11000/api/v1/blockchain/ | jq '[.blocks[].transactions | length] | add'
```

### ** Troubleshooting Transactions**

#### **Common Issues & Solutions**

**Transaction Not Included in Blocks:**
```bash
# Check leader status
curl http://localhost:11000/api/v1/blockchain/leader/current/ | jq

# Verify node connectivity
python tools/leader_monitor.py --once

# Check transaction pool
curl http://localhost:11000/api/v1/transaction/transaction_pool/ | jq '. | length'

# Check recent blocks
curl http://localhost:11000/api/v1/blockchain/ | jq '.blocks[-3:] | length'
```

**Invalid Signature Errors:**
```bash
# Verify key loading
python -c "
with open('keys/genesis_private_key.pem', 'r') as f:
    print('Private key loaded:', len(f.read()), 'characters')
with open('keys/genesis_public_key.pem', 'r') as f:
    print('Public key loaded:', len(f.read()), 'characters')
"

# If you suspect key mismatch, re-run key generation:
./scripts/generate_keys.sh
```

**Network Connectivity Issues:**
```bash
# Test all node endpoints
for port in {11000..11004}; do
    echo "Testing node on port $port:"
    curl -s http://localhost:$port/api/v1/health/ | jq '.status' || echo "Failed"
done

# Check P2P connectivity
netstat -an | grep :10000
netstat -an | grep :11000
```

#### **Transaction Testing Checklist**

 **Prerequisites Check:**
- [ ] All nodes started: `./start_nodes.sh`
- [ ] Keys generated: `ls keys/` shows .pem files
- [ ] Leader selection active: `python tools/leader_monitor.py --once`

 **Basic Transaction Test:**
- [ ] Node connectivity: `curl http://localhost:11000/api/v1/health/`
- [ ] Simple transaction: `python clients/test_sample_transaction.py`
- [ ] Blockchain updated: Check block count increased

 **Advanced Testing:**
- [ ] Gulf Stream forwarding: `python tests/test_gulf_stream_transactions.py`
- [ ] Load test: `python clients/send_100_transactions.py`
- [ ] Solana compliance: `python tests/test_solana_validation.py`

### ** Transaction Performance Metrics**

Expected transaction processing performance:

| Metric | Value | Notes |
|--------|-------|-------|
| **API Submission Rate** | 272+ TPS | HTTP POST to `/api/v1/transaction/create/` |
| **Transaction Validation** | ~1ms | Signature + balance verification |
| **Gulf Stream Forwarding** | ~5ms | Leader-targeted forwarding |
| **PoH Integration** | ~0.2ms | Transaction sequencing |
| **Sealevel Execution** | ~2ms | Parallel execution per transaction |
| **Block Inclusion Time** | 2-15s | Depends on leader selection timing |
| **End-to-End Latency** | 3-20s | Submit → Block inclusion → Confirmation |

##  **Monitoring & Logging**

### ** Leader Selection Monitoring**  **NEW**
Real-time monitoring of leader selection and consensus:

```bash
# Continuous leader monitoring (recommended)
python tools/leader_monitor.py

# Output shows real-time leader information:
# ═══════════════════════════════════════════
#  QUANTUM BLOCKCHAIN LEADER MONITOR
# ═══════════════════════════════════════════
#  Timestamp: 2024-01-15 10:30:15
#  Monitoring Node: localhost:11000
# 
#  CURRENT LEADER
# ├─ Leader: node_10001
# ├─ Slot: 150
# ├─ Status:  Valid
# └─ Next Change: 1.2s
# 
#  UPCOMING LEADERS
# ├─ Slot 151: node_10002
# ├─ Slot 152: node_10000
# └─ Slot 153: node_10001

# Monitor specific node
python tools/leader_monitor.py --node-port 11001

# Single check (non-continuous)
python tools/leader_monitor.py --once

# Quick API test
./scripts/test_leader_apis.sh
```

### ** Log Overview**
```bash
# Tail logs for a node
tail -f logs/node1.log
```

### ** Performance Analysis**
```bash
# Run a comprehensive performance report
python tools/comprehensive_metrics.py
```

##  **Testing**

> ** See the [Transaction Testing Guide](#-sending-transactions--testing) above for comprehensive transaction testing instructions.**

### **Quick Testing Commands**
```bash
# Quick health check
curl http://localhost:11000/api/v1/health/

# Quick transaction test
python clients/test_sample_transaction.py

# Quick leader check  
python tools/leader_monitor.py --once
```

### **Test Categories Overview**

** Basic Tests:**
- **Node connectivity**: `curl` health endpoints
- **Key verification**: Check genesis and node keys exist
- **Leader selection**: Verify quantum consensus working

** Transaction Tests:**
- **Simple transaction**: `python clients/test_sample_transaction.py`
- **High-volume testing**: `python clients/send_100_transactions.py`
- **Gulf Stream forwarding**: `python tests/test_gulf_stream_transactions.py`

** Solana Component Tests:**
- **Complete pipeline**: `python tests/test_solana_validation.py`
- **PoH + Turbine**: `python tests/simple_turbine_test.py`
- **Gulf Stream**: `python tests/test_gulf_stream_fix.py`

** Performance Tests:**
- **TPS analysis**: `python tests/test_performance_metrics.py`
- **Comprehensive report**: `python tools/comprehensive_metrics.py`
- **Load testing**: Multi-threaded transaction submission
- **Latency analysis**: End-to-end timing measurements

##  **Configuration**

### **Node Configuration**
Modify node startup parameters in `start_nodes.sh`:
```bash
# Default configuration
NUM_NODES=5           # Number of nodes to start
PORT_START=10000      # Starting P2P port
API_START=11000       # Starting API port

# To start more nodes:
# Edit start_nodes.sh and change NUM_NODES=10
```

### **Consensus Configuration**  **ENHANCED**
Quantum consensus parameters in `blockchain/quantum_consensus/`:
- **Slot duration**: 2 seconds (configurable)
- **Leader lookahead**: 5 slots
- **Auto leader selection**: Starts 2 seconds after blockchain initialization
- **Continuous updates**: Leader schedule refreshed every 30 seconds
- **Dynamic discovery**: New nodes trigger immediate leader schedule updates
- **Quantum annealing parameters**: Tunable in quantum_consensus.py

### **Performance Tuning**
PoH and Sealevel parameters in their respective files:
```python
# In proof_of_history.py
self.ticks_per_second = 5000  # PoH frequency
self.max_entries_in_memory = 10000

# In sealevel.py  
self.thread_pool_size = 8  # Parallel execution threads
self.max_batch_size = 100  # Transaction batch size
```

##  **Docker Deployment**

### **Build Docker Image**
```bash
docker build -t quantum-blockchain .
```

### **Run Single Node**
```bash
docker run -p 10000:10000 -p 11000:11000 \
  -e NODE_PORT=10000 \
  -e API_PORT=11000 \
  quantum-blockchain
```

### **Run Multi-Node with Docker Compose**
```bash
# Use the provided docker-compose.yml
docker-compose up -d

# Scale to more nodes
docker-compose up -d --scale node=5
```

##  **API Reference**

### **Leader Selection Monitoring Endpoints**  **NEW**
The blockchain now provides comprehensive APIs for monitoring leader selection and consensus:

```bash
# Get current leader information
GET http://localhost:11000/api/v1/blockchain/leader/current/

# Response:
{
  "current_leader": "node_10001",
  "current_slot": 150,
  "leader_valid": true,
  "next_leader": "node_10002",
  "next_slot": 151,
  "time_until_next_slot": 1.2
}

# Get upcoming leader schedule
GET http://localhost:11000/api/v1/blockchain/leader/upcoming/

# Response:
{
  "upcoming_leaders": [
    {"slot": 151, "leader": "node_10002"},
    {"slot": 152, "leader": "node_10000"},
    {"slot": 153, "leader": "node_10001"}
  ],
  "current_slot": 150,
  "schedule_generated_at": "2024-01-15T10:30:00Z"
}

# Get quantum consensus selection details
GET http://localhost:11000/api/v1/blockchain/leader/quantum-selection/

# Response:
{
  "quantum_enabled": true,
  "selection_method": "quantum_annealing",
  "last_selection_time": "2024-01-15T10:29:58Z",
  "participants": ["node_10000", "node_10001", "node_10002"],
  "selection_success": true
}

# Get complete leader schedule with timing
GET http://localhost:11000/api/v1/blockchain/leader/schedule/

# Response:
{
  "total_slots": 10,
  "slot_duration": 2.0,
  "current_slot": 150,
  "schedule": [
    {
      "slot": 150,
      "leader": "node_10001",
      "status": "active",
      "start_time": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### **Leader Monitoring Tools**  **NEW**
Enhanced monitoring capabilities with automated tools:

```bash
# Continuous leader monitoring (Python script)
python tools/leader_monitor.py

# Monitor specific node
python tools/leader_monitor.py --node-port 11001

# Single-time check
python tools/leader_monitor.py --once

# Quick API test (Bash script)
./scripts/test_leader_apis.sh

# API testing with specific node
./scripts/test_leader_apis.sh 11002
```

### **Blockchain Endpoints**
```bash
# Get blockchain status
GET http://localhost:11000/api/v1/blockchain/

# Get specific block
GET http://localhost:11000/api/v1/blockchain/block/{block_index}

# Get node statistics
GET http://localhost:11000/api/v1/blockchain/node-stats/
```

### **Transaction Endpoints**
```bash
# Submit transaction
POST http://localhost:11000/api/v1/transaction/create/
Content-Type: application/json
{
  "transaction": "<base64_encoded_transaction>"
}

# Get transaction pool status
GET http://localhost:11000/api/v1/blockchain/mempool/
```

### **Health Check**
```bash
# Node health status
GET http://localhost:11000/api/v1/health/

# Expected response:
{
  "status": "healthy",
  "node_id": "node_10000",
  "uptime": "0:05:23",
  "consensus": "active",
  "poh_ticks": 1500000,
  "blocks": 42
}
```

##  **Troubleshooting**

> ** See the [Transaction Troubleshooting Guide](#-troubleshooting-transactions) above for detailed transaction debugging.**

### **Quick Diagnostic Commands**
```bash
# Check node health
curl http://localhost:11000/api/v1/health/

# Check leader status
python tools/leader_monitor.py --once

# Check transaction pool
curl http://localhost:11000/api/v1/transaction/transaction_pool/ | jq '. | length'

# Check recent blocks
curl http://localhost:11000/api/v1/blockchain/ | jq '.blocks[-3:] | length'
```

### **Common Issues**

#### **Port Already in Use**
```bash
# Check what's using the port
lsof -i :10000

# Kill existing processes
pkill -f 'run_node.py'

# Start fresh
./start_nodes.sh
```

#### **Key Generation Fails**
```bash
# Ensure OpenSSL is installed
openssl version

# Regenerate keys
rm keys/*.pem
./scripts/generate_keys.sh
```

#### **Nodes Not Connecting**
```bash
# Check node logs
tail -n 200 logs/node1.log

# Verify network connectivity
curl http://localhost:11000/api/v1/health/
```

#### **Transaction Not Included in Blocks**
```bash
# Check current leader
curl http://localhost:11000/api/v1/blockchain/leader/current/ | jq

# Check pending transactions
curl http://localhost:11000/api/v1/transaction/transaction_pool/ | jq '. | length'

# Check recent blocks
curl http://localhost:11000/api/v1/blockchain/ | jq '.blocks[-3:] | length'

# Detailed leader monitoring
python tools/leader_monitor.py 11000 1 --detailed
```

#### **Leader Selection Issues**  **NEW**
```bash
# Leader not being selected
curl http://localhost:11000/api/v1/blockchain/leader/current/

# If no leader, check quantum consensus
curl http://localhost:11000/api/v1/blockchain/leader/quantum-selection/

# Monitor leader selection process
python tools/leader_monitor.py --once

# Check if nodes are properly connected
curl http://localhost:11000/api/v1/health/ | jq '.consensus'
```

#### **Leader Selection Not Starting**
```bash
# Ensure auto-start is working (should start within 2-3 seconds)
# Check node logs for leader selection initialization
tail -n 200 logs/node1.log

# Manually trigger if needed (shouldn't be necessary)
# Leader selection now starts automatically on network startup
```
#### **Poor Performance**
```bash
# Check system resources
htop

# Generate a performance report
python tools/comprehensive_metrics.py

# Monitor leader selection performance
python tools/leader_monitor.py

# Tune configuration parameters
# Edit blockchain/consensus/ configuration files
```

### **Debug Mode**
```bash
# Start with debug logging
export LOG_LEVEL=DEBUG
python run_node.py --ip localhost --node_port 10000 --api_port 11000

# View debug logs
tail -n 200 -f logs/node1.log
```

##  **Performance Benchmarks**

### **Expected Performance**  **UPDATED**
Based on testing with 5 nodes on modern hardware:

| Metric | Value | Notes |
|--------|-------|-------|
| **Transaction Submission** | 272+ TPS | API submission rate |
| **PoH Tick Rate** | 5,000/sec | Cryptographic clock |
| **Consensus Time** | 2-15 seconds | Leader selection + block creation |
| **Leader Selection Startup** | 2-3 seconds | NEW: Automatic on network start |
| **Leader Schedule Updates** | Every 30 seconds | NEW: Continuous background updates |
| **Sealevel Threads** | 8 parallel | Configurable |
| **Block Size** | Unlimited | Removed artificial limits |
| **Network Latency** | <10ms | Localhost testing |
| **Leader API Response** | <50ms | NEW: Real-time leader monitoring |

### **Scaling Considerations**
- **Vertical scaling**: Increase `ticks_per_second`, `thread_pool_size`
- **Horizontal scaling**: Add more nodes (tested up to 10 nodes)
- **Network optimization**: Tune Turbine fanout and shred sizes
- **Storage optimization**: Implement block pruning for long-running deployments

##  **Development**

### **Code Structure**  **UPDATED**
```
blockchain/
├── blockchain/           # Core implementation
│   ├── consensus/       # PoH, Sealevel, Turbine
│   ├── quantum_consensus/ # Quantum leader selection
│   ├── transaction/     # Transaction processing
│   ├── p2p/            # P2P networking
│   └── utils/          # Enhanced logging & utilities
├── api/                # FastAPI endpoints + leader monitoring APIs
│   └── api_v1/
│       └── blockchain/
│           └── views.py # NEW: Leader selection endpoints
├── clients/            # Client scripts (transaction submitters)
├── scripts/            # Shell scripts
├── tests/              # Test scripts
├── tools/              # Diagnostics and ops tools
├── docs/               # Documentation
├── keys/               # Cryptographic keys
├── logs/               # Enhanced logging output
└── genesis_config/     # Genesis file + bootstrap keys
```

### **Adding New Features**  **UPDATED**
1. **New consensus mechanism**: Extend `blockchain/consensus/`
2. **New transaction types**: Modify `blockchain/transaction/`
3. **New APIs**: Add endpoints in `api/` (see leader monitoring APIs as example)
4. **New monitoring**: Add scripts under `tools/` or `monitoring/`
5. **Leader selection enhancements**: Modify `blockchain/quantum_consensus/`

### **Contributing**
1. Fork the repository
2. Create feature branch: `git checkout -b feature/new-feature`
3. Add tests for new functionality
4. Ensure all tests pass: `python tests/test_solana_validation.py`
5. Submit pull request

##  **Additional Resources**

### **Documentation**  **UPDATED**
- **[blockchain/docs/LEADER_MONITORING_GUIDE.md](blockchain/docs/LEADER_MONITORING_GUIDE.md)** - Leader monitoring API guide
- **[blockchain/docs/LEADER_SCHEDULE_GUIDE.md](blockchain/docs/LEADER_SCHEDULE_GUIDE.md)** - Leader schedule guide

### **Architecture References**
- **Solana Whitepaper**: Proof of History and parallel processing concepts
- **Quantum Computing**: D-Wave quantum annealing for consensus
- **Byzantine Fault Tolerance**: Enhanced with quantum consensus

##  **License**

This project is licensed under the MIT License - see the LICENSE file for details.

### **Support**  **ENHANCED**

- **Issues**: Report bugs and request features via GitHub Issues
- **Monitoring**: Tail logs (e.g. `tail -f logs/node1.log`)
- **Leader Selection**: Use `python tools/leader_monitor.py` for real-time leader monitoring
- **API Testing**: Use `./scripts/test_leader_apis.sh` for quick API verification
- **Documentation**: See `docs/LEADER_MONITORING_GUIDE.md` for complete API documentation

---

** Ready to build the future of quantum-enhanced blockchain technology!**

##  **Latest Updates**

### **v2.1 - Comprehensive Transaction Testing & Health-Based Consensus**
-  **Complete Transaction Guide**: Step-by-step instructions for creating, signing, and submitting transactions
-  **Enhanced Testing Suite**: Multiple testing patterns for different use cases and load scenarios
-  **Transaction Troubleshooting**: Detailed debugging guide for common transaction issues
-  **Health-Based Voting**: Consensus now prioritizes healthy nodes over stake weights (100% Solana compliant)
-  **Performance Metrics**: Detailed transaction processing benchmarks and monitoring
-  **API Examples**: Complete Python and curl examples for transaction submission

### **v2.0 - Enhanced Leader Selection & Monitoring**
-  **Automatic Leader Selection**: Leaders selected immediately on network startup (2-3 seconds)
-  **Real-time Monitoring APIs**: 4 new endpoints for comprehensive leader monitoring
-  **Continuous Updates**: Leader schedules refreshed every 30 seconds automatically  
-  **Dynamic Discovery**: New nodes trigger immediate leader schedule updates
-  **Monitoring Tools**: Python and bash scripts for real-time leader tracking
-  **Complete Documentation**: `docs/LEADER_MONITORING_GUIDE.md` with examples and integration patterns

### **Key Features Added**
**v2.1 Transaction & Testing Enhancements:**
1. **Transaction Guide**: Complete walkthrough from wallet creation to blockchain confirmation
2. **Testing Patterns**: Simple self-transfer, multi-node, high-volume, and load testing examples
3. **API Integration**: Python and curl examples for direct transaction submission
4. **Performance Benchmarks**: Detailed metrics for transaction processing stages
5. **Troubleshooting Tools**: Comprehensive debugging guide for transaction issues
6. **Health-Based Consensus**: Voting system prioritizes node health over economic stake

**v2.0 Leader Selection & Monitoring:**
1. **API Endpoints**: `/leader/current/`, `/leader/upcoming/`, `/leader/quantum-selection/`, `/leader/schedule/`
2. **Monitoring Tools**: `tools/leader_monitor.py`, `tests/api_test.py`, `scripts/test_leader_apis.sh`
3. **Auto-start**: No waiting for transactions - leader selection begins immediately
4. **Background Processing**: Continuous 30-second updates maintain fresh schedules
5. **Network Intelligence**: Auto-discovery triggers dynamic leader updates

 **Note**: This is a research and demonstration project. Not intended for production use.

---

##  **Quick Reference**

### **Essential Commands**
```bash
# Start the network
./start_nodes.sh

# Test transaction submission (NEW - recommended for beginners)
python clients/simple_transaction_example.py

# Alternative transaction tests
python clients/test_sample_transaction.py

# Monitor leaders
python tools/leader_monitor.py --once

# Check node health
curl http://localhost:11000/api/v1/health/

# View blockchain status
curl http://localhost:11000/api/v1/blockchain/ | jq '.blocks | length'

# Submit custom transaction (see Transaction Guide above)
curl -X POST http://localhost:11000/api/v1/transaction/create/ \
  -H "Content-Type: application/json" \
  -d '{"transaction": "<base64_encoded_transaction>"}'
```

### **Key URLs**
- **Node API**: `http://localhost:11000-11004/api/v1/`
- **Health Check**: `/api/v1/health/`
- **Blockchain Status**: `/api/v1/blockchain/`
- **Submit Transaction**: `/api/v1/transaction/create/`
- **Leader Status**: `/api/v1/blockchain/leader/current/`
- **Transaction Pool**: `/api/v1/transaction/transaction_pool/`

### **Important Files**
- **Keys**: `keys/genesis_*_key.pem` (for testing)
- **Start Script**: `./start_nodes.sh`
- **Transaction Examples**: `clients/simple_transaction_example.py`, `clients/test_sample_transaction.py`, `clients/send_100_transactions.py`
- **Monitoring**: `tools/leader_monitor.py`, `tools/comprehensive_metrics.py`, `logs/node*.log`
