#!/usr/bin/env python3
"""
Test Block Synchronization API
"""

import json
import requests
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_sync_api():
    """Test the synchronization API endpoint"""
    
    print("Testing block synchronization API...")
    
    # Get reference blockchain from node 11000
    print("1. Getting reference blockchain from node 11000...")
    resp = requests.get('http://localhost:11000/api/v1/blockchain/')
    reference_data = resp.json()
    reference_blocks = reference_data['blocks']
    print(f"   Reference has {len(reference_blocks)} blocks")
    
    # Test sync on node 11001 (has 5 blocks, needs 9 more)
    target_port = 11001
    print(f"\n2. Testing sync API on node {target_port}...")
    
    # Get current state
    resp = requests.get(f'http://localhost:{target_port}/api/v1/blockchain/')
    current_blocks = resp.json()['blocks']
    print(f"   Node {target_port} currently has {len(current_blocks)} blocks")
    
    # Prepare sync data - send missing blocks only
    missing_blocks = reference_blocks[len(current_blocks):]  # Only missing blocks
    sync_payload = {
        "type": "blocks",
        "blocks": missing_blocks
    }
    
    print(f"3. Sending sync request to node {target_port}...")
    
    try:
        resp = requests.post(
            f'http://localhost:{target_port}/api/v1/blockchain/sync',
            json=sync_payload,
            timeout=30
        )
        
        print(f"   Sync response status: {resp.status_code}")
        
        if resp.status_code == 200:
            result = resp.json()
            print(f"   ✅ Sync successful: {result}")
            
            # Verify the result
            print("4. Verifying sync result...")
            resp = requests.get(f'http://localhost:{target_port}/api/v1/blockchain/')
            updated_blocks = resp.json()['blocks']
            print(f"   Node {target_port} now has {len(updated_blocks)} blocks")
            
            if len(updated_blocks) == len(reference_blocks):
                print("   ✅ Synchronization successful!")
                return True
            else:
                print(f"   ❌ Partial sync: expected {len(reference_blocks)}, got {len(updated_blocks)}")
                return False
                
        else:
            print(f"   ❌ Sync failed: {resp.status_code}")
            try:
                error_data = resp.json()
                print(f"   Error details: {error_data}")
            except:
                print(f"   Raw response: {resp.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Exception during sync: {e}")
        return False

if __name__ == "__main__":
    success = test_sync_api()
    sys.exit(0 if success else 1)
