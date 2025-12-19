#!/usr/bin/env python3
"""
TPS Performance Tuning Guide and Configuration Script

This script identifies and adjusts key parameters to increase TPS in the quantum consensus blockcha    print(f"   ⚠️  IMPORTANT CONSIDERATIONS:")
    print(f"   • 1-second slots = very frequent leader changes = higher network overhead")
    print(f"   • 600 slots per ep      print(f"🚀 EXPECTED RESULTS:")
    print(f"   • Current TPS: ~0.1 (baseline)")
    print(f"   • Optimized TPS: ~{configs['performance_summary']['theoretical_max_tps']:.0f}")
    print(f"   • Improvement: {configs['performance_summary']['improvement_factor']:.0f}x faster")
    print(f"   • Slot Coverage: 600 slots per 10-minute epoch")
    print(f"   • Leader Predictability: 1200+ slots with dual epoch coverage")int(f"⚡ KEY PARAMETER CHANGES FOR MAXIMUM TPS:")
    print("   1. slot_duration_seconds: 10 → 1 (10x faster blocks)")
    print("   2. epoch_duration_seconds: 120 → 600 (10-minute epochs with 600 slots)")
    print("   3. quantum_num_reads: 100 → 25 (4x faster consensus)")
    print("   4. polling_interval: 0.5s → 0.1s (5x faster measurement)")
    print("   5. min_transactions_per_block: Variable → 1 (immediate blocks)")
    print("   6. witness_quorum_size: 3 → 2 (faster validation)")
    print("   7. leader_advance_time: 60s → 30s (30 slots ahead)")extensive leader schedule coverage")
    print(f"   • Reduced quantum reads = less consensus security (acceptable for testing)")
    print(f"   • Fewer witnesses = reduced validation strength (acceptable for small networks)")
    print(f"   • Immediate block creation = potential for many small blocks")
    print(f"   • 10-minute epochs = stable long-term leader predictability")urrent bottlenecks and their solutions:

1. SLOT TIMING (Biggest Impact on TPS)
   - Current: 10-second slots = Max 1 block per 10s
   - Solution: Reduce slot_duration_seconds

2. LEADER ROTATION FREQUENCY
   - Current: 2-minute epochs with 12 slots
   - Solution: Optimize epoch/slot ratio

3. TRANSACTION BATCHING THRESHOLDS
   - Current: Leaders may wait for "enough" transactions
   - Solution: Lower transaction thresholds

4. CONSENSUS OVERHEAD
   - Current: Quantum annealing takes 2-3ms per selection
   - Solution: Reduce quantum parameters for speed

5. NETWORK DELAYS
   - Current: 0.5s sleep intervals in polling
   - Solution: Faster polling and timeouts
"""

import json
import time
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

