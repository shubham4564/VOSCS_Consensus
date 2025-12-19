import socket
import json
import threading
import time
from typing import Callable, Dict, List
from blockchain.utils.logger import logger
from blockchain.utils.helpers import BlockchainUtils


class TPUListener:
    """
    Transaction Processing Unit (TPU) Listener for Leaders
    
    This implements the Solana-style TPU system where leaders listen on dedicated UDP ports
    for incoming transactions forwarded by Gulf Stream. Leaders pack ALL received transactions
    into their assigned slot, regardless of transaction count.
    """
    
    def __init__(self, node_public_key: str, tpu_port: int, transaction_handler: Callable):
        self.node_public_key = node_public_key
        self.tpu_port = tpu_port
        self.transaction_handler = transaction_handler
        
        # TPU state
        self.is_listening = False
        self.socket = None
        self.listener_thread = None
        
        # Transaction collection for current slot
        self.current_slot_transactions = []
        self.slot_transaction_lock = threading.Lock()
        
        # Performance metrics
        self.packets_received = 0
        self.transactions_received = 0
        self.invalid_packets = 0
        
        logger.info({
            "message": "TPU Listener initialized",
            "node": self.node_public_key[:20] + "...",
            "tpu_port": self.tpu_port
        })
    
    def start_listening(self):
        """Start listening for incoming transactions on TPU port"""
        if self.is_listening:
            logger.warning("TPU listener already running")
            return
        
        try:
            # Create UDP socket for TPU
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('localhost', self.tpu_port))
            self.socket.settimeout(1.0)  # Non-blocking with timeout
            
            self.is_listening = True
            
            # Start listener thread
            self.listener_thread = threading.Thread(target=self._listen_for_transactions, daemon=True)
            self.listener_thread.start()
            
            logger.info({
                "message": "TPU listener started",
                "node": self.node_public_key[:20] + "...",
                "tpu_port": self.tpu_port,
                "status": "listening"
            })
            
        except Exception as e:
            logger.error({
                "message": "Failed to start TPU listener",
                "node": self.node_public_key[:20] + "...",
                "tpu_port": self.tpu_port,
                "error": str(e)
            })
            self.is_listening = False
    
    def stop_listening(self):
        """Stop the TPU listener"""
        self.is_listening = False
        
        if self.socket:
            self.socket.close()
            self.socket = None
        
        if self.listener_thread:
            self.listener_thread.join(timeout=2.0)
        
        logger.info({
            "message": "TPU listener stopped",
            "node": self.node_public_key[:20] + "...",
            "tpu_port": self.tpu_port
        })
    
    def _listen_for_transactions(self):
        """Main listening loop for TPU transactions"""
        logger.info({
            "message": "TPU listener thread started",
            "node": self.node_public_key[:20] + "...",
            "tpu_port": self.tpu_port
        })
        
        while self.is_listening:
            try:
                # Receive UDP packet
                data, addr = self.socket.recvfrom(65536)  # Max UDP packet size
                self.packets_received += 1
                
                # Parse transaction packet
                self._process_transaction_packet(data, addr)
                
            except socket.timeout:
                # Normal timeout, continue listening
                continue
            except Exception as e:
                if self.is_listening:  # Only log if we're still supposed to be listening
                    logger.error({
                        "message": "TPU listener error",
                        "node": self.node_public_key[:20] + "...",
                        "error": str(e)
                    })
        
        logger.info({
            "message": "TPU listener thread terminated",
            "node": self.node_public_key[:20] + "...",
            "packets_received": self.packets_received,
            "transactions_received": self.transactions_received
        })
    
    def _process_transaction_packet(self, data: bytes, addr: tuple):
        """Process incoming transaction packet from Gulf Stream"""
        try:
            # Decode JSON packet
            packet = json.loads(data.decode('utf-8'))
            
            # Validate packet structure
            if not self._validate_packet(packet):
                self.invalid_packets += 1
                return
            
            # Extract transaction data
            transaction_data = packet.get('transaction')
            source_node = packet.get('source_node', 'unknown')
            packet_id = packet.get('packet_id', 'unknown')
            
            # Decode transaction
            transaction = BlockchainUtils.decode(transaction_data)
            
            # Add to current slot transaction collection
            with self.slot_transaction_lock:
                self.current_slot_transactions.append({
                    'transaction': transaction,
                    'source_node': source_node,
                    'packet_id': packet_id,
                    'received_time': time.time(),
                    'source_addr': addr
                })
            
            self.transactions_received += 1
            
            # Handle transaction immediately (leader must pack ALL transactions)
            self.transaction_handler(transaction, from_tpu=True)
            
            logger.debug({
                "message": "TPU transaction received",
                "node": self.node_public_key[:20] + "...",
                "tx_id": transaction.id[:16] + "...",
                "source": source_node[:16] + "...",
                "packet_id": packet_id
            })
            
        except json.JSONDecodeError:
            logger.warning({
                "message": "Invalid JSON in TPU packet",
                "node": self.node_public_key[:20] + "...",
                "source_addr": addr
            })
            self.invalid_packets += 1
        except Exception as e:
            logger.error({
                "message": "Error processing TPU packet",
                "node": self.node_public_key[:20] + "...",
                "error": str(e),
                "source_addr": addr
            })
            self.invalid_packets += 1
    
    def _validate_packet(self, packet: dict) -> bool:
        """Validate Gulf Stream transaction packet"""
        required_fields = ['transaction', 'source_node', 'packet_id', 'timestamp']
        
        for field in required_fields:
            if field not in packet:
                logger.warning({
                    "message": "Missing required field in TPU packet",
                    "node": self.node_public_key[:20] + "...",
                    "missing_field": field
                })
                return False
        
        return True
    
    def get_slot_transactions(self) -> List[Dict]:
        """
        Get all transactions received for the current slot.
        Leader MUST pack ALL transactions regardless of count.
        """
        with self.slot_transaction_lock:
            transactions = self.current_slot_transactions.copy()
            return transactions
    
    def clear_slot_transactions(self):
        """Clear transaction collection for new slot"""
        with self.slot_transaction_lock:
            self.current_slot_transactions.clear()
            
        logger.debug({
            "message": "TPU slot transactions cleared",
            "node": self.node_public_key[:20] + "..."
        })
    
    def get_tpu_metrics(self) -> Dict:
        """Get TPU performance metrics"""
        with self.slot_transaction_lock:
            current_slot_count = len(self.current_slot_transactions)
        
        return {
            "tpu_port": self.tpu_port,
            "is_listening": self.is_listening,
            "packets_received": self.packets_received,
            "transactions_received": self.transactions_received,
            "invalid_packets": self.invalid_packets,
            "current_slot_transactions": current_slot_count,
            "packet_success_rate": (
                (self.packets_received - self.invalid_packets) / max(1, self.packets_received) * 100
            )
        }
    
    def send_transaction_to_tpu(self, target_tpu_port: int, transaction_data: str, source_node: str) -> bool:
        """
        Send transaction to another leader's TPU port via Gulf Stream.
        This is used by non-leaders to forward transactions to upcoming leaders.
        """
        try:
            # Create Gulf Stream packet
            packet = {
                'transaction': transaction_data,
                'source_node': source_node,
                'packet_id': f"{source_node}_{int(time.time() * 1000000)}",  # Microsecond precision
                'timestamp': time.time(),
                'gulf_stream_version': '1.0'
            }
            
            # Send UDP packet to target TPU
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(json.dumps(packet).encode(), ('localhost', target_tpu_port))
            
            logger.debug({
                "message": "Transaction forwarded to TPU",
                "source": source_node[:16] + "...",
                "target_tpu_port": target_tpu_port,
                "packet_id": packet['packet_id']
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "message": "Failed to forward transaction to TPU",
                "source": source_node[:16] + "...",
                "target_tpu_port": target_tpu_port,
                "error": str(e)
            })
            return False


