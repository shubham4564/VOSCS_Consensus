# Leader Selection Monitoring API Guide

This guide shows you exactly how to monitor current and upcoming leaders through the blockchain API endpoints.

## 🎯 Available API Endpoints

### 1. Current Leader Information
**Endpoint:** `GET /api/v1/blockchain/leader/current/`

**What it tells you:**
- Who is the current leader (if any)
- Current slot number and timing
- Whether this node is the current leader
- Network consensus status

**Example:**
```bash
curl http://localhost:11001/api/v1/blockchain/leader/current/
```

**Response fields:**
```json
{
  "current_leader_info": {
    "current_leader": "-----BEGIN PUBLIC KEY-----\nMII...",  // Current leader's public key
    "current_slot": 157,                                      // Current slot number
    "slot_duration": 2,                                       // Slot duration in seconds
    "time_remaining_in_slot": 0.4,                           // Time left in current slot
    "slot_start_time": 1737988451.123,                       // Slot start timestamp
    "slot_end_time": 1737988453.123,                         // Slot end timestamp
    "upcoming_leaders": []                                    // Next 5 leaders
  },
  "consensus_context": {
    "total_nodes": 2,                                         // Total nodes in consensus
    "active_nodes": 0,                                        // Currently active nodes
    "gossip_peers": 3                                         // Connected gossip peers
  },
  "am_i_current_leader": false,                              // Whether this node is leader
  "node_public_key": "-----BEGIN PUBLIC KEY-----\nMII...",  // This node's public key
  "timestamp": 1737988453.123                                // Response timestamp
}
```

### 2. Upcoming Leaders Schedule
**Endpoint:** `GET /api/v1/blockchain/leader/upcoming/`

**What it tells you:**
- Future leaders and their slot assignments
- Whether this node has upcoming leadership
- Leader schedule timing information

**Example:**
```bash
curl http://localhost:11001/api/v1/blockchain/leader/upcoming/
```

**Response fields:**
```json
{
  "upcoming_leaders": [                                       // Array of upcoming leaders
    {
      "leader": "-----BEGIN PUBLIC KEY-----\nMII...",        // Leader's public key
      "slot": 160,                                            // Slot number
      "time_until_slot": 45.2                                // Seconds until this slot
    }
  ],
  "schedule_size": 5,                                         // Number of upcoming slots
  "my_upcoming_leadership": {                                 // This node's next leadership (if any)
    "slot": 165,
    "time_until_slot": 120.5
  },
  "leader_schedule_epoch": 0,                                 // Current epoch
  "slot_duration_seconds": 2,                                 // Slot duration
  "current_slot": 157,                                        // Current slot number
  "schedule_advance_time": 120                                // Leaders known 2 minutes in advance
}
```

### 3. Quantum Leader Selection Details
**Endpoint:** `GET /api/v1/blockchain/leader/quantum-selection/`

**What it tells you:**
- Quantum consensus selection mechanism status
- Node scores and selection probability
- Next quantum-selected proposer

**Example:**
```bash
curl http://localhost:11001/api/v1/blockchain/leader/quantum-selection/
```

**Response fields:**
```json
{
  "quantum_consensus_enabled": true,                          // Whether quantum consensus is active
  "next_quantum_proposer": "-----BEGIN PUBLIC KEY-----...", // Next quantum-selected leader
  "node_scores": {                                           // All node scores
    "-----BEGIN PUBLIC KEY-----...": {
      "suitability_score": 0.5,                             // Base suitability score
      "effective_score": 0.500002,                          // Final selection score
      "uptime": 1.0,                                         // Uptime percentage
      "latency": 0.1,                                        // Average latency
      "throughput": 100.0,                                   // Throughput score
      "proposals_success": 1,                                // Successful proposals
      "proposals_failed": 0                                  // Failed proposals
    }
  },
  "total_registered_nodes": 2,                               // Total nodes in consensus
  "active_nodes": 0,                                         // Currently active nodes
  "protocol_parameters": {                                   // Consensus parameters
    "max_delay_tolerance": 30.0,
    "block_proposal_timeout": 60.0,
    "witness_quorum_size": 3,
    "penalty_coefficient": 1000.0
  }
}
```

### 4. Full Leader Schedule
**Endpoint:** `GET /api/v1/blockchain/leader/schedule/`

**What it tells you:**
- Complete current and next epoch schedules
- Slot assignments for all leaders
- Schedule timing and epoch information

**Example:**
```bash
curl http://localhost:11001/api/v1/blockchain/leader/schedule/
```

### 5. General Quantum Metrics
**Endpoint:** `GET /api/v1/blockchain/quantum-metrics/`

**What it tells you:**
- Overall consensus health
- Node scores and gossip status
- Protocol parameters

**Example:**
```bash
curl http://localhost:11001/api/v1/blockchain/quantum-metrics/
```

## 🔧 Testing Tools

