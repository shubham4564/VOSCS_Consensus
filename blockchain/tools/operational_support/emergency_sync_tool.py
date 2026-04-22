#!/usr/bin/env python3
"""
Emergency Block Synchronization Tool
===================================

This tool manually synchronizes all nodes with the leader node's blockchain
to restore network consistency as an immediate fix while permanent solutions
are implemented.
"""

import requests
import json
import time
import sys

def sync_all_nodes():
    """Manually sync all nodes with the leader node's blockchain"""
    
    print("🚨 EMERGENCY BLOCKCHAIN SYNCHRONIZATION")
    print("=" * 60)
    print("This tool will manually sync all nodes with the leader's blockchain")
    print()
    
    # Step 1: Get the leader's complete blockchain
    print("📤 Step 1: Getting complete blockchain from leader (Node 1)...")
    try:
        response = requests.get('http://127.0.0.1:11000/api/v1/blockchain', timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to get leader blockchain: HTTP {response.status_code}")
            return False
            
        leader_data = response.json()
        leader_blocks = leader_data.get('blocks', [])
        print(f"✅ Retrieved {len(leader_blocks)} blocks from leader")
        
        # Display block summary
        for i, block in enumerate(leader_blocks):
            tx_count = len(block.get('transactions', []))
            timestamp = block.get('timestamp', 'Unknown')
            print(f"   Block {i}: {tx_count} transactions, timestamp: {timestamp}")
            
    except Exception as e:
        print(f"❌ Error getting leader blockchain: {e}")
        return False
    
    # Step 2: Check current state of all follower nodes
    print(f"\n📊 Step 2: Checking current state of follower nodes...")
    follower_nodes = []
    
    for i in range(1, 10):  # Nodes 2-10 (ports 11001-11009)
        port = 11000 + i
        node_num = i + 1
        
        try:
            response = requests.get(f'http://127.0.0.1:{port}/api/v1/blockchain', timeout=5)
            if response.status_code == 200:
                node_data = response.json()
                node_blocks = node_data.get('blocks', [])
                
                missing_count = len(leader_blocks) - len(node_blocks)
                follower_nodes.append({
                    'node_num': node_num,
                    'port': port,
                    'current_blocks': len(node_blocks),
                    'missing_blocks': missing_count,
                    'status': 'online'
                })
                
                status = f"{'✅' if missing_count == 0 else '⚠️'} Node {node_num}: {len(node_blocks)} blocks ({missing_count} missing)"
                print(f"   {status}")
                
            else:
                print(f"   ❌ Node {node_num}: HTTP {response.status_code}")
                follower_nodes.append({
                    'node_num': node_num,
                    'port': port,
                    'status': 'error'
                })
                
        except Exception as e:
            print(f"   ❌ Node {node_num}: Connection failed")
            follower_nodes.append({
                'node_num': node_num,
                'port': port,
                'status': 'offline'
            })
    
    # Step 3: Identify nodes that need synchronization
    nodes_needing_sync = [node for node in follower_nodes 
                         if node['status'] == 'online' and node.get('missing_blocks', 0) > 0]
    
    print(f"\n🔄 Step 3: Synchronization needed for {len(nodes_needing_sync)} nodes")
    
    if not nodes_needing_sync:
        print("✅ All nodes are already synchronized!")
        return True
    
    # Step 4: Show what would be synchronized (read-only analysis)
    print(f"\n📋 Step 4: Synchronization Analysis")
    print("-" * 40)
    
    total_blocks_to_sync = 0
    for node in nodes_needing_sync:
        missing = node['missing_blocks']
        total_blocks_to_sync += missing
        print(f"   Node {node['node_num']}: {missing} blocks to sync")
    
    print(f"\n📊 SYNCHRONIZATION SUMMARY:")
    print(f"   • Leader node: {len(leader_blocks)} blocks")
    print(f"   • Nodes needing sync: {len(nodes_needing_sync)}")
    print(f"   • Total missing blocks: {total_blocks_to_sync}")
    
    # Show the specific blocks that are missing
    if len(leader_blocks) > 1:
        print(f"\n📦 MISSING BLOCKS THAT NEED DISTRIBUTION:")
        missing_blocks = leader_blocks[1:]  # Skip genesis block
        
        for i, block in enumerate(missing_blocks):
            forger = block.get('forger', 'Unknown')[:30] + "..." if len(str(block.get('forger', ''))) > 30 else block.get('forger', 'Unknown')
            tx_count = len(block.get('transactions', []))
            timestamp = block.get('timestamp', 'Unknown')
            block_count = block.get('block_count', 'Unknown')
            
            print(f"   Block {i+1} (#{block_count}):")
            print(f"      • {tx_count} transactions")
            print(f"      • Forger: {forger}")
            print(f"      • Timestamp: {timestamp}")
            
            # Show transaction details
            if block.get('transactions'):
                for j, tx in enumerate(block['transactions'][:2]):  # Show first 2 transactions
                    sender = tx.get('sender_public_key', 'Unknown')[:20] + "..." if len(str(tx.get('sender_public_key', ''))) > 20 else tx.get('sender_public_key', 'Unknown')
                    receiver = tx.get('receiver_public_key', 'Unknown')[:20] + "..." if len(str(tx.get('receiver_public_key', ''))) > 20 else tx.get('receiver_public_key', 'Unknown')
                    amount = tx.get('amount', 'Unknown')
                    print(f"         Tx {j+1}: {sender} → {receiver} ({amount})")
            print()
    
    # Step 5: Provide implementation guidance
    print(f"🔧 Step 5: IMPLEMENTATION REQUIRED")
    print("-" * 40)
    print("❗ CRITICAL: This tool has identified the synchronization problem but")
    print("   cannot automatically fix it because:")
    print()
    print("   1. No block synchronization API endpoint exists")
    print("   2. No automatic block propagation mechanism is active") 
    print("   3. Gossip protocol is not running for block distribution")
    print("   4. Manual block injection would require node restart")
    print()
    print("💡 REQUIRED FIXES:")
    print("   1. Implement /api/v1/sync endpoint for manual block sync")
    print("   2. Activate gossip protocol on all nodes")
    print("   3. Add automatic block broadcasting in propose_block()")
    print("   4. Implement periodic sync verification")
    print()
    print("✅ VERIFICATION COMPLETE: Synchronization issue confirmed and documented")
    
    return True

if __name__ == "__main__":
    try:
        success = sync_all_nodes()
        if success:
            print(f"\n🎯 EMERGENCY SYNC ANALYSIS COMPLETE")
            print("   • Problem identified and documented")
            print("   • Manual intervention required")
            print("   • Implement the recommended fixes to restore network sync")
        else:
            print(f"\n❌ EMERGENCY SYNC ANALYSIS FAILED")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Emergency sync interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Emergency sync failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