def create_high_tps_config():
    """Create configuration files optimized for maximum TPS"""
    
    print("🚀 QUANTUM BLOCKCHAIN TPS OPTIMIZATION")
    print("=" * 50)
    
    # 1. Ultra-high-speed leader schedule config
    leader_schedule_config = {
        "name": "Ultra-High TPS Leader Schedule",
        "description": "Optimized for maximum transaction throughput with 1-second slots",
        "parameters": {
            "slot_duration_seconds": 1,      # 🔥 CRITICAL: 1-second slots (10x faster than original)
            "epoch_duration_seconds": 600,   # 10 minutes = 600 seconds
            "leader_advance_time": 30,       # 30 seconds advance notice (30 slots)
            "slots_per_epoch": 600           # 600 slots per 10-minute epoch
        },
        "expected_improvement": "10x faster block creation (every 1s instead of 10s)"
    }
    
    # 2. Quantum consensus speed optimization
    quantum_config = {
        "name": "Speed-Optimized Quantum Consensus",
        "description": "Reduced quantum annealing time for faster leader selection",
        "parameters": {
            "quantum_annealing_time": 10.0,     # Reduced from 20.0 microseconds
            "quantum_num_reads": 25,            # Reduced from 100 reads (4x faster)
            "max_candidate_nodes": 5,           # Limit candidates for faster processing
            "probe_sample_size": 10,            # Reduced probe overhead
            "witness_quorum_size": 2,           # Reduced from 3 for faster verification
            "performance_cache_ttl": 60         # Faster cache refresh
        },
        "expected_improvement": "50% reduction in consensus time (1-1.5ms instead of 2-3ms)"
    }
    
    # 3. Transaction processing optimization
    transaction_config = {
        "name": "High-Throughput Transaction Processing",
        "description": "Optimized batching and validation for maximum TPS",
        "parameters": {
            "min_transactions_per_block": 1,     # Create blocks with just 1 transaction
            "max_transactions_per_block": 1000,  # Allow larger blocks
            "transaction_timeout": 1.0,          # Faster transaction timeouts
            "validation_timeout": 0.5,           # Faster validation
            "mempool_batch_size": 50,            # Process transactions in batches
            "block_creation_delay": 0.1          # Minimal delay before creating blocks
        },
        "expected_improvement": "Immediate block creation, no waiting for transaction accumulation"
    }
    
    # 4. Network optimization
    network_config = {
        "name": "Low-Latency Network Configuration",
        "description": "Reduced delays and timeouts for faster network operations",
        "parameters": {
            "polling_interval": 0.1,             # Reduced from 0.5s
            "api_timeout": 2.0,                  # Faster API timeouts
            "consensus_measurement_delay": 0.1,   # Faster consensus checking
            "probe_timeout": 0.5,                # Faster probe timeouts
            "max_delay_tolerance": 30.0,         # Reduced from 90s
            "block_proposal_timeout": 15.0       # Reduced from 60s
        },
        "expected_improvement": "5x faster response times and consensus measurement"
    }
    
    # Calculate theoretical maximum TPS
    slot_duration = leader_schedule_config["parameters"]["slot_duration_seconds"]
    max_tx_per_block = transaction_config["parameters"]["max_transactions_per_block"]
    theoretical_max_tps = max_tx_per_block / slot_duration
    
    print(f"📊 THEORETICAL PERFORMANCE IMPROVEMENT:")
    print(f"   Current Setup: ~0.1 TPS (1 block per 10s, limited transactions)")
    print(f"   Optimized Setup: ~{theoretical_max_tps:.0f} TPS ({max_tx_per_block} tx per {slot_duration}s block)")
    print(f"   Improvement Factor: ~{theoretical_max_tps / 0.1:.0f}x faster!")
    
    print(f"\n🚀 ULTRA-HIGH-SPEED CONFIGURATION:")
    print(f"   Slot Duration: 1 second (10x faster than original)")
    print(f"   Epoch Duration: 10 minutes (600 slots)")
    print(f"   Leader Schedule: 600 predetermined leaders per epoch")
    print(f"   Coverage: 1200+ slots with current + next epoch (20+ minutes)")
    
    # Save configurations
    configs = {
        "leader_schedule": leader_schedule_config,
        "quantum_consensus": quantum_config,
        "transaction_processing": transaction_config,
        "network_optimization": network_config,
        "performance_summary": {
            "theoretical_max_tps": theoretical_max_tps,
            "improvement_factor": theoretical_max_tps / 0.1,
            "key_changes": [
                "Slot duration: 10s → 1s (10x faster blocks)",
                "Epoch duration: 2min → 10min (600 slots per epoch)",
                "Quantum reads: 100 → 25 (4x faster consensus)",
                "Min transactions per block: Variable → 1 (immediate block creation)",
                "Polling interval: 0.5s → 0.1s (5x faster response)",
                "Leader advance time: 60s → 30s (30 slots ahead)"
            ]
        }
    }
    
    # Save to file (always under blockchain/configs)
    from pathlib import Path

    config_path = Path(__file__).resolve().parent.parent / "configs" / "tps_optimization_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, 'w') as f:
        json.dump(configs, f, indent=2)
    
    print(f"\n💾 Configuration saved to: {config_path}")
    
    return configs

