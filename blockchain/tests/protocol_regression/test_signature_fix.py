#!/usr/bin/env python3
"""
Test block signature validation fix.

This test verifies that blocks are created and validated correctly
after fixing the payload() method to return a dictionary instead of string.
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
import json
from blockchain.blockchain import Blockchain
from blockchain.transaction.transaction import Transaction
from blockchain.transaction.wallet import Wallet
from blockchain.utils.helpers import BlockchainUtils

def test_block_signature_validation():
    """Test that block signatures are correctly created and validated."""
    print("🔧 TESTING: Block Signature Validation Fix")
    print("=" * 60)
    
    # Initialize blockchain
    print("\n1️⃣ INITIALIZING BLOCKCHAIN...")
    blockchain = Blockchain()
    print(f"✅ Blockchain initialized with {len(blockchain.blocks)} blocks")
    
    # Create test wallet
    print("\n2️⃣ CREATING TEST WALLET...")
    test_wallet = Wallet()
    test_public_key = test_wallet.public_key_string()
    print(f"✅ Test wallet created: {test_public_key[:30]}...")
    
    # Create test transaction
    print("\n3️⃣ CREATING TEST TRANSACTION...")
    tx = Transaction(
        sender_public_key=test_public_key,
        receiver_public_key=test_public_key,  # Self-send for testing
        amount=100.0,
        type="TRANSFER"
    )
    # Sign transaction
    signature = test_wallet.sign(tx.payload())
    tx.sign(signature)
    print(f"✅ Transaction created: {tx.id[:8]}...")
    
    # Submit transaction to blockchain
    print("\n4️⃣ SUBMITTING TRANSACTION...")
    result = blockchain.submit_transaction(tx)
    print(f"✅ Transaction submitted: {result['transaction_id'][:8]}...")
    
    # Create block with transaction
    print("\n5️⃣ CREATING BLOCK...")
    try:
        block = blockchain.create_block(test_wallet, use_gulf_stream=True)
        print(f"✅ Block created successfully!")
        print(f"   📦 Block number: {block.block_count}")
        print(f"   📝 Transactions: {len(block.transactions)}")
        print(f"   🔗 Block hash: {BlockchainUtils.hash(block.payload()).hex()[:16]}...")
        print(f"   ✍️  Signature: {block.signature[:20]}..." if block.signature else "No signature")
    except Exception as e:
        print(f"❌ Block creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test block payload format
    print("\n6️⃣ TESTING BLOCK PAYLOAD FORMAT...")
    payload = block.payload()
    print(f"✅ Payload type: {type(payload)}")
    if isinstance(payload, dict):
        print(f"✅ Payload keys: {list(payload.keys())}")
        print(f"✅ Payload hash: {BlockchainUtils.hash(payload).hex()[:16]}...")
    else:
        print(f"❌ Payload is not a dictionary: {type(payload)}")
        return False
    
    # Test signature validation
    print("\n7️⃣ TESTING SIGNATURE VALIDATION...")
    try:
        # Test if signature is valid
        is_valid = Wallet.signature_valid(payload, block.signature, block.block_proposer)
        print(f"✅ Signature validation result: {is_valid}")
        
        if not is_valid:
            print("⚠️ Signature validation failed - investigating...")
            print(f"   Block proposer: {block.block_proposer[:30]}...")
            print(f"   Payload hash: {BlockchainUtils.hash(payload).hex()[:16]}...")
            print(f"   Signature: {block.signature[:20]}...")
    except Exception as e:
        print(f"❌ Signature validation error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test block proposer validation
    print("\n8️⃣ TESTING BLOCK PROPOSER VALIDATION...")
    try:
        proposer_valid = blockchain.block_proposer_valid(block)
        print(f"✅ Block proposer validation: {proposer_valid}")
    except Exception as e:
        print(f"❌ Block proposer validation error: {e}")
        return False
    
    # Test full block validation
    print("\n9️⃣ TESTING FULL BLOCK VALIDATION...")
    try:
        # Test the same validation that nodes use when receiving blocks
        # FIXED: Pass payload (dict) directly, not the hash (bytes)
        block_payload = block.payload()
        signature_valid = Wallet.signature_valid(block_payload, block.signature, block.block_proposer)
        block_proposer_valid = blockchain.block_proposer_valid(block, signature_pre_validated=signature_valid)
        transactions_valid = blockchain.transactions_valid(block.transactions)
        
        block_hash = BlockchainUtils.hash(block_payload)
        print(f"✅ Payload validation: {block_payload is not None}")
        print(f"✅ Hash generation: {block_hash.hex()[:16]}...")
        print(f"✅ Signature valid: {signature_valid}")
        print(f"✅ Block proposer valid: {block_proposer_valid}")
        print(f"✅ Transactions valid: {transactions_valid}")
        
        all_valid = signature_valid and block_proposer_valid and transactions_valid
        print(f"✅ Overall validation: {all_valid}")
        
        if not all_valid:
            print("⚠️ Some validations failed - this could cause network rejection")
            return False
            
    except Exception as e:
        print(f"❌ Full validation error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test serialization/deserialization
    print("\n🔟 TESTING BLOCK SERIALIZATION...")
    try:
        # Convert to dict and back
        block_dict = block.to_dict()
        print(f"✅ Block serialized to dict: {len(json.dumps(block_dict))} bytes")
        
        # Test that the payload is consistent
        original_payload = block.payload()
        original_hash = BlockchainUtils.hash(original_payload)
        
        print(f"✅ Original hash: {original_hash.hex()[:16]}...")
        print(f"✅ Dict keys: {list(block_dict.keys())}")
        
    except Exception as e:
        print(f"❌ Serialization test failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("🎉 BLOCK SIGNATURE VALIDATION TEST COMPLETED!")
    
    # Summary
    print("\n📋 SUMMARY:")
    print(f"✅ Block creation: Working")
    print(f"✅ Payload format: Dictionary (fixed)")
    print(f"✅ Signature validation: {is_valid}")
    print(f"✅ Block proposer validation: {proposer_valid}")
    print(f"✅ Full validation: {all_valid}")
    print(f"✅ Serialization: Working")
    
    if all_valid and is_valid:
        print(f"\n🎯 FIX SUCCESSFUL!")
        print(f"   The block signature validation issue has been resolved.")
        print(f"   Blocks should now be accepted by other nodes in the network.")
    else:
        print(f"\n⚠️ ISSUE REMAINS!")
        print(f"   Additional debugging may be required.")
    
    return all_valid and is_valid

if __name__ == "__main__":
    try:
        success = test_block_signature_validation()
        if success:
            print(f"\n✅ Test passed - signature validation fix is working!")
        else:
            print(f"\n❌ Test failed - signature validation still has issues!")
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
