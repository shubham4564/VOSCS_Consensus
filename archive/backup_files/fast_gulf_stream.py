"""
Fast Gulf Stream - Ultra-fast UDP transaction forwarding to current and next leaders.

This module implements the Fast Gulf Stream system that forwards transactions
directly to current and next leaders via UDP to minimize leader transition delays.
Inspired by Solana's Gulf Stream architecture for high-performance transaction processing.
"""

import asyncio
import socket
import json
import time
import threading
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FastGulfStreamForwarder:
    """
    Fast Gulf Stream transaction forwarder using UDP for minimal latency.
    
    This class implements ultra-fast transaction forwarding to both current and next
    leaders to minimize delays during leader transitions. Transactions are sent via
    UDP for maximum speed and minimal network overhead.
    """
    
    def __init__(self, node_public_key: str, leader_schedule, port_base: int = 15000):
        """
        Initialize the Fast Gulf Stream forwarder.
        
        Args:
            node_public_key: Public key identifier for this node
            leader_schedule: Reference to the leader schedule system
            port_base: Base port for Fast Gulf Stream UDP (default: 15000)
        """
        self.node_public_key = node_public_key
        self.leader_schedule = leader_schedule
        self.port_base = port_base
        
        # UDP configuration
        self.udp_port_base = port_base  # Base port for Fast Gulf Stream UDP
        self.udp_port_range = 1000  # Port range (15000-15999)
        self.udp_server_port = None
        self.udp_socket = None
        self.server_thread = None
        self.is_running = False
        
        # Node registry for UDP communication
        self.node_registry: Dict[str, Tuple[str, int]] = {}
        
        # Performance metrics
        self.metrics = {
            'performance': {
                'total_sent': 0,
                'successful_sends': 0,
                'failed_sends': 0,
                'success_rate': 0.0,
                'last_forward_time_ms': 0.0,
                'avg_forward_time_ms': 0.0,
                'forward_times': []
            },
            'leader_forwarding': {
                'current_leader_forwards': 0,
                'next_leader_forwards': 0,
                'leader_lookup_failures': 0
            },
            'reception': {
                'udp_receives': 0,
                'processed_transactions': 0,
                'invalid_transactions': 0
            }
        }
        
        # Transaction buffer for Fast Gulf Stream
        self.fast_gulf_stream_transactions: List[Dict] = []
        
        logger.info(f"Fast Gulf Stream Forwarder initialized for node {self.node_public_key[:20]}...")
    
    def start_udp_server(self) -> bool:
        """
        Start the UDP server for receiving forwarded transactions.
        
        Returns:
            bool: True if server started successfully, False otherwise
        """
        try:
            # Find an available port in the range
            for port_offset in range(self.udp_port_range):
                candidate_port = self.udp_port_base + port_offset
                try:
                    test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    test_socket.bind(('localhost', candidate_port))
                    test_socket.close()
                    
                    # Port is available
                    self.udp_server_port = candidate_port
                    break
                except OSError:
                    continue
            
            if not self.udp_server_port:
                logger.error("No available UDP ports in Fast Gulf Stream range")
                return False
            
            # Create UDP socket
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.bind(('localhost', self.udp_server_port))
            self.udp_socket.settimeout(1.0)  # 1 second timeout for shutdown
            
            # Start server thread
            self.is_running = True
            self.server_thread = threading.Thread(target=self._udp_server_loop, daemon=True)
            self.server_thread.start()
            
            logger.info(f"Fast Gulf Stream UDP server started on port {self.udp_server_port}")
            
            # Register this node in the registry
            self._register_node(self.node_public_key, 'localhost', self.udp_server_port)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Fast Gulf Stream UDP server: {e}")
            return False
    
    def stop_udp_server(self):
        """Stop the UDP server and cleanup resources."""
        self.is_running = False
        
        if hasattr(self, 'server_thread') and self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=2.0)
        
        if hasattr(self, 'udp_socket') and self.udp_socket:
            try:
                self.udp_socket.close()
            except:
                pass
            self.udp_socket = None
        
        logger.info("Fast Gulf Stream UDP server stopped")
    
    def _udp_server_loop(self):
        """Main UDP server loop for receiving forwarded transactions."""
        logger.info("Fast Gulf Stream UDP server loop started")
        
        while self.is_running:
            try:
                # Receive UDP packet
                data, addr = self.udp_socket.recvfrom(4096)
                self.metrics['reception']['udp_receives'] += 1
                
                # Parse transaction data
                try:
                    transaction_data = json.loads(data.decode('utf-8'))
                    
                    # Validate transaction structure
                    if self._validate_transaction(transaction_data):
                        # Add to Fast Gulf Stream transaction pool
                        self.fast_gulf_stream_transactions.append({
                            'transaction': transaction_data,
                            'received_at': time.time(),
                            'source': 'fast_gulf_stream_udp',
                            'priority': 'high'
                        })
                        
                        self.metrics['reception']['processed_transactions'] += 1
                        logger.debug(f"Fast Gulf Stream: Received transaction from {addr}")
                    else:
                        self.metrics['reception']['invalid_transactions'] += 1
                        logger.warning(f"Fast Gulf Stream: Invalid transaction from {addr}")
                        
                except json.JSONDecodeError as e:
                    self.metrics['reception']['invalid_transactions'] += 1
                    logger.warning(f"Fast Gulf Stream: JSON decode error from {addr}: {e}")
                
            except socket.timeout:
                # Timeout is expected for shutdown checks
                continue
            except Exception as e:
                if self.is_running:  # Only log if we're supposed to be running
                    logger.error(f"Fast Gulf Stream UDP server error: {e}")
    
    def _validate_transaction(self, transaction_data: Dict) -> bool:
        """
        Validate a transaction received via Fast Gulf Stream.
        
        Args:
            transaction_data: Transaction data to validate
            
        Returns:
            bool: True if transaction is valid, False otherwise
        """
        required_fields = ['sender_public_key', 'receiver_public_key', 'amount', 'transaction_type']
        
        try:
            return all(field in transaction_data for field in required_fields)
        except:
            return False
    
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
    
    def _register_node(self, node_id: str, host: str, port: int):
        """Register a node in the Fast Gulf Stream registry."""
        self.node_registry[node_id] = (host, port)
        logger.debug(f"Registered node {node_id} at {host}:{port}")
    
    def _get_node_address(self, node_id: str) -> Optional[Tuple[str, int]]:
        """Get the UDP address for a node."""
        return self.node_registry.get(node_id)
    
    def forward_transaction_fast(self, transaction_data: Dict) -> Dict:
        """
        Forward a transaction via Fast Gulf Stream UDP to current and next leaders.
        
        Args:
            transaction_data: Transaction to forward
            
        Returns:
            Dict: Results of the forwarding operation
        """
        start_time = time.time()
        current_leader_sent = False
        next_leader_sent = False
        
        try:
            # Get current and next leaders
            current_leader = self._get_current_leader()
            next_leader = self._get_next_leader()
            
            # Forward to current leader
            if current_leader and current_leader != self.node_public_key:
                success = self._send_udp_transaction(current_leader, transaction_data)
                if success:
                    self.metrics['leader_forwarding']['current_leader_forwards'] += 1
                    current_leader_sent = True
                    logger.debug(f"Fast Gulf Stream: Forwarded to current leader {current_leader}")
            
            # Forward to next leader (for transition preparation)
            if next_leader and next_leader != self.node_public_key and next_leader != current_leader:
                success = self._send_udp_transaction(next_leader, transaction_data)
                if success:
                    self.metrics['leader_forwarding']['next_leader_forwards'] += 1
                    next_leader_sent = True
                    logger.debug(f"Fast Gulf Stream: Forwarded to next leader {next_leader}")
            
            # Update performance metrics
            forward_time_ms = (time.time() - start_time) * 1000
            forwarding_success = current_leader_sent or next_leader_sent
            self._update_performance_metrics(forward_time_ms, forwarding_success)
            
            return {
                'current_leader_sent': current_leader_sent,
                'next_leader_sent': next_leader_sent,
                'forward_time_ms': forward_time_ms,
                'success': forwarding_success
            }
            
        except Exception as e:
            logger.error(f"Fast Gulf Stream forward error: {e}")
            self.metrics['performance']['failed_sends'] += 1
            return False
    
    def _get_current_leader(self) -> Optional[str]:
        """Get the current leader node ID."""
        try:
            current_leader_info = self.leader_schedule.get_current_leader()
            if current_leader_info and 'node_id' in current_leader_info:
                return current_leader_info['node_id']
        except Exception as e:
            logger.warning(f"Fast Gulf Stream: Failed to get current leader: {e}")
            self.metrics['leader_forwarding']['leader_lookup_failures'] += 1
        return None
    
    def _get_next_leader(self) -> Optional[str]:
        """Get the next leader node ID."""
        try:
            # Calculate next slot
            current_leader_info = self.leader_schedule.get_current_leader()
            if current_leader_info and 'current_slot' in current_leader_info:
                next_slot = current_leader_info['current_slot'] + 1
                next_leader_info = self.leader_schedule.get_leader_for_slot(next_slot)
                if next_leader_info and 'node_id' in next_leader_info:
                    return next_leader_info['node_id']
        except Exception as e:
            logger.warning(f"Fast Gulf Stream: Failed to get next leader: {e}")
            self.metrics['leader_forwarding']['leader_lookup_failures'] += 1
        return None
    
    def _send_udp_transaction(self, target_node_id: str, transaction_data: Dict) -> bool:
        """
        Send a transaction via UDP to a specific node.
        
        Args:
            target_node_id: ID of the target node
            transaction_data: Transaction to send
            
        Returns:
            bool: True if send was successful, False otherwise
        """
        try:
            # Get target node address
            node_address = self._get_node_address(target_node_id)
            if not node_address:
                # Try to infer address from node_id pattern
                node_address = self._infer_node_address(target_node_id)
                
            if not node_address:
                logger.warning(f"Fast Gulf Stream: No address for node {target_node_id}")
                return False
            
            host, port = node_address
            
            # Serialize transaction
            message = json.dumps(transaction_data).encode('utf-8')
            
            # Send UDP packet
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(0.1)  # 100ms timeout for ultra-fast forwarding
                sock.sendto(message, (host, port))
            
            return True
            
        except Exception as e:
            logger.warning(f"Fast Gulf Stream: Failed to send to {target_node_id}: {e}")
            return False
    
    def _infer_node_address(self, node_id: str) -> Optional[Tuple[str, int]]:
        """
        Infer node UDP address from node_id patterns.
        
        Args:
            node_id: Node identifier
            
        Returns:
            Tuple of (host, port) or None if cannot infer
        """
        try:
            # Pattern: node_<api_port> -> UDP port is 15000 + (api_port - 11000)
            if node_id.startswith('node_'):
                api_port_str = node_id.replace('node_', '')
                api_port = int(api_port_str)
                udp_port = 15000 + (api_port - 11000)
                
                if 15000 <= udp_port < 16000:  # Valid range
                    self._register_node(node_id, 'localhost', udp_port)
                    return ('localhost', udp_port)
                    
        except ValueError:
            pass
        
        return None
    
    def _update_performance_metrics(self, forward_time_ms: float, success: bool):
        """Update performance metrics after a forwarding attempt."""
        self.metrics['performance']['total_sent'] += 1
        self.metrics['performance']['last_forward_time_ms'] = forward_time_ms
        
        if success:
            self.metrics['performance']['successful_sends'] += 1
        else:
            self.metrics['performance']['failed_sends'] += 1
        
        # Update success rate
        total = self.metrics['performance']['total_sent']
        successful = self.metrics['performance']['successful_sends']
        self.metrics['performance']['success_rate'] = (successful / total) * 100 if total > 0 else 0
        
        # Update average forward time
        self.metrics['performance']['forward_times'].append(forward_time_ms)
        if len(self.metrics['performance']['forward_times']) > 100:
            self.metrics['performance']['forward_times'] = self.metrics['performance']['forward_times'][-100:]
        
        times = self.metrics['performance']['forward_times']
        self.metrics['performance']['avg_forward_time_ms'] = sum(times) / len(times) if times else 0
    
    def get_fast_gulf_stream_transactions(self) -> List[Dict]:
        """
        Get transactions from the Fast Gulf Stream pool.
        
        Returns:
            List of transactions received via Fast Gulf Stream
        """
        transactions = self.fast_gulf_stream_transactions.copy()
        self.fast_gulf_stream_transactions.clear()  # Clear after retrieval
        return transactions
    
    def get_transactions_for_leader(self, leader_public_key: str) -> List[Dict]:
        """
        Get transactions intended for a specific leader.
        
        Args:
            leader_public_key: Public key of the leader to get transactions for
            
        Returns:
            List of transactions intended for the specified leader
        """
        # For Fast Gulf Stream, return all available transactions
        # In the future, this could be filtered by intended leader
        return self.get_fast_gulf_stream_transactions()
    
    def get_metrics(self) -> Dict:
        """
        Get Fast Gulf Stream performance metrics.
        
        Returns:
            Dictionary containing performance and operational metrics
        """
        return {
            'fast_gulf_stream': {
                **self.metrics,
                'udp_server_port': self.udp_server_port,
                'is_running': self.is_running,
                'registered_nodes': len(self.node_registry),
                'active_transactions': len(self.fast_gulf_stream_transactions)
            }
        }
    
    def __del__(self):
        """Cleanup on destruction."""
        try:
            self.stop_udp_server()
        except AttributeError:
            # Handle case where __init__ failed before server_thread was created
            pass
