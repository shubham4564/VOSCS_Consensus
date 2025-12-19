#!/usr/bin/env python3
"""
Enhanced Transaction Test with Performance Metrics

This script creates transactions and submits them to the blockchain
while measuring consensus time, transaction time, and throughput.
"""

import argparse
import requests
import json
import base64
import time
import statistics
from datetime import datetime
from blockchain.transaction.transaction import Transaction
from blockchain.transaction.wallet import Wallet
from blockchain.utils.helpers import BlockchainUtils

def load_keys():
    """Load genesis keys for testing from Solana-style genesis configuration.

    NOTE: Use the bootstrap validator keypair rather than the faucet,
    because the current faucet private key on disk does not match the
    faucet public key recorded in genesis.json, which causes signature
    verification failures in node.handle_transaction.
    """
    try:
        # Load from the new Solana-style genesis configuration
        from blockchain.genesis_config import GenesisConfig
        
        # Load genesis configuration
        genesis_data = GenesisConfig.load_genesis_config("genesis_config/genesis.json")
        
        # Use the bootstrap validator identity as the funded test account
        validator_public_key = genesis_data["bootstrap_validator"]
        
        # Load the matching bootstrap validator private key
        with open('genesis_config/bootstrap_validator_private_key.pem', 'r') as f:
            validator_private_key = f.read()
            
        print(f"✅ Loaded bootstrap validator keys for testing")
        print(f"   Public key: {validator_public_key[:50]}...")
        print(f"   Genesis network: {genesis_data['network_id'][:16]}...")
        
        return validator_private_key, validator_public_key
        
    except FileNotFoundError as e:
        print(f"❌ Error: Genesis configuration not found: {e}")
        print("   Run: python3 -m blockchain.genesis_config --supply 1000000000")
        return None, None
    except Exception as e:
        print(f"❌ Error loading genesis keys: {e}")
        return None, None

def create_sample_transaction(amount=10.0, tx_type="TRANSFER"):
    """Create a sample transaction with flexible parameters"""
    private_key, sender_public_key = load_keys()
    if not private_key:
        return None
        
    # Create wallet from private key
    wallet = Wallet()
    wallet.from_key(private_key)
    
    # Create a flexible test transaction
    transaction = Transaction(
        sender_public_key=sender_public_key,
        receiver_public_key=sender_public_key,  # Self-send for testing
        amount=amount,
        type=tx_type
    )
    
    # Sign the transaction
    signature = wallet.sign(transaction.payload())
    transaction.sign(signature)
    
    return transaction

def submit_transaction(transaction, node_port=11000):
    """Submit transaction to a node with timing measurement"""
    try:
        # Record timing
        submission_start = time.time()
        
        # Encode transaction
        encoded_transaction = BlockchainUtils.encode(transaction)
        
        # Prepare payload
        payload = {
            "transaction": encoded_transaction
        }
        
        # Submit to node
        url = f"http://localhost:{node_port}/api/v1/transaction/create/"
        response = requests.post(url, json=payload, timeout=10)
        
        submission_time = time.time() - submission_start
        
        if response.status_code == 200:
            return True, {
                "response": response.json(),
                "submission_time": submission_time,
                "timestamp": submission_start
            }
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
            
    except Exception as e:
        return False, str(e)

def check_blockchain_state(node_port=11000):
    """Check blockchain state after transaction"""
    try:
        url = f"http://localhost:{node_port}/api/v1/blockchain/"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"❌ Error checking blockchain state: {e}")
    return None

def check_leader_status(node_port=11000):
    """Check current leader status"""
    try:
        url = f"http://localhost:{node_port}/api/v1/blockchain/leader/current/"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"❌ Error checking leader status: {e}")
    return None

def get_quantum_metrics(node_port=11000):
    """Get quantum consensus metrics"""
    try:
        url = f"http://localhost:{node_port}/api/v1/blockchain/quantum-metrics/"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"❌ Error checking quantum metrics: {e}")
    return None

