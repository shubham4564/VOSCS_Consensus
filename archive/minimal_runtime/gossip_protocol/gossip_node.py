"""
Gossip Protocol Node Implementation
=================================

Main gossip protocol implementation that manages CRDS, peer connections,
and message handling for distributing leader schedule information.
"""

import asyncio
import json
import time
import random
import socket
import logging
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass
from .crds import CRDS, ContactInfo, Vote, EpochSlots, HealthInfo, CrdsValue
from .bloom_filter import BloomFilter
from .messages import (
    PushMessage, PullRequest, PullResponse, PruneMessage,
    GossipMessageFactory, MessageValidator
)

logger = logging.getLogger(__name__)

@dataclass
class GossipConfig:
    """Configuration for gossip protocol"""
    push_fanout: int = 6  # Number of nodes to push to
    push_interval_ms: int = 1000  # Push every 1 second
    pull_interval_ms: int = 2000  # Pull every 2 seconds
    prune_interval_ms: int = 30000  # Prune every 30 seconds
    max_active_peers: int = 200
    max_failures_before_prune: int = 3
    peer_timeout_seconds: int = 300  # 5 minutes
    bloom_filter_size: int = 10000
    bloom_filter_false_positive_rate: float = 0.01

class GossipNode:
    """
    Gossip protocol node for distributing leader schedules and network information
    
    Implements Solana-style gossip with health-based pruning instead of stake-based pruning
    """
    
    def __init__(self, public_key: str, ip_address: str, gossip_port: int, 
                 tpu_port: int, tvu_port: int, config: GossipConfig = None):
        self.public_key = public_key
        self.ip_address = ip_address
        self.gossip_port = gossip_port
        self.tpu_port = tpu_port
        self.tvu_port = tvu_port
        self.config = config or GossipConfig()
        
        # Initialize CRDS
        self.crds = CRDS(public_key)
        
        # Peer management
        self.known_peers: Dict[str, ContactInfo] = {}
        self.active_gossip_set: Set[str] = set()  # Active peers for pushing
        self.pruned_peers: Set[str] = set()  # Peers we've pruned
        
        # Network state
        self.socket: Optional[socket.socket] = None
        self.running = False
        
        # Metrics
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'push_messages_sent': 0,
            'pull_requests_sent': 0,
            'pull_responses_sent': 0,
            'prune_messages_sent': 0,
            'peers_pruned': 0,
            'crds_updates': 0
        }
        
        # Register our own contact info
        self._register_self()
        
        logger.info(f"GossipNode initialized: {public_key[:16]}... on {ip_address}:{gossip_port}")
    
    def _register_self(self):
        """Register our own contact information in CRDS"""
        contact_info = ContactInfo(
            public_key=self.public_key,
            ip_address=self.ip_address,
            gossip_port=self.gossip_port,
            tpu_port=self.tpu_port,
            tvu_port=self.tvu_port,
            wallclock=time.time()
        )
        
        success = self.crds.insert_contact_info(contact_info)
        if success:
            logger.info(f"Self contact info registered in CRDS")
        
        # Also add to known peers
        self.known_peers[self.public_key] = contact_info
    
    async def start(self):
        """Start the gossip protocol node"""
        if self.running:
            return
        
        # Create UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.ip_address, self.gossip_port))
        self.socket.setblocking(False)
        
        self.running = True
        logger.info(f"Gossip node started on {self.ip_address}:{self.gossip_port}")
        
        # Start gossip tasks
        await asyncio.gather(
            self._gossip_loop(),
            self._message_handler(),
            self._maintenance_loop()
        )
    
    async def stop(self):
        """Stop the gossip protocol node"""
        self.running = False
        if self.socket:
            self.socket.close()
        logger.info("Gossip node stopped")
    
    async def _gossip_loop(self):
        """Main gossip loop - push and pull operations"""
        last_push = 0
        last_pull = 0
        
        while self.running:
            current_time = time.time() * 1000  # milliseconds
            
            # PUSH phase
            if current_time - last_push >= self.config.push_interval_ms:
                await self._perform_push()
                last_push = current_time
            
            # PULL phase  
            if current_time - last_pull >= self.config.pull_interval_ms:
                await self._perform_pull()
                last_pull = current_time
            
            await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
    
    async def _perform_push(self):
        """Push newest CRDS data to active peers"""
        if not self.active_gossip_set:
            self._update_active_gossip_set()
        
        if not self.active_gossip_set:
            return  # No peers to push to
        
        # Get newest CRDS items (limit to prevent message size issues)
        newest_items = self.crds.get_newest_items(1)  # Reduced to 1 item to prevent UDP size issues
        if not newest_items:
            return
        
        # Select random peers to push to (up to fanout limit)
        push_targets = random.sample(
            list(self.active_gossip_set), 
            min(self.config.push_fanout, len(self.active_gossip_set))
        )
        
        # Create and send push messages
        push_message = GossipMessageFactory.create_push_message(self.public_key, newest_items)
        
        for target_key in push_targets:
            target_info = self.known_peers.get(target_key)
            if target_info and target_key not in self.pruned_peers:
                await self._send_message(target_info, push_message)
                self.stats['push_messages_sent'] += 1
        
        logger.debug(f"Pushed {len(newest_items)} items to {len(push_targets)} peers")
    
    async def _perform_pull(self):
        """Pull missing data from a random peer"""
        available_peers = [key for key in self.known_peers.keys() 
                          if key != self.public_key and key not in self.pruned_peers]
        
        if not available_peers:
            return
        
        # Select random peer to pull from
        target_key = random.choice(available_peers)
        target_info = self.known_peers[target_key]
        
        # Create bloom filter of our current CRDS
        bloom_filter = BloomFilter(
            expected_elements=500,  # Reduced from config value
            false_positive_rate=0.05  # Slightly higher rate for smaller size
        )
        
        # Add all our CRDS hashes to bloom filter
        all_hashes = self.crds.get_all_hashes()
        bloom_filter.add_multiple(list(all_hashes))
        
        # Create and send pull request
        pull_request = GossipMessageFactory.create_pull_request(self.public_key, bloom_filter)
        await self._send_message(target_info, pull_request)
        self.stats['pull_requests_sent'] += 1
        
        logger.debug(f"Sent pull request to {target_key[:16]}... (bloom filter: {len(all_hashes)} items)")
    
    async def _message_handler(self):
        """Handle incoming gossip messages"""
        while self.running:
            try:
                # Receive message
                data, addr = await asyncio.get_event_loop().sock_recvfrom(self.socket, 65536)
                message_dict = json.loads(data.decode())
                
                # Parse message
                message = GossipMessageFactory.parse_message(message_dict)
                if not message:
                    continue
                
                # Handle message based on type
                if isinstance(message, PushMessage):
                    await self._handle_push_message(message, addr)
                elif isinstance(message, PullRequest):
                    await self._handle_pull_request(message, addr)
                elif isinstance(message, PullResponse):
                    await self._handle_pull_response(message, addr)
                elif isinstance(message, PruneMessage):
                    await self._handle_prune_message(message, addr)
                
                self.stats['messages_received'] += 1
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error handling message: {e}")
                await asyncio.sleep(0.1)
    
    async def _handle_push_message(self, message: PushMessage, addr: Tuple[str, int]):
        """Handle received push message"""
        if not MessageValidator.validate_push_message(message):
            logger.warning(f"Invalid push message from {message.sender_public_key[:16]}...")
            return
        
        # Update health info for sender
        self._update_peer_health(message.sender_public_key, True, 0.0)
        
        # Insert CRDS values
        crds_values = message.get_crds_values()
        updates_count = 0
        
        for crds_value in crds_values:
            if self.crds.insert(crds_value):
                updates_count += 1
                
                # If this is contact info, add to known peers
                if crds_value.data_type == 'ContactInfo':
                    self.known_peers[crds_value.public_key] = crds_value.data
        
        if updates_count > 0:
            self.stats['crds_updates'] += updates_count
            logger.debug(f"Push message: {updates_count} new/updated items from {message.sender_public_key[:16]}...")
    
    async def _handle_pull_request(self, message: PullRequest, addr: Tuple[str, int]):
        """Handle received pull request"""
        if not MessageValidator.validate_pull_request(message):
            logger.warning(f"Invalid pull request from {message.sender_public_key[:16]}...")
            return
        
        # Update health info for sender
        self._update_peer_health(message.sender_public_key, True, 0.0)
        
        # Get bloom filter and find missing items
        bloom_filter = message.get_bloom_filter()
        known_hashes = set()
        
        # Reconstruct the set of hashes the requester has
        for crds_value in self.crds.table.values():
            if bloom_filter.contains(crds_value.get_hash()):
                known_hashes.add(crds_value.get_hash())
        
        # Find items we have that the requester doesn't (limit response size)
        missing_items = self.crds.get_missing_items(known_hashes)[:3]  # Limit to 3 items
        
        # Create and send pull response
        if missing_items:
            sender_info = self.known_peers.get(self.public_key)
            if sender_info:
                pull_response = GossipMessageFactory.create_pull_response(
                    self.public_key, message.sender_public_key, missing_items, message.message_id
                )
                
                # Send to requester
                requester_info = self.known_peers.get(message.sender_public_key)
                if requester_info:
                    await self._send_message(requester_info, pull_response)
                    self.stats['pull_responses_sent'] += 1
                    
                    logger.debug(f"Sent pull response: {len(missing_items)} items to {message.sender_public_key[:16]}...")
    
    async def _handle_pull_response(self, message: PullResponse, addr: Tuple[str, int]):
        """Handle received pull response"""
        if not MessageValidator.validate_pull_response(message):
            logger.warning(f"Invalid pull response from {message.sender_public_key[:16]}...")
            return
        
        # Update health info for sender
        self._update_peer_health(message.sender_public_key, True, 0.0)
        
        # Insert received CRDS values
        crds_values = message.get_crds_values()
        updates_count = 0
        
        for crds_value in crds_values:
            if self.crds.insert(crds_value):
                updates_count += 1
                
                # If this is contact info, add to known peers
                if crds_value.data_type == 'ContactInfo':
                    self.known_peers[crds_value.public_key] = crds_value.data
        
        if updates_count > 0:
            self.stats['crds_updates'] += updates_count
            logger.debug(f"Pull response: {updates_count} new items from {message.sender_public_key[:16]}...")
    
    async def _handle_prune_message(self, message: PruneMessage, addr: Tuple[str, int]):
        """Handle received prune message"""
        if not MessageValidator.validate_prune_message(message):
            return
        
        if message.target_public_key == self.public_key:
            # We've been pruned by the sender
            self.active_gossip_set.discard(message.sender_public_key)
            logger.info(f"Pruned by {message.sender_public_key[:16]}... (reason: {message.reason})")
    
    async def _maintenance_loop(self):
        """Periodic maintenance tasks"""
        last_prune = 0
        last_cleanup = 0
        
        while self.running:
            current_time = time.time() * 1000
            
            # Prune unhealthy peers
            if current_time - last_prune >= self.config.prune_interval_ms:
                await self._perform_pruning()
                last_prune = current_time
            
            # Cleanup old CRDS entries
            if current_time - last_cleanup >= 300000:  # Every 5 minutes
                self.crds.cleanup_old_entries()
                last_cleanup = current_time
            
            await asyncio.sleep(5)  # Check every 5 seconds
    
    async def _perform_pruning(self):
        """Prune unhealthy peers from active gossip set and trigger network healing"""
        unhealthy_peers = self.crds.get_unhealthy_nodes(
            max_failures=self.config.max_failures_before_prune,
            max_age_seconds=self.config.peer_timeout_seconds
        )
        
        initial_active_size = len(self.active_gossip_set)
        pruned_count = 0
        
        for peer_key in unhealthy_peers:
            if peer_key in self.active_gossip_set:
                self.active_gossip_set.discard(peer_key)
                self.pruned_peers.add(peer_key)
                
                # Send prune message
                peer_info = self.known_peers.get(peer_key)
                if peer_info:
                    prune_message = GossipMessageFactory.create_prune_message(
                        self.public_key, peer_key, "unhealthy"
                    )
                    await self._send_message(peer_info, prune_message)
                    self.stats['prune_messages_sent'] += 1
                
                pruned_count += 1
        
        if pruned_count > 0:
            self.stats['peers_pruned'] += pruned_count
            logger.info(f"Pruned {pruned_count} unhealthy peers from active gossip set")
        
        # NETWORK HEALING: Always update active set after pruning
        self._update_active_gossip_set()
        
        # If we lost significant connectivity, trigger immediate peer discovery
        final_active_size = len(self.active_gossip_set)
        connectivity_loss = (initial_active_size - final_active_size) / max(initial_active_size, 1)
        
        if connectivity_loss > 0.4 or final_active_size < 3:  # Increased threshold and minimum check
            logger.info(f"Significant connectivity loss ({connectivity_loss:.1%}) or low peer count ({final_active_size}), triggering network healing")
            await self._trigger_network_healing()
    
    async def _trigger_network_healing(self):
        """Actively seek new healthy peers when network connectivity is low"""
        # Perform additional pull requests to discover healthy peers
        available_peers = [key for key in self.known_peers.keys() 
                          if key != self.public_key and key not in self.pruned_peers]
        
        # Pull from multiple peers to discover network state
        healing_targets = min(3, len(available_peers))
        if healing_targets > 0:
            targets = random.sample(available_peers, healing_targets)
            for target_key in targets:
                target_info = self.known_peers[target_key]
                
                # Create bloom filter and send pull request
                bloom_filter = BloomFilter(expected_elements=100, false_positive_rate=0.1)
                all_hashes = self.crds.get_all_hashes()
                bloom_filter.add_multiple(list(all_hashes))
                
                pull_request = GossipMessageFactory.create_pull_request(
                    self.public_key, bloom_filter
                )
                
                await self._send_message(target_info, pull_request)
                self.stats['pull_requests_sent'] += 1
            
            logger.info(f"Network healing: Sent pull requests to {healing_targets} peers")
    
    def _update_active_gossip_set(self):
        """Update the active gossip set with healthy peers and ensure network resilience"""
        healthy_peers = self.crds.get_healthy_nodes()
        
        # Remove ourselves
        healthy_peers = [peer for peer in healthy_peers if peer != self.public_key]
        
        # Remove already pruned peers
        healthy_peers = [peer for peer in healthy_peers if peer not in self.pruned_peers]
        
        # NETWORK RESILIENCE IMPROVEMENT:
        # If we don't have enough healthy peers in CRDS, expand from known_peers
        min_target_peers = min(8, len(self.known_peers) - 1)  # Increased target to 8 peers
        
        if len(healthy_peers) < min_target_peers:
            # Add healthy peers from known_peers that aren't in pruned set
            additional_peers = []
            for peer_key, peer_info in self.known_peers.items():
                if (peer_key != self.public_key and 
                    peer_key not in self.pruned_peers and 
                    peer_key not in healthy_peers):
                    
                    # Check if this peer has recent activity or no health record (assume healthy)
                    health_info = self.crds.get_health_info(peer_key)
                    if health_info is None or health_info.is_healthy:
                        additional_peers.append(peer_key)
            
            # Add additional peers to maintain connectivity
            needed_peers = min_target_peers - len(healthy_peers)
            healthy_peers.extend(additional_peers[:needed_peers])
            logger.info(f"Network healing: Added {len(additional_peers[:needed_peers])} additional peers for resilience")
        
        # Update active set (ensure robust connectivity)
        target_size = min(max(min_target_peers, 4), self.config.max_active_peers)  # At least 4 peers
        self.active_gossip_set = set(healthy_peers[:target_size])
        
        # Force inclusion of some healthy peers even if not in CRDS health records
        if len(self.active_gossip_set) < 3 and len(self.known_peers) > 1:
            backup_peers = [key for key in self.known_peers.keys() 
                           if key != self.public_key and key not in self.pruned_peers]
            for peer in backup_peers[:3]:
                self.active_gossip_set.add(peer)
            logger.info(f"Emergency connectivity: Added {min(3, len(backup_peers))} backup peers")
        
        logger.debug(f"Active gossip set updated: {len(self.active_gossip_set)} peers (target: {target_size})")
    
    def _update_peer_health(self, public_key: str, is_healthy: bool, response_time: float):
        """Update health information for a peer"""
        health_info = HealthInfo(
            public_key=public_key,
            is_healthy=is_healthy,
            last_seen=time.time(),
            response_time_ms=response_time,
            consecutive_failures=0 if is_healthy else 1,
            uptime_percentage=100.0 if is_healthy else 50.0,
            timestamp=time.time()
        )
        
        self.crds.insert_health_info(health_info)
    
    async def _send_message(self, target_info: ContactInfo, message: Any):
        """Send a message to a target peer"""
        try:
            message_data = json.dumps(message.to_dict()).encode()
            message_size = len(message_data)
            
            # Check if message is too large for UDP (max 65507 bytes)
            if message_size > 65507:
                logger.warning(f"Message too large ({message_size} bytes) for UDP to {target_info.ip_address}:{target_info.gossip_port}")
                return
            
            await asyncio.get_event_loop().sock_sendto(
                self.socket, message_data, (target_info.ip_address, target_info.gossip_port)
            )
            self.stats['messages_sent'] += 1
            
            # Log large messages for debugging
            if message_size > 1024:  # Log messages over 1KB
                logger.debug(f"Large gossip message sent: {message_size} bytes to {target_info.ip_address}:{target_info.gossip_port}")
            
        except Exception as e:
            logger.warning(f"Failed to send message to {target_info.ip_address}:{target_info.gossip_port}: {e}")
            # Mark peer as unhealthy
            self._update_peer_health(target_info.public_key, False, 999.0)
    
    # Public API methods
    
    def add_bootstrap_peer(self, peer_info: ContactInfo):
        """Add a bootstrap peer to start gossip with"""
        self.known_peers[peer_info.public_key] = peer_info
        self.crds.insert_contact_info(peer_info)
        logger.info(f"Added bootstrap peer: {peer_info.public_key[:16]}...")
    
    def publish_vote(self, slot: int, block_hash: str):
        """Publish a vote to the network"""
        vote = Vote(
            public_key=self.public_key,
            slot=slot,
            block_hash=block_hash,
            timestamp=time.time()
        )
        
        success = self.crds.insert_vote(vote)
        if success:
            logger.info(f"Published vote for slot {slot}")
    
    def publish_leader_schedule(self, epoch: int, slot_leaders: Dict[int, str]):
        """Publish leader schedule information"""
        epoch_slots = EpochSlots(
            epoch=epoch,
            slot_leaders=slot_leaders,
            timestamp=time.time()
        )
        
        success = self.crds.insert_epoch_slots(epoch_slots)
        if success:
            logger.info(f"Published leader schedule for epoch {epoch} ({len(slot_leaders)} slots)")
    
    def get_leader_for_slot(self, slot: int, epoch: int = None) -> Optional[str]:
        """Get the leader for a specific slot"""
        epoch_slots_list = self.crds.get_epoch_slots(epoch)
        
        for epoch_slots in epoch_slots_list:
            if slot in epoch_slots.slot_leaders:
                return epoch_slots.slot_leaders[slot]
        
        return None
    
    def get_current_leader_schedule(self) -> Dict[int, str]:
        """Get the most recent leader schedule"""
        epoch_slots_list = self.crds.get_epoch_slots()
        
        if not epoch_slots_list:
            return {}
        
        # Get the most recent epoch slots
        latest_epoch = max(epoch_slots_list, key=lambda x: x.timestamp)
        return latest_epoch.slot_leaders
    
    def get_network_stats(self) -> Dict:
        """Get comprehensive network and gossip statistics"""
        crds_stats = self.crds.get_stats()
        
        return {
            'node_info': {
                'public_key': self.public_key[:16] + '...',
                'address': f"{self.ip_address}:{self.gossip_port}",
                'running': self.running
            },
            'crds_stats': crds_stats,
            'peer_stats': {
                'known_peers': len(self.known_peers),
                'active_gossip_set': len(self.active_gossip_set),
                'pruned_peers': len(self.pruned_peers)
            },
            'message_stats': self.stats,
            'config': {
                'push_fanout': self.config.push_fanout,
                'push_interval_ms': self.config.push_interval_ms,
                'pull_interval_ms': self.config.pull_interval_ms,
                'max_active_peers': self.config.max_active_peers
            }
        }
