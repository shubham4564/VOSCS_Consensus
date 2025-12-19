import socket
import json
import time
import threading
from typing import List, Dict, Optional, Tuple
from blockchain.utils.logger import logger
from blockchain.utils.helpers import BlockchainUtils

class FastGulfStreamForwarder:
    """
    Fast UDP-based Gulf Stream transaction forwarding.
    
    When nodes receive transactions, they immediately forward them to:
    1. Current leader (for immediate block inclusion)
    2. Next scheduled leader (for leader transition continuity)
    
    Uses direct UDP transfers to minimize delays during leader transitions.
    """
    
    def __init__(self, node_public_key: str, leader_schedule, port_base: int = 15000):
        self.node_public_key = node_public_key
        self.leader_schedule = leader_schedule
        self.port_base = port_base  # Base port for Gulf Stream UDP (15000-15999)
        
        # UDP socket for sending transactions
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # UDP server for receiving forwarded transactions
        self.server_port = port_base + self._get_node_index()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('localhost', self.server_port))
        
        # Transaction pools for different purposes
        self.current_leader_pool = []      # Transactions for current leader
        self.next_leader_pool = []         # Transactions for next leader
        self.received_transactions = []    # Transactions received via UDP
        
        # Node registry: public_key -> (ip, port) mapping
        self.node_registry = {}
        self._populate_node_registry()
        
        # Performance metrics
        self.forwarding_stats = {
            'total_sent': 0,
            'successful_sends': 0,
            'failed_sends': 0,
            'current_leader_forwards': 0,
            'next_leader_forwards': 0,
            'udp_receives': 0,
            'last_forward_time': 0
        }
        
        # Start UDP server thread
        self.server_running = True
        self.server_thread = threading.Thread(target=self._udp_server_loop, daemon=True)
        self.server_thread.start()
        
        logger.info(f"Fast Gulf Stream forwarder initialized on UDP port {self.server_port}")
    
    def _get_node_index(self) -> int:
        """Get node index based on public key hash for consistent port assignment"""
        import hashlib
        hash_digest = hashlib.md5(self.node_public_key.encode()).hexdigest()
        return int(hash_digest[:4], 16) % 1000  # 0-999 range
    
    def _populate_node_registry(self):
        """Populate node registry with known nodes and their UDP ports"""
        # In a real implementation, this would come from peer discovery or configuration
        # For now, we'll use the standard port mapping
        base_api_port = 11000
        for i in range(10):  # Support up to 10 nodes
            api_port = base_api_port + i
            udp_port = self.port_base + i
            node_key = f"node_{i+1}"  # Placeholder - in real implementation use actual public keys
            self.node_registry[node_key] = ('localhost', udp_port)
            
        logger.debug(f"Node registry populated with {len(self.node_registry)} entries")
    
    def register_node(self, public_key: str, ip: str, udp_port: int):
        """Register a node for Gulf Stream forwarding"""
        self.node_registry[public_key] = (ip, udp_port)
        logger.info(f"Registered node for Gulf Stream: {public_key[:20]}... at {ip}:{udp_port}")
    
    def get_transactions_for_leader(self, leader_id: str) -> List[Dict]:
        """
        Get pending transactions that should be forwarded to a specific leader.
        
        Args:
            leader_id: The public key of the leader
            
        Returns:
            List[Dict]: List of transactions for the leader
        """
        # Return transactions from pending pool for this leader
        # In a full implementation, this would filter by leader assignment
        return []
    
    def forward_transaction_fast(self, transaction) -> Dict:
        """
        Immediately forward transaction to current leader and next leader via UDP.
        
        This is the core fast forwarding function called when a transaction is received.
        """
        start_time = time.time()
        
        # Get current and next leaders
        current_leader = self.leader_schedule.get_current_leader()
        upcoming_leaders = self.leader_schedule.get_upcoming_leaders(2)  # Next 2 leaders
        next_leader = upcoming_leaders[0][1] if upcoming_leaders else None
        
        forwarding_results = {
            'transaction_id': transaction.transaction_id,
            'current_leader_sent': False,
            'next_leader_sent': False,
            'forward_time_ms': 0,
            'errors': []
        }
        
        # Serialize transaction for UDP transmission
        try:
            transaction_data = {
                'type': 'gulf_stream_transaction',
                'transaction': BlockchainUtils.encode(transaction),
                'sender_node': self.node_public_key[:20] + '...',
                'timestamp': time.time(),
                'priority': 'high'  # Gulf Stream transactions have high priority
            }
            message_bytes = json.dumps(transaction_data).encode('utf-8')
            
            if len(message_bytes) > 65507:  # UDP max payload size
                logger.error(f"Transaction too large for UDP forwarding: {len(message_bytes)} bytes")
                forwarding_results['errors'].append("Transaction exceeds UDP size limit")
                return forwarding_results
                
        except Exception as e:
            logger.error(f"Failed to serialize transaction for UDP forwarding: {e}")
            forwarding_results['errors'].append(f"Serialization error: {e}")
            return forwarding_results
        
        # Forward to current leader (highest priority)
        if current_leader and current_leader != self.node_public_key:
            try:
                sent = self._send_udp_transaction(current_leader, message_bytes, 'current_leader')
                forwarding_results['current_leader_sent'] = sent
                if sent:
                    self.forwarding_stats['current_leader_forwards'] += 1
            except Exception as e:
                error_msg = f"Failed to forward to current leader: {e}"
                forwarding_results['errors'].append(error_msg)
                logger.warning(error_msg)
        
        # Forward to next leader (for transition continuity)
        if next_leader and next_leader != self.node_public_key and next_leader != current_leader:
            try:
                sent = self._send_udp_transaction(next_leader, message_bytes, 'next_leader')
                forwarding_results['next_leader_sent'] = sent
                if sent:
                    self.forwarding_stats['next_leader_forwards'] += 1
            except Exception as e:
                error_msg = f"Failed to forward to next leader: {e}"
                forwarding_results['errors'].append(error_msg)
                logger.warning(error_msg)
        
        # Update performance metrics
        forward_time_ms = (time.time() - start_time) * 1000
        forwarding_results['forward_time_ms'] = forward_time_ms
        self.forwarding_stats['last_forward_time'] = forward_time_ms
        self.forwarding_stats['total_sent'] += 1
        
        if forwarding_results['current_leader_sent'] or forwarding_results['next_leader_sent']:
            self.forwarding_stats['successful_sends'] += 1
            logger.info(f"Fast Gulf Stream forward completed in {forward_time_ms:.2f}ms: "
                       f"current={forwarding_results['current_leader_sent']}, "
                       f"next={forwarding_results['next_leader_sent']}")
        else:
            self.forwarding_stats['failed_sends'] += 1
            logger.warning(f"Fast Gulf Stream forward failed for transaction {transaction.transaction_id}")
        
        return forwarding_results
    
    def _send_udp_transaction(self, leader_public_key: str, message_bytes: bytes, leader_type: str) -> bool:
        """Send transaction to a specific leader via UDP"""
        try:
            # Look up leader's UDP endpoint
            if leader_public_key in self.node_registry:
                ip, port = self.node_registry[leader_public_key]
            else:
                # Fallback: try to derive port from public key
                leader_index = self._get_node_index_from_key(leader_public_key)
                ip, port = 'localhost', self.port_base + leader_index
                logger.debug(f"Using derived UDP port {port} for leader {leader_public_key[:20]}...")
            
            # Send UDP packet
            self.udp_socket.sendto(message_bytes, (ip, port))
            
            logger.debug(f"UDP transaction sent to {leader_type} {leader_public_key[:20]}... at {ip}:{port}")
            return True
            
        except Exception as e:
            logger.error(f"UDP send failed to {leader_type} {leader_public_key[:20]}...: {e}")
            return False
    
    def _get_node_index_from_key(self, public_key: str) -> int:
        """Derive node index from public key for port calculation"""
        import hashlib
        hash_digest = hashlib.md5(public_key.encode()).hexdigest()
        return int(hash_digest[:4], 16) % 1000
    
    def _udp_server_loop(self):
        """UDP server loop to receive forwarded transactions"""
        logger.info(f"Gulf Stream UDP server listening on port {self.server_port}")
        
        while self.server_running:
            try:
                self.server_socket.settimeout(1.0)  # 1 second timeout for graceful shutdown
                data, addr = self.server_socket.recvfrom(65536)  # Max UDP size
                
                # Process received transaction
                self._process_received_transaction(data, addr)
                self.forwarding_stats['udp_receives'] += 1
                
            except socket.timeout:
                continue  # Normal timeout, keep listening
            except Exception as e:
                if self.server_running:  # Only log if we're still supposed to be running
                    logger.error(f"Gulf Stream UDP server error: {e}")
                    time.sleep(0.1)  # Brief pause before retrying
    
    def _process_received_transaction(self, data: bytes, addr: Tuple[str, int]):
        """Process a transaction received via UDP"""
        try:
            message = json.loads(data.decode('utf-8'))
            
            if message.get('type') != 'gulf_stream_transaction':
                logger.debug(f"Ignoring non-Gulf Stream message from {addr}")
                return
            
            # Decode transaction
            transaction_data = message.get('transaction')
            sender_node = message.get('sender_node', 'unknown')
            timestamp = message.get('timestamp', time.time())
            
            # Decode transaction object
            transaction = BlockchainUtils.decode(transaction_data)
            
            # Add to received transactions pool
            self.received_transactions.append({
                'transaction': transaction,
                'received_from': addr,
                'sender_node': sender_node,
                'received_at': time.time(),
                'original_timestamp': timestamp
            })
            
            logger.info(f"Gulf Stream transaction received from {sender_node} via UDP: "
                       f"{transaction.transaction_id[:16]}... (delay: {time.time() - timestamp:.3f}s)")
            
        except Exception as e:
            logger.error(f"Failed to process Gulf Stream UDP transaction from {addr}: {e}")
    
    def get_transactions_for_leader(self, leader_public_key: str) -> List:
        """
        Get all transactions available for a specific leader.
        Called by leaders when their slot starts.
        """
        current_leader = self.leader_schedule.get_current_leader()
        
        # If this node is the current leader, return received transactions
        if leader_public_key == current_leader:
            transactions = [item['transaction'] for item in self.received_transactions]
            
            # Clear received transactions after retrieval
            self.received_transactions.clear()
            
            logger.info(f"Leader {leader_public_key[:20]}... retrieved {len(transactions)} Gulf Stream transactions")
            return transactions
        
        return []
    
    def get_fast_forwarding_stats(self) -> Dict:
        """Get comprehensive Gulf Stream forwarding statistics"""
        current_time = time.time()
        return {
            'udp_server_port': self.server_port,
            'node_registry_size': len(self.node_registry),
            'performance': {
                'total_sent': self.forwarding_stats['total_sent'],
                'successful_sends': self.forwarding_stats['successful_sends'],
                'failed_sends': self.forwarding_stats['failed_sends'],
                'success_rate': (
                    self.forwarding_stats['successful_sends'] / 
                    max(1, self.forwarding_stats['total_sent'])
                ) * 100,
                'last_forward_time_ms': self.forwarding_stats['last_forward_time']
            },
            'leader_forwarding': {
                'current_leader_forwards': self.forwarding_stats['current_leader_forwards'],
                'next_leader_forwards': self.forwarding_stats['next_leader_forwards']
            },
            'reception': {
                'udp_receives': self.forwarding_stats['udp_receives'],
                'pending_transactions': len(self.received_transactions)
            },
            'network': {
                'registered_nodes': list(self.node_registry.keys()),
                'server_running': self.server_running
            }
        }
    
    def shutdown(self):
        """Gracefully shutdown the Gulf Stream forwarder"""
        logger.info("Shutting down Fast Gulf Stream forwarder...")
        
        self.server_running = False
        
        # Close sockets
        try:
            self.server_socket.close()
            self.udp_socket.close()
        except:
            pass
        
        # Wait for server thread to finish
        if self.server_thread.is_alive():
            self.server_thread.join(timeout=2.0)
        
        logger.info("Fast Gulf Stream forwarder shutdown complete")
    
    def get_network_status(self) -> Dict:
        """Get current network status for monitoring"""
        current_leader = self.leader_schedule.get_current_leader()
        upcoming_leaders = self.leader_schedule.get_upcoming_leaders(3)
        
        return {
            'current_leader': current_leader[:20] + '...' if current_leader else None,
            'upcoming_leaders': [
                {
                    'slot': slot,
                    'leader': leader[:20] + '...',
                    'time_until_slot': abs_time - time.time()
                }
                for slot, leader, abs_time in upcoming_leaders
            ],
            'am_current_leader': current_leader == self.node_public_key,
            'registered_for_forwarding': self.node_public_key in self.node_registry,
            'udp_endpoints': {
                'server_port': self.server_port,
                'registered_nodes': len(self.node_registry)
            }
        }
