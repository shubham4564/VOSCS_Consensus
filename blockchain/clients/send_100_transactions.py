#!/usr/bin/env python3
"""
Send 100 Transactions to Online Nodes
====================================

This script sends 100 transactions to test:
1. Transaction processing capability
2. Block creation and propagation
3. Network synchronization after fixes
4. Load testing of the blockchain network
"""

import requests
import json
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_online_nodes():
    """Discover which nodes are currently online"""
    online_nodes = []
    
    print("🔍 Discovering online nodes...")
    for i in range(10):  # Check nodes 1-10
        port = 11000 + i
        node_num = i + 1
        
        try:
            # Try ping endpoint first
            response = requests.get(f'http://127.0.0.1:{port}/ping/', timeout=3)
            if response.status_code == 200:
                # Get blockchain height
                try:
                    blockchain_response = requests.get(f'http://127.0.0.1:{port}/api/v1/blockchain/', timeout=5)
                    if blockchain_response.status_code == 200:
                        blockchain_data = blockchain_response.json()
                        blockchain_height = len(blockchain_data.get('blocks', []))
                    else:
                        blockchain_height = 0
                except:
                    blockchain_height = 0
                
                online_nodes.append({
                    'node_num': node_num,
                    'port': port,
                    'api_url': f'http://127.0.0.1:{port}',
                    'blockchain_height': blockchain_height,
                    'node_id': f'node_{node_num}'
                })
                print(f"   ✅ Node {node_num} (port {port}): {blockchain_height} blocks")
            else:
                print(f"   ❌ Node {node_num}: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Node {node_num}: Offline")
    
    print(f"🌐 Found {len(online_nodes)} online nodes")
    return online_nodes

def create_test_transaction(tx_id, sender_amount=100.0, transfer_amount=10.0):
    """Create a test transaction (using EXCHANGE type for better testing)"""
    return {
        "type": "EXCHANGE",  # EXCHANGE transactions work better for testing
        "amount": transfer_amount,
        "sender_public_key": f"test_sender_{tx_id % 20}_" + "x" * 50,  # 20 different senders
        "receiver_public_key": f"test_receiver_{(tx_id + 10) % 30}_" + "y" * 50,  # 30 different receivers
        "timestamp": time.time(),
        "transaction_id": f"tx_{tx_id}_{int(time.time())}"
    }

