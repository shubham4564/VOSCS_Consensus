import json
import socket
import time

from p2pnetwork.node import Node

from blockchain.p2p.peer_discovery_handler import PeerDiscoveryHandler
from blockchain.p2p.socket_connector import SocketConnector
from blockchain.utils.helpers import BlockchainUtils
from blockchain.utils.logger import logger


class SocketCommunication(Node):
    def __init__(self, ip, port):
        super(SocketCommunication, self).__init__(ip, port, None)
        self.peers = []
        self.peer_discovery_handler = PeerDiscoveryHandler(self)
        self.socket_connector = SocketConnector(ip, port)
        # Message deduplication cache
        self._processed_messages = {}
        self._last_cache_cleanup = time.time()

    def init_server(self):
        logger.info(
            {
                "message": f"Node initialisation on port: {self.port}",
                "node": {"id": self.id, "ip": self.host, "port": self.port},
            }
        )
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(10.0)
        self.sock.listen(1)

    def connect_to_first_node(self):
        port = self.socket_connector.first_node_config()["port"]
        ip = self.socket_connector.first_node_config()["ip"]
        logger.info({
            "message": "First node config retrieved",
            "target_ip": ip,
            "target_port": port,
            "own_port": self.socket_connector.port,
            "port_type": type(port).__name__
        })
        if self.socket_connector.port != port:
            logger.info({
                "message": "Attempting to connect to first node",
                "target": f"{ip}:{port}"
            })
            self.connect_with_node(ip, port)
            logger.info({
                "message": "Connect call completed",
                "target": f"{ip}:{port}"
            })
        else:
            logger.info({
                "message": "I am the first node, skipping connection",
                "port": port
            })

    def start_socket_communication(self, node):
        self.node = node
        self.start()
        self.peer_discovery_handler.start()
        self.connect_to_first_node()

    def inbound_node_connected(self, connected_node):
        self.peer_discovery_handler.handshake(connected_node)

    def outbound_node_connected(self, connected_node):
        self.peer_discovery_handler.handshake(connected_node)

    def node_message(self, connected_node, message):
        # Batch message processing to reduce CPU overhead
        if not hasattr(self, '_message_batch'):
            self._message_batch = []
            self._last_batch_process = time.time()
        
        # Add to batch
        self._message_batch.append((connected_node, message))
        
        # Process batch every 0.5 seconds or when batch reaches 10 messages
        current_time = time.time()
        batch_ready = (len(self._message_batch) >= 10 or 
                      current_time - self._last_batch_process >= 0.5)
        
        if batch_ready:
            self._process_message_batch()
            self._message_batch = []
            self._last_batch_process = current_time
    
    def _process_message_batch(self):
        # Process messages in batch for efficiency
        for connected_node, message in self._message_batch:
            try:
                message = BlockchainUtils.decode(json.dumps(message))
                
                # Message deduplication for discovery messages
                if message.message_type == "DISCOVERY" and hasattr(message, 'message_id'):
                    if message.message_id in self._processed_messages:
                        continue  # Skip duplicate message
                    self._processed_messages[message.message_id] = time.time()
                
                # Clean up old message cache periodically
                current_time = time.time()
                if current_time - self._last_cache_cleanup > 300:  # Every 5 minutes
                    self._cleanup_message_cache()
                    self._last_cache_cleanup = current_time
                
                if message.message_type == "DISCOVERY":
                    # Discovery messages are frequent - batch process them
                    self.peer_discovery_handler.handle_message(message)
                elif message.message_type == "TRANSACTION":
                    # Legacy direct transaction broadcast (deprecated)
                    transaction = message.data
                    self.node.handle_transaction(transaction)
                elif message.message_type == "INV":
                    # Bitcoin-style inventory announcement
                    self.node.handle_inventory(connected_node, message.data)
                elif message.message_type == "GETDATA":
                    # Request for specific transaction/block data
                    self.node.handle_getdata(connected_node, message.data)
                elif message.message_type == "TX":
                    # Transaction data response
                    self.node.handle_transaction_data(message.data)
                elif message.message_type == "BLOCK":
                    # Legacy direct block broadcast
                    block = message.data
                    self.node.handle_block(block)
                elif message.message_type == "BLOCK_DATA":
                    # Block data response
                    self.node.handle_block_data(message.data)
                elif message.message_type == "BLOCKCHAINREQUEST":
                    self.node.handle_blockchain_request(connected_node)
                elif message.message_type == "BLOCKCHAIN":
                    blockchain = message.data
                    self.node.handle_blockchain(blockchain)
                elif message.message_type == "PING":
                    # Respond to ping with pong
                    self.node.handle_ping(connected_node, message.data)
                elif message.message_type == "PONG":
                    # Handle pong response
                    self.node.handle_pong(connected_node, message.data)
            except Exception as e:
                # Silently handle decode errors to prevent log spam
                pass
    
    def _cleanup_message_cache(self):
        """Remove old message IDs from cache to prevent memory leaks"""
        current_time = time.time()
        old_messages = [msg_id for msg_id, timestamp in self._processed_messages.items() 
                       if current_time - timestamp > 600]  # Remove messages older than 10 minutes
        for msg_id in old_messages:
            del self._processed_messages[msg_id]

    def send(self, receiver, message):
        self.send_to_node(receiver, message)

    def broadcast(self, message):
        self.send_to_nodes(message)
