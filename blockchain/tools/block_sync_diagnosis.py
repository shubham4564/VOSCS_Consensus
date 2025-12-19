#!/usr/bin/env python3
"""
Block Synchronization Diagnosis Tool
===================================

This tool diagnoses why blocks created on one node aren't propagating to other nodes.
It checks network connectivity, gossip protocol status, and block propagation mechanisms.
"""

import requests
import json
import time
import sys
import os

def check_node_detailed_status(port):
    """Get detailed status from a node including network information"""
    base_url = f"http://127.0.0.1:{port}"
    
    # Try multiple endpoints to get comprehensive information
    endpoints = [
        "/api/v1/blockchain",
        "/api/v1/status", 
        "/api/v1/info",
        "/api/v1/peers",
        "/api/v1/network_status",
        "/status",
        "/info"
    ]
    
    node_info = {
        "port": port,
        "node_number": port - 11000 + 1,
        "status": "unknown",
        "endpoints": {},
        "blockchain": None,
        "network": None
    }
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=3)
            if response.status_code == 200:
                try:
                    data = response.json()
                    node_info["endpoints"][endpoint] = data
                    
                    # Extract specific information
                    if endpoint == "/api/v1/blockchain":
                        node_info["blockchain"] = {
                            "total_blocks": len(data.get("blocks", [])),
                            "blocks": data.get("blocks", [])
                        }
                        
                except json.JSONDecodeError:
                    node_info["endpoints"][endpoint] = {"raw_response": response.text[:200]}
                    
                node_info["status"] = "online"
            else:
                node_info["endpoints"][endpoint] = {"error": f"HTTP {response.status_code}"}
                
        except requests.exceptions.RequestException as e:
            node_info["endpoints"][endpoint] = {"error": f"Connection failed: {str(e)}"}
    
    return node_info

def analyze_block_propagation_failure():
    """Analyze why blocks aren't propagating between nodes"""
    
    print("🔍 BLOCK SYNCHRONIZATION DIAGNOSIS")
    print("=" * 80)
    print()
    
    # Get detailed information from all nodes
    all_nodes = []
    online_nodes = []
    
    for i in range(10):
        port = 11000 + i
        node_info = check_node_detailed_status(port)
        all_nodes.append(node_info)
        
        if node_info["status"] == "online":
            online_nodes.append(node_info)
    
    print(f"📊 NETWORK STATUS: {len(online_nodes)}/10 nodes online")
    print()
    
    # Analyze blockchain state
    print("📦 BLOCKCHAIN STATE ANALYSIS:")
    print("-" * 50)
    
    block_counts = {}
    for node in online_nodes:
        if node["blockchain"]:
            count = node["blockchain"]["total_blocks"]
            if count not in block_counts:
                block_counts[count] = []
            block_counts[count].append(node["node_number"])
    
    for block_count, nodes in sorted(block_counts.items()):
        print(f"   {block_count} blocks: Nodes {nodes}")
    
    print()
    
    # Find the node with most blocks (likely the leader)
    if online_nodes:
        leader_node = max(online_nodes, key=lambda n: n["blockchain"]["total_blocks"] if n["blockchain"] else 0)
        follower_nodes = [n for n in online_nodes if n != leader_node]
        
        print(f"🎯 ANALYSIS RESULTS:")
        print("-" * 50)
        print(f"Leader Node: #{leader_node['node_number']} (port {leader_node['port']}) - {leader_node['blockchain']['total_blocks']} blocks")
        
        if follower_nodes:
            avg_follower_blocks = sum(n["blockchain"]["total_blocks"] if n["blockchain"] else 0 for n in follower_nodes) / len(follower_nodes)
            print(f"Follower Nodes: Average {avg_follower_blocks:.1f} blocks")
            
            # Check for sync gap
            sync_gap = leader_node["blockchain"]["total_blocks"] - avg_follower_blocks
            print(f"Synchronization Gap: {sync_gap:.1f} blocks")
            
            if sync_gap > 0:
                print()
                print("🚨 SYNCHRONIZATION PROBLEM DETECTED!")
                print("-" * 50)
                
                # Analyze the missing blocks
                if leader_node["blockchain"]["total_blocks"] > 1:
                    missing_blocks = leader_node["blockchain"]["blocks"][1:]  # Skip genesis
                    print(f"Missing blocks on follower nodes:")
                    
                    for i, block in enumerate(missing_blocks, 1):
                        block_proposer = block.get("forger", "Unknown")[:30] + "..." if len(str(block.get("forger", ""))) > 30 else block.get("forger", "Unknown")  # Note: 'forger' field kept for compatibility
                        tx_count = len(block.get("transactions", []))
                        timestamp = block.get("timestamp", "Unknown")
                        
                        print(f"   Block {i}: {tx_count} transactions, block proposer: {block_proposer}, time: {timestamp}")
                
                print()
                print("🔧 PROBABLE CAUSES:")
                print("-" * 30)
                print("1. Block broadcasting not working between nodes")
                print("2. Gossip protocol not propagating blocks")
                print("3. P2P network connectivity issues")
                print("4. Block validation failing on receiving nodes")
                print("5. Turbine protocol not properly implemented for block sync")
                
                print()
                print("💡 RECOMMENDED FIXES:")
                print("-" * 30)
                print("1. Implement active block broadcasting in propose_block()")
                print("2. Add block synchronization endpoint (e.g., /api/v1/sync)")
                print("3. Verify P2P connections between nodes")
                print("4. Check gossip protocol is running and connected")
                print("5. Add block propagation retry mechanism")
                print("6. Implement periodic sync checks")
            else:
                print("✅ All nodes are properly synchronized!")
        
        print()
        
        # Check network connectivity features
        print("🌐 NETWORK CONNECTIVITY ANALYSIS:")
        print("-" * 50)
        
        # Look for network/peer information
        has_network_endpoints = False
        for node in online_nodes[:3]:  # Check first 3 nodes
            for endpoint, data in node["endpoints"].items():
                if "peer" in endpoint.lower() or "network" in endpoint.lower():
                    has_network_endpoints = True
                    print(f"   Node {node['node_number']}: {endpoint} available")
        
        if not has_network_endpoints:
            print("   ⚠️  No network/peer status endpoints found")
            print("   ⚠️  Cannot verify P2P connectivity")
        
        # Check if gossip protocol endpoints exist
        gossip_ports = [12000 + i for i in range(10)]
        print()
        print("📡 GOSSIP PROTOCOL STATUS:")
        print("-" * 30)
        
        import socket
        gossip_active = 0
        for i, port in enumerate(gossip_ports):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                
                if result == 0:
                    gossip_active += 1
                    print(f"   ✅ Node {i+1} gossip (port {port}): Active")
                else:
                    print(f"   ❌ Node {i+1} gossip (port {port}): Inactive")
            except Exception:
                print(f"   ❌ Node {i+1} gossip (port {port}): Error")
        
        print(f"   📊 Gossip Status: {gossip_active}/10 nodes have active gossip ports")
        
        if gossip_active == 0:
            print("   🚨 CRITICAL: No gossip ports active - this explains sync failure!")
        elif gossip_active < len(online_nodes):
            print("   ⚠️  WARNING: Some nodes missing gossip connectivity")
    
    print()
    print("=" * 80)
    print("DIAGNOSIS COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    try:
        analyze_block_propagation_failure()
    except KeyboardInterrupt:
        print("\n🛑 Diagnosis interrupted by user")
    except Exception as e:
        print(f"\n❌ Diagnosis failed: {e}")
        import traceback
        traceback.print_exc()
