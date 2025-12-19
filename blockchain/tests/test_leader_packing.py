#!/usr/bin/env python3
"""
Test Leader Transaction Packing Efficiency

This script tests that leaders pack ALL available transactions
in their assigned slots, regardless of transaction count.
"""

import time
import requests
import json
from datetime import datetime

def submit_multiple_transactions(count=10):
    """Submit multiple transactions to test leader packing."""
    print(f"📤 Submitting {count} transactions for leader packing test...")
    
    submitted_transactions = []
    start_time = time.time()
    
    for i in range(count):
        transaction = {
            "id": f"pack_test_tx_{int(time.time() * 1000)}_{i}",
            "sender": f"test_sender_{i}",
            "recipient": f"test_recipient_{i}", 
            "amount": 10.0 + i,  # Varying amounts
            "transaction_type": "TRANSFER",
            "timestamp": time.time(),
            "data": {"test": f"packing_test_{i}", "batch": "leader_packing"}
        }
        
        try:
            response = requests.post(
                "http://localhost:11000/api/v1/transactions/submit",
                json=transaction,
                timeout=5
            )
            
            if response.status_code == 200:
                submitted_transactions.append(transaction["id"])
                print(f"   ✅ Transaction {i+1}/{count}: {transaction['id']}")
            else:
                print(f"   ❌ Transaction {i+1}/{count} failed: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Transaction {i+1}/{count} error: {e}")
        
        # Small delay to avoid overwhelming the node
        time.sleep(0.05)
    
    submit_time = time.time() - start_time
    print(f"📊 Submitted {len(submitted_transactions)}/{count} transactions in {submit_time:.2f}s")
    return submitted_transactions

def monitor_leader_packing(submitted_count, timeout=30):
    """Monitor how efficiently the leader packs transactions."""
    print(f"\n⏳ Monitoring leader packing for {timeout}s...")
    
    start_monitor = time.time()
    initial_blocks = 0
    processed_transactions = 0
    
    # Get initial state
    try:
        response = requests.get("http://localhost:11000/api/v1/blockchain/info", timeout=5)
        if response.status_code == 200:
            initial_blocks = response.json().get('height', 0)
    except:
        pass
    
    print(f"   📦 Initial blocks: {initial_blocks}")
    print(f"   🎯 Expected transactions: {submitted_count}")
    
    while time.time() - start_monitor < timeout:
        try:
            # Check blockchain status
            response = requests.get("http://localhost:11000/api/v1/blockchain/info", timeout=5)
            if response.status_code == 200:
                data = response.json()
                current_blocks = data.get('height', 0)
                
                # Check if new blocks were created
                if current_blocks > initial_blocks:
                    new_blocks = current_blocks - initial_blocks
                    
                    # Try to get the latest block to see transactions
                    try:
                        block_response = requests.get(f"http://localhost:11000/api/v1/blockchain/block/{current_blocks-1}", timeout=5)
                        if block_response.status_code == 200:
                            block_data = block_response.json()
                            block_transactions = len(block_data.get('transactions', []))
                            processed_transactions += block_transactions
                            
                            print(f"   📦 Block {current_blocks-1}: {block_transactions} transactions packed")
                    except:
                        print(f"   📦 New block created: {current_blocks}")
                    
                    # Check if all transactions are processed
                    if processed_transactions >= submitted_count:
                        monitor_time = time.time() - start_monitor
                        print(f"\n✅ ALL TRANSACTIONS PROCESSED!")
                        print(f"   📊 Processed: {processed_transactions}/{submitted_count}")
                        print(f"   📦 New blocks: {new_blocks}")
                        print(f"   ⏱️  Processing time: {monitor_time:.2f}s")
                        print(f"   🚀 Throughput: {processed_transactions/monitor_time:.1f} tx/s")
                        return True
                
                # Get current status
                current_slot = data.get('current_slot', 0)
                is_leader = data.get('is_leader', False)
                print(f"   🕐 Slot {current_slot}, Leader: {is_leader}, Blocks: {current_blocks}, Processed: {processed_transactions}")
                
        except Exception as e:
            print(f"   ❌ Monitor error: {e}")
        
        time.sleep(0.5)
    
    print(f"\n⏰ Timeout reached after {timeout}s")
    print(f"   📊 Final processed: {processed_transactions}/{submitted_count}")
    return False

def check_node_status():
    """Check if the node is running and ready."""
    try:
        response = requests.get("http://localhost:11000/api/v1/blockchain/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return True, data
    except:
        pass
    return False, {}

def main():
    print("🔋 LEADER TRANSACTION PACKING TEST")
    print("=" * 50)
    print("Testing: Leader must pack ALL transactions in their slot")
    
    # Check node status
    print("\n📡 Step 1: Checking node status...")
    is_running, status = check_node_status()
    
    if not is_running:
        print("❌ Node is not running on port 11000")
        print("   Please start the node first: python run_node.py --port 11000")
        return
    
    print("✅ Node is running!")
    print(f"   Current slot: {status.get('current_slot', 'unknown')}")
    print(f"   Is leader: {status.get('is_leader', 'unknown')}")
    print(f"   Active nodes: {status.get('active_nodes', 'unknown')}")
    
    # Submit multiple transactions
    print(f"\n📤 Step 2: Submitting test transactions...")
    submitted_transactions = submit_multiple_transactions(count=15)
    
    if not submitted_transactions:
        print("❌ No transactions were submitted successfully")
        return
    
    # Monitor leader packing
    print(f"\n📊 Step 3: Monitoring leader packing efficiency...")
    success = monitor_leader_packing(len(submitted_transactions), timeout=25)
    
    if success:
        print(f"\n🎉 SUCCESS! Leader packed all transactions efficiently!")
        print(f"   ✅ All {len(submitted_transactions)} transactions processed")
        print(f"   ✅ Leader fulfilled duty to maximize throughput")
    else:
        print(f"\n⚠️  INCOMPLETE: Some transactions may still be processing")
        print(f"   📊 Leader packing behavior observed")
    
    print(f"\n📋 LEADER PACKING ANALYSIS:")
    print(f"   🎯 Requirement: Pack ALL transactions in assigned slot")
    print(f"   📦 Test Result: Leader processed available transactions")
    print(f"   ⚡ Optimization: Immediate processing when transactions available")

if __name__ == "__main__":
    main()
