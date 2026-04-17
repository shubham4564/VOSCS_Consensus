import hashlib
import time
from typing import Dict, Set, List, Optional
from blockchain.utils.helpers import BlockchainUtils
from blockchain.utils.logger import logger


class TransactionMempool:
    """
    Bitcoin-style transaction mempool with inventory tracking and gossip protocol.
    Manages transaction propagation using INV/GETDATA/TX message pattern.
    """
    
    def __init__(self, max_mempool_size=10000):
        # Core mempool storage
        self.transactions = {}  # hash -> transaction object
        self.transaction_hashes = set()  # Quick lookup for existence
        
        # Peer tracking for intelligent propagation
        self.peer_inventories = {}  # peer_id -> set of transaction hashes they know
        self.pending_requests = {}  # peer_id -> set of hashes we've requested from them
        self.announcement_cache = {}  # tx_hash -> timestamp when we announced it
        
        # Configuration
        self.max_mempool_size = max_mempool_size
        self.max_peer_connections = 10  # Target 8-10 connections like Bitcoin
        self.announcement_timeout = 60  # Seconds before re-announcing
        self.request_timeout = 30  # Seconds before re-requesting
        
        # Performance tracking
        self.stats = {
            'total_received': 0,
            'total_announced': 0,
            'total_requested': 0,
            'total_served': 0,
            'duplicate_announcements': 0,
            'cache_hits': 0
        }
    
    def calculate_transaction_hash(self, transaction) -> str:
        """Calculate consistent hash for a transaction"""
        tx_data = transaction.payload() if hasattr(transaction, 'payload') else str(transaction.__dict__)
        return hashlib.sha256(str(tx_data).encode()).hexdigest()
    
    def add_transaction(self, transaction, source_peer=None) -> bool:
        """
        Add transaction to mempool if valid and new.
        Returns True if transaction was added, False if duplicate/invalid.
        """
        tx_hash = self.calculate_transaction_hash(transaction)
        
        # Check if we already have this transaction
        if tx_hash in self.transaction_hashes:
            self.stats['cache_hits'] += 1
            self._update_peer_inventory(source_peer, tx_hash)
            return False
        
        # Add to mempool
        self.transactions[tx_hash] = transaction
        self.transaction_hashes.add(tx_hash)
        self.stats['total_received'] += 1
        
        # Track which peer sent us this transaction
        if source_peer:
            self._update_peer_inventory(source_peer, tx_hash)
        
        # Cleanup if mempool is getting too large
        if len(self.transactions) > self.max_mempool_size:
            self._cleanup_old_transactions()
        
        logger.info({
            "message": "Transaction added to mempool",
            "tx_hash": tx_hash[:16] + "...",
            "mempool_size": len(self.transactions),
            "source_peer": source_peer[:20] + "..." if source_peer else "local"
        })
        
        return True
    
    def has_transaction(self, tx_hash: str) -> bool:
        """Check if we have a transaction by its hash"""
        return tx_hash in self.transaction_hashes
    
    def get_transaction(self, tx_hash: str):
        """Get transaction by hash, return None if not found"""
        return self.transactions.get(tx_hash)
    
    def get_transactions_for_announcement(self, exclude_peer=None) -> List[str]:
        """
        Get list of transaction hashes that should be announced to peers.
        Excludes transactions we know the peer already has.
        """
        if not exclude_peer:
            return list(self.transaction_hashes)
        
        peer_known = self.peer_inventories.get(exclude_peer, set())
        return [tx_hash for tx_hash in self.transaction_hashes if tx_hash not in peer_known]
    
    def mark_announced_to_peer(self, peer_id: str, tx_hashes: List[str]):
        """Mark that we've announced these transactions to a peer"""
        current_time = time.time()
        
        # Update peer inventory
        if peer_id not in self.peer_inventories:
            self.peer_inventories[peer_id] = set()
        self.peer_inventories[peer_id].update(tx_hashes)
        
        # Update announcement cache
        for tx_hash in tx_hashes:
            self.announcement_cache[tx_hash] = current_time
        
        self.stats['total_announced'] += len(tx_hashes)
    
    def get_missing_transactions(self, announced_hashes: List[str], source_peer: str) -> List[str]:
        """
        Determine which announced transactions we don't have and should request.
        Updates peer inventory tracking.
        """
        # Update what we know this peer has
        self._update_peer_inventory(source_peer, announced_hashes)
        
        # Find transactions we don't have
        missing = [tx_hash for tx_hash in announced_hashes if not self.has_transaction(tx_hash)]
        
        # Track pending requests
        if source_peer not in self.pending_requests:
            self.pending_requests[source_peer] = set()
        self.pending_requests[source_peer].update(missing)
        
        self.stats['total_requested'] += len(missing)
        
        if missing:
            logger.info({
                "message": "Requesting missing transactions",
                "count": len(missing),
                "source_peer": source_peer[:20] + "..." if source_peer else "unknown",
                "sample_hashes": [h[:8] + "..." for h in missing[:3]]
            })
        
        return missing
    
    def mark_request_fulfilled(self, peer_id: str, tx_hash: str):
        """Mark that a pending request has been fulfilled"""
        if peer_id in self.pending_requests:
            self.pending_requests[peer_id].discard(tx_hash)
    
    def get_pending_requests(self, peer_id: str) -> Set[str]:
        """Get list of transaction hashes we're still waiting for from a peer"""
        return self.pending_requests.get(peer_id, set())
    
    def should_reannounce(self, tx_hash: str) -> bool:
        """Check if a transaction should be re-announced (Bitcoin-style flooding)"""
        if tx_hash not in self.announcement_cache:
            return True
        
        last_announced = self.announcement_cache[tx_hash]
        return time.time() - last_announced > self.announcement_timeout
    
    def cleanup_peer(self, peer_id: str):
        """Clean up tracking data when a peer disconnects"""
        if peer_id in self.peer_inventories:
            del self.peer_inventories[peer_id]
        if peer_id in self.pending_requests:
            del self.pending_requests[peer_id]
        
        logger.info({
            "message": "Cleaned up peer tracking data",
            "peer_id": peer_id[:20] + "..." if peer_id else "unknown"
        })
    
    def get_mempool_stats(self) -> dict:
        """Get comprehensive mempool statistics"""
        return {
            'mempool_size': len(self.transactions),
            'unique_transactions': len(self.transaction_hashes),
            'tracked_peers': len(self.peer_inventories),
            'pending_requests_total': sum(len(reqs) for reqs in self.pending_requests.values()),
            'announced_transactions': len(self.announcement_cache),
            'performance_stats': self.stats.copy()
        }
    
    def _update_peer_inventory(self, peer_id: str, tx_hashes):
        """Update what we know a peer has (single hash or list)"""
        if not peer_id:
            return
        
        if peer_id not in self.peer_inventories:
            self.peer_inventories[peer_id] = set()
        
        if isinstance(tx_hashes, str):
            self.peer_inventories[peer_id].add(tx_hashes)
        else:
            self.peer_inventories[peer_id].update(tx_hashes)
    
    def _cleanup_old_transactions(self):
        """Remove oldest transactions to keep mempool size manageable"""
        if len(self.transactions) <= self.max_mempool_size:
            return
        
        # Simple FIFO cleanup - in production, would use fee-based priority
        excess_count = len(self.transactions) - self.max_mempool_size + 100  # Remove extra buffer
        
        # Get oldest transactions (this is simplified - production would use proper ordering)
        old_hashes = list(self.transaction_hashes)[:excess_count]
        
        for tx_hash in old_hashes:
            self.transactions.pop(tx_hash, None)
            self.transaction_hashes.discard(tx_hash)
            self.announcement_cache.pop(tx_hash, None)
        
        # Clean up peer inventories
        for peer_id in self.peer_inventories:
            self.peer_inventories[peer_id] -= set(old_hashes)
        
        logger.info({
            "message": "Cleaned up old transactions from mempool",
            "removed_count": excess_count,
            "new_mempool_size": len(self.transactions)
        })
