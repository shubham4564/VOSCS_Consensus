#!/usr/bin/env python3
"""
Quick test to verify current block propagation status
"""

import requests
import json
import time

def check_block_propagation():
    """Check current block propagation status across nodes"""
    
    print("🔍 BLOCK PROPAGATION STATUS CHECK")
    print("=" * 40)
    
    nodes = [
        {'name': 'Node 1', 'port': 11000},
        {'name': 'Node 2', 'port': 11001}, 
        {'name': 'Node 3', 'port': 11002}
    ]
    
    for i in range(3):  # Check 3 times with delays
        print(f"\n📊 Check #{i+1}:")
        
        for node in nodes:
            try:
                response = requests.get(f'http://127.0.0.1:{node["port"]}/api/v1/blockchain/node-stats/', timeout=3)
                if response.status_code == 200:
                    stats = response.json()
                    total_blocks = stats['blockchain']['total_blocks']
                    connected_peers = stats['p2p']['connected_peers']
                    last_hash = stats['blockchain']['last_block_hash'][:12]
                    
                    print(f"   {node['name']}: {total_blocks} blocks, {connected_peers} peers, hash:{last_hash}")
                else:
                    print(f"   {node['name']}: API error {response.status_code}")
            except Exception as e:
                print(f"   {node['name']}: Offline - {str(e)[:30]}")
        
        if i < 2:  # Don't wait after last check
            time.sleep(10)
    
    print("\n" + "=" * 40)

if __name__ == "__main__":
    check_block_propagation()
