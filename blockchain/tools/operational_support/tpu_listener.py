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

import socket
import threading
import time
import json
from typing import Callable, Optional
from blockchain.utils.logger import logger
from blockchain.utils.helpers import BlockchainUtils


class TPUListener:
    """
    Solana-style TPU (Transaction Processing Unit) Listener
    
    Leaders listen on their TPU port for incoming transactions via UDP.
    This enables immediate transaction processing without polling or checking.
    """
    
    def __init__(self, ip: str, tpu_port: int, transaction_handler: Callable):
        self.ip = ip
        self.tpu_port = tpu_port
        self.transaction_handler = transaction_handler
        self.socket = None
        self.running = False
        self.listener_thread = None
        
        # Performance metrics
        self.stats = {
            "transactions_received": 0,
            "invalid_packets": 0,
            "processing_errors": 0,
            "bytes_received": 0,
            "uptime_start": time.time()
        }
        
    def start_listening(self):
        """Start listening on TPU port for incoming transactions"""
        try:
            # Create UDP socket for TPU
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.ip, self.tpu_port))
            self.socket.settimeout(1.0)  # 1 second timeout for graceful shutdown
            
            self.running = True
            
            # Start listener thread
            self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.listener_thread.start()
            
            logger.info({
                "message": "TPU Listener started - ready to receive transactions",
                "ip": self.ip,
                "tpu_port": self.tpu_port,
                "protocol": "UDP",
                "buffer_size": "64KB"
            })
            
        except Exception as e:
            logger.error(f"Failed to start TPU listener on {self.ip}:{self.tpu_port}: {e}")
            self.running = False
            
    def stop_listening(self):
        """Stop TPU listener gracefully"""
        self.running = False
        
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=5.0)
            
        if self.socket:
            self.socket.close()
            
        logger.info({
            "message": "TPU Listener stopped",
            "final_stats": self.get_stats()
        })
    
    def _listen_loop(self):
        """Main listening loop - runs in background thread"""
        buffer_size = 65536  # 64KB buffer for transaction packets
        
        logger.info(f"TPU listening loop started on {self.ip}:{self.tpu_port}")
        
        while self.running:
            try:
                # Receive UDP packet
                data, address = self.socket.recvfrom(buffer_size)
                self.stats["bytes_received"] += len(data)
                
                # Process transaction packet immediately
                self._process_transaction_packet(data, address)
                
            except socket.timeout:
                # Timeout is expected - allows graceful shutdown check
                continue
            except Exception as e:
                if self.running:  # Only log errors if we're supposed to be running
                    logger.warning(f"TPU listener error: {e}")
                    self.stats["processing_errors"] += 1
                continue
    
    def _process_transaction_packet(self, data: bytes, address: tuple):
        """Process incoming transaction packet from UDP"""
        try:
            # Decode transaction from UDP packet
            packet_str = data.decode('utf-8')
            packet_data = json.loads(packet_str)
            
            # Validate packet structure
            if not self._validate_transaction_packet(packet_data):
                self.stats["invalid_packets"] += 1
                return
                
            # Extract transaction
            transaction_data = packet_data.get('transaction')
            if not transaction_data:
                self.stats["invalid_packets"] += 1
                return
                
            # Decode transaction object
            transaction = BlockchainUtils.decode(transaction_data)
            
            # IMMEDIATE PROCESSING: Call transaction handler immediately
            self.transaction_handler(transaction, from_tpu=True, source_address=address)
            
            self.stats["transactions_received"] += 1
            
            logger.info({
                "message": "TPU received transaction - processing immediately",
                "transaction_id": transaction.id[:8] if hasattr(transaction, 'id') else 'unknown',
                "source_ip": address[0],
                "source_port": address[1],
                "packet_size": len(data),
                "processing": "immediate"
            })
            
        except json.JSONDecodeError:
            logger.warning(f"TPU received invalid JSON packet from {address}")
            self.stats["invalid_packets"] += 1
        except Exception as e:
            logger.warning(f"TPU packet processing error from {address}: {e}")
            self.stats["processing_errors"] += 1
    
    def _validate_transaction_packet(self, packet_data: dict) -> bool:
        """Validate incoming transaction packet structure"""
        required_fields = ['transaction', 'timestamp', 'source_node']
        
        for field in required_fields:
            if field not in packet_data:
                logger.debug(f"TPU packet missing required field: {field}")
                return False
                
        return True
    
    def get_stats(self) -> dict:
        """Get TPU listener performance statistics"""
        uptime = time.time() - self.stats["uptime_start"]
        
        return {
            "tpu_listener": {
                "running": self.running,
                "ip": self.ip,
                "port": self.tpu_port,
                "uptime_seconds": uptime,
                "transactions_received": self.stats["transactions_received"],
                "invalid_packets": self.stats["invalid_packets"],
                "processing_errors": self.stats["processing_errors"],
                "bytes_received": self.stats["bytes_received"],
                "avg_transactions_per_second": self.stats["transactions_received"] / max(uptime, 1)
            }
        }
    
    def is_listening(self) -> bool:
        """Check if TPU listener is active"""
        return self.running and self.socket is not None


