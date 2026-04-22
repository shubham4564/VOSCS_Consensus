#!/usr/bin/env python3
"""
Manual Block Synchronization Script
Ensures proper block ordering across all nodes
"""

import json
import requests
import sys

def manual_sync_blocks():
    """Manually synchronize blocks across nodes with proper ordering"""
    
    # Get reference blockchain from node 11000 (fully synchronized)
    print("Getting reference blockchain from node 11000...")
    resp = requests.get('http://localhost:11000/api/v1/blockchain/')
    reference_blocks = resp.json()['blocks']
    print(f"Reference blockchain has {len(reference_blocks)} blocks")
    
    # Check each node
    nodes_to_sync = [11001, 11002, 11003, 11004]
    
    for port in nodes_to_sync:
        print(f"\n=== Checking Node {port} ===")
        
        try:
            # Get current state
            resp = requests.get(f'http://localhost:{port}/api/v1/blockchain/')
            current_blocks = resp.json()['blocks']
            current_count = len(current_blocks)
            
            print(f"Node {port} has {current_count} blocks")
            
            # Verify ordering of existing blocks
            ordering_ok = True
            for i, block in enumerate(current_blocks):
                expected_count = i
                actual_count = block['block_count']
                if actual_count != expected_count:
                    print(f"  ❌ ORDERING ERROR: Block {i} has block_count {actual_count}, expected {expected_count}")
                    ordering_ok = False
                
                # Check if this block matches reference
                if i < len(reference_blocks):
                    ref_block = reference_blocks[i]
                    if block['last_hash'] != ref_block['last_hash']:
                        print(f"  ❌ HASH MISMATCH: Block {i} hash differs from reference")
                        ordering_ok = False
                    elif block['timestamp'] != ref_block['timestamp']:
                        print(f"  ❌ TIMESTAMP MISMATCH: Block {i} timestamp differs from reference")
                        ordering_ok = False
            
            if ordering_ok and current_count > 0:
                print(f"  ✅ Block ordering is correct for {current_count} blocks")
            
            # Check if node needs more blocks
            if current_count < len(reference_blocks):
                missing_count = len(reference_blocks) - current_count
                print(f"  📊 Node needs {missing_count} more blocks")
                
                # For now, just report the missing blocks
                print(f"  📋 Missing blocks: {current_count} to {len(reference_blocks)-1}")
                
                # Show next few blocks that should be added
                for i in range(current_count, min(current_count + 3, len(reference_blocks))):
                    next_block = reference_blocks[i]
                    print(f"     Next block {i}: {len(next_block['transactions'])} transactions, "
                          f"timestamp {next_block['timestamp']}")
            
            elif current_count == len(reference_blocks):
                print(f"  ✅ Node {port} is fully synchronized")
            
            else:
                print(f"  ⚠️  Node {port} has MORE blocks than reference ({current_count} vs {len(reference_blocks)})")
                
        except Exception as e:
            print(f"  ❌ Error checking node {port}: {e}")
    
    # Summary
    print(f"\n📊 SYNCHRONIZATION SUMMARY")
    print(f"Reference blockchain: {len(reference_blocks)} blocks")
    
    all_synced = True
    for port in nodes_to_sync:
        try:
            resp = requests.get(f'http://localhost:{port}/api/v1/blockchain/')
            current_count = len(resp.json()['blocks'])
            status = "✅ Synced" if current_count == len(reference_blocks) else f"❌ Behind ({current_count}/{len(reference_blocks)})"
            print(f"Node {port}: {status}")
            if current_count != len(reference_blocks):
                all_synced = False
        except:
            print(f"Node {port}: ❌ Error")
            all_synced = False
    
    if all_synced:
        print("\n🎉 All nodes are properly synchronized!")
    else:
        print("\n⚠️  Some nodes need synchronization")
    
    return all_synced

if __name__ == "__main__":
    manual_sync_blocks()
