import time
import json

class TransactionPool:
    def __init__(self):
        self.transactions = []
        self.last_forge_time = time.time()  # Initialize to current time
        self.forge_interval = 4.0  # REDUCED: 4-second block proposal interval to align better with 2-second slots
        self.max_block_size_bytes = 10 * 1024 * 1024  # 10 MB block size limit
        
        # Block size considerations
        self.estimated_transaction_size = 300  # Bytes per transaction (rough estimate)

    def add_transaction(self, transaction):
        self.transactions.append(transaction)

    def transaction_exists(self, transaction):
        for pool_transaction in self.transactions:
            if pool_transaction.equals(transaction):
                return True
        return False

    def remove_from_pool(self, transactions):
        new_pool_transactions = []
        for pool_transaction in self.transactions:
            insert = True
            for transaction in transactions:
                if pool_transaction.equals(transaction):
                    insert = False
            if insert:
                new_pool_transactions.append(pool_transaction)
        self.transactions = new_pool_transactions

    def block_proposal_required(self):  # Updated method name for clarity
        """
        Determine if block proposal is required based on:
        1. Fixed 4-second interval - block proposal occurs every 4 seconds regardless of transaction count
        2. No minimum transaction requirements - any number of transactions can be included
        3. ENHANCED: More frequent block creation to align with slot-based leader selection
        """
        current_time = time.time()
        time_since_last_forge = current_time - self.last_forge_time
        
        # Propose block every 4 seconds regardless of transaction count (aligned with slot timing)
        if time_since_last_forge >= self.forge_interval:
            return True
            
        return False
    
    def forging_required(self):  # Compatibility method - delegates to block_proposal_required
        """Legacy method name for compatibility - delegates to block_proposal_required"""
        return self.block_proposal_required()
    
    def get_transactions_for_block(self, max_block_size_bytes=None):
        """
        Get transactions for a new block, respecting the 10 MB block size limit.
        Returns all available transactions that fit within the size limit.
        
        Args:
            max_block_size_bytes: Maximum block size in bytes (defaults to 10 MB)
            
        Returns:
            list: List of transactions that fit within the block size limit
        """
        if not self.transactions:
            return []
        
        # Use 10 MB default or provided size limit
        if max_block_size_bytes is None:
            max_block_size_bytes = self.max_block_size_bytes
        
        selected_transactions = []
        current_size = 0
        
        # Add transactions until we reach the size limit
        for transaction in self.transactions:
            transaction_size = self.estimate_transaction_size(transaction)
            
            # Check if adding this transaction would exceed the block size limit
            if current_size + transaction_size <= max_block_size_bytes:
                selected_transactions.append(transaction)
                current_size += transaction_size
            else:
                # Stop adding transactions if we would exceed the limit
                break
        
        return selected_transactions
    
    def estimate_transaction_size(self, transaction):
        """
        Estimate the size of a transaction in bytes.
        
        Args:
            transaction: Transaction object
            
        Returns:
            int: Estimated size in bytes
        """
        try:
            transaction_dict = transaction.to_dict()
            transaction_json = json.dumps(transaction_dict, separators=(',', ':'))
            return len(transaction_json.encode('utf-8'))
        except Exception:
            # Fallback estimate if serialization fails
            return self.estimated_transaction_size
    
    def get_pool_size_estimate(self):
        """
        Get an estimate of the total size of all transactions in the pool.
        
        Returns:
            int: Estimated size in bytes
        """
        if not self.transactions:
            return 0
        
        # Sample a few transactions to get better size estimate
        sample_size = min(5, len(self.transactions))
        total_sample_size = sum(self.estimate_transaction_size(tx) for tx in self.transactions[:sample_size])
        avg_transaction_size = total_sample_size / sample_size
        
        return int(avg_transaction_size * len(self.transactions))
    
    def can_fit_in_block(self, max_block_size_bytes):
        """
        Check if the current pool can fit in a block of the given size.
        
        Args:
            max_block_size_bytes (int): Maximum block size in bytes
            
        Returns:
            bool: True if transactions can fit, False otherwise
        """
        estimated_pool_size = self.get_pool_size_estimate()
        block_overhead = 200  # bytes for block headers and metadata
        return (estimated_pool_size + block_overhead) <= max_block_size_bytes
    
    def update_last_forge_time(self):  # Method name kept for compatibility
        """Update the last block proposal time to current time"""
        self.last_forge_time = time.time()

    def get_time_since_last_forge(self):  # Method name kept for compatibility
        """Get the time elapsed since the last block proposal"""
        return time.time() - self.last_forge_time

    def get_time_until_next_forge(self):  # Method name kept for compatibility
        """Get the time remaining until the next 4-second block proposal interval"""
        time_since_last = self.get_time_since_last_forge()
        if time_since_last >= self.forge_interval:
            return 0.0  # Ready to propose block now
        return self.forge_interval - time_since_last