#!/bin/bash

# Simple Bash Script to Test Leader Selection APIs
# Usage: ./scripts/test_leader_apis.sh [base_port] [num_nodes]

BASE_PORT=${1:-11000}
NUM_NODES=${2:-3}

echo "🔍 TESTING LEADER SELECTION APIs"
echo "Base Port: $BASE_PORT, Nodes: $NUM_NODES"
echo "=========================================="

# Test each node
for ((i=0; i<$NUM_NODES; i++)); do
    PORT=$((BASE_PORT + i))
    NODE_NUM=$((i + 1))
    
    echo ""
    echo "📡 Node $NODE_NUM (Port $PORT):"
    
    # Test basic connectivity
    if curl -s --connect-timeout 2 "http://localhost:$PORT/api/v1/blockchain/quantum-metrics/" > /dev/null; then
        echo "   ✅ Node is online"
        
        # Test Current Leader API
        echo "   🎯 Current Leader Info:"
        curl -s "http://localhost:$PORT/api/v1/blockchain/leader/current/" | \
        python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    leader_info = data.get('current_leader_info', {})
    consensus = data.get('consensus_context', {})
    print(f'      Leader: {leader_info.get(\"current_leader\", \"None\")}')
    print(f'      Slot: {leader_info.get(\"current_slot\", \"Unknown\")}')
    print(f'      Time Left: {leader_info.get(\"time_remaining_in_slot\", 0):.1f}s')
    print(f'      Am I Leader: {data.get(\"am_i_current_leader\", False)}')
    print(f'      Total Nodes: {consensus.get(\"total_nodes\", 0)}')
except Exception as e:
    print(f'      Error: {e}')
"
        
        # Test Quantum Selection API
        echo "   🔮 Quantum Selection:"
        curl -s "http://localhost:$PORT/api/v1/blockchain/leader/quantum-selection/" | \
        python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f'      Quantum Enabled: {data.get(\"quantum_consensus_enabled\", False)}')
    print(f'      Next Proposer: {data.get(\"next_quantum_proposer\", \"None\")[:30]}...')
    print(f'      Node Scores: {len(data.get(\"node_scores\", {}))}')
    print(f'      Active Nodes: {data.get(\"active_nodes\", 0)}')
except Exception as e:
    print(f'      Error: {e}')
"
        
    else
        echo "   ❌ Node is offline"
    fi
done

echo ""
echo "💡 Manual API Testing Examples:"
echo ""
echo "# Get current leader info:"
echo "curl http://localhost:11001/api/v1/blockchain/leader/current/"
echo ""
echo "# Get upcoming leaders:"
echo "curl http://localhost:11001/api/v1/blockchain/leader/upcoming/"
echo ""
echo "# Get quantum selection details:"
echo "curl http://localhost:11001/api/v1/blockchain/leader/quantum-selection/"
echo ""
echo "# Get full leader schedule:"
echo "curl http://localhost:11001/api/v1/blockchain/leader/schedule/"
echo ""
echo "# Get quantum metrics:"
echo "curl http://localhost:11001/api/v1/blockchain/quantum-metrics/"