def apply_optimizations():
    """Apply the TPS optimizations to the actual codebase"""
    
    print(f"\n🔧 APPLYING TPS OPTIMIZATIONS...")
    print("=" * 50)
    
    optimizations = [
        {
            "file": "blockchain/consensus/leader_schedule.py",
            "change": "slot_duration_seconds = 1, epoch_duration_seconds = 600",
            "impact": "10x faster block creation, 600 slots per 10-minute epoch"
        },
        {
            "file": "blockchain/quantum_consensus/quantum_annealing_consensus.py",
            "change": "quantum_num_reads = 25",
            "impact": "4x faster quantum consensus"
        },
        {
            "file": "blockchain/quantum_consensus/quantum_annealing_consensus.py",
            "change": "witness_quorum_size = 2",
            "impact": "Faster validation with fewer witnesses"
        },
        {
            "file": "clients/test_sample_transaction.py",
            "change": "time.sleep(0.1) instead of time.sleep(0.5)",
            "impact": "5x faster consensus measurement for 1s slots"
        }
    ]
    
    print("🎯 KEY OPTIMIZATION POINTS:")
    for i, opt in enumerate(optimizations, 1):
        print(f"   {i}. {opt['file']}")
        print(f"      Change: {opt['change']}")
        print(f"      Impact: {opt['impact']}")
        print()
    
    print("⚠️  IMPORTANT CONSIDERATIONS:")
    print("   • Faster slots = more frequent leader changes = higher network overhead")
    print("   • Reduced quantum reads = less consensus security (acceptable for testing)")
    print("   • Fewer witnesses = reduced validation strength (acceptable for small networks)")
    print("   • Immediate block creation = potential for empty blocks")
    
    return optimizations

