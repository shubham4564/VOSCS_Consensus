#!/usr/bin/env python3
"""
Gulf Stream 4-Leader Forwarding Test
Tests that Gulf Stream only forwards transactions to current leader + next 3 leaders.
"""

import sys
import time
import json
sys.path.append('/Users/shubham/Documents/fromgithub/proofwithquantumannealing/blockchain/blockchain')

from blockchain import Blockchain
from transaction.transaction import Transaction
from transaction.account_manager import AccountManager

def test_gulf_stream_4_leader_limit():
    """Test that Gulf Stream forwards to maximum 4 leaders only"""
    print("🧪 TESTING: Gulf Stream 4-Leader Forwarding Limit")
    print("="*70)

    # Initialize blockchain with Gulf Stream
    print("\n1️⃣ INITIALIZING BLOCKCHAIN WITH GULF STREAM...")
    blockchain = Blockchain(config_file="blockchain_config.json")
    print("✅ Blockchain initialized")
    
    # Check Gulf Stream configuration
    print("\n2️⃣ CHECKING GULF STREAM CONFIGURATION...")
    gulf_stream = blockchain.consensus_protocol.gulf_stream
    print(f"✅ Gulf Stream max_forwarding_slots: {gulf_stream.max_forwarding_slots}")
    
    # Get leader schedule targets
    leader_schedule = blockchain.consensus_protocol.leader_schedule
    gulf_stream_targets = leader_schedule.get_gulf_stream_targets()
    print(f"✅ Gulf Stream targets returned: {len(gulf_stream_targets)} leaders")
    
    # Show the targets
    print("\n📋 Gulf Stream Target Details:")
    for i, target in enumerate(gulf_stream_targets):
        leader_short = target['leader'][:20] + "..." if len(target['leader']) > 20 else target['leader']
        print(f"   {i+1}. Slot {target['slot']}: {leader_short} (in {target['time_until_slot']:.1f}s)")
    
    # Create test transaction
    print("\n3️⃣ CREATING TEST TRANSACTION...")
    account_manager = AccountManager()
    test_account = account_manager.create_account()
    
    transaction = Transaction(
        sender_public_key=test_account['public_key'],
        receiver_public_key="test_receiver_key",
        amount=100.0,
        timestamp=time.time()
    )
    print("✅ Test transaction created")
    
    # Test Gulf Stream forwarding
    print("\n4️⃣ TESTING GULF STREAM FORWARDING...")
    
    # Get current leader and upcoming leaders
    current_leader = leader_schedule.get_current_leader()
    upcoming_leaders = leader_schedule.get_upcoming_leaders(10)  # Request 10 to test the limit
    
    print(f"✅ Current leader: {current_leader[:20] + '...' if current_leader else 'None'}")
    print(f"✅ Upcoming leaders available: {len(upcoming_leaders)}")
    
    # Test the forwarding logic
    tx_hash = gulf_stream._calculate_transaction_hash(transaction)
    forwarding_result = gulf_stream._forward_to_leaders(
        transaction, tx_hash, current_leader, upcoming_leaders
    )
    
    print(f"\n📊 FORWARDING RESULTS:")
    print(f"   Total leaders contacted: {forwarding_result['total_leaders']}")
    print(f"   Leaders contacted details:")
    
    for i, leader_info in enumerate(forwarding_result['leaders_contacted']):
        print(f"      {i+1}. {leader_info['leader']} (Slot: {leader_info['slot']})")
    
    # Verify the 4-leader limit
    print(f"\n🔍 VERIFICATION:")
    leaders_contacted = forwarding_result['total_leaders']
    
    if leaders_contacted <= 4:
        print(f"✅ PASS: Forwarded to {leaders_contacted} leaders (≤ 4 limit)")
        print(f"✅ Gulf Stream correctly limited forwarding to current + next 3 leaders")
    else:
        print(f"❌ FAIL: Forwarded to {leaders_contacted} leaders (> 4 limit)")
        return False
    
    # Test should_forward_transaction method
    print(f"\n5️⃣ TESTING should_forward_transaction METHOD...")
    gulf_stream_node = blockchain.gulf_stream_node
    forward_targets = gulf_stream_node.should_forward_transaction(transaction)
    
    print(f"✅ should_forward_transaction returned {len(forward_targets)} leaders")
    
    if len(forward_targets) <= 4:
        print(f"✅ PASS: Forward targets {len(forward_targets)} ≤ 4 limit")
    else:
        print(f"❌ FAIL: Forward targets {len(forward_targets)} > 4 limit")
        return False
    
    print(f"\n🎉 ALL TESTS PASSED!")
    print(f"✅ Gulf Stream is correctly limited to 4 leaders maximum")
    print(f"✅ Current implementation forwards to: current leader + next 3 upcoming leaders")
    
    return True

if __name__ == "__main__":
    try:
        success = test_gulf_stream_4_leader_limit()
        if success:
            print(f"\n🏆 Gulf Stream 4-Leader Limit Test: SUCCESS")
            sys.exit(0)
        else:
            print(f"\n💥 Gulf Stream 4-Leader Limit Test: FAILED")
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