### 1. Quick Manual Testing
```bash
# Test basic connectivity
curl http://localhost:11001/api/v1/blockchain/quantum-metrics/

# Check current leader
curl http://localhost:11001/api/v1/blockchain/leader/current/

# Check upcoming leaders
curl http://localhost:11001/api/v1/blockchain/leader/upcoming/

# Check quantum selection
curl http://localhost:11001/api/v1/blockchain/leader/quantum-selection/
```

### 2. Automated Testing Scripts

**Python Script:** `tests/runtime_validation/api_test.py`
```bash
# Test single node
python tests/runtime_validation/api_test.py 11001

# Test multiple nodes
python tests/runtime_validation/api_test.py 11001 3
```

**Bash Script:** `scripts/test_leader_apis.sh`
```bash
# Test across multiple nodes
./scripts/test_leader_apis.sh 11000 3
```

**Comprehensive Monitor:** `tools/operational_support/leader_monitor.py`
```bash
# Single monitoring run
python tools/operational_support/leader_monitor.py 11000 3 --detailed

# Continuous monitoring
python tools/operational_support/leader_monitor.py 11000 3 --continuous --interval 10
```

## 📊 Understanding the Results

### Leader Selection Status
- **Current Leader: None** = No leader currently assigned (schedule empty)
- **Current Leader: [Public Key]** = Active leader for current slot
- **Am I Leader: true** = This node is the current leader
- **Am I Leader: false** = This node is not the current leader

### Network Health
- **Total Nodes: X** = Nodes registered in consensus system
- **Active Nodes: X** = Nodes currently participating
- **Gossip Peers: X** = Connected gossip protocol peers

### Timing Information
- **Current Slot: X** = Current slot number in the epoch
- **Time Remaining: Xs** = Seconds left in current slot
- **Slot Duration: Xs** = Length of each slot (typically 2 seconds)

### Quantum Selection
- **Quantum Enabled: true** = Quantum consensus is working
- **Node Scores** = Selection probability based on performance
- **Next Proposer** = Quantum-selected next block proposer

## 🎯 Common Use Cases

### 1. Check if Leaders are Being Selected
```bash
curl http://localhost:11001/api/v1/blockchain/leader/current/ | grep current_leader
```

### 2. Monitor Network Health
```bash
curl http://localhost:11001/api/v1/blockchain/quantum-metrics/ | grep total_nodes
```

### 3. Check Node's Leadership Status
```bash
curl http://localhost:11001/api/v1/blockchain/leader/current/ | grep am_i_current_leader
```

### 4. Monitor Upcoming Leadership
```bash
curl http://localhost:11001/api/v1/blockchain/leader/upcoming/ | grep my_upcoming_leadership
```

### 5. Continuous Monitoring
```bash
# Monitor every 10 seconds
watch -n 10 'curl -s http://localhost:11001/api/v1/blockchain/leader/current/ | python3 -m json.tool'
```

## 🚨 Troubleshooting

### No Leaders Assigned
- **Check:** `total_nodes` in quantum-metrics
- **Fix:** Ensure nodes are registered in consensus
- **Fix:** Update leader schedule with `update_leader_schedule()`

### Node Not Becoming Leader
- **Check:** Node scores in quantum-selection API
- **Check:** `am_i_upcoming_leader` status
- **Fix:** Improve node performance metrics

### API Not Responding
- **Check:** Node is running on expected port
- **Check:** API server is started
- **Fix:** Restart node or check logs

## 📝 Integration Examples

### Python Integration
```python
import requests

def get_current_leader(node_port=11001):
    response = requests.get(f"http://localhost:{node_port}/api/v1/blockchain/leader/current/")
    if response.status_code == 200:
        data = response.json()
        leader_info = data.get('current_leader_info', {})
        return {
            'leader': leader_info.get('current_leader'),
            'slot': leader_info.get('current_slot'),
            'am_i_leader': data.get('am_i_current_leader', False)
        }
    return None

# Usage
leader_status = get_current_leader()
if leader_status:
    print(f"Current Leader: {leader_status['leader']}")
    print(f"Current Slot: {leader_status['slot']}")
    print(f"Am I Leader: {leader_status['am_i_leader']}")
```

### JavaScript Integration
```javascript
async function getCurrentLeader(nodePort = 11001) {
    try {
        const response = await fetch(`http://localhost:${nodePort}/api/v1/blockchain/leader/current/`);
        const data = await response.json();
        return {
            leader: data.current_leader_info?.current_leader,
            slot: data.current_leader_info?.current_slot,
            amILeader: data.am_i_current_leader
        };
    } catch (error) {
        console.error('Error fetching leader info:', error);
        return null;
    }
}

// Usage
getCurrentLeader().then(status => {
    if (status) {
        console.log(`Current Leader: ${status.leader}`);
        console.log(`Current Slot: ${status.slot}`);
        console.log(`Am I Leader: ${status.amILeader}`);
    }
});
```