class TPUManager:
    """
    Manages TPU listeners across the blockchain network.
    Handles TPU lifecycle and Gulf Stream forwarding coordination.
    """
    
    def __init__(self):
        self.tpu_listeners = {}  # node_public_key -> TPUListener
        self.active_leaders = set()  # Currently active leader public keys
        
    def register_tpu_listener(self, node_public_key: str, tpu_port: int, transaction_handler: Callable):
        """Register a new TPU listener for a node"""
        if node_public_key in self.tpu_listeners:
            logger.warning(f"TPU listener already registered for node {node_public_key[:20]}...")
            return
        
        tpu_listener = TPUListener(node_public_key, tpu_port, transaction_handler)
        tpu_listener.start_listening()
        
        self.tpu_listeners[node_public_key] = tpu_listener
        
        logger.info({
            "message": "TPU listener registered",
            "node": node_public_key[:20] + "...",
            "tpu_port": tpu_port,
            "total_listeners": len(self.tpu_listeners)
        })
    
    def unregister_tpu_listener(self, node_public_key: str):
        """Unregister and stop TPU listener for a node"""
        if node_public_key in self.tpu_listeners:
            self.tpu_listeners[node_public_key].stop_listening()
            del self.tpu_listeners[node_public_key]
            
            logger.info({
                "message": "TPU listener unregistered",
                "node": node_public_key[:20] + "...",
                "remaining_listeners": len(self.tpu_listeners)
            })
    
    def forward_transaction_to_leaders(self, transaction_data: str, source_node: str, target_leaders: List[Dict]):
        """
        Forward transaction to multiple leaders via their TPU ports.
        Implements Gulf Stream forwarding with minimum 200 slot buffer.
        """
        successful_forwards = 0
        
        for leader_info in target_leaders:
            leader_key = leader_info['leader']
            tpu_port = leader_info['tpu_port']
            
            # Only forward if leader has TPU listener
            if leader_key in self.tpu_listeners:
                success = self.tpu_listeners[leader_key].send_transaction_to_tpu(
                    tpu_port, transaction_data, source_node
                )
                if success:
                    successful_forwards += 1
        
        logger.info({
            "message": "Gulf Stream transaction forwarding complete",
            "source": source_node[:16] + "...",
            "target_leaders": len(target_leaders),
            "successful_forwards": successful_forwards,
            "success_rate": f"{successful_forwards}/{len(target_leaders)}"
        })
        
        return successful_forwards
    
    def get_network_tpu_metrics(self) -> Dict:
        """Get TPU metrics for the entire network"""
        metrics = {
            "total_tpu_listeners": len(self.tpu_listeners),
            "active_leaders": len(self.active_leaders),
            "listener_details": {}
        }
        
        for node_key, listener in self.tpu_listeners.items():
            metrics["listener_details"][node_key[:20] + "..."] = listener.get_tpu_metrics()
        
        return metrics
