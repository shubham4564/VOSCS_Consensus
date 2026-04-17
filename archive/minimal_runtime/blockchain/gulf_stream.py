import time
from typing import List, Dict, Optional
from blockchain.utils.logger import logger

class GulfStreamProtocol:
    """
    Gulf Stream transaction forwarding protocol.
    
    Forwards transactions to upcoming leaders before their slot starts,
    allowing leaders to prepare blocks in advance for faster consensus.
    """
    
    def __init__(self, leader_schedule):
        self.leader_schedule = leader_schedule
        self.forwarded_transactions = {}  # leader_id -> [transactions]
        self.forwarding_stats = {
            'total_forwarded': 0,
            'successful_forwards': 0,
            'failed_forwards': 0
        }
        
        logger.info("Gulf Stream protocol initialized for transaction forwarding")
    
    def should_forward_transaction(self, transaction, current_time: float = None) -> List[str]:
        """
        Determine which upcoming leaders should receive this transaction.
        Returns list of leader public keys to forward to.
        FIXED: Only forward to current leader + next 3 upcoming leaders (4 total max).
        """
        if current_time is None:
            current_time = time.time()
        
        # FIXED: Get current leader + only next 3 upcoming leaders (4 total max)
        current_leader = self.leader_schedule.get_current_leader()
        upcoming_leaders = self.leader_schedule.get_upcoming_leaders(3)  # Only next 3 leaders
        
        forward_to_leaders = []
        
        # Add current leader if available
        if current_leader:
            forward_to_leaders.append(current_leader)
        
        # Add next 3 upcoming leaders
        for slot_num, leader_key, future_time in upcoming_leaders:
            if leader_key not in forward_to_leaders:  # Avoid duplicates
                forward_to_leaders.append(leader_key)
        
        # Ensure maximum 4 leaders (current + 3 upcoming)
        forward_to_leaders = forward_to_leaders[:4]
        
        logger.debug(f"Transaction should be forwarded to {len(forward_to_leaders)} upcoming leaders (max 4: current + 3 upcoming)")
        return forward_to_leaders
    
    def forward_transaction(self, transaction, target_leaders: List[str]) -> Dict:
        """
        Forward a transaction to multiple upcoming leaders.
        
        Args:
            transaction: Transaction to forward
            target_leaders: List of leader public keys
            
        Returns:
            Dictionary with forwarding results
        """
        forwarding_results = {
            'transaction_id': transaction.id,
            'forwarded_to': [],
            'failed_forwards': [],
            'timestamp': time.time()
        }
        
        for leader_id in target_leaders:
            try:
                # Add transaction to leader's forwarded pool
                if leader_id not in self.forwarded_transactions:
                    self.forwarded_transactions[leader_id] = []
                
                self.forwarded_transactions[leader_id].append(transaction)
                forwarding_results['forwarded_to'].append(leader_id)
                
                self.forwarding_stats['successful_forwards'] += 1
                
                logger.debug(f"Transaction {transaction.id[:8]} forwarded to leader {leader_id[:20]}...")
                
            except Exception as e:
                forwarding_results['failed_forwards'].append({
                    'leader_id': leader_id,
                    'error': str(e)
                })
                self.forwarding_stats['failed_forwards'] += 1
                logger.warning(f"Failed to forward transaction to {leader_id[:20]}...: {e}")
        
        self.forwarding_stats['total_forwarded'] += 1
        
        logger.info(f"Gulf Stream forwarded transaction {transaction.id[:8]} to {len(forwarding_results['forwarded_to'])} leaders (max 4: current + 3 upcoming)")
        return forwarding_results
    
    def get_forwarded_transactions(self, leader_id: str) -> List:
        """
        Get transactions that have been forwarded to a specific leader.
        Called by leaders when their slot starts.
        """
        transactions = self.forwarded_transactions.get(leader_id, [])
        
        # Clear the forwarded transactions for this leader
        if leader_id in self.forwarded_transactions:
            del self.forwarded_transactions[leader_id]
        
        logger.info(f"Leader {leader_id[:20]}... retrieved {len(transactions)} forwarded transactions")
        return transactions
    
    def clean_expired_forwards(self, current_time: float = None):
        """
        Clean up forwarded transactions for leaders whose slots have passed.
        """
        if current_time is None:
            current_time = time.time()
        
        current_leader = self.leader_schedule.get_current_leader()
        upcoming_leaders = [target['leader'] for target in self.leader_schedule.get_gulf_stream_targets()]
        
        # Keep only current and upcoming leaders
        active_leaders = set([current_leader] + upcoming_leaders)
        
        expired_leaders = []
        for leader_id in list(self.forwarded_transactions.keys()):
            if leader_id not in active_leaders:
                expired_leaders.append(leader_id)
                del self.forwarded_transactions[leader_id]
        
        if expired_leaders:
            logger.info(f"Cleaned up forwarded transactions for {len(expired_leaders)} expired leaders")
    
    def get_forwarding_stats(self) -> Dict:
        """Get Gulf Stream forwarding statistics"""
        return {
            'total_forwarded': self.forwarding_stats['total_forwarded'],
            'successful_forwards': self.forwarding_stats['successful_forwards'],
            'failed_forwards': self.forwarding_stats['failed_forwards'],
            'success_rate': (
                self.forwarding_stats['successful_forwards'] / 
                max(1, self.forwarding_stats['total_forwarded'])
            ) * 100,
            'active_forward_pools': len(self.forwarded_transactions),
            'total_queued_transactions': sum(len(txs) for txs in self.forwarded_transactions.values())
        }
    
    def get_network_view(self) -> Dict:
        """
        Get current network view for Gulf Stream forwarding.
        Shows which leaders are receiving forwarded transactions.
        """
        current_time = time.time()
        upcoming_targets = self.leader_schedule.get_gulf_stream_targets()
        
        network_view = {
            'current_time': current_time,
            'upcoming_leaders': [],
            'forwarding_pools': {}
        }
        
        for target in upcoming_targets[:10]:  # Show next 10 leaders (20 seconds)
            network_view['upcoming_leaders'].append({
                'leader': target['leader'][:20] + "...",
                'slot': target['slot'],
                'time_until_slot': round(target['time_until_slot'], 1),
                'receiving_forwards': target['leader'] in self.forwarded_transactions
            })
        
        for leader_id, transactions in self.forwarded_transactions.items():
            network_view['forwarding_pools'][leader_id[:20] + "..."] = len(transactions)
        
        return network_view

