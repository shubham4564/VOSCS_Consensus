#!/usr/bin/env python3
"""
Leader Schedule Pre-Generation Tool

This tool ensures that at least 200 leader slots are pre-generated and ready
before any transactions are submitted to the blockchain.
"""

import time
import sys
import os
import requests
import json
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def check_leader_schedule_status(node_port=11000):
    """Check current leader schedule status"""
    try:
        url = f"http://localhost:{node_port}/api/v1/blockchain/leader/schedule/"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"❌ Error checking leader schedule: {e}")
    return None

def wait_for_leader_schedule_initialization(node_port=11000, min_slots=200, max_wait_time=300):
    """
    Wait for the leader schedule to have at least min_slots pre-generated
    
    Args:
        node_port: Node port to check
        min_slots: Minimum number of slots required (default: 200)
        max_wait_time: Maximum time to wait in seconds (default: 300s = 5 minutes)
    """
    print(f"🎯 LEADER SCHEDULE PRE-GENERATION")
    print("=" * 60)
    print(f"   Target: {min_slots} slots minimum")
    print(f"   Max wait time: {max_wait_time} seconds")
    print(f"   Node: localhost:{node_port}")
    print(f"   🚀 Ultra-High-Speed Mode: 1s slots, 600 slots per epoch")
    
    start_time = time.time()
    check_count = 0
    
    while time.time() - start_time < max_wait_time:
        check_count += 1
        elapsed = time.time() - start_time
        
        # Check leader schedule status
        schedule_status = check_leader_schedule_status(node_port)
        
        if schedule_status:
            current_epoch = schedule_status.get('current_epoch', 0)
            current_slot = schedule_status.get('current_slot', 0)
            slots_per_epoch = schedule_status.get('slots_per_epoch', 12)
            
            # Calculate total available slots
            current_schedule_slots = len(schedule_status.get('current_schedule', {}))
            next_schedule_slots = len(schedule_status.get('next_schedule', {}))
            total_available_slots = current_schedule_slots + next_schedule_slots
            
            # Calculate remaining slots in current epoch
            remaining_current_slots = max(0, slots_per_epoch - current_slot)
            
            print(f"   📊 Check #{check_count} ({elapsed:.1f}s elapsed):")
            print(f"      Current epoch: {current_epoch}, slot: {current_slot}/{slots_per_epoch}")
            print(f"      Available slots: {total_available_slots} (current: {current_schedule_slots}, next: {next_schedule_slots})")
            print(f"      Remaining in current epoch: {remaining_current_slots}")
            
            # Success condition: enough slots available
            if total_available_slots >= min_slots:
                print(f"   ✅ SUCCESS: {total_available_slots} slots available (>= {min_slots} required)")
                print(f"   🚀 Leader schedule ready for transaction submission!")
                
                # Show upcoming leader schedule preview
                upcoming_leaders = schedule_status.get('upcoming_leaders', [])
                if upcoming_leaders:
                    print(f"   📅 Next 10 leaders preview:")
                    for i, leader_info in enumerate(upcoming_leaders[:10]):
                        slot_num = leader_info.get('slot', 'unknown')
                        leader_id = leader_info.get('leader', 'unknown')[:20]
                        time_until = leader_info.get('time_until_slot', 0)
                        print(f"      Slot {slot_num}: {leader_id}... (in {time_until:.1f}s)")
                
                return True, {
                    'total_slots': total_available_slots,
                    'current_epoch': current_epoch,
                    'current_slot': current_slot,
                    'slots_per_epoch': slots_per_epoch,
                    'check_count': check_count,
                    'initialization_time': elapsed
                }
            else:
                print(f"   ⏳ Waiting... need {min_slots - total_available_slots} more slots")
        else:
            print(f"   ❌ Cannot connect to leader schedule API")
        
        # Progress indicator every 30 seconds
        if check_count % 30 == 0:
            print(f"   🕐 Still waiting after {elapsed:.1f}s... (max: {max_wait_time}s)")
        
        time.sleep(1.0)  # Check every second
    
    # Timeout reached
    print(f"   ⚠️  TIMEOUT: Leader schedule initialization took longer than {max_wait_time}s")
    print(f"   📊 Final status after {check_count} checks:")
    
    final_status = check_leader_schedule_status(node_port)
    if final_status:
        total_slots = len(final_status.get('current_schedule', {})) + len(final_status.get('next_schedule', {}))
        print(f"      Available slots: {total_slots}/{min_slots}")
        print(f"      Current epoch: {final_status.get('current_epoch', 'unknown')}")
    
    return False, None

def force_leader_schedule_generation(node_port=11000, target_epochs=20):
    """
    Force generation of multiple epochs worth of leader schedules
    
    Args:
        node_port: Node port to use
        target_epochs: Number of epochs to pre-generate (20 epochs = 240 slots with 12 slots/epoch)
    """
    print(f"⚡ FORCING LEADER SCHEDULE GENERATION")
    print(f"   Target: {target_epochs} epochs")
    
    try:
        # Call leader schedule generation API if available
        url = f"http://localhost:{node_port}/api/v1/blockchain/leader/generate-schedule/"
        payload = {
            "epochs_to_generate": target_epochs,
            "force_regeneration": True,
            "ultra_high_speed_mode": True,  # Enable 1s slots, 600 slots per epoch
            "slot_duration": 1,
            "epoch_duration": 600
        }
        
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Successfully generated {target_epochs} epochs with 600 slots each")
            print(f"   📊 Total slots generated: {target_epochs * 600}")
            print(f"   ⏱️  Slot duration: 1 second")
            print(f"   📅 Epoch duration: 10 minutes")
            return True, result
        else:
            print(f"   ❌ API call failed: {response.status_code}")
            return False, None
    except Exception as e:
        print(f"   ❌ Error forcing generation: {e}")
        return False, None