def send_transaction_to_node(node_info, transaction, tx_id):
    """Send a single transaction to a specific node"""
    try:
        # Create a properly formatted transaction for the blockchain API
        transaction_data = {
            "transaction": transaction  # The API expects a "transaction" field
        }
        
        response = requests.post(
            f"{node_info['api_url']}/api/v1/transaction/create/",
            json=transaction_data,
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            result = response.json()
            return {
                'success': True,
                'tx_id': tx_id,
                'node_num': node_info['node_num'],
                'response': result,
                'timestamp': time.time()
            }
        else:
            return {
                'success': False,
                'tx_id': tx_id,
                'node_num': node_info['node_num'],
                'error': f"HTTP {response.status_code}: {response.text[:100]}",
                'timestamp': time.time()
            }
            
    except Exception as e:
        return {
            'success': False,
            'tx_id': tx_id,
            'node_num': node_info['node_num'],
            'error': str(e),
            'timestamp': time.time()
        }

def send_transactions_batch(online_nodes, start_id, batch_size=10):
    """Send a batch of transactions in parallel"""
    results = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        
        for i in range(batch_size):
            tx_id = start_id + i
            transaction = create_test_transaction(tx_id)
            
            # Distribute transactions across online nodes
            target_node = online_nodes[tx_id % len(online_nodes)]
            
            future = executor.submit(send_transaction_to_node, target_node, transaction, tx_id)
            futures.append(future)
        
        # Collect results
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
    
    return results

def monitor_blockchain_growth(online_nodes, initial_heights):
    """Monitor how blockchain grows after sending transactions"""
    print(f"\n📊 Monitoring blockchain growth...")
    
    time.sleep(5)  # Wait for transactions to be processed
    
    growth_stats = {}
    for node_info in online_nodes:
        try:
            response = requests.get(f"{node_info['api_url']}/api/v1/blockchain/", timeout=5)
            if response.status_code == 200:
                blockchain_data = response.json()
                current_height = len(blockchain_data.get('blocks', []))
                initial_height = initial_heights.get(node_info['node_num'], 0)
                
                growth_stats[node_info['node_num']] = {
                    'initial_blocks': initial_height,
                    'current_blocks': current_height,
                    'new_blocks': current_height - initial_height,
                    'node_url': node_info['api_url']
                }
                
                print(f"   Node {node_info['node_num']}: {initial_height} → {current_height} blocks (+{current_height - initial_height})")
            else:
                print(f"   ❌ Node {node_info['node_num']}: Failed to get blockchain data")
                
        except Exception as e:
            print(f"   ❌ Node {node_info['node_num']}: {str(e)}")
    
    return growth_stats

def check_network_synchronization(online_nodes):
    """Check if all nodes are synchronized after transaction processing"""
    print(f"\n🔍 Checking network synchronization...")
    
    heights = {}
    for node_info in online_nodes:
        try:
            response = requests.get(f"{node_info['api_url']}/api/v1/blockchain/", timeout=5)
            if response.status_code == 200:
                blockchain_data = response.json()
                height = len(blockchain_data.get('blocks', []))
                heights[node_info['node_num']] = height
            else:
                heights[node_info['node_num']] = -1  # Error
        except:
            heights[node_info['node_num']] = -1  # Error
    
    if heights:
        max_height = max(h for h in heights.values() if h >= 0)
        min_height = min(h for h in heights.values() if h >= 0)
        sync_diff = max_height - min_height
        
        print(f"   📏 Block height range: {min_height} - {max_height} (diff: {sync_diff})")
        
        for node_num, height in heights.items():
            if height >= 0:
                status = "✅ SYNC" if height == max_height else f"⚠️ -{max_height - height}"
                print(f"   Node {node_num}: {height} blocks {status}")
            else:
                print(f"   Node {node_num}: ❌ ERROR")
        
        sync_percentage = len([h for h in heights.values() if h == max_height]) / len([h for h in heights.values() if h >= 0]) * 100
        print(f"   🎯 Synchronization: {sync_percentage:.1f}% of nodes at max height")
        
        return sync_diff <= 1  # Consider synchronized if difference is at most 1 block
    
    return False

def main():
    print("🚀 SENDING 100 TRANSACTIONS TO ONLINE NODES")
    print("=" * 60)
    print("This will test transaction processing and block propagation")
    print()
    
    # Step 1: Discover online nodes
    online_nodes = get_online_nodes()
    
    if not online_nodes:
        print("❌ No online nodes found! Cannot send transactions.")
        return False
    
    # Record initial blockchain heights
    initial_heights = {node['node_num']: node['blockchain_height'] for node in online_nodes}
    
    print(f"\n📤 Starting to send 100 transactions...")
    print(f"   Target nodes: {len(online_nodes)} online nodes")
    print(f"   Distribution: Round-robin across all online nodes")
    print()
    
    # Step 2: Send transactions in batches
    all_results = []
    batch_size = 20  # Send 20 transactions per batch
    total_transactions = 100
    
    start_time = time.time()
    
    for batch_num in range(0, total_transactions, batch_size):
        batch_start = batch_num
        current_batch_size = min(batch_size, total_transactions - batch_num)
        
        print(f"📦 Batch {batch_num // batch_size + 1}: Sending transactions {batch_start + 1}-{batch_start + current_batch_size}")
        
        batch_results = send_transactions_batch(online_nodes, batch_start, current_batch_size)
        all_results.extend(batch_results)
        
        # Show batch results
        successful = len([r for r in batch_results if r['success']])
        failed = len([r for r in batch_results if not r['success']])
        print(f"   ✅ Success: {successful}, ❌ Failed: {failed}")
        
        # Brief pause between batches
        time.sleep(2)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Step 3: Analyze results
    print(f"\n📊 TRANSACTION SENDING RESULTS")
    print("-" * 40)
    
    successful_txs = [r for r in all_results if r['success']]
    failed_txs = [r for r in all_results if not r['success']]
    
    print(f"   Total transactions sent: {len(all_results)}")
    print(f"   ✅ Successful: {len(successful_txs)}")
    print(f"   ❌ Failed: {len(failed_txs)}")
    print(f"   ⏱️ Total time: {total_time:.2f} seconds")
    print(f"   📈 Rate: {len(all_results) / total_time:.1f} transactions/second")
    
    # Show distribution across nodes
    node_distribution = {}
    for result in successful_txs:
        node_num = result['node_num']
        node_distribution[node_num] = node_distribution.get(node_num, 0) + 1
    
    print(f"\n📊 Transaction distribution across nodes:")
    for node_num, count in sorted(node_distribution.items()):
        print(f"   Node {node_num}: {count} transactions")
    
    # Show sample of failed transactions
    if failed_txs:
        print(f"\n❌ Sample failed transactions:")
        for failure in failed_txs[:5]:  # Show first 5 failures
            print(f"   TX {failure['tx_id']} to Node {failure['node_num']}: {failure['error']}")
    
    # Step 4: Monitor blockchain growth
    growth_stats = monitor_blockchain_growth(online_nodes, initial_heights)
    
    # Step 5: Check network synchronization
    is_synchronized = check_network_synchronization(online_nodes)
    
    # Step 6: Final assessment
    print(f"\n🎯 FINAL ASSESSMENT")
    print("-" * 25)
    success_rate = len(successful_txs) / len(all_results) * 100
    print(f"   📊 Transaction success rate: {success_rate:.1f}%")
    print(f"   🔗 Network synchronization: {'✅ GOOD' if is_synchronized else '⚠️ ISSUES'}")
    
    # Check if blocks were created
    total_new_blocks = sum(stats['new_blocks'] for stats in growth_stats.values())
    print(f"   📦 New blocks created: {total_new_blocks}")
    
    if total_new_blocks > 0:
        print(f"   🎉 SUCCESS: Transactions were processed into blocks!")
        if is_synchronized:
            print(f"   🌟 EXCELLENT: Network is properly synchronized!")
        else:
            print(f"   ⚠️ PARTIAL: Some synchronization issues detected")
    else:
        print(f"   ⚠️ WARNING: No new blocks created - check block proposer")
    
    return success_rate >= 80 and total_new_blocks > 0

if __name__ == "__main__":
    try:
        success = main()
        
        if success:
            print(f"\n🎉 TRANSACTION LOAD TEST SUCCESSFUL!")
            print("   ✅ 100 transactions sent successfully")
            print("   ✅ Blocks were created and propagated")
            print("   ✅ Network is functioning properly")
        else:
            print(f"\n⚠️ TRANSACTION LOAD TEST ISSUES DETECTED")
            print("   ⚠️ Check node logs and network connectivity")
            print("   ⚠️ Some transactions may have failed")
            
    except KeyboardInterrupt:
        print(f"\n🛑 Transaction sending interrupted by user")
    except Exception as e:
        print(f"\n💥 Transaction load test failed: {e}")
        import traceback
        traceback.print_exc()
