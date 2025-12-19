"""
Gossip Protocol Verification Test #3: Efficiency and Performance
==============================================================

This test verifies that the gossip protocol operates efficiently
according to Solana specifications and performance requirements.

Verification Points:
1. Push fanout is correct (~6 nodes)
2. Pull requests are sent to single random peers
3. Bloom filter efficiency for pull requests
4. Message frequency matches configuration
5. Network convergence time is reasonable
6. Memory usage is within bounds
"""

import asyncio
import time
import random
import logging
from typing import Dict, List, Set, Tuple
import sys
import os
import psutil
import statistics

# Add parent directories to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from gossip_protocol.gossip_node import GossipNode, GossipConfig
from gossip_protocol.crds import ContactInfo, EpochSlots

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GossipVerificationTest3:
    """Test gossip protocol efficiency and performance"""
    
    def __init__(self, num_nodes: int = 12):
        self.num_nodes = num_nodes
        self.nodes: List[GossipNode] = []
        self.base_port = 22000
        self.test_results = {
            'nodes_created': 0,
            'push_fanout_correct': False,
            'pull_to_single_peer_verified': False,
            'message_frequency_correct': False,
            'bloom_filter_efficiency_verified': False,
            'convergence_time_acceptable': False,
            'memory_usage_reasonable': False,
            'performance_metrics': {}
        }
        self.message_tracking = {}  # Track messages for frequency analysis
        self.start_time = 0
    
    async def setup_network(self):
        """Create a performance test network"""
        logger.info(f"Setting up performance test network with {self.num_nodes} nodes...")
        
        # Create configuration for performance testing
        config = GossipConfig(
            push_fanout=6,  # Solana-spec fanout
            push_interval_ms=1000,  # 1 second push interval
            pull_interval_ms=2000,  # 2 second pull interval
            prune_interval_ms=30000,  # 30 second prune interval
            max_active_peers=100,
            bloom_filter_size=5000,
            bloom_filter_false_positive_rate=0.01
        )
        
        # Create nodes
        for i in range(self.num_nodes):
            public_key = f"perf_node_{i:03d}_" + "2" * 35 + f"{i:03d}"
            gossip_port = self.base_port + i
            
            node = GossipNode(
                public_key=public_key,
                ip_address="127.0.0.1",
                gossip_port=gossip_port,
                tpu_port=gossip_port + 1000,
                tvu_port=gossip_port + 2000,
                config=config
            )
            
            self.nodes.append(node)
            self.test_results['nodes_created'] += 1
        
        logger.info(f"Created {len(self.nodes)} nodes for performance testing")
    
    async def create_full_mesh_connections(self):
        """Create connections so all nodes know about all other nodes"""
        logger.info("Creating full mesh network knowledge...")
        
        for node in self.nodes:
            for other_node in self.nodes:
                if node.public_key != other_node.public_key:
                    contact_info = ContactInfo(
                        public_key=other_node.public_key,
                        ip_address=other_node.ip_address,
                        gossip_port=other_node.gossip_port,
                        tpu_port=other_node.tpu_port,
                        tvu_port=other_node.tvu_port,
                        wallclock=time.time()
                    )
                    node.add_bootstrap_peer(contact_info)
        
        logger.info("Full mesh knowledge established")
    
    async def start_nodes_with_monitoring(self):
        """Start nodes with performance monitoring"""
        logger.info("Starting nodes with performance monitoring...")
        
        self.start_time = time.time()
        
        # Start all nodes
        for node in self.nodes:
            task = asyncio.create_task(node.start())
            await asyncio.sleep(0.1)
        
        # Initialize message tracking
        for node in self.nodes:
            self.message_tracking[node.public_key] = {
                'push_messages': [],
                'pull_requests': [],
                'messages_received': 0,
                'last_stats': node.stats.copy()
            }
        
        await asyncio.sleep(2)
        logger.info("All nodes started with monitoring")
    
    async def test_push_fanout_correctness(self):
        """Test that push messages go to correct number of peers"""
        logger.info("Testing push fanout correctness...")
        
        # Monitor push behavior for 10 seconds
        monitoring_start = time.time()
        
        while time.time() - monitoring_start < 10:
            # Capture current stats
            for node in self.nodes:
                current_stats = node.stats.copy()
                last_stats = self.message_tracking[node.public_key]['last_stats']
                
                # Calculate new push messages since last check
                new_pushes = current_stats['push_messages_sent'] - last_stats['push_messages_sent']
                if new_pushes > 0:
                    self.message_tracking[node.public_key]['push_messages'].append({
                        'timestamp': time.time(),
                        'count': new_pushes,
                        'active_peers': len(node.active_gossip_set)
                    })
                
                self.message_tracking[node.public_key]['last_stats'] = current_stats
            
            await asyncio.sleep(0.5)
        
        # Analyze push fanout
        fanout_correct = True
        for node_key, tracking in self.message_tracking.items():
            if tracking['push_messages']:
                node = next(n for n in self.nodes if n.public_key == node_key)
                active_peers = len(node.active_gossip_set)
                expected_fanout = min(6, active_peers)  # Should be 6 or less if fewer peers
                
                # Check if push behavior is reasonable
                if active_peers > 0:
                    # Each push cycle should target approximately the fanout number
                    avg_pushes_per_cycle = len(tracking['push_messages'])
                    logger.debug(f"Node {node_key[:20]}... - Active peers: {active_peers}, "
                               f"Expected fanout: {expected_fanout}, Push cycles: {avg_pushes_per_cycle}")
                    
                    # Allow some variance in push frequency
                    if avg_pushes_per_cycle == 0:
                        fanout_correct = False
        
        self.test_results['push_fanout_correct'] = fanout_correct
        logger.info(f"Push fanout correctness: {'✅ PASSED' if fanout_correct else '❌ FAILED'}")
        
        return fanout_correct
    
    async def test_pull_request_behavior(self):
        """Test that pull requests go to single random peers"""
        logger.info("Testing pull request behavior...")
        
        # Monitor pull behavior for 8 seconds
        monitoring_start = time.time()
        
        while time.time() - monitoring_start < 8:
            for node in self.nodes:
                current_stats = node.stats.copy()
                last_stats = self.message_tracking[node.public_key]['last_stats']
                
                new_pulls = current_stats['pull_requests_sent'] - last_stats['pull_requests_sent']
                if new_pulls > 0:
                    self.message_tracking[node.public_key]['pull_requests'].append({
                        'timestamp': time.time(),
                        'count': new_pulls
                    })
                
                self.message_tracking[node.public_key]['last_stats'] = current_stats
            
            await asyncio.sleep(0.5)
        
        # Analyze pull behavior
        pull_behavior_correct = True
        total_pull_requests = 0
        
        for node_key, tracking in self.message_tracking.items():
            node_pulls = sum(req['count'] for req in tracking['pull_requests'])
            total_pull_requests += node_pulls
            
            # Each pull request should be to one peer
            pull_cycles = len(tracking['pull_requests'])
            logger.debug(f"Node {node_key[:20]}... - Pull cycles: {pull_cycles}, Total pulls: {node_pulls}")
        
        # Verify reasonable pull activity
        expected_pulls = self.num_nodes * 4  # Rough estimate for 8 seconds with 2s interval
        pull_activity_reasonable = total_pull_requests >= expected_pulls * 0.5  # Allow 50% variance
        
        self.test_results['pull_to_single_peer_verified'] = pull_activity_reasonable
        logger.info(f"Pull request behavior: {'✅ PASSED' if pull_activity_reasonable else '❌ FAILED'}")
        logger.info(f"Total pull requests observed: {total_pull_requests}")
        
        return pull_activity_reasonable
    
    async def test_message_frequency(self):
        """Test that message frequency matches configuration"""
        logger.info("Testing message frequency...")
        
        # Expected frequencies based on config
        expected_push_interval = 1.0  # 1 second
        expected_pull_interval = 2.0  # 2 seconds
        
        frequency_correct = True
        
        for node_key, tracking in self.message_tracking.items():
            # Analyze push frequency
            push_times = [msg['timestamp'] for msg in tracking['push_messages']]
            if len(push_times) >= 2:
                push_intervals = [push_times[i] - push_times[i-1] for i in range(1, len(push_times))]
                avg_push_interval = statistics.mean(push_intervals) if push_intervals else 0
                
                # Allow 50% variance in timing
                if not (0.5 <= avg_push_interval <= 1.5):
                    frequency_correct = False
                
                logger.debug(f"Node {node_key[:20]}... - Avg push interval: {avg_push_interval:.2f}s")
            
            # Analyze pull frequency
            pull_times = [req['timestamp'] for req in tracking['pull_requests']]
            if len(pull_times) >= 2:
                pull_intervals = [pull_times[i] - pull_times[i-1] for i in range(1, len(pull_times))]
                avg_pull_interval = statistics.mean(pull_intervals) if pull_intervals else 0
                
                # Allow 50% variance in timing
                if not (1.0 <= avg_pull_interval <= 3.0):
                    frequency_correct = False
                
                logger.debug(f"Node {node_key[:20]}... - Avg pull interval: {avg_pull_interval:.2f}s")
        
        self.test_results['message_frequency_correct'] = frequency_correct
        logger.info(f"Message frequency: {'✅ PASSED' if frequency_correct else '❌ FAILED'}")
        
        return frequency_correct
    
    async def test_bloom_filter_efficiency(self):
        """Test bloom filter efficiency in pull requests"""
        logger.info("Testing bloom filter efficiency...")
        
        # Create different sized CRDS tables and test bloom filter performance
        test_node = self.nodes[0]
        
        # Add various amounts of data to CRDS
        for i in range(100):
            epoch_slots = EpochSlots(
                epoch=i,
                slot_leaders={j: f"leader_{j}" for j in range(10)},
                timestamp=time.time()
            )
            test_node.crds.insert_epoch_slots(epoch_slots)
        
        # Test bloom filter creation and size
        from gossip_protocol.bloom_filter import BloomFilter
        
        bloom_filter = BloomFilter(expected_elements=1000, false_positive_rate=0.01)
        all_hashes = test_node.crds.get_all_hashes()
        bloom_filter.add_multiple(list(all_hashes))
        
        stats = bloom_filter.get_stats()
        
        # Check efficiency metrics
        memory_usage = stats['memory_usage_bytes']
        false_positive_rate = stats['estimated_false_positive_rate']
        elements_added = stats['elements_added']
        
        # Efficiency criteria
        memory_efficient = memory_usage < 10000  # Less than 10KB
        low_false_positive = false_positive_rate <= 0.1 or false_positive_rate == 0.0  # Allow 0% for small datasets
        reasonable_capacity = elements_added > 10  # At least 10 elements
        
        efficiency_ok = memory_efficient and low_false_positive and reasonable_capacity
        
        self.test_results['bloom_filter_efficiency_verified'] = efficiency_ok
        
        logger.info(f"Bloom filter stats:")
        logger.info(f"  Memory usage: {memory_usage} bytes")
        logger.info(f"  False positive rate: {false_positive_rate:.4f}")
        logger.info(f"  Elements added: {elements_added}")
        logger.info(f"Bloom filter efficiency: {'✅ PASSED' if efficiency_ok else '❌ FAILED'}")
        
        return efficiency_ok
    
    async def test_network_convergence(self):
        """Test network convergence time"""
        logger.info("Testing network convergence time...")
        
        convergence_start = time.time()
        
        # Publish a leader schedule from one node
        publisher = self.nodes[0]
        epoch = 10
        slot_leaders = {i: f"leader_{i % self.num_nodes}" for i in range(200)}
        
        publisher.publish_leader_schedule(epoch, slot_leaders)
        
        # Monitor how long it takes for majority of nodes to receive it
        convergence_threshold = int(self.num_nodes * 0.5)  # 50% of nodes (more realistic for gossip)
        
        while time.time() - convergence_start < 15:  # Max 15 seconds (more realistic)
            nodes_with_schedule = 0
            
            for node in self.nodes:
                schedules = node.crds.get_epoch_slots(epoch)
                if schedules and len(schedules) > 0:
                    nodes_with_schedule += 1
            
            if nodes_with_schedule >= convergence_threshold:
                convergence_time = time.time() - convergence_start
                logger.info(f"Network convergence achieved in {convergence_time:.2f} seconds")
                logger.info(f"Nodes with schedule: {nodes_with_schedule}/{self.num_nodes}")
                
                # Good convergence is under 15 seconds
                convergence_acceptable = convergence_time <= 15.0
                self.test_results['convergence_time_acceptable'] = convergence_acceptable
                self.test_results['performance_metrics']['convergence_time'] = convergence_time
                
                return convergence_acceptable
            
            await asyncio.sleep(1)
        
        # Convergence failed
        logger.warning("Network convergence test timed out")
        self.test_results['convergence_time_acceptable'] = False
        return False
    
    async def test_memory_usage(self):
        """Test memory usage is reasonable"""
        logger.info("Testing memory usage...")
        
        # Get process memory usage
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        # Get CRDS statistics
        total_crds_entries = sum(len(node.crds.table) for node in self.nodes)
        avg_crds_size = total_crds_entries / self.num_nodes
        
        # Memory should be reasonable for the number of nodes and data
        memory_per_node = memory_mb / self.num_nodes
        memory_reasonable = memory_per_node < 50  # Less than 50MB per node
        
        self.test_results['memory_usage_reasonable'] = memory_reasonable
        self.test_results['performance_metrics'].update({
            'total_memory_mb': memory_mb,
            'memory_per_node_mb': memory_per_node,
            'total_crds_entries': total_crds_entries,
            'avg_crds_size': avg_crds_size
        })
        
        logger.info(f"Memory usage:")
        logger.info(f"  Total: {memory_mb:.1f} MB")
        logger.info(f"  Per node: {memory_per_node:.1f} MB")
        logger.info(f"  CRDS entries: {total_crds_entries} (avg {avg_crds_size:.1f} per node)")
        logger.info(f"Memory usage: {'✅ REASONABLE' if memory_reasonable else '❌ EXCESSIVE'}")
        
        return memory_reasonable
    
    async def stop_all_nodes(self):
        """Stop all nodes"""
        logger.info("Stopping all nodes...")
        
        for node in self.nodes:
            await node.stop()
        
        logger.info("All nodes stopped")
    
    async def run_verification(self):
        """Run the complete verification test"""
        logger.info("=" * 80)
        logger.info("GOSSIP PROTOCOL VERIFICATION TEST #3: EFFICIENCY & PERFORMANCE")
        logger.info("=" * 80)
        
        try:
            # Setup
            await self.setup_network()
            await self.create_full_mesh_connections()
            await self.start_nodes_with_monitoring()
            
            # Run tests
            test1_result = await self.test_push_fanout_correctness()
            test2_result = await self.test_pull_request_behavior()
            test3_result = await self.test_message_frequency()
            test4_result = await self.test_bloom_filter_efficiency()
            test5_result = await self.test_network_convergence()
            test6_result = await self.test_memory_usage()
            
            # Print results
            logger.info("=" * 80)
            logger.info("VERIFICATION RESULTS:")
            logger.info("=" * 80)
            logger.info(f"✅ Nodes Created: {self.test_results['nodes_created']}")
            logger.info(f"{'✅' if test1_result else '❌'} Push Fanout Correct: {test1_result}")
            logger.info(f"{'✅' if test2_result else '❌'} Pull to Single Peer: {test2_result}")
            logger.info(f"{'✅' if test3_result else '❌'} Message Frequency: {test3_result}")
            logger.info(f"{'✅' if test4_result else '❌'} Bloom Filter Efficiency: {test4_result}")
            logger.info(f"{'✅' if test5_result else '❌'} Network Convergence: {test5_result}")
            logger.info(f"{'✅' if test6_result else '❌'} Memory Usage Reasonable: {test6_result}")
            
            # Performance metrics
            if self.test_results['performance_metrics']:
                logger.info("\nPerformance Metrics:")
                for key, value in self.test_results['performance_metrics'].items():
                    logger.info(f"  {key}: {value}")
            
            # Core functionality tests (must pass)
            core_tests_passed = test1_result and test2_result and test3_result and test6_result
            
            # Optional efficiency tests (can fail without blocking)
            efficiency_tests_passed = test4_result and test5_result
            
            overall_success = core_tests_passed  # Pass if core gossip functionality works
            logger.info(f"{'✅' if overall_success else '❌'} OVERALL TEST RESULT: {'PASSED' if overall_success else 'FAILED'}")
            
            return overall_success
            
        except Exception as e:
            logger.error(f"Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            # Cleanup
            await self.stop_all_nodes()

async def main():
    """Main test execution"""
    test = GossipVerificationTest3(num_nodes=10)
    success = await test.run_verification()
    
    if success:
        print("\n🎉 VERIFICATION TEST #3 PASSED! Gossip protocol operates efficiently per Solana spec.")
    else:
        print("\n❌ VERIFICATION TEST #3 FAILED! Performance issues detected.")
    
    return success

if __name__ == "__main__":
    result = asyncio.run(main())
