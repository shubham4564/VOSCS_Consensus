# Blockchain Validation Tests

This directory contains validation tests for the blockchain network. These tests are designed to validate running blockchain nodes and verify various aspects of the system.

## Available Validation Tests

### 1. Leader Schedule Validator (`leader_schedule_validator.py`)

**Purpose**: Real-time monitoring and validation of the leader schedule system.

**What it validates**:
- How many leaders are currently chosen
- Real-time leader rotation 
- Epoch transitions (every 2 minutes)
- Gulf Stream transaction forwarding status
- Node connectivity and health

**Features**:
-  Monitors multiple nodes simultaneously (ports 11000-11009)
-  Real-time leader schedule display
-  Detects leader changes and epoch transitions
-  Tracks validation statistics
-  Configurable update intervals
-  Gulf Stream protocol status

**Usage**:
```bash
# Run leader schedule validation
python3 leader_schedule_validator.py

# Or using the test runner
python3 validate.py leader-schedule
```

## Test Runner (`validate.py`)

Convenient script to run validation tests with options.

**Usage**:
```bash
# List available tests
python3 validate.py list

# Run leader schedule validation
python3 validate.py leader-schedule

# Run with custom update interval (default: 2.0 seconds)
python3 validate.py leader-schedule --update-interval 1.0

# Run all validation tests
python3 validate.py all
```

## Prerequisites

### Running Nodes
The validation tests assume that blockchain nodes are already running. Start nodes using:

```bash
# Start multiple nodes
./start_nodes.sh

# Or start individual nodes
python3 run_node.py --ip 0.0.0.0 --node_port 10000 --api_port 11000 --key_file keys/genesis_private_key.pem
python3 run_node.py --ip 0.0.0.0 --node_port 10001 --api_port 11001 --key_file keys/node2_private_key.pem
# ... etc
```

### Dependencies
The validation tests require:
- `aiohttp` for async HTTP requests
- `asyncio` for concurrent operations
- Standard blockchain modules

Install dependencies:
```bash
pip install aiohttp
```

## Expected Output

### Leader Schedule Validator

When running, you'll see real-time output like:

```
 REAL-TIME LEADER SCHEDULE VALIDATION
================================================================================
 Started: 2025-07-26 14:30:00
 Monitoring nodes: 10 nodes (ports 11000-11009)
 Epoch duration: 120s (2 minutes)
 Slot duration: 2s
 Total slots per epoch: 60
================================================================================

 NODES STATUS (8/10 online)
──────────────────────────────────────────────────
 Online Nodes:
   Port 11000: Ready
   Port 11001: Ready
   Port 11002: Ready
   Port 11003: Ready
   Port 11004: Ready
   ... and 3 more
 Offline Nodes:
   Port 11008: timeout (Connection timeout)
   Port 11009: offline (Connection refused)

 CURRENT LEADER INFORMATION
──────────────────────────────────────────────────
 Current Slot: 15
 Current Leader: -----BEGIN PUBLIC KEY-----MII...
 Epoch Progress: 15/60
  Time in Slot: 1.2s / 2s

 UPCOMING LEADERS (Next 5 slots):
   1. Slot 16: -----BEGIN PUBLIC KE... (in 0.8s)
   2. Slot 17: -----BEGIN PUBLIC KE... (in 2.8s)
   3. Slot 18: -----BEGIN PUBLIC KE... (in 4.8s)
   4. Slot 19: -----BEGIN PUBLIC KE... (in 6.8s)
   5. Slot 20: -----BEGIN PUBLIC KE... (in 8.8s)

 GULF STREAM STATUS
──────────────────────────────────
 Transactions Forwarded: 42
 Active Forwarding Pools: 5
  Average Forward Time: 15.3ms
 Forward Success Rate: 98.5%

 VALIDATION STATISTICS
──────────────────────────────────
  Runtime: 125.3s
 Total Checks: 62
 Successful Connections: 496
 Leader Changes: 7
 Epoch Transitions: 1
 Connection Success Rate: 80.0%

 Last Updated: 14:32:05 (Press Ctrl+C to stop)
================================================================================
```

## Adding New Validation Tests

To add a new validation test:

1. Create a new Python file in this directory
2. Implement your validation logic
3. Add the test to `validate.py` in the `run_all_validations()` function
4. Update this README with documentation

### Template for New Validation Test

```python
#!/usr/bin/env python3
"""
New Validation Test Template
"""

import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

class NewValidator:
    def __init__(self):
        # Initialize your validator
        pass
    
    def run_validation(self):
        # Implement validation logic
        print(" Running new validation...")
        # Your validation code here
        return True  # Return success/failure

def main():
    validator = NewValidator()
    return validator.run_validation()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
```

## Troubleshooting

### Common Issues

1. **No nodes responding**: Ensure nodes are started and running on expected ports
2. **Connection timeouts**: Check network connectivity and firewall settings
3. **Import errors**: Ensure you're running from the correct directory with proper PYTHONPATH

### Debug Mode

For detailed debugging, modify the validation tests to include more verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Real-Time Monitoring Features

The leader schedule validator provides:

- **Live Updates**: Screen refreshes every 2 seconds (configurable)
- **Change Detection**: Highlights when leaders change or epochs transition
- **Health Monitoring**: Shows which nodes are online/offline
- **Performance Metrics**: Tracks connection success rates and timing
- **Gulf Stream Status**: Monitors transaction forwarding efficiency

## Integration with CI/CD

These validation tests can be integrated into automated testing pipelines:

```bash
# Run validation as part of automated testing
python3 validate.py all
echo "Exit code: $?"
```

The tests return appropriate exit codes (0 for success, 1 for failure) for automation compatibility.
