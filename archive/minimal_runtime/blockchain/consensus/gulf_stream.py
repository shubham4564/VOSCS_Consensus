import time
import hashlib
import socket
import json
from typing import List, Dict, Optional, Set
from collections import defaultdict
from blockchain.utils.logger import logger


class GulfStreamProcessor:
    """
    Solana-style Gulf Stream protocol implementation.
    Forwards transactions directly to current and upcoming leaders instead of using mempool.
    """
    
    def __init__(self, leader_schedule, node_public_key: str):
        self.leader_schedule = leader_schedule
        self.node_public_key = node_public_key
        
        # Gulf Stream Configuration - Updated for 200-slot minimum buffer
        self.max_forwarding_slots = 200  # Minimum 200 slots ahead for proper buffering
        self.min_slot_buffer = 200  # Must maintain at least 200 slots between current and first forwarded slot
        
        # Transaction tracking
        self.pending_transactions_by_block_proposer = {}
        self.tracked_transactions = {}
        self.transaction_lifetime_seconds = 90  # 200 slots * 0.45s = 90 seconds
        
        # Performance metrics
        self.gulf_stream_stats = {
            "transactions_forwarded": 0,
            "block_proposers_contacted": 0,
            "tpu_transmissions_successful": 0,
            "tpu_transmissions_failed": 0,
            "forwarding_errors": 0
        }
        
        logger.info({
            "message": "Gulf Stream processor initialized with TPU integration",
            "node": self.node_public_key[:20] + "...",
            "max_forwarding_slots": self.max_forwarding_slots,
            "min_slot_buffer": self.min_slot_buffer,
            "transaction_lifetime": self.transaction_lifetime_seconds
        })
    
    def process_transaction(self, transaction, source_node_id: str = None) -> Dict:
        """
        Process a transaction using Gulf Stream protocol.
        Returns forwarding results and next steps.
        """
        tx_hash = self._calculate_transaction_hash(transaction)
        current_time = time.time()
        
        # Check if transaction is already being processed
        if tx_hash in self.transaction_timestamps:
            self.stats["cache_hits"] += 1
            return {
                "status": "already_processed",
                "tx_hash": tx_hash,
                "message": "Transaction already in Gulf Stream pipeline"
            }
        
        # Validate transaction lifetime (Recent Blockhash equivalent)
        if not self._validate_transaction_freshness(transaction):
            return {
                "status": "expired",
                "tx_hash": tx_hash,
                "message": "Transaction blockhash expired"
            }
        
        # Get current and upcoming leaders (FIXED: limit to only 3 upcoming leaders)
        current_leader = self.leader_schedule.get_current_leader()
        upcoming_leaders = self.leader_schedule.get_upcoming_leaders(3)  # Only get next 3 leaders, not 200!
        
        if not current_leader:
            return {
                "status": "no_leader",
                "tx_hash": tx_hash,
                "message": "No current leader available"
            }
        
        # Record transaction
        self.transaction_timestamps[tx_hash] = current_time
        
        # Forward to current leader and upcoming leaders
        forwarding_results = self._forward_to_leaders(transaction, tx_hash, current_leader, upcoming_leaders, source_node_id)
        
        self.stats["transactions_forwarded"] += 1
        
        logger.info({
            "message": "Transaction processed via Gulf Stream",
            "tx_hash": tx_hash[:16] + "...",
            "current_block_proposer": current_leader[:20] + "..." if current_leader else None,
            "forwarded_to": len(forwarding_results["leaders_contacted"]),
            "tpu_transmissions": forwarding_results.get("tpu_transmissions", 0),
            "source_node": source_node_id[:20] + "..." if source_node_id else "API"
        })
        
        return {
            "status": "forwarded",
            "tx_hash": tx_hash,
            "forwarding_results": forwarding_results,
            "current_block_proposer": current_leader,
            "upcoming_block_proposers": len(upcoming_leaders)
        }
    
    def _forward_to_leaders(self, transaction, tx_hash: str, current_leader: str, upcoming_leaders: List, source_node: str):
        """
        Forward transaction to current leader + next 3 upcoming leaders (4 total).
        Leaders receive transactions via TPU UDP ports for immediate processing.
        """
        try:
            # Prepare list of all target leaders (current + upcoming)
            target_leaders = [current_leader]
            
            # Add upcoming leaders (limited to next 3)
            for slot_num, leader_key, future_time in upcoming_leaders:
                if leader_key not in target_leaders:  # Avoid duplicates
                    target_leaders.append(leader_key)
            
            # Limit to maximum 4 leaders (current + 3 upcoming)
            target_leaders = target_leaders[:4]
            
            if not target_leaders:
                logger.warning({
                    "message": "No valid Gulf Stream targets found",
                    "tx_hash": tx_hash[:16] + "..."
                })
                return {
                    "leaders_contacted": [],
                    "tpu_transmissions": 0,
                    "successful_transmissions": 0
                }
            
            # Convert transaction to JSON for TPU transmission
            transaction_data = json.dumps({
                'sender_public_key': transaction.sender_public_key,
                'receiver_public_key': transaction.receiver_public_key,
                'amount': transaction.amount,
                'transaction_type': transaction.type,
                'timestamp': transaction.timestamp,
                'transaction_id': transaction.id,
                'signature': transaction.signature
            })
            
            # Forward to each target leader via TPU
            successful_transmissions = 0
            leaders_contacted = []
            
            for leader_key in target_leaders:
                # Calculate TPU port for this leader
                tpu_port = self._get_tpu_port_for_leader(leader_key)
                
                # Send transaction to leader's TPU port
                success = self._send_transaction_to_tpu(leader_key, tpu_port, transaction_data, source_node)
                
                if success:
                    successful_transmissions += 1
                    self.gulf_stream_stats["tpu_transmissions_successful"] += 1
                    leaders_contacted.append(leader_key)
                    
                    # Track pending transaction
                    if leader_key not in self.pending_transactions_by_block_proposer:
                        self.pending_transactions_by_block_proposer[leader_key] = []
                    
                    self.pending_transactions_by_block_proposer[leader_key].append({
                        'tx_hash': tx_hash,
                        'forwarded_time': time.time(),
                        'tpu_port': tpu_port
                    })
                else:
                    self.gulf_stream_stats["tpu_transmissions_failed"] += 1
            
            # Update statistics
            self.gulf_stream_stats["transactions_forwarded"] += 1
            self.gulf_stream_stats["block_proposers_contacted"] += len(leaders_contacted)
            
            logger.info({
                "message": "Transaction forwarded to limited leader set (current + 3 upcoming)",
                "tx_hash": tx_hash[:16] + "...",
                "current_leader": current_leader[:20] + "..." if current_leader else None,
                "total_leaders_contacted": len(leaders_contacted),
                "successful_transmissions": successful_transmissions,
                "target_leaders": [leader[:20] + "..." for leader in target_leaders],
                "source_node": source_node[:16] + "..." if source_node else "API"
            })
            
            return {
                "leaders_contacted": leaders_contacted,
                "tpu_transmissions": len(target_leaders),
                "successful_transmissions": successful_transmissions
            }
            
        except Exception as e:
            logger.error({
                "message": "Failed to forward transaction via Gulf Stream",
                "tx_hash": tx_hash[:16] + "...",
                "error": str(e)
            })
            return {
                "leaders_contacted": [],
                "tpu_transmissions": 0,
                "successful_transmissions": 0
            }
    
    def get_transactions_for_leader(self, leader_public_key: str) -> List:
        """
        Get pending transactions for a specific block proposer.
        Called by the block proposer when it's their turn to create a block.
        """
        if leader_public_key not in self.pending_transactions:
            return []
        
        # Get transactions and clear the cache for this leader
        transactions = self.pending_transactions[leader_public_key].copy()
        
        # Clear processed transactions
        self.pending_transactions[leader_public_key].clear()
        self.forwarded_transactions[leader_public_key].clear()
        
        # Filter out expired transactions
        valid_transactions = []
        current_time = time.time()
        
        for tx in transactions:
            tx_hash = self._calculate_transaction_hash(tx)
            tx_time = self.transaction_timestamps.get(tx_hash, current_time)
            
            if current_time - tx_time < self.transaction_lifetime_seconds:
                valid_transactions.append(tx)
            else:
                self.stats["transactions_expired"] += 1
                # Clean up expired transaction
                if tx_hash in self.transaction_timestamps:
                    del self.transaction_timestamps[tx_hash]
        
        logger.info({
            "message": "Transactions retrieved for block proposer",
            "block_proposer": leader_public_key[:20] + "...",
            "total_transactions": len(transactions),
            "valid_transactions": len(valid_transactions),
            "expired_transactions": len(transactions) - len(valid_transactions)
        })
        
        return valid_transactions
    
    def _send_transaction_to_tpu(self, leader_public_key: str, tpu_port: int, transaction_data: str, source_node: str) -> bool:
        """
        Send transaction directly to leader's TPU via UDP.
        This implements the core Gulf Stream -> TPU forwarding mechanism.
        """
        try:
            # Create Gulf Stream packet for TPU
            packet = {
                'transaction': transaction_data,
                'source_node': source_node,
                'packet_id': f"{source_node}_{int(time.time() * 1000000)}",
                'timestamp': time.time(),
                'gulf_stream_version': '1.0',
                'target_leader': leader_public_key
            }
            
            # Send UDP packet to leader's TPU port
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(0.1)  # 100ms timeout for fast transmission
                sock.sendto(json.dumps(packet).encode(), ('localhost', tpu_port))
            
            logger.debug({
                "message": "Transaction sent to TPU",
                "target_leader": leader_public_key[:16] + "...",
                "tpu_port": tpu_port,
                "packet_id": packet['packet_id'],
                "source": source_node[:16] + "..."
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "message": "Failed to send transaction to TPU",
                "target_leader": leader_public_key[:16] + "...",
                "tpu_port": tpu_port,
                "source": source_node[:16] + "...",
                "error": str(e)
            })
            return False
    
    def _get_tpu_port_for_leader(self, leader_public_key: str) -> Optional[int]:
        """
        Calculate TPU port for a block proposer based on their public key.
        TPU ports follow pattern: 13000 + node_index
        """
        try:
            # Use hash of public key to determine consistent node index
            import hashlib
            key_hash = hashlib.sha256(leader_public_key.encode()).hexdigest()
            node_index = int(key_hash[:8], 16) % 100  # Limit to 100 nodes (ports 13000-13099)
            tpu_port = 13000 + node_index
            return tpu_port
        except Exception as e:
            logger.warning(f"Failed to calculate TPU port for leader {leader_public_key[:20]}...: {e}")
            return None
    
    def _validate_transaction_freshness(self, transaction) -> bool:
        """
        Validate transaction freshness (equivalent to Recent Blockhash check).
        In our system, we check if the transaction was created recently.
        """
        # For now, we'll assume all transactions are fresh
        # In a full implementation, you'd check against recent block hashes
        # stored in the transaction similar to Solana's Recent Blockhash
        return True
    
    def _calculate_transaction_hash(self, transaction) -> str:
        """Calculate unique hash for transaction"""
        # Create a unique identifier for the transaction
        tx_data = f"{transaction.sender_public_key}_{transaction.receiver_public_key}_{transaction.amount}_{transaction.timestamp}"
        return hashlib.sha256(tx_data.encode()).hexdigest()
    
    def cleanup_expired_transactions(self):
        """Remove expired transactions from memory"""
        current_time = time.time()
        expired_hashes = []
        
        for tx_hash, timestamp in self.transaction_timestamps.items():
            if current_time - timestamp > self.transaction_lifetime_seconds:
                expired_hashes.append(tx_hash)
        
        # Clean up expired transactions
        for tx_hash in expired_hashes:
            del self.transaction_timestamps[tx_hash]
            self.stats["transactions_expired"] += 1
            
            # Remove from forwarded transaction sets
            for leader_txs in self.forwarded_transactions.values():
                leader_txs.discard(tx_hash)
        
        if expired_hashes:
            logger.info({
                "message": "Cleaned up expired transactions",
                "expired_count": len(expired_hashes)
            })
    
    def get_stats(self) -> Dict:
        """Get Gulf Stream performance statistics"""
        return {
            "gulf_stream_stats": self.stats.copy(),
            "pending_transactions_by_block_proposer": {
                leader[:20] + "...": len(txs) 
                for leader, txs in self.pending_transactions.items()
            },
            "total_pending_transactions": sum(len(txs) for txs in self.pending_transactions.values()),
            "tracked_transactions": len(self.transaction_timestamps),
            "transaction_lifetime_seconds": self.transaction_lifetime_seconds,
            "max_forwarding_slots": self.max_forwarding_slots
        }
    
    def reset_stats(self):
        """Reset performance statistics"""
        self.stats = {
            "transactions_forwarded": 0,
            "transactions_expired": 0,
            "leaders_contacted": 0,
            "cache_hits": 0
        }
    
    def forward_transaction(self, transaction, upcoming_leaders: List[str]) -> bool:
        """
        Forward transaction to block proposers - compatibility wrapper for process_transaction
        """
        result = self.process_transaction(transaction)
        return result.get("status") == "forwarded"
    
    def update_forwarding_state(self, transaction):
        """
        Update forwarding state for a transaction - used for P2P transactions
        """
        tx_hash = self._calculate_transaction_hash(transaction)
        if tx_hash not in self.transaction_timestamps:
            # Process this P2P transaction through Gulf Stream
            self.process_transaction(transaction)
    
    def get_transactions_for_block(self, max_block_size_bytes: int = None) -> List:
        """
        Get all transactions ready for block creation from Gulf Stream pipeline.
        Block proposer includes all valid transactions received during their slot.
        """
        # Get current block proposer
        current_leader = self.leader_schedule.get_current_leader()
        if not current_leader:
            return []
        
        # Get ALL transactions forwarded to current block proposer
        leader_transactions = self.get_transactions_for_leader(current_leader)
        
        logger.debug(f"Gulf Stream returning {len(leader_transactions)} transactions for block proposer")
        return leader_transactions
    
    def remove_transactions(self, transactions):
        """
        Remove transactions from Gulf Stream after they're included in a block
        """
        for transaction in transactions:
            tx_hash = self._calculate_transaction_hash(transaction)
            
            # Remove from timestamp tracking
            if tx_hash in self.transaction_timestamps:
                del self.transaction_timestamps[tx_hash]
            
            # Remove from all block proposer queues
            for leader_key in list(self.pending_transactions.keys()):
                self.pending_transactions[leader_key] = [
                    tx for tx in self.pending_transactions[leader_key] 
                    if self._calculate_transaction_hash(tx) != tx_hash
                ]
                
                # Remove from forwarded tracking
                self.forwarded_transactions[leader_key].discard(tx_hash)
    
    def get_forwarding_stats(self) -> Dict:
        """
        Get forwarding statistics - compatibility wrapper for get_stats
        """
        return self.get_stats()