class GulfStreamNode:
    """
    Node-level Gulf Stream integration.
    Handles transaction forwarding when transactions are received.
    """
    
    def __init__(self, blockchain):
        self.blockchain = blockchain
        self.gulf_stream = GulfStreamProtocol(blockchain.leader_schedule)
        self.local_transaction_pool = []
        
        logger.info("Gulf Stream node integration initialized")
    
    def receive_transaction(self, transaction):
        """
        Process incoming transaction with Gulf Stream forwarding.
        
        This is called when a transaction first enters the network.
        """
        # Add to local pool
        self.local_transaction_pool.append(transaction)
        
        # Determine if and where to forward
        forward_targets = self.gulf_stream.should_forward_transaction(transaction)
        
        if forward_targets:
            # Forward to upcoming leaders
            result = self.gulf_stream.forward_transaction(transaction, forward_targets)
            logger.info(f"Transaction {transaction.id[:8]} forwarded via Gulf Stream to {len(result['forwarded_to'])} leaders")
        else:
            logger.debug(f"Transaction {transaction.id[:8]} not forwarded - no suitable upcoming leaders")
    
    def get_transactions_for_leader(self, leader_id: str) -> List:
        """
        Get all transactions available for a leader to include in their block.
        Combines local pool + Gulf Stream forwarded transactions.
        """
        # Get locally received transactions
        local_transactions = self.local_transaction_pool.copy()
        
        # Get Gulf Stream forwarded transactions
        forwarded_transactions = self.gulf_stream.get_forwarded_transactions(leader_id)
        
        # Combine and deduplicate
        all_transactions = local_transactions + forwarded_transactions
        
        # Remove duplicates based on transaction ID
        seen_ids = set()
        unique_transactions = []
        for tx in all_transactions:
            if tx.id not in seen_ids:
                unique_transactions.append(tx)
                seen_ids.add(tx.id)
        
        logger.info(f"Leader {leader_id[:20]}... has {len(unique_transactions)} total transactions ({len(local_transactions)} local + {len(forwarded_transactions)} forwarded)")
        return unique_transactions
    
    def start_leader_slot(self, leader_id: str):
        """
        Called when this node becomes the leader for current slot.
        Retrieves all available transactions for block creation.
        """
        available_transactions = self.get_transactions_for_leader(leader_id)
        
        logger.info(f"Leader slot started for {leader_id[:20]}... with {len(available_transactions)} available transactions")
        return available_transactions
    
    def cleanup_expired_data(self):
        """Regular cleanup of expired Gulf Stream data"""
        self.gulf_stream.clean_expired_forwards()
        
        # Optional: Clean old transactions from local pool
        # In production, you might want to implement transaction TTL
    
    def get_gulf_stream_status(self) -> Dict:
        """Get comprehensive Gulf Stream status for monitoring"""
        return {
            'forwarding_stats': self.gulf_stream.get_forwarding_stats(),
            'network_view': self.gulf_stream.get_network_view(),
            'local_pool_size': len(self.local_transaction_pool),
            'leader_schedule_info': self.blockchain.leader_schedule.get_schedule_info()
        }
