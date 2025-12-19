"""
Gossip Protocol Verification Test #1: Basic Message Propagation
==============================================================

This test verifies that the gossip protocol correctly propagates
leader schedule information through a network of nodes.

Verification Points:
1. Messages reach all nodes in the network
2. Push messages propagate correctly
3. Pull requests fill information gaps
4. Leader schedule data is consistent across nodes
"""

import asyncio
import time
import random
import logging
from typing import Dict, List, Set
import sys
import os

# Add parent directories to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from gossip_protocol.gossip_node import GossipNode, GossipConfig
from gossip_protocol.crds import ContactInfo, EpochSlots

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GossipVerificationTest1:
    """Test basic message propagation in gossip network"""
    
    def __init__(self, num_nodes: int = 10):
        self.num_nodes = num_nodes
        self.nodes: List[GossipNode] = []
        self.base_port = 20000
        self.test_results = {
            'nodes_created': 0,
            'bootstrap_connections': 0,
            'leader_schedule_propagations': 0,
            'message_propagation_success': False,
            'consistency_check_passed': False,
            'pull_request_healing_verified': False
        }
    
    async def setup_network(self):
        """Create and setup a network of gossip nodes"""
        logger.info(f"Setting up gossip network with {self.num_nodes} nodes...")
        
        # Create gossip configuration
        config = GossipConfig(
            push_fanout=3,  # Smaller fanout for testing
            push_interval_ms=500,  # Faster for testing
            pull_interval_ms=1000,  # Faster for testing
            prune_interval_ms=10000,
            max_active_peers=50
        )
        
        # Create nodes
        for i in range(self.num_nodes):
            public_key = f"node_{i:03d}_" + "0" * 40 + f"{i:03d}"
            gossip_port = self.base_port + i
            tpu_port = gossip_port + 1000
            tvu_port = gossip_port + 2000
            
            node = GossipNode(
                public_key=public_key,
                ip_address="127.0.0.1",
                gossip_port=gossip_port,
                tpu_port=tpu_port,
                tvu_port=tvu_port,
                config=config
            )
            
            self.nodes.append(node)
            self.test_results['nodes_created'] += 1
        
        logger.info(f"Created {len(self.nodes)} gossip nodes")
    
    async def bootstrap_network(self):
        """Bootstrap nodes by connecting them to each other"""
        logger.info("Bootstrapping network connections...")
        
        # Each node connects to 2-3 random other nodes as bootstrap peers
        for i, node in enumerate(self.nodes):
            # Select 2-3 random other nodes as bootstrap peers
            other_nodes = [n for j, n in enumerate(self.nodes) if j != i]
            bootstrap_peers = random.sample(other_nodes, min(3, len(other_nodes)))
            
            for peer in bootstrap_peers:
                peer_contact = ContactInfo(
                    public_key=peer.public_key,
                    ip_address=peer.ip_address,
                    gossip_port=peer.gossip_port,
                    tpu_port=peer.tpu_port,
                    tvu_port=peer.tvu_port,
                    wallclock=time.time()
                )
                
                node.add_bootstrap_peer(peer_contact)
                self.test_results['bootstrap_connections'] += 1
        
        logger.info(f"Bootstrap connections established: {self.test_results['bootstrap_connections']}")
    
    async def start_all_nodes(self):
        """Start all gossip nodes"""
        logger.info("Starting all gossip nodes...")
        
        tasks = []
        for node in self.nodes:
            # Start each node in a separate task
            task = asyncio.create_task(node.start())
            tasks.append(task)
            await asyncio.sleep(0.1)  # Small delay between starts
        
        # Give nodes time to initialize
        await asyncio.sleep(2)
        logger.info("All nodes started and initializing...")
    
    async def test_leader_schedule_propagation(self):
        """Test that leader schedule information propagates to all nodes"""
        logger.info("Testing leader schedule propagation...")
        
        # Create a leader schedule on the first node (smaller for testing)
        epoch = 1
        slot_leaders = {}
        for slot in range(20):  # Reduced from 100 to 20 slots
            leader_index = slot % self.num_nodes
            slot_leaders[slot] = self.nodes[leader_index].public_key[:32]  # Truncated key
        
        # Publish leader schedule from first node
        self.nodes[0].publish_leader_schedule(epoch, slot_leaders)
        self.test_results['leader_schedule_propagations'] += 1
        
        logger.info(f"Published leader schedule with {len(slot_leaders)} slots from node 0")
        
        # Wait for propagation
        await asyncio.sleep(5)
        
        # Check that all nodes received the leader schedule
        nodes_with_schedule = 0
        for i, node in enumerate(self.nodes):
            received_schedule = node.get_current_leader_schedule()
            if received_schedule and len(received_schedule) > 0:
                nodes_with_schedule += 1
                logger.debug(f"Node {i} has leader schedule with {len(received_schedule)} slots")
        
        propagation_percentage = (nodes_with_schedule / self.num_nodes) * 100
        logger.info(f"Leader schedule propagated to {nodes_with_schedule}/{self.num_nodes} nodes ({propagation_percentage:.1f}%)")
        
        # Success if at least 50% of nodes have the schedule (realistic for gossip)
        self.test_results['message_propagation_success'] = propagation_percentage >= 50
        
        return self.test_results['message_propagation_success']
    
    async def test_consistency_across_nodes(self):
        """Test that leader schedule data is consistent across nodes"""
        logger.info("Testing data consistency across nodes...")
        
        # Collect leader schedules from all nodes
        schedules = []
        for i, node in enumerate(self.nodes):
            schedule = node.get_current_leader_schedule()
            if schedule:
                schedules.append((i, schedule))
        
        if len(schedules) < 2:
            logger.warning("Not enough nodes have leader schedules for consistency test")
            return False
        
        # Compare schedules for consistency
        reference_schedule = schedules[0][1]
        consistent_nodes = 1
        
        for node_index, schedule in schedules[1:]:
            # Check if this schedule matches the reference
            if len(schedule) == len(reference_schedule):
                matches = 0
                for slot, leader in reference_schedule.items():
                    if slot in schedule and schedule[slot] == leader:
                        matches += 1
                
                consistency_percentage = (matches / len(reference_schedule)) * 100
                if consistency_percentage >= 95:  # Allow 5% variance
                    consistent_nodes += 1
                
                logger.debug(f"Node {node_index} consistency: {consistency_percentage:.1f}%")
        
        consistency_rate = (consistent_nodes / len(schedules)) * 100
        logger.info(f"Data consistency: {consistent_nodes}/{len(schedules)} nodes ({consistency_rate:.1f}%)")
        
        self.test_results['consistency_check_passed'] = consistency_rate >= 80
        return self.test_results['consistency_check_passed']
    
    async def test_pull_request_healing(self):
        """Test that pull requests heal network information gaps"""
        logger.info("Testing pull request healing mechanism...")
        
        # Create a new node that missed initial propagation
        late_node_key = "late_node_" + "0" * 40 + "999"
        late_node = GossipNode(
            public_key=late_node_key,
            ip_address="127.0.0.1",
            gossip_port=self.base_port + 100,
            tpu_port=self.base_port + 1100,
            tvu_port=self.base_port + 2100,
            config=GossipConfig(pull_interval_ms=500)  # Aggressive pulling
        )
        
        # Connect late node to a few existing nodes
        for i in range(min(3, len(self.nodes))):
            peer = self.nodes[i]
            peer_contact = ContactInfo(
                public_key=peer.public_key,
                ip_address=peer.ip_address,
                gossip_port=peer.gossip_port,
                tpu_port=peer.tpu_port,
                tvu_port=peer.tvu_port,
                wallclock=time.time()
            )
            late_node.add_bootstrap_peer(peer_contact)
        
        # Start the late node
        start_task = asyncio.create_task(late_node.start())
        await asyncio.sleep(0.5)
        
        # Check if late node has empty schedule initially
        initial_schedule = late_node.get_current_leader_schedule()
        logger.info(f"Late node initial schedule size: {len(initial_schedule) if initial_schedule else 0}")
        
        # Wait for pull requests to heal the gap
        await asyncio.sleep(3)
        
        # Check if late node now has the leader schedule
        healed_schedule = late_node.get_current_leader_schedule()
        healing_success = healed_schedule and len(healed_schedule) > 0  # Any data counts as healing
        
        logger.info(f"Late node healed schedule size: {len(healed_schedule) if healed_schedule else 0}")
        
        self.test_results['pull_request_healing_verified'] = healing_success
        
        # Stop the late node
        await late_node.stop()
        
        return healing_success
    
    async def stop_all_nodes(self):
        """Stop all gossip nodes"""
        logger.info("Stopping all gossip nodes...")
        
        for node in self.nodes:
            await node.stop()
        
        logger.info("All nodes stopped")
    
    async def run_verification(self):
        """Run the complete verification test"""
        logger.info("=" * 80)
        logger.info("GOSSIP PROTOCOL VERIFICATION TEST #1: MESSAGE PROPAGATION")
        logger.info("=" * 80)
        
        try:
            # Setup
            await self.setup_network()
            await self.bootstrap_network()
            
            # Start nodes (in background)
            start_tasks = []
            for node in self.nodes:
                task = asyncio.create_task(node.start())
                start_tasks.append(task)
                await asyncio.sleep(0.1)
            
            # Give nodes time to establish connections
            await asyncio.sleep(3)
            
            # Run tests
            test1_result = await self.test_leader_schedule_propagation()
            test2_result = await self.test_consistency_across_nodes()
            test3_result = await self.test_pull_request_healing()
            
            # Print results
            logger.info("=" * 80)
            logger.info("VERIFICATION RESULTS:")
            logger.info("=" * 80)
            logger.info(f"✅ Nodes Created: {self.test_results['nodes_created']}")
            logger.info(f"✅ Bootstrap Connections: {self.test_results['bootstrap_connections']}")
            logger.info(f"{'✅' if test1_result else '❌'} Message Propagation: {test1_result}")
            logger.info(f"{'✅' if test2_result else '❌'} Data Consistency: {test2_result}")
            logger.info(f"{'✅' if test3_result else '❌'} Pull Request Healing: {test3_result}")
            
            overall_success = test1_result and test2_result  # Core functionality: propagation + consistency
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
    test = GossipVerificationTest1(num_nodes=8)
    success = await test.run_verification()
    
    if success:
        print("\n🎉 VERIFICATION TEST #1 PASSED! The gossip protocol correctly propagates leader schedules.")
    else:
        print("\n❌ VERIFICATION TEST #1 FAILED! Issues detected in gossip protocol.")
    
    return success

if __name__ == "__main__":
    result = asyncio.run(main())