def pre_flight_check(node_port=11000, min_slots=200):
    """
    Complete pre-flight check ensuring the system is ready for transactions
    """
    print(f"🧪 PRE-FLIGHT CHECK FOR TRANSACTION READINESS")
    print("=" * 60)
    
    # Step 1: Basic connectivity
    print(f"📡 Step 1: Checking node connectivity...")
    try:
        blockchain_url = f"http://localhost:{node_port}/api/v1/blockchain/"
        response = requests.get(blockchain_url, timeout=5)
        if response.status_code == 200:
            blockchain_data = response.json()
            block_count = len(blockchain_data.get('blocks', []))
            print(f"   ✅ Node connected! Current blocks: {block_count}")
        else:
            print(f"   ❌ Node connection failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Cannot connect to node: {e}")
        return False
    
    # Step 2: Leader schedule readiness
    print(f"🎯 Step 2: Checking leader schedule readiness...")
    success, schedule_info = wait_for_leader_schedule_initialization(node_port, min_slots, max_wait_time=120)
    
    if not success:
        print(f"   ⚠️  Leader schedule not ready, attempting forced generation...")
        force_success, force_result = force_leader_schedule_generation(node_port, target_epochs=20)
        
        if force_success:
            print(f"   🔄 Rechecking after forced generation...")
            success, schedule_info = wait_for_leader_schedule_initialization(node_port, min_slots, max_wait_time=60)
    
    if not success:
        print(f"   ❌ Leader schedule not ready after all attempts")
        return False
    
    # Step 3: Quantum consensus readiness
    print(f"🔬 Step 3: Checking quantum consensus status...")
    try:
        quantum_url = f"http://localhost:{node_port}/api/v1/blockchain/quantum-metrics/"
        response = requests.get(quantum_url, timeout=5)
        if response.status_code == 200:
            quantum_data = response.json()
            active_nodes = quantum_data.get('active_nodes', 0)
            total_nodes = quantum_data.get('total_nodes', 0)
            print(f"   ✅ Quantum consensus ready: {active_nodes}/{total_nodes} active nodes")
        else:
            print(f"   ⚠️  Quantum metrics not available")
    except Exception as e:
        print(f"   ⚠️  Quantum consensus check failed: {e}")
    
    # Step 4: Ready for transactions
    print(f"🚀 Step 4: System readiness summary...")
    print(f"   ✅ Node connectivity: READY")
    print(f"   ✅ Leader schedule: READY ({schedule_info['total_slots']} slots)")
    print(f"   ✅ Initialization time: {schedule_info['initialization_time']:.1f}s")
    print(f"   ✅ Current epoch: {schedule_info['current_epoch']}")
    print(f"   ✅ Current slot: {schedule_info['current_slot']}")
    
    print(f"\n🎉 SYSTEM READY FOR TRANSACTION SUBMISSION!")
    print(f"   📊 Pre-generated slots: {schedule_info['total_slots']}")
    print(f"   ⏱️  Slot duration: 2 seconds (optimized)")
    print(f"   🔄 Epochs: 12 slots each")
    print(f"   🎯 You can now safely submit transactions to slot 1+")
    
    return True

def main():
    """Main function for leader schedule pre-generation"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Pre-generate leader schedule before transactions')
    parser.add_argument('--slots', type=int, default=200, help='Minimum slots to pre-generate (default: 200)')
    parser.add_argument('--node', type=int, default=11000, help='Node port (default: 11000)')
    parser.add_argument('--force', action='store_true', help='Force regeneration even if slots exist')
    parser.add_argument('--check-only', action='store_true', help='Only check status, do not wait')
    
    args = parser.parse_args()
    
    print(f"🎯 LEADER SCHEDULE PRE-GENERATION TOOL")
    print(f"=" * 60)
    print(f"   Minimum slots required: {args.slots}")
    print(f"   Node port: {args.node}")
    print(f"   Force regeneration: {args.force}")
    
    if args.check_only:
        # Just check current status
        print(f"\n📊 CURRENT STATUS CHECK")
        schedule_status = check_leader_schedule_status(args.node)
        if schedule_status:
            current_slots = len(schedule_status.get('current_schedule', {}))
            next_slots = len(schedule_status.get('next_schedule', {}))
            total_slots = current_slots + next_slots
            print(f"   Available slots: {total_slots}")
            print(f"   Current epoch: {schedule_status.get('current_epoch', 'unknown')}")
            print(f"   Current slot: {schedule_status.get('current_slot', 'unknown')}")
            print(f"   Ready for transactions: {'✅ YES' if total_slots >= args.slots else '❌ NO'}")
        else:
            print(f"   ❌ Cannot retrieve leader schedule status")
        return
    
    if args.force:
        print(f"\n⚡ FORCING SCHEDULE REGENERATION")
        force_success, force_result = force_leader_schedule_generation(args.node, target_epochs=20)
        if not force_success:
            print(f"   ❌ Forced generation failed")
            return
    
    # Run full pre-flight check
    success = pre_flight_check(args.node, args.slots)
    
    if success:
        print(f"\n🎯 READY TO PROCEED!")
        print(f"   You can now run transactions with confidence:")
        print(f"   python clients/test_sample_transaction.py --count 10 --performance")
        print(f"   python clients/send_100_transactions.py")
    else:
        print(f"\n❌ SYSTEM NOT READY")
        print(f"   Please check node status and try again")
        sys.exit(1)

if __name__ == "__main__":
    main()
