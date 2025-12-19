#!/bin/bash

# Start N blockchain nodes with different ports and keys
# Usage: ./start_10_nodes.sh [NUMBER_OF_NODES]
# Default: 10 nodes if no parameter provided
# Node ports: 10000-1000N (P2P communication)
# API ports: 11000-1100N (HTTP REST API)
# TPU ports: 13000-1300N (UDP Transaction Processing Unit for Gulf Stream)

# Get number of nodes from command line argument, default to 10
NUM_NODES=${1:-10}

# Validate input
if ! [[ "$NUM_NODES" =~ ^[0-9]+$ ]] || [ "$NUM_NODES" -lt 1 ] || [ "$NUM_NODES" -gt 1000 ]; then
    echo "❌ Error: Please provide a valid number of nodes (1-1000)"
    echo "Usage: $0 [NUMBER_OF_NODES]"
    echo "Example: $0 5    # Start 5 nodes"
    echo "Example: $0      # Start 10 nodes (default)"
    exit 1
fi

echo "Starting $NUM_NODES blockchain nodes..."

# Write a shared cluster start time so all nodes compute identical slot/epoch boundaries.
python3 - <<'PY'
import json, os, time
os.makedirs('genesis_config', exist_ok=True)
path = os.path.join('genesis_config', 'cluster_start_time.json')
payload = {'epoch_start_time': time.time()}
with open(path, 'w', encoding='utf-8') as f:
    json.dump(payload, f)
print(f"🕒 Wrote shared epoch_start_time to {path}: {payload['epoch_start_time']}")
PY

# Kill any existing python processes for clean start
pkill -f "run_node.py" 2>/dev/null || true
sleep 2

# Function to start a node
start_node() {
    local node_num=$1
    local node_port=$((10000 + node_num - 1))
    local api_port=$((11000 + node_num - 1))
    local key_file="keys/node${node_num}_private_key.pem"
    
    # Use genesis key for node 1, or generate/use existing keys for other nodes
    if [ $node_num -eq 1 ]; then
        key_file="keys/genesis_private_key.pem"
    elif [ ! -f "$key_file" ]; then
        # If node key doesn't exist, use staker key as fallback
        if [ -f "keys/staker_private_key.pem" ]; then
            key_file="keys/staker_private_key.pem"
        else
            echo "⚠️  Warning: Key file $key_file not found, using genesis key as fallback"
            key_file="keys/genesis_private_key.pem"
        fi
    fi
    
    echo "Starting Node $node_num - Port: $node_port, API: $api_port, Key: $key_file"
    
    python run_node.py \
        --ip 0.0.0.0 \
        --node_port $node_port \
        --api_port $api_port \
        --key_file $key_file \
        > logs/node${node_num}.log 2>&1 &
    
    echo "Node $node_num started with PID $!"
}

# Create logs directory if it doesn't exist
mkdir -p logs

# Start all nodes
echo "🚀 Launching $NUM_NODES nodes..."
for i in $(seq 1 $NUM_NODES); do
    start_node $i
    sleep 1  # Small delay between node starts
done

echo ""
echo "✅ All $NUM_NODES nodes started!"
echo "📡 Node ports: 10000-$((10000 + NUM_NODES - 1))"
echo "🌐 API ports: 11000-$((11000 + NUM_NODES - 1))"
echo "⚡ TPU ports: 13000-$((13000 + NUM_NODES - 1))"
echo "📝 Logs: logs/node1.log - logs/node${NUM_NODES}.log"
echo ""
echo "⏳ Wait 10 seconds for nodes to initialize and connect..."
sleep 10

echo "🔗 Bootstrapping P2P + gossip peer connections..."
python3 tools/bootstrap_network.py || true

echo "🔍 Checking node status..."
active_nodes=0
active_apis=0
active_tpus=0

for i in $(seq 1 $NUM_NODES); do
    node_port=$((10000 + i - 1))
    api_port=$((11000 + i - 1))
    tpu_port=$((13000 + i - 1))
    
    echo -n "Node $i: "
    
    # Check API endpoint
    api_status="❌"
    if curl -s "http://localhost:$api_port/api/v1/blockchain/" >/dev/null 2>&1; then
        api_status="✅"
        ((active_apis++))
        ((active_nodes++))
    fi
    
    # Check TPU port (UDP port check)
    tpu_status="❌"
    if command -v nc >/dev/null 2>&1; then
        # Use netcat to check if UDP port is listening
        if nc -u -z localhost $tpu_port >/dev/null 2>&1; then
            tpu_status="✅"
            ((active_tpus++))
        elif lsof -i :$tpu_port >/dev/null 2>&1; then
            # Fallback: check if any process is using the port
            tpu_status="✅"
            ((active_tpus++))
        fi
    else
        # Fallback: use lsof if netcat is not available
        if lsof -i :$tpu_port >/dev/null 2>&1; then
            tpu_status="✅"
            ((active_tpus++))
        fi
    fi
    
    echo "API($api_port): $api_status | TPU($tpu_port): $tpu_status"
done

echo ""
echo "📊 Network Summary:"
echo "   🌐 Total Nodes Configured: $NUM_NODES"
echo "   ✅ Active APIs: $active_apis/$NUM_NODES"
echo "   ⚡ Active TPUs: $active_tpus/$NUM_NODES"
echo "   📡 Overall Health: $active_nodes/$NUM_NODES nodes responding"

if command -v bc >/dev/null 2>&1; then
    health_pct=$(echo "scale=1; $active_nodes * 1000 / $NUM_NODES" | bc -l 2>/dev/null || echo "0")
    tpu_health_pct=$(echo "scale=1; $active_tpus * 1000 / $NUM_NODES" | bc -l 2>/dev/null || echo "0")
    echo "   📈 API Health: ${health_pct}%"
    echo "   ⚡ TPU Health: ${tpu_health_pct}%"
else
    echo "   📈 API Health: $active_apis/$NUM_NODES"
    echo "   ⚡ TPU Health: $active_tpus/$NUM_NODES"
fi

if [ $active_nodes -eq $NUM_NODES ] && [ $active_tpus -eq $NUM_NODES ]; then
    echo "   🎉 Perfect! All nodes and TPU listeners are running successfully."
elif [ $active_nodes -eq $NUM_NODES ] && [ $active_tpus -lt $NUM_NODES ]; then
    echo "   ⚠️  All APIs running, but some TPU listeners not active. Leaders may not be processing immediate transactions."
elif [ $active_nodes -gt 0 ]; then
    echo "   ⚠️  Some nodes/services failed to start. Check logs for details."
else
    echo "   ❌ No nodes are responding. Check configuration and logs."
fi

echo ""
echo "💡 Useful commands:"
echo "   🧪 Run transactions: python3 clients/test_sample_transaction.py --count 10"
echo "   💬 Interactive transaction: python3 clients/simple_transaction_example.py"
echo "   ⚡ Test TPU Gulf Stream: python3 tests/test_tpu_gulf_stream.py"
echo "   📊 Performance metrics: python3 tools/comprehensive_metrics.py"
echo "   🔍 Check TPU status: bash scripts/check_tpu_status.sh"
echo "   🔍 Check TPU ports: lsof -i :13000-13009"
echo "   🛑 Stop all nodes: pkill -f 'run_node.py'"
