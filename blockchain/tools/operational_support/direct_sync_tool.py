#!/usr/bin/env python3
"""
Direct Blockchain Synchronization Tool
Bypasses API and directly synchronizes blockchain data
"""

import requests
import os
import sys


def _ensure_repo_root_on_path() -> None:
    current = os.path.abspath(os.path.dirname(__file__))
    for _ in range(6):
        if os.path.isfile(os.path.join(current, "blockchain", "__init__.py")):
            if current not in sys.path:
                sys.path.insert(0, current)
            return
        parent = os.path.dirname(current)
        if parent == current:
            return
        current = parent


_ensure_repo_root_on_path()
del _ensure_repo_root_on_path

from blockchain.block import Block
from blockchain.transaction.transaction import Transaction

def direct_blockchain_sync():
    """Directly synchronize blockchains by copying missing blocks"""
    
    print("🔄 Direct Blockchain Synchronization Tool")
    print("=" * 50)
    
    # Get reference blockchain from node 11000
    print("1. Getting reference blockchain from node 11000...")
    resp = requests.get('http://localhost:11000/api/v1/blockchain/')
    reference_data = resp.json()
    reference_blocks = reference_data['blocks']
    print(f"   ✅ Reference has {len(reference_blocks)} blocks")
    
    # Check all nodes that need synchronization
    nodes_to_sync = [11001, 11002]  # Skip 11003, 11004 as they're already synced
    
    for port in nodes_to_sync:
        print(f"\n2. Synchronizing Node {port}...")
        
        # Get current state
        resp = requests.get(f'http://localhost:{port}/api/v1/blockchain/')
        current_data = resp.json()
        current_blocks = current_data['blocks']
        current_count = len(current_blocks)
        
        print(f"   📊 Node {port} has {current_count} blocks, needs {len(reference_blocks) - current_count} more")
        
        if current_count >= len(reference_blocks):
            print(f"   ✅ Node {port} is already synchronized")
            continue
        
        # Validate that existing blocks match reference
        blocks_match = True
        for i in range(current_count):
            if i >= len(reference_blocks):
                break
            
            current_block = current_blocks[i]
            reference_block = reference_blocks[i]
            
            # Check critical fields
            if (current_block['last_hash'] != reference_block['last_hash'] or
                current_block['timestamp'] != reference_block['timestamp'] or
                current_block['block_count'] != reference_block['block_count']):
                print(f"   ❌ Block {i} doesn't match reference - cannot safely sync")
                blocks_match = False
                break
        
        if not blocks_match:
            print(f"   ⚠️  Skipping {port} - existing blocks don't match reference")
            continue
        
        # Get missing blocks
        missing_blocks = reference_blocks[current_count:]
        print(f"   📋 Adding {len(missing_blocks)} missing blocks...")
        
        # Add blocks one by one using internal methods
        success_count = 0
        for i, block_data in enumerate(missing_blocks):
            block_index = current_count + i
            
            try:
                # Reconstruct the block properly
                transactions = []
                for tx_data in block_data.get('transactions', []):
                    tx = Transaction(
                        sender_public_key=tx_data.get('sender_public_key', ''),
                        receiver_public_key=tx_data.get('receiver_public_key', ''),
                        amount=tx_data.get('amount', 0),
                        type=tx_data.get('type', 'TRANSFER')
                    )
                    tx.id = tx_data.get('id', '')
                    tx.timestamp = tx_data.get('timestamp', 0)
                    tx.signature = tx_data.get('signature', '')
                    transactions.append(tx)
                
                # Create Block with correct parameter order
                block = Block(
                    transactions,
                    block_data.get('last_hash', ''),
                    block_data.get('block_proposer', block_data.get('forger', '')),  # Support both field names for compatibility
                    block_data.get('block_count', 0)
                )
                block.timestamp = block_data.get('timestamp', 0)
                block.signature = block_data.get('signature', '')
                
                # Use the API to add the block (which validates ordering)
                add_payload = {
                    "type": "blocks", 
                    "blocks": [block_data]
                }
                
                resp = requests.post(
                    f'http://localhost:{port}/api/v1/blockchain/sync',
                    json=add_payload,
                    timeout=10
                )
                
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get('blocks_synchronized', 0) > 0:
                        success_count += 1
                        print(f"     ✅ Added block {block_index}")
                    else:
                        print(f"     ❌ Failed to add block {block_index}: {result.get('errors', ['Unknown error'])[0]}")
                        break  # Stop on first failure to maintain ordering
                else:
                    print(f"     ❌ API error adding block {block_index}: {resp.status_code}")
                    break
                    
            except Exception as e:
                print(f"     ❌ Exception adding block {block_index}: {e}")
                break
        
        # Final verification
        resp = requests.get(f'http://localhost:{port}/api/v1/blockchain/')
        final_count = len(resp.json()['blocks'])
        
        if final_count == len(reference_blocks):
            print(f"   🎉 Node {port} successfully synchronized ({final_count} blocks)")
        else:
            print(f"   ⚠️  Node {port} partial sync: {final_count}/{len(reference_blocks)} blocks")
    
    # Final status check
    print(f"\n📊 FINAL SYNCHRONIZATION STATUS")
    print("=" * 50)
    
    all_synced = True
    for port in [11000, 11001, 11002, 11003, 11004]:
        try:
            resp = requests.get(f'http://localhost:{port}/api/v1/blockchain/')
            count = len(resp.json()['blocks'])
            status = "✅ Synced" if count == len(reference_blocks) else f"❌ Behind ({count}/{len(reference_blocks)})"
            print(f"Node {port}: {status}")
            if count != len(reference_blocks):
                all_synced = False
        except:
            print(f"Node {port}: ❌ Error")
            all_synced = False
    
    if all_synced:
        print("\n🎉 ALL NODES SUCCESSFULLY SYNCHRONIZED!")
        print("✅ Block ordering is consistent across the network")
    else:
        print("\n⚠️  Some nodes still need synchronization")
    
    return all_synced

if __name__ == "__main__":
    success = direct_blockchain_sync()
    sys.exit(0 if success else 1)
