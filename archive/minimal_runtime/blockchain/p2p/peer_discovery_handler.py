import os
import threading
import time

from blockchain.p2p.message import Message
from blockchain.utils.helpers import BlockchainUtils
from blockchain.utils.logger import logger


class PeerDiscoveryHandler:
    def __init__(self, node):
        self.socket_communication = node
        self.use_docker = os.environ.get("USE_DOCKER", False)

    def start(self):
        status_thread = threading.Thread(target=self.status, args=())
        status_thread.start()
        discovery_thread = threading.Thread(target=self.discovery, args=())
        discovery_thread.start()

    def status(self):
        count = 1
        while True:
            current_connections = []
            for peer in self.socket_communication.peers:
                current_connections.append(f"{peer.ip}: {peer.port}")
            
            # Only log status periodically to reduce CPU overhead
            if count % 10 == 1:  # Log every 10th check (every 5-50 minutes)
                if not self.socket_communication.peers:
                    logger.info({"message": "No nodes connected"})
                else:
                    logger.info(
                        {
                            "message": "Node connection status",
                            "connections": f"Current connections: {current_connections}",
                            "peer_count": len(current_connections),
                            "whoami": str(self.socket_communication.socket_connector)
                        }
                    )
            count += 1
            # Adaptive sleep: longer intervals as network stabilizes
            sleep_time = min(60 + (count * 10), 600)  # 60s to 10min max
            time.sleep(sleep_time)

    def discovery(self):
        discovery_count = 0
        stable_network_threshold = 10  # Consider network stable after 10 rounds
        
        while True:
            discovery_count += 1
            peer_count = len(self.socket_communication.peers)
            
            # Reduce discovery frequency as network grows and stabilizes
            if peer_count >= 5 and discovery_count > stable_network_threshold:
                # Network is stable, reduce discovery frequency
                discovery_interval = 120  # 2 minutes for stable networks
            elif peer_count >= 3:
                # Medium-sized network
                discovery_interval = 60   # 1 minute
            else:
                # Small network or early stages
                discovery_interval = 30   # 30 seconds
            
            # Only broadcast if we don't have enough peers or periodically for maintenance
            if peer_count < 8 or discovery_count % 5 == 0:
                handshake_message = self.handshake_message()
                self.socket_communication.broadcast(handshake_message)
            
            time.sleep(discovery_interval)

    def handshake(self, connected_node):
        handshake_message = self.handshake_message()
        self.socket_communication.send(connected_node, handshake_message)

    def handshake_message(self):
        connector_self = self.socket_communication.socket_connector
        peers_self = self.socket_communication.peers
        data = peers_self
        message_type = "DISCOVERY"
        message = Message(connector_self, message_type, data)
        encoded_message = BlockchainUtils.encode(message)
        return encoded_message

    def handle_message(self, message):
        peers_socket_connector = message.sender_connector
        peers_peer_list = message.data

        # Rate limiting: avoid processing too many discovery messages
        current_time = time.time()
        if not hasattr(self, '_last_discovery_process'):
            self._last_discovery_process = 0
        
        # Limit discovery message processing to once every 5 seconds per sender
        sender_key = f"{peers_socket_connector.ip}:{peers_socket_connector.port}"
        if not hasattr(self, '_sender_cooldowns'):
            self._sender_cooldowns = {}
        
        if sender_key in self._sender_cooldowns:
            if current_time - self._sender_cooldowns[sender_key] < 5:
                return  # Skip processing, too frequent
        
        self._sender_cooldowns[sender_key] = current_time

        # Clean up old cooldown entries to prevent memory leaks
        if len(self._sender_cooldowns) > 50:  # Limit cache size
            old_entries = [k for k, v in self._sender_cooldowns.items() 
                          if current_time - v > 300]  # Remove entries older than 5 minutes
            for k in old_entries:
                del self._sender_cooldowns[k]

        # Check if sender is already known
        sender_known = any(
            peer.equals(peers_socket_connector)
            for peer in self.socket_communication.peers
        )
        
        if not sender_known:
            # Limit maximum peer connections to prevent network overload
            max_peers = 15  # Reasonable limit for consensus efficiency
            if len(self.socket_communication.peers) < max_peers:
                self.socket_communication.peers.append(peers_socket_connector)

        # Process peer list with connection limits
        new_connections = 0
        max_new_connections_per_discovery = 2  # Limit new connections per discovery message
        
        for peers_peer in peers_peer_list:
            if new_connections >= max_new_connections_per_discovery:
                break  # Prevent connection storms
                
            peer_known = any(
                peer.equals(peers_peer)
                for peer in self.socket_communication.peers
            )

            if (not peer_known and 
                not peers_peer.equals(self.socket_communication.socket_connector) and
                len(self.socket_communication.peers) < max_peers):
                
                ip = peers_peer.ip
                if self.use_docker:
                    ip = peers_peer.docker_ip
                
                # Add small delay to prevent thundering herd
                time.sleep(0.1 * new_connections)
                self.socket_communication.connect_with_node(ip, peers_peer.port)
                new_connections += 1
