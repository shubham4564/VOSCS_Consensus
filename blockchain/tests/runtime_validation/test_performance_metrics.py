#!/usr/bin/env python3
"""
Advanced Transaction Performance Test

This script measures consensus time, transaction time, and transaction throughput
with flexible transaction testing capabilities.
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
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from blockchain.transaction.transaction import Transaction
from blockchain.transaction.wallet import Wallet
from blockchain.utils.helpers import BlockchainUtils

class TransactionPerformanceTester:
    def __init__(self, node_ports=[11000, 11001, 11002]):
        self.node_ports = node_ports
        self.results = []
        self.lock = threading.Lock()
        
    def load_keys(self):
        """Load genesis keys for testing"""
        try:
            from blockchain.genesis_config import GenesisConfig
            genesis_data = GenesisConfig.load_genesis_config("genesis_config/genesis.json")
            faucet_public_key = genesis_data["faucet"]
            
            with open('genesis_config/faucet_private_key.pem', 'r') as f:
                faucet_private_key = f.read()
                
            print(f"✅ Loaded faucet keys for testing")
            print(f"   Public key: {faucet_public_key[:50]}...")
            print(f"   Genesis network: {genesis_data['network_id'][:16]}...")
            
            return faucet_private_key, faucet_public_key
            
        except Exception as e:
            print(f"❌ Error loading genesis keys: {e}")
            return None, None

    def create_transaction(self, amount=10.0, tx_type="TRANSFER"):
        """Create a single transaction"""
        private_key, sender_public_key = self.load_keys()
        if not private_key:
            return None
            
        wallet = Wallet()
        wallet.from_key(private_key)
        
        transaction = Transaction(
            sender_public_key=sender_public_key,
            receiver_public_key=sender_public_key,  # Self-send for testing
            amount=amount,
            type=tx_type
        )
        
        signature = wallet.sign(transaction.payload())
        transaction.sign(signature)
        
        return transaction, wallet

    def submit_transaction_with_timing(self, transaction, node_port=11000):
        """Submit transaction and measure timing metrics"""
        try:
            # Record submission start time
            submission_start = time.time()
            
            # Encode transaction
            encoded_transaction = BlockchainUtils.encode(transaction)
            payload = {"transaction": encoded_transaction}
            
            # Submit to node
            url = f"http://localhost:{node_port}/api/v1/transaction/create/"
            response = requests.post(url, json=payload, timeout=30)
            
            submission_end = time.time()
            submission_time = submission_end - submission_start
            
            if response.status_code == 200:
                return True, {
                    "submission_time": submission_time,
                    "submission_timestamp": submission_start,
                    "response": response.json()
                }
            else:
                return False, f"HTTP {response.status_code}: {response.text}"
                
        except Exception as e:
            return False, str(e)

    def get_blockchain_state(self, node_port=11000):
        """Get current blockchain state"""
        try:
            url = f"http://localhost:{node_port}/api/v1/blockchain/"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"❌ Error getting blockchain state: {e}")
        return None

    def get_leader_info(self, node_port=11000):
        """Get current leader information"""
        try:
            url = f"http://localhost:{node_port}/api/v1/blockchain/leader/current/"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"❌ Error getting leader info: {e}")
        return None

    def get_quantum_metrics(self, node_port=11000):
        """Get quantum consensus metrics"""
        try:
            url = f"http://localhost:{node_port}/api/v1/blockchain/quantum-metrics/"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"❌ Error getting quantum metrics: {e}")
        return None

    def wait_for_block_creation(self, initial_block_count, timeout=60):
        """Wait for new block creation and measure consensus time"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            current_state = self.get_blockchain_state()
            if current_state:
                current_block_count = len(current_state.get('blocks', []))
                
                if current_block_count > initial_block_count:
                    consensus_time = time.time() - start_time
                    latest_block = current_state['blocks'][-1]
                    
                    return True, {
                        "consensus_time": consensus_time,
                        "new_block_count": current_block_count,
                        "block_increase": current_block_count - initial_block_count,
                        "latest_block": latest_block,
                        "transactions_in_block": len(latest_block.get('transactions', []))
                    }
            
            time.sleep(0.5)  # Check every 500ms
        
        return False, {"timeout": timeout}

    def single_transaction_test(self, tx_id, amount=10.0, node_port=11000):
        """Test a single transaction and measure all timing metrics"""
        test_start = time.time()
        
        # Get initial state
        initial_state = self.get_blockchain_state(node_port)
        if not initial_state:
            return {"error": "Cannot get initial blockchain state"}
        
        initial_block_count = len(initial_state.get('blocks', []))
        
        # Create transaction
        transaction, wallet = self.create_transaction(amount)
        if not transaction:
            return {"error": "Failed to create transaction"}
        
        creation_time = time.time() - test_start
        
        # Submit transaction
        success, submit_result = self.submit_transaction_with_timing(transaction, node_port)
        if not success:
            return {"error": f"Transaction submission failed: {submit_result}"}
        
        submission_time = submit_result["submission_time"]
        
        # Wait for block creation
        block_success, block_result = self.wait_for_block_creation(initial_block_count)
        
        total_time = time.time() - test_start
        
        result = {
            "tx_id": tx_id,
            "transaction_id": transaction.id,
            "amount": amount,
            "node_port": node_port,
            "creation_time": creation_time,
            "submission_time": submission_time,
            "total_transaction_time": total_time,
            "block_created": block_success,
            "timestamp": test_start
        }
        
        if block_success:
            result["consensus_time"] = block_result["consensus_time"]
            result["transactions_in_block"] = block_result["transactions_in_block"]
            result["block_increase"] = block_result["block_increase"]
        else:
            result["consensus_timeout"] = True
            
        return result

    def concurrent_transaction_test(self, num_transactions=10, amount=10.0, max_workers=5):
        """Test multiple transactions concurrently to measure throughput"""
        print(f"\n🚀 CONCURRENT TRANSACTION TEST ({num_transactions} transactions)")
        print("=" * 60)
        
        start_time = time.time()
        results = []
        
        # Get initial blockchain state
        initial_state = self.get_blockchain_state()
        initial_block_count = len(initial_state.get('blocks', []))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all transactions concurrently
            futures = []
            for i in range(num_transactions):
                node_port = self.node_ports[i % len(self.node_ports)]  # Distribute across nodes
                future = executor.submit(self.single_transaction_test, i+1, amount, node_port)
                futures.append(future)
            
            # Collect results as they complete
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                    if "error" not in result:
                        print(f"   ✅ Transaction {result['tx_id']}: {result['submission_time']*1000:.1f}ms submission")
                    else:
                        print(f"   ❌ Transaction failed: {result['error']}")
                except Exception as e:
                    print(f"   ❌ Transaction error: {e}")
        
        total_test_time = time.time() - start_time
        
        # Wait for all blocks to be created
        print(f"\n⏳ Waiting for block creation (up to 30 seconds)...")
        final_wait_start = time.time()
        
        while time.time() - final_wait_start < 30:
            current_state = self.get_blockchain_state()
            if current_state:
                current_block_count = len(current_state.get('blocks', []))
                if current_block_count > initial_block_count:
                    break
            time.sleep(1)
        
        return results, total_test_time

    def calculate_performance_metrics(self, results, total_test_time):
        """Calculate comprehensive performance metrics"""
        successful_results = [r for r in results if "error" not in r]
        
        if not successful_results:
            return {"error": "No successful transactions"}
        
        # Transaction timing metrics
        submission_times = [r["submission_time"] for r in successful_results]
        creation_times = [r["creation_time"] for r in successful_results]
        total_tx_times = [r["total_transaction_time"] for r in successful_results]
        
        # Consensus timing metrics
        consensus_results = [r for r in successful_results if "consensus_time" in r]
        consensus_times = [r["consensus_time"] for r in consensus_results] if consensus_results else []
        
        # Throughput calculations
        successful_count = len(successful_results)
        throughput_tps = successful_count / total_test_time if total_test_time > 0 else 0
        
        metrics = {
            "total_transactions": len(results),
            "successful_transactions": successful_count,
            "failed_transactions": len(results) - successful_count,
            "success_rate": (successful_count / len(results)) * 100 if results else 0,
            "total_test_time": total_test_time,
            "throughput_tps": throughput_tps,
            
            "transaction_timing": {
                "avg_creation_time": statistics.mean(creation_times),
                "avg_submission_time": statistics.mean(submission_times),
                "avg_total_transaction_time": statistics.mean(total_tx_times),
                "min_submission_time": min(submission_times),
                "max_submission_time": max(submission_times),
                "median_submission_time": statistics.median(submission_times)
            }
        }
        
        if consensus_times:
            metrics["consensus_timing"] = {
                "avg_consensus_time": statistics.mean(consensus_times),
                "min_consensus_time": min(consensus_times),
                "max_consensus_time": max(consensus_times),
                "median_consensus_time": statistics.median(consensus_times),
                "consensus_success_rate": (len(consensus_times) / successful_count) * 100
            }
        else:
            metrics["consensus_timing"] = {"error": "No consensus timing data available"}
        
        return metrics

    def print_performance_report(self, metrics):
        """Print detailed performance report"""
        print(f"\n📊 PERFORMANCE METRICS REPORT")
        print("=" * 60)
        
        # Transaction Summary
        print(f"📈 Transaction Summary:")
        print(f"   Total Transactions: {metrics['total_transactions']}")
        print(f"   Successful: {metrics['successful_transactions']}")
        print(f"   Failed: {metrics['failed_transactions']}")
        print(f"   Success Rate: {metrics['success_rate']:.1f}%")
        
        # Throughput
        print(f"\n🚀 Throughput:")
        print(f"   Total Test Time: {metrics['total_test_time']:.2f} seconds")
        print(f"   Transactions Per Second (TPS): {metrics['throughput_tps']:.2f}")
        
        # Transaction Timing
        tx_timing = metrics["transaction_timing"]
        print(f"\n⏱️  Transaction Timing:")
        print(f"   Average Creation Time: {tx_timing['avg_creation_time']*1000:.1f}ms")
        print(f"   Average Submission Time: {tx_timing['avg_submission_time']*1000:.1f}ms")
        print(f"   Average Total Transaction Time: {tx_timing['avg_total_transaction_time']*1000:.1f}ms")
        print(f"   Submission Time Range: {tx_timing['min_submission_time']*1000:.1f}ms - {tx_timing['max_submission_time']*1000:.1f}ms")
        print(f"   Median Submission Time: {tx_timing['median_submission_time']*1000:.1f}ms")
        
        # Consensus Timing
        if "error" not in metrics["consensus_timing"]:
            consensus_timing = metrics["consensus_timing"]
            print(f"\n🎯 Consensus Timing:")
            print(f"   Average Consensus Time: {consensus_timing['avg_consensus_time']:.2f} seconds")
            print(f"   Consensus Time Range: {consensus_timing['min_consensus_time']:.2f}s - {consensus_timing['max_consensus_time']:.2f}s")
            print(f"   Median Consensus Time: {consensus_timing['median_consensus_time']:.2f} seconds")
            print(f"   Consensus Success Rate: {consensus_timing['consensus_success_rate']:.1f}%")
        else:
            print(f"\n🎯 Consensus Timing: {metrics['consensus_timing']['error']}")

