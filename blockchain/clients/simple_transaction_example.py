#!/usr/bin/env python3
"""
🚀 Simple Transaction Example

This script demonstrates how to create and submit a transaction to the blockchain.
Perfect for testing and learning the transaction flow.

Usage:
    python simple_transaction_example.py
    python simple_transaction_example.py --amount 25.0
    python simple_transaction_example.py --node-port 11001
"""

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

import argparse
import requests
import json
import time
from blockchain.transaction.transaction import Transaction
from blockchain.transaction.wallet import Wallet
from blockchain.utils.helpers import BlockchainUtils

def print_section(title):
    """Print a section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def load_genesis_keys():
    """Load genesis keys for testing"""
    try:
        with open('keys/genesis_private_key.pem', 'r') as f:
            private_key = f.read()
        with open('keys/genesis_public_key.pem', 'r') as f:
            public_key = f.read()
        print("✅ Genesis keys loaded successfully")
        return private_key, public_key
    except FileNotFoundError:
        print("❌ Error: Genesis key files not found")
        print("💡 Please run: ./generate_keys.sh")
        return None, None

def create_transaction(sender_key, receiver_key, amount):
    """Create and sign a transaction"""
    print(f"\n📝 Creating transaction:")
    print(f"   💰 Amount: {amount}")
    print(f"   📤 From: {sender_key[:30]}...")
    print(f"   📥 To: {receiver_key[:30]}...")
    
    # Create wallet from private key
    private_key, _ = load_genesis_keys()
    if not private_key:
        return None
        
    wallet = Wallet()
    wallet.from_key(private_key)
    
    # Create transaction
    transaction = Transaction(
        sender_public_key=sender_key,
        receiver_public_key=receiver_key,
        amount=amount,
        type="TRANSFER"
    )
    
    # Sign the transaction
    signature = wallet.sign(transaction.payload())
    transaction.sign(signature)

    print(f"   🆔 Transaction ID: {transaction.id}")
    print("✅ Transaction created and signed")
    return transaction


def wait_for_transaction_confirmation(node_port, transaction_id, timeout_seconds, poll_interval_seconds=2):
    """Poll the blockchain until the transaction appears in a block."""
    deadline = time.time() + max(0, timeout_seconds)
    url = f"http://localhost:{node_port}/api/v1/blockchain/"

    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                blocks = data.get("blocks", [])
                for block in reversed(blocks):
                    for tx in block.get("transactions", []) or []:
                        if isinstance(tx, dict) and tx.get("id") == transaction_id:
                            return True, (block.get("last_hash") or block.get("hash"))
        except Exception:
            pass

        time.sleep(poll_interval_seconds)

    return False, None

def submit_transaction(transaction, node_port):
    """Submit transaction to the blockchain"""
    print(f"\n🚀 Submitting transaction to node on port {node_port}...")
    
    try:
        # Encode transaction
        encoded_transaction = BlockchainUtils.encode(transaction)
        
        # Prepare payload
        payload = {
            "transaction": encoded_transaction
        }
        
        # Submit to node
        url = f"http://localhost:{node_port}/api/v1/transaction/create/"
        print(f"   🌐 URL: {url}")
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Transaction submitted successfully!")
            print(f"   📋 Response: {result}")
            return True
        else:
            print(f"❌ Transaction submission failed: HTTP {response.status_code}")
            print(f"   📄 Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        print(f"💡 Make sure the blockchain node is running on port {node_port}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def check_node_health(node_port):
    """Check if the node is healthy and responsive"""
    print(f"\n🔍 Checking node health on port {node_port}...")
    
    try:
        url = f"http://localhost:{node_port}/api/v1/blockchain/"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            blockchain_data = response.json()
            print("✅ Node is healthy and responsive")
            print(f"   📊 Status: Active")
            print(f"   📦 Blocks: {len(blockchain_data.get('blocks', []))}")
            print(f"   🔗 Blockchain endpoint working")
            return True
        else:
            print(f"❌ Node health check failed: HTTP {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to node: {e}")
        print(f"💡 Make sure the blockchain node is running: ./start_nodes.sh")
        return False

def check_blockchain_status(node_port):
    """Check blockchain status before and after transaction"""
    print(f"\n📊 Checking blockchain status...")
    
    try:
        url = f"http://localhost:{node_port}/api/v1/blockchain/"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            blockchain_data = response.json()
            blocks = blockchain_data.get('blocks', [])
            block_count = len(blocks)
            
            print(f"✅ Blockchain status retrieved")
            print(f"   📦 Total blocks: {block_count}")
            
            if block_count > 0:
                latest_block = blocks[-1]
                tx_count = len(latest_block.get('transactions', []))
                print(f"   💳 Latest block transactions: {tx_count}")
                print(f"   🆔 Latest block ID: {latest_block.get('block_count', 'unknown')}")
            
            return block_count
        else:
            print(f"❌ Blockchain status check failed: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Error checking blockchain: {e}")
        return None

def check_transaction_pool(node_port):
    """Check current transaction pool status"""
    print(f"\n🏊 Checking transaction pool...")
    
    try:
        url = f"http://localhost:{node_port}/api/v1/transaction/transaction_pool/"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            pool_data = response.json()
            pool_size = len(pool_data) if isinstance(pool_data, list) else len(pool_data.keys()) if isinstance(pool_data, dict) else 0
            
            print(f"✅ Transaction pool checked")
            print(f"   📝 Pending transactions: {pool_size}")
            
            return pool_size
        else:
            print(f"❌ Transaction pool check failed: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Error checking transaction pool: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Simple blockchain transaction example')
    parser.add_argument('--amount', type=float, default=10.0, help='Transaction amount (default: 10.0)')
    parser.add_argument('--node-port', type=int, default=11000, help='Node API port (default: 11000)')
    parser.add_argument('--wait-time', type=int, default=5, help='Wait time between checks (default: 5 seconds)')
    
    args = parser.parse_args()
    
    print_section("🚀 SIMPLE TRANSACTION EXAMPLE")
    print(f"   💰 Amount: {args.amount}")
    print(f"   🌐 Node Port: {args.node_port}")
    
    # Step 1: Check node health
    print_section("Step 1: Node Health Check")
    if not check_node_health(args.node_port):
        print("\n❌ Cannot proceed - node is not accessible")
        print("💡 Try: ./start_nodes.sh")
        return 1
    
    # Step 2: Load keys
    print_section("Step 2: Loading Cryptographic Keys")
    private_key, public_key = load_genesis_keys()
    if not private_key:
        print("\n❌ Cannot proceed - keys not available")
        return 1
    
    # Step 3: Check initial blockchain state
    print_section("Step 3: Initial Blockchain State")
    initial_blocks = check_blockchain_status(args.node_port)
    initial_pool = check_transaction_pool(args.node_port)
    
    # Step 4: Create transaction
    print_section("Step 4: Creating Transaction")
    transaction = create_transaction(public_key, public_key, args.amount)  # Self-send for testing
    if not transaction:
        print("\n❌ Failed to create transaction")
        return 1
    
    # Step 5: Submit transaction
    print_section("Step 5: Submitting Transaction")
    success = submit_transaction(transaction, args.node_port)
    if not success:
        print("\n❌ Transaction submission failed")
        return 1
    
    # Step 6: Wait and check results
    print_section(f"Step 6: Waiting up to {args.wait_time} seconds for confirmation...")
    confirmed, block_id = wait_for_transaction_confirmation(args.node_port, transaction.id, timeout_seconds=args.wait_time)
    if confirmed:
        if block_id:
            print(f"✅ Transaction confirmed (block hash: {block_id})")
        else:
            print("✅ Transaction confirmed")
    else:
        print("⚠️ Transaction not confirmed within wait window")
    
    # Step 7: Check final state
    print_section("Step 7: Final Blockchain State")
    final_blocks = check_blockchain_status(args.node_port)
    final_pool = check_transaction_pool(args.node_port)
    
    # Step 8: Summary
    print_section("🎉 TRANSACTION TEST SUMMARY")
    
    if initial_blocks is not None and final_blocks is not None:
        block_change = final_blocks - initial_blocks
        print(f"   📦 Blocks: {initial_blocks} → {final_blocks} (change: +{block_change})")
    
    if initial_pool is not None and final_pool is not None:
        pool_change = final_pool - initial_pool
        print(f"   🏊 Pool: {initial_pool} → {final_pool} (change: {pool_change:+d})")
    
    print(f"   ✅ Transaction submitted successfully")
    
    if final_blocks and final_blocks > initial_blocks:
        print("   🎉 New block(s) created - transaction likely included!")
    elif final_pool and final_pool > initial_pool:
        print("   ⏳ Transaction in pool - waiting for block creation")
    else:
        print("   ℹ️ Check leader selection: python tools/leader_monitor.py --once")
    
    print("\n📋 Next Steps:")
    print("   • Monitor leaders: python tools/leader_monitor.py")
    print("   • View logs: tail -f logs/node1.log")
    print("   • Check health: curl http://localhost:11000/api/v1/health/")
    print("   • Run more tests: python clients/test_sample_transaction.py --count 10 --performance")
    
    return 0

if __name__ == "__main__":
    exit(main())
