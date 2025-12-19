#!/bin/bash

# Quick TPU status checker based on our updated start_nodes.sh logic
# This checks the currently running nodes for API and TPU port status

echo "🔍 Checking current node status (API + TPU ports)..."

NUM_NODES=4  # Check first 4 nodes that we know are running
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
    fi
    
    # Check TPU port (UDP port check with actual test)
    tpu_status="❌"
    if python3 -c "
import socket
import json
import sys
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)
    test_data = {'test': 'tpu_check'}
    sock.sendto(json.dumps(test_data).encode(), ('127.0.0.1', $tpu_port))
    sock.close()
    print('TPU_RESPONSIVE')
    sys.exit(0)
except:
    sys.exit(1)
" 2>/dev/null | grep -q "TPU_RESPONSIVE"; then
        tpu_status="✅"
        ((active_tpus++))
    fi
    
    echo "API($api_port): $api_status | TPU($tpu_port): $tpu_status"
done

echo ""
echo "📊 Status Summary:"
echo "   ✅ Active APIs: $active_apis/$NUM_NODES"
echo "   ⚡ Active TPUs: $active_tpus/$NUM_NODES"

if [ $active_tpus -eq 0 ]; then
    echo "   ❌ No TPU listeners detected - leaders not ready for immediate transaction processing"
    echo ""
    echo "🔧 Debugging TPU ports:"
    echo "   Check what processes are using UDP ports 13000-13003:"
    lsof -i :13000-13003 2>/dev/null || echo "   No processes found on TPU ports"
elif [ $active_tpus -lt $NUM_NODES ]; then
    echo "   ⚠️  Some TPU listeners missing - only some leaders ready for immediate processing"
else
    echo "   🎉 All TPU listeners active - Gulf Stream ready!"
fi