def main():
    parser = argparse.ArgumentParser(description='Transaction Performance Tester')
    parser.add_argument('--count', type=int, default=5, help='Number of transactions to test (default: 5)')
    parser.add_argument('--amount', type=float, default=10.0, help='Transaction amount (default: 10.0)')
    parser.add_argument('--concurrent', action='store_true', help='Run transactions concurrently')
    parser.add_argument('--workers', type=int, default=3, help='Number of concurrent workers (default: 3)')
    parser.add_argument('--nodes', nargs='+', type=int, default=[11000, 11001, 11002], help='Node ports to use')
    parser.add_argument('--single', action='store_true', help='Run single transaction test')
    
    args = parser.parse_args()
    
    tester = TransactionPerformanceTester(node_ports=args.nodes)
    
    print(f"🧪 BLOCKCHAIN TRANSACTION PERFORMANCE TEST")
    print("=" * 60)
    print(f"📊 Test Configuration:")
    print(f"   Transaction Count: {args.count}")
    print(f"   Transaction Amount: {args.amount}")
    print(f"   Concurrent Mode: {args.concurrent}")
    print(f"   Worker Threads: {args.workers}")
    print(f"   Target Nodes: {args.nodes}")
    
    # Check initial system state
    print(f"\n🔍 Checking initial system state...")
    initial_state = tester.get_blockchain_state()
    leader_info = tester.get_leader_info()
    quantum_metrics = tester.get_quantum_metrics()
    
    if not initial_state:
        print("❌ Cannot connect to blockchain nodes. Make sure nodes are running.")
        return False
    
    print(f"✅ System Status:")
    print(f"   Blockchain Length: {len(initial_state.get('blocks', []))} blocks")
    if leader_info:
        current_slot = leader_info.get('current_leader_info', {}).get('current_slot', 'unknown')
        print(f"   Current Slot: {current_slot}")
    if quantum_metrics:
        print(f"   Active Nodes: {quantum_metrics.get('active_nodes', 0)}/{quantum_metrics.get('total_nodes', 0)}")
    
    if args.single:
        # Single transaction test
        print(f"\n🎯 SINGLE TRANSACTION TEST")
        print("=" * 40)
        result = tester.single_transaction_test(1, args.amount)
        
        if "error" in result:
            print(f"❌ Test failed: {result['error']}")
            return False
        
        print(f"✅ Transaction Results:")
        print(f"   Transaction ID: {result['transaction_id']}")
        print(f"   Creation Time: {result['creation_time']*1000:.1f}ms")
        print(f"   Submission Time: {result['submission_time']*1000:.1f}ms")
        print(f"   Total Transaction Time: {result['total_transaction_time']*1000:.1f}ms")
        
        if "consensus_time" in result:
            print(f"   Consensus Time: {result['consensus_time']:.2f} seconds")
            print(f"   Transactions in Block: {result['transactions_in_block']}")
        else:
            print(f"   Consensus: Timed out")
        
    elif args.concurrent:
        # Concurrent transaction test
        results, total_time = tester.concurrent_transaction_test(
            num_transactions=args.count,
            amount=args.amount,
            max_workers=args.workers
        )
        
        metrics = tester.calculate_performance_metrics(results, total_time)
        tester.print_performance_report(metrics)
        
    else:
        # Sequential transaction test
        print(f"\n📈 SEQUENTIAL TRANSACTION TEST ({args.count} transactions)")
        print("=" * 60)
        
        results = []
        start_time = time.time()
        
        for i in range(args.count):
            node_port = args.nodes[i % len(args.nodes)]
            print(f"   🔄 Testing transaction {i+1}/{args.count} on node {node_port}...")
            
            result = tester.single_transaction_test(i+1, args.amount, node_port)
            results.append(result)
            
            if "error" in result:
                print(f"   ❌ Transaction {i+1} failed: {result['error']}")
            else:
                print(f"   ✅ Transaction {i+1}: {result['submission_time']*1000:.1f}ms submission")
                if "consensus_time" in result:
                    print(f"      Consensus: {result['consensus_time']:.2f}s")
        
        total_time = time.time() - start_time
        metrics = tester.calculate_performance_metrics(results, total_time)
        tester.print_performance_report(metrics)
    
    print(f"\n🎉 TEST COMPLETED!")
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