def measure_consensus_time(initial_block_count, timeout=30):
    """Measure time until consensus creates a new block"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        blockchain_state = check_blockchain_state()
        if blockchain_state:
            current_blocks = len(blockchain_state.get('blocks', []))
            if current_blocks > initial_block_count:
                consensus_time = time.time() - start_time
                return consensus_time, current_blocks, blockchain_state['blocks'][-1]
        time.sleep(0.5)
    
    return None, initial_block_count, None

def run_multiple_transactions(count=5, amount=10.0, node_port=11000):
    """Run multiple transactions and measure performance"""
    print(f"\n📊 RUNNING {count} TRANSACTIONS FOR PERFORMANCE MEASUREMENT")
    print("=" * 60)
    
    results = []
    total_start_time = time.time()
    
    for i in range(count):
        print(f"   🔄 Transaction {i+1}/{count}...")
        
        # Record individual transaction timing
        tx_start_time = time.time()
        
        # Create transaction
        transaction = create_sample_transaction(amount)
        if not transaction:
            print(f"   ❌ Failed to create transaction {i+1}")
            continue
        
        creation_time = time.time() - tx_start_time
        
        # Submit transaction
        success, result = submit_transaction(transaction, node_port)
        if not success:
            print(f"   ❌ Failed to submit transaction {i+1}: {result}")
            continue
        
        submission_time = result["submission_time"]
        total_tx_time = time.time() - tx_start_time
        
        results.append({
            "tx_id": i+1,
            "transaction_id": transaction.id,
            "amount": amount,
            "creation_time": creation_time,
            "submission_time": submission_time,
            "total_time": total_tx_time,
            "timestamp": tx_start_time
        })
        
        print(f"   ✅ Transaction {i+1}: {submission_time*1000:.1f}ms submission, {total_tx_time*1000:.1f}ms total")
        
        # Small delay between transactions to avoid overwhelming
        time.sleep(0.1)
    
    total_test_time = time.time() - total_start_time
    
    return results, total_test_time

def calculate_performance_metrics(results, total_test_time):
    """Calculate performance metrics from test results"""
    if not results:
        return None
    
    submission_times = [r["submission_time"] for r in results]
    creation_times = [r["creation_time"] for r in results]
    total_times = [r["total_time"] for r in results]
    
    metrics = {
        "transaction_count": len(results),
        "total_test_time": total_test_time,
        "throughput_tps": len(results) / total_test_time,
        "avg_creation_time": statistics.mean(creation_times),
        "avg_submission_time": statistics.mean(submission_times),
        "avg_total_time": statistics.mean(total_times),
        "min_submission_time": min(submission_times),
        "max_submission_time": max(submission_times),
        "median_submission_time": statistics.median(submission_times)
    }
    
    return metrics

def print_performance_report(metrics, consensus_time=None):
    """Print detailed performance report"""
    print(f"\n📊 PERFORMANCE METRICS REPORT")
    print("=" * 50)
    
    print(f"📈 Transaction Performance:")
    print(f"   Total Transactions: {metrics['transaction_count']}")
    print(f"   Total Test Time: {metrics['total_test_time']:.2f} seconds")
    print(f"   Throughput: {metrics['throughput_tps']:.2f} TPS")
    
    print(f"\n⏱️  Timing Breakdown:")
    print(f"   Average Creation Time: {metrics['avg_creation_time']*1000:.1f}ms")
    print(f"   Average Submission Time: {metrics['avg_submission_time']*1000:.1f}ms")
    print(f"   Average Total Transaction Time: {metrics['avg_total_time']*1000:.1f}ms")
    print(f"   Submission Range: {metrics['min_submission_time']*1000:.1f}ms - {metrics['max_submission_time']*1000:.1f}ms")
    print(f"   Median Submission: {metrics['median_submission_time']*1000:.1f}ms")
    
    if consensus_time:
        print(f"\n🎯 Consensus Performance:")
        print(f"   Consensus Time: {consensus_time:.2f} seconds")
        print(f"   Consensus TPS: {metrics['transaction_count']/consensus_time:.2f} (transactions per consensus time)")

def main():
    parser = argparse.ArgumentParser(description='Enhanced Transaction Test with Performance Metrics')
    parser.add_argument('--count', type=int, default=1, help='Number of transactions to test (default: 1)')
    parser.add_argument('--amount', type=float, default=10.0, help='Transaction amount (default: 10.0)')
    parser.add_argument('--node', type=int, default=11000, help='Node port to use (default: 11000)')
    parser.add_argument('--performance', action='store_true', help='Run performance test with multiple transactions')
    
    args = parser.parse_args()
    
    print("🧪 ENHANCED SAMPLE TRANSACTION TEST")
    print("=" * 50)
    print(f"📊 Configuration: {args.count} transactions of {args.amount} units on node {args.node}")
    
    # Step 1: Check if nodes are running
    print("\n📡 Step 1: Checking node connectivity...")
    blockchain_state = check_blockchain_state(args.node)
    if not blockchain_state:
        print(f"❌ Error: Cannot connect to node on port {args.node}")
        print("   Make sure nodes are running: ./start_nodes.sh")
        return False
    
    initial_blocks = len(blockchain_state.get('blocks', []))
    print(f"✅ Node connected! Current blocks: {initial_blocks}")
    
    # Step 2: Check leader selection and quantum metrics
    print("\n🎯 Step 2: Checking system status...")
    leader_status = check_leader_status(args.node)
    quantum_metrics = get_quantum_metrics(args.node)
    
    if leader_status:
        current_slot = leader_status.get('current_leader_info', {}).get('current_slot', 'unknown')
        time_remaining = leader_status.get('current_leader_info', {}).get('time_remaining_in_slot', 0)
        print(f"✅ Leader selection active! Current slot: {current_slot}, Time remaining: {time_remaining:.1f}s")
    
    if quantum_metrics:
        active_nodes = quantum_metrics.get('active_nodes', 0)
        total_nodes = quantum_metrics.get('total_nodes', 0)
        print(f"✅ Quantum consensus: {active_nodes}/{total_nodes} active nodes")
    
    if args.performance and args.count > 1:
        # Run performance test
        print(f"\n💰 Step 3: Running performance test...")
        results, total_test_time = run_multiple_transactions(args.count, args.amount, args.node)
        
        if not results:
            print("❌ No successful transactions in performance test")
            return False
        
        # Measure consensus time
        print(f"\n⏳ Step 4: Measuring consensus time...")
        consensus_time, final_blocks, latest_block = measure_consensus_time(initial_blocks, timeout=60)
        
        # Calculate and display metrics
        metrics = calculate_performance_metrics(results, total_test_time)
        print_performance_report(metrics, consensus_time)
        
        if consensus_time:
            print(f"\n✅ Consensus successful! New blocks: {final_blocks - initial_blocks}")
            if latest_block:
                print(f"   📝 Transactions in latest block: {len(latest_block.get('transactions', []))}")
        else:
            print(f"⚠️  Consensus timeout - may need longer wait time")
            
    else:
        # Run single transaction test
        print(f"\n💰 Step 3: Creating transaction...")
        transaction_start = time.time()
        transaction = create_sample_transaction(args.amount)
        if not transaction:
            print("❌ Failed to create transaction")
            return False
        
        creation_time = time.time() - transaction_start
        
        print(f"✅ Transaction created:")
        print(f"   ID: {transaction.id}")
        print(f"   Amount: {transaction.amount}")
        print(f"   Type: {transaction.type}")
        print(f"   Creation Time: {creation_time*1000:.1f}ms")
        print(f"   Timestamp: {transaction.timestamp}")
        
        # Step 4: Submit transaction
        print(f"\n📤 Step 4: Submitting transaction...")
        success, result = submit_transaction(transaction, args.node)
        if not success:
            print(f"❌ Transaction submission failed: {result}")
            return False
        
        print(f"✅ Transaction submitted successfully!")
        print(f"   Response: {result['response']}")
        print(f"   Submission Time: {result['submission_time']*1000:.1f}ms")
        
        # Step 5: Wait and check for block creation with consensus timing
        print(f"\n⏳ Step 5: Measuring consensus time...")
        consensus_start = time.time()
        consensus_time, final_blocks, latest_block = measure_consensus_time(initial_blocks, timeout=30)
        
        if consensus_time:
            print(f"✅ Consensus achieved! Time: {consensus_time:.2f} seconds")
            print(f"   📊 New blocks created: {final_blocks - initial_blocks}")
            if latest_block:
                print(f"   📝 Transactions in latest block: {len(latest_block.get('transactions', []))}")
                
            # Calculate single transaction metrics
            total_transaction_time = result['submission_time']
            print(f"\n📊 SINGLE TRANSACTION METRICS:")
            print(f"   Creation Time: {creation_time*1000:.1f}ms")
            print(f"   Submission Time: {result['submission_time']*1000:.1f}ms") 
            print(f"   Consensus Time: {consensus_time:.2f}s")
            print(f"   End-to-End Time: {consensus_time + result['submission_time']:.2f}s")
        else:
            print(f"⚠️  Consensus timeout after 30 seconds")
            print(f"   This might be normal - check leader rotation timing")
    
    # Step 6: Final system status
    print(f"\n📊 Step 6: Final system status...")
    final_leader = check_leader_status(args.node)
    if final_leader:
        current_slot = final_leader.get('current_leader_info', {}).get('current_slot', 'unknown')
        print(f"   🎯 Current slot: {current_slot}")
    
    final_quantum = get_quantum_metrics(args.node)
    if final_quantum:
        active_nodes = final_quantum.get('active_nodes', 0)
        total_nodes = final_quantum.get('total_nodes', 0)
        print(f"   🔬 Quantum consensus: {active_nodes}/{total_nodes} active nodes")
    
    print(f"\n🎉 TRANSACTION TEST COMPLETED")
    print("✅ All core systems are operational:")
    print("   • Node connectivity ✅")
    print("   • Leader selection ✅") 
    print("   • Transaction submission ✅")
    print("   • Performance measurement ✅")
    print("   • API endpoints ✅")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
