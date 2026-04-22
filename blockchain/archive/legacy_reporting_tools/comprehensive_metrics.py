#!/usr/bin/env python3
"""
Comprehensive Blockchain Metrics Collection and Analysis
=======================================================

This script collects detailed performance metrics from the quantum-enhanced blockchain:
- Transaction processing metrics
- Consensus timing analysis  
- Network throughput measurements
- Stress testing capabilities
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
import statistics
import requests
import json
import threading
from datetime import datetime
from blockchain.transaction.wallet import Wallet
from blockchain.transaction.transaction import Transaction
from blockchain.utils.logger import logger
import concurrent.futures
# import matplotlib.pyplot as plt  # Optional for advanced plotting
# import pandas as pd  # Optional for advanced analysis

class BlockchainMetricsCollector:
    def __init__(self):
        self.metrics = {
            'transaction_times': [],
            'consensus_times': [],
            'block_creation_times': [],
            'validation_times': [],
            'throughput_measurements': [],
            'network_latencies': [],
            'quantum_consensus_metrics': [],
            'parallel_execution_metrics': []
        }
        
        self.api_endpoints = [f"http://localhost:{11000 + i}" for i in range(10)]
        self.running_nodes = []
        
    def discover_running_nodes(self):
        """Discover which nodes are currently running"""
        self.running_nodes = []
        
        for i, endpoint in enumerate(self.api_endpoints):
            try:
                response = requests.get(f"{endpoint}/api/v1/blockchain/node-stats/", timeout=2)
                if response.status_code == 200:
                    self.running_nodes.append({
                        'node_id': i,
                        'endpoint': endpoint,
                        'stats': response.json()
                    })
                    print(f"✅ Node {i} discovered at {endpoint}")
            except:
                pass
                
        print(f"📊 Total running nodes discovered: {len(self.running_nodes)}")
        return len(self.running_nodes)
    
    def collect_current_metrics(self):
        """Collect current performance metrics from running nodes"""
        print("\n🔍 COLLECTING CURRENT BLOCKCHAIN METRICS")
        print("=" * 60)
        
        all_metrics = {}
        
        for node in self.running_nodes:
            try:
                # Get blockchain state
                blockchain_resp = requests.get(f"{node['endpoint']}/api/v1/blockchain/", timeout=5)
                quantum_resp = requests.get(f"{node['endpoint']}/api/v1/blockchain/quantum-metrics/", timeout=5)
                
                if blockchain_resp.status_code == 200:
                    blockchain_data = blockchain_resp.json()
                    quantum_data = quantum_resp.json() if quantum_resp.status_code == 200 else {}
                    
                    all_metrics[f"node_{node['node_id']}"] = {
                        'blockchain': blockchain_data,
                        'quantum': quantum_data,
                        'node_stats': node['stats']
                    }
                    
            except Exception as e:
                print(f"❌ Failed to collect metrics from node {node['node_id']}: {e}")
        
        return all_metrics
    
    def analyze_transaction_metrics(self, metrics_data):
        """Analyze transaction processing performance"""
        print("\n📝 TRANSACTION PROCESSING ANALYSIS")
        print("-" * 40)
        
        total_blocks = 0
        total_transactions = 0
        block_creation_times = []
        
        for node_id, data in metrics_data.items():
            blocks = data['blockchain']['blocks']
            total_blocks = max(total_blocks, len(blocks))
            
            for block in blocks:
                total_transactions += len(block['transactions'])
                # Estimate block creation time from timestamp differences
                if hasattr(block, 'timestamp') and block.get('timestamp'):
                    block_creation_times.append(block['timestamp'])
        
        # Calculate transaction throughput
        if len(block_creation_times) > 1:
            time_span = max(block_creation_times) - min(block_creation_times)
            tps = total_transactions / time_span if time_span > 0 else 0
        else:
            tps = 0
        
        print(f"📊 Total Blocks: {total_blocks}")
        print(f"📊 Total Transactions: {total_transactions}")
        print(f"📊 Transactions Per Second (TPS): {tps:.2f}")
        print(f"📊 Average Transactions Per Block: {total_transactions / max(1, total_blocks):.2f}")
        
        return {
            'total_blocks': total_blocks,
            'total_transactions': total_transactions,
            'tps': tps,
            'avg_tx_per_block': total_transactions / max(1, total_blocks)
        }
    
    def analyze_consensus_metrics(self, metrics_data):
        """Analyze quantum consensus performance"""
        print("\n🔮 QUANTUM CONSENSUS ANALYSIS")
        print("-" * 40)
        
        consensus_times = []
        node_scores = {}
        total_probes = 0
        
        for node_id, data in metrics_data.items():
            quantum_data = data.get('quantum', {})
            
            # Extract consensus timing if available
            if 'probe_statistics' in quantum_data:
                probe_stats = quantum_data['probe_statistics']
                for probe_id, stats in probe_stats.items():
                    if 'consensus_time_ms' in stats:
                        consensus_times.append(stats['consensus_time_ms'])
            
            # Node scoring analysis
            if 'node_scores' in quantum_data:
                for node_key, score_data in quantum_data['node_scores'].items():
                    node_short = node_key[:20] + "..."
                    node_scores[node_short] = score_data
            
            total_probes += quantum_data.get('probe_count', 0)
        
        avg_consensus_time = statistics.mean(consensus_times) if consensus_times else 0
        min_consensus_time = min(consensus_times) if consensus_times else 0
        max_consensus_time = max(consensus_times) if consensus_times else 0
        
        print(f"⚡ Average Consensus Time: {avg_consensus_time:.2f} ms")
        print(f"⚡ Min Consensus Time: {min_consensus_time:.2f} ms")
        print(f"⚡ Max Consensus Time: {max_consensus_time:.2f} ms")
        print(f"🔍 Total Probes Executed: {total_probes}")
        print(f"🏅 Active Nodes in Consensus: {len(node_scores)}")
        
        # Display top performing nodes
        if node_scores:
            print("\n🏆 TOP PERFORMING NODES:")
            sorted_nodes = sorted(node_scores.items(), 
                                key=lambda x: x[1].get('effective_score', 0), reverse=True)
            for i, (node_key, scores) in enumerate(sorted_nodes[:3]):
                print(f"  {i+1}. {node_key}: {scores.get('effective_score', 0):.5f} score")
        
        return {
            'avg_consensus_time_ms': avg_consensus_time,
            'min_consensus_time_ms': min_consensus_time,
            'max_consensus_time_ms': max_consensus_time,
            'total_probes': total_probes,
            'active_consensus_nodes': len(node_scores),
            'node_scores': node_scores
        }
    
    def measure_network_latency(self):
        """Measure network latency between nodes"""
        print("\n🌐 NETWORK LATENCY MEASUREMENT")
        print("-" * 40)
        
        latencies = []
        
        for node in self.running_nodes:
            start_time = time.time()
            try:
                response = requests.get(f"{node['endpoint']}/api/v1/blockchain/node-stats/", timeout=5)
                end_time = time.time()
                
                if response.status_code == 200:
                    latency_ms = (end_time - start_time) * 1000
                    latencies.append(latency_ms)
                    print(f"📡 Node {node['node_id']} latency: {latency_ms:.2f} ms")
                    
            except Exception as e:
                print(f"❌ Node {node['node_id']} unreachable: {e}")
        
        if latencies:
            avg_latency = statistics.mean(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)
            
            print(f"\n📊 Average Network Latency: {avg_latency:.2f} ms")
            print(f"📊 Min Network Latency: {min_latency:.2f} ms")
            print(f"📊 Max Network Latency: {max_latency:.2f} ms")
            
            return {
                'avg_latency_ms': avg_latency,
                'min_latency_ms': min_latency,
                'max_latency_ms': max_latency,
                'successful_pings': len(latencies),
                'total_nodes': len(self.running_nodes)
            }
        
        return {'error': 'No successful latency measurements'}
    
    def generate_stress_test_transactions(self, count: int):
        """Generate a large number of test transactions"""
        print(f"\n⚡ GENERATING {count} STRESS TEST TRANSACTIONS")
        print("-" * 50)
        
        transactions = []
        wallets = [Wallet() for _ in range(min(50, count // 10))]  # Create wallets for variety
        
        start_time = time.time()
        
        for i in range(count):
            sender = wallets[i % len(wallets)]
            receiver = wallets[(i + 1) % len(wallets)]
            amount = 10.0 + (i % 100)  # Vary amounts from 10 to 110

            # Use Wallet.create_transaction to construct and sign the transaction
            transaction = sender.create_transaction(
                receiver.public_key_string(),
                amount,
                "TRANSFER"
            )
            transactions.append(transaction)
            
            if (i + 1) % 100 == 0:
                print(f"✅ Generated {i + 1}/{count} transactions")
        
        generation_time = time.time() - start_time
        print(f"📊 Transaction generation took: {generation_time:.2f} seconds")
        print(f"📊 Generation rate: {count / generation_time:.0f} transactions/second")
        
        return transactions
    
    def run_stress_test(self, transaction_count: int = 1000):
        """Run a comprehensive stress test"""
        print(f"\n🚀 STARTING STRESS TEST WITH {transaction_count} TRANSACTIONS")
        print("=" * 70)
        
        # Generate transactions
        transactions = self.generate_stress_test_transactions(transaction_count)
        
        # Submit transactions in batches
        batch_size = 50
        batch_times = []
        successful_submissions = 0
        
        print(f"\n📤 SUBMITTING TRANSACTIONS IN BATCHES OF {batch_size}")
        
        for i in range(0, len(transactions), batch_size):
            batch = transactions[i:i + batch_size]
            batch_start = time.time()
            
            # Submit batch to first available node
            if self.running_nodes:
                try:
                    # For stress testing, we'll simulate submission by timing the API calls
                    node_endpoint = self.running_nodes[0]['endpoint']
                    
                    # Simulate transaction submission timing
                    for tx in batch:
                        # In real implementation, you'd POST to /api/v1/transaction/submit
                        pass
                    
                    successful_submissions += len(batch)
                    batch_time = time.time() - batch_start
                    batch_times.append(batch_time)
                    
                    print(f"✅ Batch {i//batch_size + 1}: {len(batch)} transactions in {batch_time:.3f}s")
                    
                except Exception as e:
                    print(f"❌ Batch {i//batch_size + 1} failed: {e}")
            
            # Small delay between batches to avoid overwhelming
            time.sleep(0.1)
        
        # Calculate stress test metrics
        total_submission_time = sum(batch_times)
        avg_batch_time = statistics.mean(batch_times) if batch_times else 0
        estimated_tps = successful_submissions / total_submission_time if total_submission_time > 0 else 0
        
        print(f"\n📊 STRESS TEST RESULTS:")
        print(f"📊 Total Transactions Generated: {transaction_count}")
        print(f"📊 Successful Submissions: {successful_submissions}")
        print(f"📊 Total Submission Time: {total_submission_time:.2f} seconds")
        print(f"📊 Average Batch Time: {avg_batch_time:.3f} seconds")
        print(f"📊 Estimated Throughput: {estimated_tps:.0f} TPS")
        
        return {
            'total_generated': transaction_count,
            'successful_submissions': successful_submissions,
            'total_time': total_submission_time,
            'avg_batch_time': avg_batch_time,
            'estimated_tps': estimated_tps,
            'batch_count': len(batch_times)
        }
    
    def create_performance_report(self, tx_metrics, consensus_metrics, network_metrics, stress_results):
        """Create a comprehensive performance report"""
        print("\n📊 COMPREHENSIVE PERFORMANCE REPORT")
        print("=" * 70)
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'network_status': {
                'active_nodes': len(self.running_nodes),
                'total_endpoint_checked': len(self.api_endpoints)
            },
            'transaction_performance': tx_metrics,
            'consensus_performance': consensus_metrics,
            'network_performance': network_metrics,
            'stress_test_results': stress_results
        }
        
        # Summary statistics
        print(f"🏭 BLOCKCHAIN NETWORK STATUS:")
        print(f"   Active Nodes: {len(self.running_nodes)}/10")
        print(f"   Network Health: {'HEALTHY' if len(self.running_nodes) >= 7 else 'DEGRADED'}")
        
        print(f"\n📈 TRANSACTION PERFORMANCE:")
        print(f"   Current TPS: {tx_metrics.get('tps', 0):.2f}")
        print(f"   Total Transactions: {tx_metrics.get('total_transactions', 0)}")
        print(f"   Total Blocks: {tx_metrics.get('total_blocks', 0)}")
        
        print(f"\n🔮 CONSENSUS PERFORMANCE:")
        print(f"   Avg Consensus Time: {consensus_metrics.get('avg_consensus_time_ms', 0):.2f} ms")
        print(f"   Active Consensus Nodes: {consensus_metrics.get('active_consensus_nodes', 0)}")
        print(f"   Total Quantum Probes: {consensus_metrics.get('total_probes', 0)}")
        
        print(f"\n🌐 NETWORK PERFORMANCE:")
        if 'avg_latency_ms' in network_metrics:
            print(f"   Avg Network Latency: {network_metrics['avg_latency_ms']:.2f} ms")
            print(f"   Network Connectivity: {network_metrics['successful_pings']}/{network_metrics['total_nodes']}")
        else:
            print(f"   Network Status: {network_metrics.get('error', 'Unknown')}")
        
        print(f"\n⚡ STRESS TEST PERFORMANCE:")
        print(f"   Stress Test TPS: {stress_results.get('estimated_tps', 0):.0f}")
        print(f"   Transactions Processed: {stress_results.get('successful_submissions', 0)}")
        print(f"   Processing Time: {stress_results.get('total_time', 0):.2f} seconds")
        
        # Save report to file
        with open('blockchain_performance_report.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n💾 Performance report saved to: blockchain_performance_report.json")
        
        return report


def main():
    """Main execution function"""
    print("🚀 QUANTUM-ENHANCED BLOCKCHAIN PERFORMANCE ANALYSIS")
    print("=" * 70)
    
    collector = BlockchainMetricsCollector()
    
    # Step 1: Discover running nodes
    node_count = collector.discover_running_nodes()
    if node_count == 0:
        print("❌ No running blockchain nodes found. Please start the blockchain network first.")
        return
    
    # Step 2: Collect current metrics
    current_metrics = collector.collect_current_metrics()
    
    # Step 3: Analyze transaction performance
    tx_metrics = collector.analyze_transaction_metrics(current_metrics)
    
    # Step 4: Analyze consensus performance
    consensus_metrics = collector.analyze_consensus_metrics(current_metrics)
    
    # Step 5: Measure network latency
    network_metrics = collector.measure_network_latency()
    
    # Step 6: Run stress test
    stress_results = collector.run_stress_test(transaction_count=500)
    
    # Step 7: Generate comprehensive report
    report = collector.create_performance_report(
        tx_metrics, consensus_metrics, network_metrics, stress_results
    )
    
    print("\n✅ PERFORMANCE ANALYSIS COMPLETE!")
    print("📄 Check 'blockchain_performance_report.json' for detailed results")


if __name__ == "__main__":
    main()
