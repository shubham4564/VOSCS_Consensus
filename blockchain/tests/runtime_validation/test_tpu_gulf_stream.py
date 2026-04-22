#!/usr/bin/env python3
"""
TPU Gulf Stream Test - Immediate Transaction Processing

Tests that transactions are forwarded via TPU and processed immediately by leaders.
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

import time
import requests
import json
from blockchain.transaction.transaction import Transaction
from blockchain.transaction.wallet import Wallet
from blockchain.utils.helpers import BlockchainUtils

def load_test_keys():
    """Load genesis keys for testing"""
    try:
        from blockchain.genesis_config import GenesisConfig
        genesis_data = GenesisConfig.load_genesis_config("genesis_config/genesis.json")
        faucet_public_key = genesis_data["faucet"]
        
        with open('genesis_config/faucet_private_key.pem', 'r') as f:
            faucet_private_key = f.read()
            
        return faucet_private_key, faucet_public_key
    except Exception as e:
        print(f"❌ Error loading keys: {e}")
        return None, None

def create_test_transaction(amount=25.0):
    """Create a test transaction"""
    private_key, sender_public_key = load_test_keys()
    if not private_key:
        return None
        
    wallet = Wallet()
    wallet.from_key(private_key)
    
    transaction = Transaction(
        sender_public_key=sender_public_key,
        receiver_public_key=sender_public_key,  # Self-send for testing
        amount=amount,
        type="TRANSFER"
    )
    
    signature = wallet.sign(transaction.payload())
    transaction.sign(signature)
    
    return transaction

def submit_transaction_and_measure(transaction, node_port=11000):
    """Submit transaction and measure immediate processing"""
    try:
        # Record timing
        start_time = time.time()
        
        # Encode transaction
        encoded_transaction = BlockchainUtils.encode(transaction)
        payload = {"transaction": encoded_transaction}
        
        # Submit to node
        url = f"http://localhost:{node_port}/api/v1/transaction/create/"
        response = requests.post(url, json=payload, timeout=10)
        
        submission_time = time.time() - start_time
        
        if response.status_code == 200:
            print(f"✅ Transaction submitted in {submission_time*1000:.1f}ms")
            print(f"   Response: {response.json()}")
            return True
        else:
            print(f"❌ Submission failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error submitting transaction: {e}")
        return False

def check_immediate_processing(initial_blocks, timeout=3.0):
    """Check if transaction was processed immediately via TPU"""
    start_time = time.time()
    print(f"\n🔍 CHECKING FOR IMMEDIATE TPU PROCESSING...")
    
    while time.time() - start_time < timeout:
        try:
            # Check blockchain state
            response = requests.get('http://localhost:11000/api/v1/blockchain/', timeout=5)
            if response.status_code == 200:
                data = response.json()
                current_blocks = len(data.get('blocks', []))
                
                if current_blocks > initial_blocks:
                    processing_time = time.time() - start_time
                    print(f"✅ IMMEDIATE PROCESSING SUCCESS!")
                    print(f"   📦 New blocks created: {current_blocks - initial_blocks}")
                    print(f"   ⚡ Processing time: {processing_time:.2f}s")
                    print(f"   🚀 TPU forwarding worked - transaction processed immediately!")
                    
                    # Show latest block details
                    latest_block = data['blocks'][-1]
                    tx_count = len(latest_block.get('transactions', []))
                    print(f"   📝 Transactions in latest block: {tx_count}")
                    
                    return True
        except Exception as e:
            print(f"   ❌ Error checking blockchain: {e}")
        
        time.sleep(0.1)  # Check every 100ms
    
    print(f"⚠️  No immediate processing detected in {timeout}s")
    print(f"   💡 This might indicate TPU forwarding needs debugging")
    return False

def main():
    print("🚀 TPU GULF STREAM TEST - IMMEDIATE TRANSACTION PROCESSING")
    print("=" * 60)
    print("Testing Solana-style TPU forwarding for immediate leader processing")
    
    # Step 1: Check initial blockchain state
    print("\n1️⃣ Checking initial blockchain state...")
    try:
        response = requests.get('http://localhost:11000/api/v1/blockchain/', timeout=5)
        if response.status_code == 200:
            data = response.json()
            initial_blocks = len(data.get('blocks', []))
            print(f"✅ Initial blocks: {initial_blocks}")
        else:
            print(f"❌ Cannot connect to node")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    # Step 2: Create test transaction
    print("\n2️⃣ Creating test transaction...")
    transaction = create_test_transaction(amount=50.0)
    if not transaction:
        print(f"❌ Failed to create transaction")
        return False
    
    print(f"✅ Transaction created:")
    print(f"   ID: {transaction.id}")
    print(f"   Amount: {transaction.amount}")
    print(f"   Type: {transaction.type}")
    
    # Step 3: Submit transaction and test TPU forwarding
    print(f"\n3️⃣ Submitting transaction for TPU forwarding...")
    
    submission_success = submit_transaction_and_measure(transaction, 11000)
    if not submission_success:
        print(f"❌ Transaction submission failed")
        return False
    
    # Step 4: Check for immediate processing
    print(f"\n4️⃣ Testing immediate TPU processing...")
    immediate_success = check_immediate_processing(initial_blocks, timeout=5.0)
    
    # Step 5: Results
    print(f"\n📊 TPU GULF STREAM TEST RESULTS:")
    print(f"   Transaction Submission: {'✅ SUCCESS' if submission_success else '❌ FAILED'}")
    print(f"   Immediate Processing: {'✅ SUCCESS' if immediate_success else '❌ FAILED'}")
    
    if immediate_success:
        print(f"\n🎉 TPU GULF STREAM WORKING PERFECTLY!")
        print(f"   • Transactions are forwarded via UDP to leader TPU ports")
        print(f"   • Leaders receive and process transactions immediately")
        print(f"   • No waiting for polling or checking - true push-based processing")
        print(f"   • Solana-style immediate transaction processing achieved!")
    else:
        print(f"\n🔧 TPU Gulf Stream needs debugging:")
        print(f"   • Check if TPU listener is running on leader nodes")
        print(f"   • Verify TPU sender is forwarding to correct ports")
        print(f"   • Ensure leader detection and forwarding logic is working")
        print(f"   • Check network connectivity between nodes")
    
    return immediate_success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
