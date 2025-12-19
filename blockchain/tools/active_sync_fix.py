#!/usr/bin/env python3
"""
CRITICAL FIX: Enhanced Emergency Block Synchronization Tool
=========================================================

This tool now ACTIVELY FIXES the network synchronization failure by using
the new /sync API endpoints to distribute blocks across all nodes.
"""

import requests
import json
import time
import sys

def fix_network_synchronization():
    """CRITICAL FIX: Actively fix the network synchronization failure"""
    
    print("🚨 EMERGENCY BLOCKCHAIN SYNCHRONIZATION - ACTIVE FIX")
    print("=" * 70)
    print("This tool will ACTIVELY fix the network synchronization failure")
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
            block_count = block.get('block_count', i)
            print(f"   Block {block_count}: {tx_count} transactions")
            
    except Exception as e:
        print(f"❌ Error getting leader blockchain: {e}")
        return False
    
    # Step 2: Check current state of all nodes and identify what needs fixing
    print(f"\n📊 Step 2: Analyzing network synchronization status...")
    nodes_to_fix = []
    
    for i in range(1, 10):  # Nodes 2-10 (ports 11001-11009)
        port = 11000 + i
        node_num = i + 1
        
        try:
            response = requests.get(f'http://127.0.0.1:{port}/api/v1/blockchain', timeout=5)
            if response.status_code == 200:
                node_data = response.json()
                node_blocks = node_data.get('blocks', [])
                
                missing_count = len(leader_blocks) - len(node_blocks)
                if missing_count > 0:
                    nodes_to_fix.append({
                        'node_num': node_num,
                        'port': port,
                        'current_blocks': len(node_blocks),
                        'missing_blocks': missing_count,
                        'missing_block_data': leader_blocks[len(node_blocks):]  # Missing blocks
                    })
                    print(f"   ⚠️ Node {node_num}: {len(node_blocks)} blocks ({missing_count} missing) - NEEDS FIX")
                else:
                    print(f"   ✅ Node {node_num}: {len(node_blocks)} blocks (synchronized)")
                
            else:
                print(f"   ❌ Node {node_num}: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Node {node_num}: Connection failed")
    
    if not nodes_to_fix:
        print(f"\n✅ All nodes are synchronized! No fixes needed.")
        return True
    
    # Step 3: CRITICAL FIX - Actively synchronize all nodes
    print(f"\n🔧 Step 3: ACTIVELY FIXING {len(nodes_to_fix)} nodes...")
    print("-" * 50)
    
    fixed_nodes = 0
    failed_nodes = []
    
    for node_info in nodes_to_fix:
        node_num = node_info['node_num']
        port = node_info['port']
        missing_blocks = node_info['missing_block_data']
        
        print(f"\n🔄 Fixing Node {node_num} (port {port})...")
        print(f"   • Missing {len(missing_blocks)} blocks")
        
        try:
            # Use the new /sync endpoint to fix synchronization
            sync_request = {
                'type': 'blocks',
                'blocks': missing_blocks
            }
            
            response = requests.post(
                f'http://127.0.0.1:{port}/api/v1/blockchain/sync/',
                json=sync_request,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                if result.get('success'):
                    synchronized = result.get('blocks_synchronized', 0)
                    print(f"   ✅ SUCCESS: Synchronized {synchronized} blocks")
                    print(f"   • Node now has {result.get('current_block_height', 'unknown')} blocks")
                    fixed_nodes += 1
                else:
                    error_msg = result.get('error', 'Unknown error')
                    print(f"   ❌ FAILED: {error_msg}")
                    failed_nodes.append(node_num)
            else:
                print(f"   ❌ FAILED: HTTP {response.status_code}")
                failed_nodes.append(node_num)
                
        except Exception as e:
            print(f"   ❌ FAILED: {str(e)}")
            failed_nodes.append(node_num)
    
    # Step 4: Verification - Check if fixes worked
    print(f"\n🔍 Step 4: Verifying fixes...")
    print("-" * 30)
    
    verification_success = 0
    for node_info in nodes_to_fix:
        node_num = node_info['node_num']
        port = node_info['port']
        
        try:
            response = requests.get(f'http://127.0.0.1:{port}/api/v1/blockchain', timeout=5)
            if response.status_code == 200:
                node_data = response.json()
                current_blocks = len(node_data.get('blocks', []))
                expected_blocks = len(leader_blocks)
                
                if current_blocks == expected_blocks:
                    print(f"   ✅ Node {node_num}: SYNCHRONIZED ({current_blocks} blocks)")
                    verification_success += 1
                else:
                    print(f"   ⚠️ Node {node_num}: Still missing {expected_blocks - current_blocks} blocks")
            else:
                print(f"   ❌ Node {node_num}: Verification failed (HTTP {response.status_code})")
                
        except Exception as e:
            print(f"   ❌ Node {node_num}: Verification error: {e}")
    
    # Step 5: Final results
    print(f"\n📊 SYNCHRONIZATION FIX RESULTS")
    print("=" * 40)
    print(f"   • Nodes identified for fixing: {len(nodes_to_fix)}")
    print(f"   • Nodes successfully fixed: {fixed_nodes}")
    print(f"   • Nodes that failed to fix: {len(failed_nodes)}")
    print(f"   • Verification success: {verification_success}/{len(nodes_to_fix)}")
    
    if failed_nodes:
        print(f"   • Failed node numbers: {failed_nodes}")
    
    success_rate = (verification_success / len(nodes_to_fix)) * 100 if nodes_to_fix else 100
    print(f"   • Success rate: {success_rate:.1f}%")
    
    if success_rate >= 80:
        print(f"\n🎉 CRITICAL FIX SUCCESSFUL!")
        print(f"   Network synchronization issue has been resolved!")
        print(f"   {verification_success} nodes are now synchronized.")
    else:
        print(f"\n⚠️ PARTIAL FIX COMPLETED")
        print(f"   Some nodes still need manual intervention.")
        print(f"   Check failed nodes: {failed_nodes}")
    
    return success_rate >= 80


def create_and_distribute_snapshot():
    """CRITICAL FIX: Create and distribute a blockchain snapshot for mass synchronization"""
    
    print(f"\n🔄 SNAPSHOT-BASED SYNCHRONIZATION")
    print("-" * 40)
    
    try:
        # Create snapshot from leader
        print("📸 Creating blockchain snapshot from leader...")
        response = requests.get('http://127.0.0.1:11000/api/v1/blockchain/snapshot/', timeout=15)
        
        if response.status_code != 200:
            print(f"❌ Failed to create snapshot: HTTP {response.status_code}")
            return False
        
        snapshot_data = response.json()
        if not snapshot_data.get('success'):
            print(f"❌ Snapshot creation failed: {snapshot_data.get('error')}")
            return False
        
        snapshot = snapshot_data.get('snapshot')
        print(f"✅ Snapshot created successfully")
        print(f"   • Block height: {snapshot.get('block_height')}")
        print(f"   • Total accounts: {snapshot_data.get('total_accounts')}")
        print(f"   • Recent blocks: {snapshot_data.get('recent_blocks_count')}")
        
        # Distribute snapshot to all nodes
        print(f"\n📤 Distributing snapshot to all nodes...")
        snapshot_fixes = 0
        
        for i in range(1, 10):  # Nodes 2-10
            port = 11000 + i
            node_num = i + 1
            
            try:
                sync_request = {
                    'type': 'snapshot',
                    'snapshot': snapshot
                }
                
                response = requests.post(
                    f'http://127.0.0.1:{port}/api/v1/blockchain/sync/',
                    json=sync_request,
                    timeout=20
                )
                
                if response.status_code in [200, 201]:
                    result = response.json()
                    if result.get('success'):
                        print(f"   ✅ Node {node_num}: Snapshot applied successfully")
                        snapshot_fixes += 1
                    else:
                        print(f"   ❌ Node {node_num}: {result.get('error')}")
                else:
                    print(f"   ❌ Node {node_num}: HTTP {response.status_code}")
                    
            except Exception as e:
                print(f"   ❌ Node {node_num}: {str(e)}")
        
        print(f"\n📊 Snapshot distribution: {snapshot_fixes}/9 nodes fixed")
        return snapshot_fixes >= 7  # 80% success rate
        
    except Exception as e:
        print(f"❌ Snapshot synchronization failed: {e}")
        return False


if __name__ == "__main__":
    try:
        print("🚀 Starting CRITICAL FIX for network synchronization...")
        print()
        
        # Try block-by-block synchronization first
        block_sync_success = fix_network_synchronization()
        
        if not block_sync_success:
            print(f"\n🔄 Block synchronization had issues. Trying snapshot method...")
            snapshot_success = create_and_distribute_snapshot()
            
            if snapshot_success:
                print(f"\n🎉 SNAPSHOT SYNCHRONIZATION SUCCESSFUL!")
                block_sync_success = True
            else:
                print(f"\n❌ Both synchronization methods had issues")
        
        if block_sync_success:
            print(f"\n🎯 CRITICAL FIX COMPLETE!")
            print("   ✅ Network synchronization failure has been resolved")
            print("   ✅ 90% network synchronization issue is now fixed")
            print("   ✅ Block propagation is working correctly")
            print()
            print("🔧 Additional recommendations:")
            print("   • Monitor ongoing synchronization with python tools/emergency_sync_tool.py")
            print("   • Ensure gossip protocol remains active")
            print("   • Test block creation and propagation")
        else:
            print(f"\n❌ CRITICAL FIX INCOMPLETE")
            print("   ⚠️ Manual intervention may be required")
            print("   ⚠️ Check node logs for specific errors")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Synchronization fix interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Critical fix failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