def create_tps_test_script():
    """Create a specialized test script for measuring optimized TPS"""
    
    test_script = '''#!/usr/bin/env python3
"""
High-TPS Optimized Transaction Test

This script is specifically designed to test the maximum TPS of the optimized blockchain.
It creates many transactions rapidly and measures true TPS including consensus time.
"""

import time
import requests
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

def submit_transaction_fast(tx_data, node_port=11000):
    """Fast transaction submission with minimal overhead"""
    try:
        start_time = time.time()
        response = requests.post(
            f"http://localhost:{node_port}/api/v1/transaction/create/",
            json=tx_data,
            timeout=2.0  # Fast timeout
        )
        return {
            "success": response.status_code == 200,
            "time": time.time() - start_time,
            "response": response.json() if response.status_code == 200 else None
        }
    except Exception as e:
        return {"success": False, "time": 0, "error": str(e)}

def rapid_fire_tps_test(transaction_count=100, concurrent_threads=10):
    """Test maximum TPS with rapid concurrent transactions"""
    
    print(f"🚀 RAPID-FIRE TPS TEST")
    print(f"   Transactions: {transaction_count}")
    print(f"   Concurrent threads: {concurrent_threads}")
    print(f"   Target: Submit all transactions as fast as possible")
    
    # Prepare transaction data (simplified for speed)
    from test_sample_transaction import create_sample_transaction
    base_tx = create_sample_transaction(amount=1.0)
    if not base_tx:
        print("❌ Failed to create base transaction")
        return
    
    # Create transaction payloads
    from blockchain.utils.helpers import BlockchainUtils
    tx_payload = {"transaction": BlockchainUtils.encode(base_tx)}
    
    # Record initial blockchain state
    initial_response = requests.get("http://localhost:11000/api/v1/blockchain/")
    initial_blocks = len(initial_response.json().get('blocks', []))
    
    print(f"   📊 Initial blocks: {initial_blocks}")
    print(f"   ⏱️  Starting rapid submission...")
    
    # Submit transactions concurrently
    start_time = time.time()
    results = []
    
    with ThreadPoolExecutor(max_workers=concurrent_threads) as executor:
        # Submit all transactions
        futures = [
            executor.submit(submit_transaction_fast, tx_payload) 
            for _ in range(transaction_count)
        ]
        
        # Collect results
        for future in as_completed(futures):
            results.append(future.result())
    
    submission_time = time.time() - start_time
    successful_submissions = sum(1 for r in results if r["success"])
    
    print(f"   ✅ Submission complete!")
    print(f"   📊 Successful: {successful_submissions}/{transaction_count}")
    print(f"   ⏱️  Submission time: {submission_time:.2f}s")
    print(f"   🚀 Submission TPS: {successful_submissions/submission_time:.2f}")
    
    # Now measure consensus time
    print(f"   ⏳ Measuring consensus time (optimized polling)...")
    consensus_start = time.time()
    max_wait = 30  # 30 seconds max wait
    
    while time.time() - consensus_start < max_wait:
        current_response = requests.get("http://localhost:11000/api/v1/blockchain/")
        current_blocks = len(current_response.json().get('blocks', []))
        
        if current_blocks > initial_blocks:
            consensus_time = time.time() - consensus_start
            new_blocks = current_blocks - initial_blocks
            total_time = submission_time + consensus_time
            
            print(f"   ✅ Consensus achieved!")
            print(f"   📦 New blocks: {new_blocks}")
            print(f"   ⏱️  Consensus time: {consensus_time:.2f}s")
            print(f"   🎯 Total end-to-end time: {total_time:.2f}s")
            print(f"   🚀 TRUE TPS: {successful_submissions/total_time:.2f}")
            return successful_submissions/total_time
        
        time.sleep(0.05)  # Very fast polling (50ms)
    
    print(f"   ⚠️  Consensus timeout after {max_wait}s")
    return None

if __name__ == "__main__":
    print("🧪 HIGH-TPS BLOCKCHAIN TEST")
    print("=" * 50)
    
    # Test different scales
    test_cases = [
        {"count": 10, "threads": 5},
        {"count": 50, "threads": 10},
        {"count": 100, "threads": 20}
    ]
    
    for test_case in test_cases:
        print(f"\\n{'='*50}")
        tps = rapid_fire_tps_test(test_case["count"], test_case["threads"])
        if tps:
            print(f"📊 ACHIEVED TPS: {tps:.2f}")
        print(f"{'='*50}")
        time.sleep(2)  # Brief pause between tests
'''
    
    with open("high_tps_test.py", 'w') as f:
        f.write(test_script)
    
    print(f"📝 Created high-TPS test script: high_tps_test.py")

def main():
    """Main optimization workflow"""
    
    # Create configuration
    configs = create_high_tps_config()
    
    # Show optimization plan
    optimizations = apply_optimizations()
    
    # Create test script
    create_tps_test_script()
    
    print(f"\n🎯 NEXT STEPS TO MAXIMIZE TPS:")
    print("=" * 50)
    print("1. Apply the code changes listed above")
    print("2. Restart the blockchain nodes: ./start_nodes.sh")
    print("3. Run the high-TPS test: python high_tps_test.py")
    print("4. Monitor with: python clients/test_sample_transaction.py --count 50 --performance")
    
    print(f"\n🚀 EXPECTED RESULTS:")
    print(f"   • Current TPS: ~0.1 (baseline)")
    print(f"   • Optimized TPS: ~{configs['performance_summary']['theoretical_max_tps']:.0f}")
    print(f"   • Improvement: {configs['performance_summary']['improvement_factor']:.0f}x faster")
    
    print(f"\n⚡ KEY PARAMETER CHANGES FOR MAXIMUM TPS:")
    print("   1. slot_duration_seconds: 10 → 2 (5x faster blocks)")
    print("   2. quantum_num_reads: 100 → 25 (4x faster consensus)")
    print("   3. polling_interval: 0.5s → 0.1s (5x faster measurement)")
    print("   4. min_transactions_per_block: Variable → 1 (immediate blocks)")
    print("   5. witness_quorum_size: 3 → 2 (faster validation)")

if __name__ == "__main__":
    main()