class TPUSender:
    """
    Solana-style TPU Sender
    
    Sends transactions directly to leader TPU ports via UDP.
    This enables immediate transaction delivery without network delays.
    """
    
    def __init__(self):
        self.socket = None
        self.stats = {
            "transactions_sent": 0,
            "send_errors": 0,
            "bytes_sent": 0,
            "leaders_contacted": 0
        }
        
        # Initialize UDP socket for sending
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            logger.info("TPU Sender initialized - ready to send transactions to leaders")
        except Exception as e:
            logger.error(f"Failed to initialize TPU sender: {e}")
    
    def send_transaction_to_leader(self, transaction, leader_ip: str, leader_tpu_port: int, source_node_id: str) -> bool:
        """
        Send transaction directly to leader's TPU port via UDP
        
        Args:
            transaction: Transaction object to send
            leader_ip: IP address of the leader
            leader_tpu_port: TPU port of the leader
            source_node_id: ID of the sending node
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            if not self.socket:
                logger.warning("TPU sender not initialized")
                return False
            
            # Create transaction packet
            packet_data = {
                'transaction': BlockchainUtils.encode(transaction),
                'timestamp': time.time(),
                'source_node': source_node_id,
                'packet_type': 'gulf_stream_forward'
            }
            
            # Serialize packet
            packet_str = json.dumps(packet_data, separators=(',', ':'))
            packet_bytes = packet_str.encode('utf-8')
            
            # Send UDP packet to leader's TPU port
            self.socket.sendto(packet_bytes, (leader_ip, leader_tpu_port))
            
            self.stats["transactions_sent"] += 1
            self.stats["bytes_sent"] += len(packet_bytes)
            
            logger.info({
                "message": "Transaction sent to leader TPU port",
                "transaction_id": transaction.id[:8] if hasattr(transaction, 'id') else 'unknown',
                "leader_ip": leader_ip,
                "leader_tpu_port": leader_tpu_port,
                "packet_size": len(packet_bytes),
                "transport": "UDP"
            })
            
            return True
            
        except Exception as e:
            logger.warning(f"Failed to send transaction to {leader_ip}:{leader_tpu_port}: {e}")
            self.stats["send_errors"] += 1
            return False
    
    def send_transaction_to_multiple_leaders(self, transaction, leaders: list, source_node_id: str) -> dict:
        """
        Send transaction to multiple leaders (Gulf Stream forwarding)
        
        Args:
            transaction: Transaction to send
            leaders: List of (leader_ip, leader_tpu_port) tuples
            source_node_id: ID of the sending node
            
        Returns:
            dict: Results of sending to each leader
        """
        results = {
            "successful_sends": 0,
            "failed_sends": 0,
            "leaders_contacted": [],
            "errors": []
        }
        
        for leader_ip, leader_tpu_port in leaders:
            success = self.send_transaction_to_leader(
                transaction, leader_ip, leader_tpu_port, source_node_id
            )
            
            if success:
                results["successful_sends"] += 1
                results["leaders_contacted"].append(f"{leader_ip}:{leader_tpu_port}")
            else:
                results["failed_sends"] += 1
                results["errors"].append(f"Failed to reach {leader_ip}:{leader_tpu_port}")
        
        self.stats["leaders_contacted"] += len(leaders)
        
        logger.info({
            "message": "Gulf Stream TPU forwarding completed",
            "transaction_id": transaction.id[:8] if hasattr(transaction, 'id') else 'unknown',
            "successful_sends": results["successful_sends"],
            "failed_sends": results["failed_sends"],
            "total_leaders": len(leaders)
        })
        
        return results
    
    def get_stats(self) -> dict:
        """Get TPU sender statistics"""
        return {
            "tpu_sender": self.stats.copy()
        }
    
    def close(self):
        """Close TPU sender socket"""
        if self.socket:
            self.socket.close()
            self.socket = None
            logger.info("TPU sender closed")
