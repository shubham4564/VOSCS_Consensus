#!/usr/bin/env python3
"""
Bootstrap Network Connections
===========================

This script connects running nodes to each other to establish a gossip network.
It detects running nodes and creates bootstrap connections between them.
"""

import requests
import json
import time
import sys
from typing import List, Dict

def get_running_nodes() -> List[Dict]:
    """Detect running nodes by checking API endpoints"""
    running_nodes = []
    
    # Check nodes on ports 11000-11020 (API ports)
    for i in range(20):
        port = 11000 + i
        try:
            response = requests.get(f"http://localhost:{port}/api/v1/node/status", timeout=2)
            if response.status_code == 200:
                node_data = response.json()
                running_nodes.append({
                    'api_port': port,
                    'p2p_port': 10000 + i,
                    'gossip_port': 12000 + i,
                    'tpu_port': 13000 + i,
                    'tvu_port': 14000 + i,
                    'public_key': node_data.get('public_key', ''),
                    'node_id': i + 1
                })
                print(f"✅ Found Node {i+1} on API port {port}")
        except:
            continue
    
    return running_nodes

def bootstrap_gossip_connections(nodes: List[Dict]):
    """Bootstrap gossip connections between nodes"""
    print(f"\n🔗 Bootstrapping gossip connections for {len(nodes)} nodes...")
    
    connections_made = 0
    
    for i, node in enumerate(nodes):
        # Connect each node to 2-3 other nodes as bootstrap peers
        other_nodes = [n for j, n in enumerate(nodes) if j != i]
        bootstrap_peers = other_nodes[:min(3, len(other_nodes))]
        
        for peer in bootstrap_peers:
            try:
                # Add peer via the blockchain's add_gossip_peer method
                payload = {
                    'peer_public_key': peer['public_key'],
                    'ip_address': 'localhost',
                    'gossip_port': peer['gossip_port'],
                    'tpu_port': peer['tpu_port'],
                    'tvu_port': peer['tvu_port']
                }
                
                response = requests.post(
                    f"http://localhost:{node['api_port']}/api/v1/gossip/add_peer",
                    json=payload,
                    timeout=5
                )
                
                if response.status_code == 200:
                    print(f"  ✅ Node {node['node_id']} → Node {peer['node_id']} gossip connection")
                    connections_made += 1
                else:
                    print(f"  ❌ Node {node['node_id']} → Node {peer['node_id']} failed: {response.status_code}")
                    
            except Exception as e:
                print(f"  ❌ Node {node['node_id']} → Node {peer['node_id']} error: {e}")
        
        # Small delay to prevent overwhelming the nodes
        time.sleep(0.5)
    
    return connections_made

def bootstrap_p2p_connections(nodes: List[Dict]):
    """Bootstrap P2P connections between nodes"""
    print(f"\n🔗 Bootstrapping P2P connections for {len(nodes)} nodes...")
    
    connections_made = 0
    
    for i, node in enumerate(nodes):
        # Connect each node to several other nodes
        other_nodes = [n for j, n in enumerate(nodes) if j != i]
        target_peers = other_nodes[:min(5, len(other_nodes))]
        
        for peer in target_peers:
            try:
                # Use the P2P connect endpoint if available
                payload = {
                    'ip': 'localhost',
                    'port': peer['p2p_port']
                }
                
                response = requests.post(
                    f"http://localhost:{node['api_port']}/api/v1/p2p/connect",
                    json=payload,
                    timeout=5
                )
                
                if response.status_code == 200:
                    print(f"  ✅ Node {node['node_id']} → Node {peer['node_id']} P2P connection")
                    connections_made += 1
                else:
                    print(f"  ❌ Node {node['node_id']} → Node {peer['node_id']} failed: {response.status_code}")
                    
            except Exception as e:
                print(f"  ❌ Node {node['node_id']} → Node {peer['node_id']} error: {e}")
        
        # Small delay to prevent overwhelming the nodes
        time.sleep(0.3)
    
    return connections_made

def check_network_status(nodes: List[Dict]):
    """Check the network status after bootstrapping"""
    print(f"\n📊 Checking network status...")
    
    total_gossip_peers = 0
    total_p2p_peers = 0
    
    for node in nodes:
        try:
            response = requests.get(f"http://localhost:{node['api_port']}/api/v1/node/status", timeout=3)
            if response.status_code == 200:
                status = response.json()
                gossip_peers = status.get('gossip_protocol', {}).get('active_peers', 0)
                p2p_peers = status.get('connected_peers', 0)
                
                total_gossip_peers += gossip_peers
                total_p2p_peers += p2p_peers
                
                print(f"  Node {node['node_id']}: {gossip_peers} gossip peers, {p2p_peers} P2P peers")
        except Exception as e:
            print(f"  Node {node['node_id']}: Error getting status - {e}")
    
    print(f"\n📈 Network Summary:")
    print(f"  Total Gossip Connections: {total_gossip_peers}")
    print(f"  Total P2P Connections: {total_p2p_peers}")
    print(f"  Average Gossip Peers/Node: {total_gossip_peers/len(nodes):.1f}")
    print(f"  Average P2P Peers/Node: {total_p2p_peers/len(nodes):.1f}")

def main():
    print("🚀 Blockchain Network Bootstrap Tool")
    print("="*50)
    
    # Detect running nodes
    print("🔍 Detecting running nodes...")
    nodes = get_running_nodes()
    
    if len(nodes) < 2:
        print("❌ Error: Need at least 2 running nodes to bootstrap network")
        print("   Start nodes with: ./start_nodes.sh N")
        sys.exit(1)
    
    print(f"✅ Found {len(nodes)} running nodes")
    
    # Bootstrap connections
    gossip_connections = bootstrap_gossip_connections(nodes)
    p2p_connections = bootstrap_p2p_connections(nodes)
    
    print(f"\n🎉 Bootstrap Complete!")
    print(f"  Gossip Connections Made: {gossip_connections}")
    print(f"  P2P Connections Made: {p2p_connections}")
    
    # Wait for connections to stabilize
    print(f"\n⏳ Waiting 10 seconds for connections to stabilize...")
    time.sleep(10)
    
    # Check final status
    check_network_status(nodes)
    
    print(f"\n💡 Network should now be connected!")
    print(f"   Monitor with: python3 analyze_forgers.py")

if __name__ == "__main__":
    main()
