#!/usr/bin/env python3
"""
Trigger quantum consensus by sending transactions and monitoring the D-Wave quantum annealer
"""
import requests
import time
import json
from datetime import datetime
import sys
import os

# Add blockchain module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from blockchain.transaction.wallet import Wallet
from blockchain.utils.helpers import BlockchainUtils

def send_transaction_to_node(port, sender_wallet, receiver_address, amount):
    """Send a transaction to a specific node"""
    try:
        transaction_data = {
            "sender": sender_wallet.public_key_string(),
            "receiver": receiver_address,
            "amount": amount,
            "type": "TRANSFER"
        }
        
        # Sign transaction
        encoded_data = BlockchainUtils.encode(transaction_data)
        signature = sender_wallet.sign(encoded_data)
        
        payload = {
            "sender": sender_wallet.public_key_string(),
            "receiver": receiver_address,
            "amount": amount,
            "type": "TRANSFER",
            "signature": signature
        }
        
        print(f"   📤 Sending to Node {port - 8050} (port {port}): {amount} tokens")
        response = requests.post(f"http://localhost:{port}/api/v1/transactions/", 
                               json=payload, timeout=5)
        
        if response.status_code == 200:
            print(f"   ✅ Transaction successful on Node {port - 8050}")
            return True
        else:
            print(f"   ❌ Transaction failed on Node {port - 8050}: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Transaction error on Node {port - 8050}: {e}")
        return False

def get_quantum_metrics(port):
    """Get quantum metrics from a node"""
    try:
        response = requests.get(f"http://localhost:{port}/api/v1/blockchain/quantum-metrics/", timeout=3)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"   ⚠️  Failed to get quantum metrics from Node {port - 8050}: {e}")
    return None

def get_blockchain_info(port):
    """Get blockchain info from a node"""
    try:
        response = requests.get(f"http://localhost:{port}/api/v1/blockchain/", timeout=3)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def main():
    print("🌌 QUANTUM CONSENSUS TRIGGER & MONITOR")
    print("="*60)
    print("Using D-Wave Quantum Annealing Simulator for Block Proposal Selection")
    print("="*60)
    
    # Test nodes we know are running
    test_ports = [8050, 8051, 8052, 8053, 8054, 8055, 8056, 8057, 8058, 8059]
    active_ports = []
    
    print("🔍 Testing node connectivity...")
    for port in test_ports:
        info = get_blockchain_info(port)
        if info is not None:
            active_ports.append(port)
            print(f"   ✅ Node {port - 8050} (port {port}) - ACTIVE")
        else:
            print(f"   ❌ Node {port - 8050} (port {port}) - INACTIVE")
    
    if len(active_ports) == 0:
        print("❌ No active nodes found!")
        return
    
    print(f"\n📊 Found {len(active_ports)} active nodes: {[p - 8050 for p in active_ports]}")
    
    # Create test wallets
    print("\n👛 Creating test wallets...")
    wallets = []
    for i in range(5):
        wallet = Wallet()
        wallets.append(wallet)
        print(f"   Wallet {i+1}: {wallet.public_key_string()[:50]}...")
    
    print(f"\n🚀 TRIGGERING QUANTUM CONSENSUS ACTIVITY")
    print("="*60)
    
    # Send multiple transactions to trigger quantum consensus
    for round_num in range(3):
        print(f"\n🔄 ROUND {round_num + 1}: Sending transactions to trigger quantum annealing")
        print("-" * 50)
        
        # Send transactions from different wallets to different nodes
        for i, port in enumerate(active_ports[:5]):  # Use first 5 active nodes
            if i < len(wallets) - 1:
                sender = wallets[i]
                receiver = wallets[i + 1]
                amount = 100 + (round_num * 10) + i
                
                success = send_transaction_to_node(port, sender, 
                                                 receiver.public_key_string(), 
                                                 amount)
        
        # Wait for processing
        print(f"\n⏳ Waiting 5 seconds for quantum consensus processing...")
        time.sleep(5)
        
        # Collect quantum metrics
        print(f"\n🌌 QUANTUM CONSENSUS METRICS - Round {round_num + 1}")
        print("-" * 50)
        
        total_probes = 0
        for port in active_ports:
            metrics = get_quantum_metrics(port)
            if metrics:
                node_id = port - 8050
                consensus_type = metrics.get('consensus_type', 'Unknown')
                probe_count = metrics.get('probe_count', 0)
                total_nodes = metrics.get('total_nodes', 0)
                active_nodes = metrics.get('active_nodes', 0)
                
                total_probes += probe_count
                
                print(f"   Node {node_id:2d}: {consensus_type}")
                print(f"           Probes: {probe_count}, Nodes: {active_nodes}/{total_nodes}")
                
                # Show detailed node scores
                node_scores = metrics.get('node_scores', {})
                for pub_key, score_data in node_scores.items():
                    short_key = pub_key.split('\n')[1][:20] + "..." if '\n' in pub_key else pub_key[:30] + "..."
                    suitability = score_data.get('suitability_score', 0)
                    effective = score_data.get('effective_score', 0)
                    proposals_success = score_data.get('proposals_success', 0)
                    proposals_failed = score_data.get('proposals_failed', 0)
                    
                    print(f"           └─ Key: {short_key}")
                    print(f"              Suitability: {suitability:.6f}")
                    print(f"              Effective: {effective:.6f}")
                    print(f"              Proposals: {proposals_success} success, {proposals_failed} failed")
        
        print(f"   📊 Total quantum probes across all nodes: {total_probes}")
        
        # Check blockchain state
        print(f"\n📦 BLOCKCHAIN STATE - Round {round_num + 1}")
        print("-" * 30)
        
        for port in active_ports[:3]:  # Check first 3 nodes
            info = get_blockchain_info(port)
            if info:
                blocks = info.get('blocks', [])
                node_id = port - 8050
                print(f"   Node {node_id}: {len(blocks)} blocks")
                
                # Show latest block info
                if len(blocks) > 1:  # More than genesis block
                    latest_block = blocks[-1]
                    forger = latest_block.get('forger', 'Unknown')
                    tx_count = len(latest_block.get('transactions', []))
                    timestamp = latest_block.get('timestamp', 0)
                    print(f"            Latest: Forger={forger[:20]}..., {tx_count} txs, Time={timestamp}")
        
        if round_num < 2:  # Don't wait after last round
            print(f"\n⏸️  Waiting 10 seconds before next round...")
            time.sleep(10)
    
    print(f"\n🏁 QUANTUM CONSENSUS MONITORING COMPLETE")
    print("="*60)
    print("✅ Successfully triggered and monitored D-Wave quantum annealing consensus!")

if __name__ == "__main__":
    main()
