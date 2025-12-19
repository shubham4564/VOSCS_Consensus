import time
import hashlib
import threading
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from blockchain.utils.logger import logger
from blockchain.utils.enhanced_logger import get_poh_logger, get_performance_logger
from blockchain.utils.helpers import BlockchainUtils


@dataclass
class PoHEntry:
    """Represents a single entry in the Proof of History sequence"""
    hash: str
    tick: int
    transaction_data: Optional[str] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class ProofOfHistoryGenerator:
    """
    Solana-style Proof of History implementation.
    Creates a verifiable, cryptographically-secure order of transactions
    using a continuous Verifiable Delay Function (VDF).
    """
    
    def __init__(self, node_id: str = "node1"):
        self.running = False
        self.current_hash = self._generate_genesis_hash()
        self.tick_count = 0
        self.entries = []
        self.thread = None
        self.node_id = node_id
        
        # Enhanced logging
        self.poh_logger = get_poh_logger(node_id)
        self.performance_logger = get_performance_logger(node_id)
        
        # PoH timing configuration
        self.ticks_per_second = 5000  # High-frequency hashing for cryptographic clock
        self.tick_interval = 1.0 / self.ticks_per_second  # ~0.2ms per tick
        
        # Entry management
        self.max_entries_in_memory = 10000
        self.pending_transactions = []
        self.lock = threading.Lock()
        
        # Performance metrics
        self.stats = {
            "total_ticks": 0,
            "transactions_sequenced": 0,
            "average_tick_time": 0.0,
            "entries_created": 0
        }
        
        logger.info(f"PoH Generator initialized with {self.ticks_per_second} ticks/second")
    
    def _generate_genesis_hash(self) -> str:
        """Generate the initial hash for PoH sequence"""
        genesis_data = f"solana_poh_genesis_{time.time()}"
        return hashlib.sha256(genesis_data.encode()).hexdigest()
    
    def start_poh_generation(self):
        """Start the continuous PoH generation process"""
        if self.running:
            logger.warning("PoH generation already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._poh_generation_loop, daemon=True)
        self.thread.start()
        logger.info("PoH continuous generation started")
    
    def stop_poh_generation(self):
        """Stop the PoH generation process"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        logger.info("PoH generation stopped")
    
    def _poh_generation_loop(self):
        """Main PoH generation loop - runs continuously creating cryptographic clock"""
        last_tick_time = time.time()
        
        while self.running:
            try:
                start_time = time.time()
                
                # Check for pending transactions to sequence
                with self.lock:
                    if self.pending_transactions:
                        # Process the next transaction
                        transaction_data = self.pending_transactions.pop(0)
                        self._sequence_transaction(transaction_data)
                    else:
                        # Generate regular tick (empty hash for clock advancement)
                        self._generate_tick()
                
                # Maintain timing for consistent tick rate
                elapsed = time.time() - start_time
                sleep_time = max(0, self.tick_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
                # Update performance stats
                actual_interval = time.time() - last_tick_time
                self.stats["average_tick_time"] = (
                    self.stats["average_tick_time"] * 0.9 + actual_interval * 0.1
                )
                last_tick_time = time.time()
                
            except Exception as e:
                logger.error(f"PoH generation error: {e}")
                time.sleep(0.001)  # Brief pause on error
    
    def _generate_tick(self):
        """Generate a regular PoH tick (advances cryptographic clock)"""
        # Hash the current hash to advance the sequence
        self.current_hash = hashlib.sha256(self.current_hash.encode()).hexdigest()
        self.tick_count += 1
        self.stats["total_ticks"] += 1
        
        # Create PoH entry for this tick
        entry = PoHEntry(
            hash=self.current_hash,
            tick=self.tick_count,
            transaction_data=None  # Regular tick, no transaction
        )
        
        self._add_entry(entry)
    
    def _sequence_transaction(self, transaction_data: str):
        """
        Sequence a transaction into the PoH stream.
        Mixes transaction data with current hash to create verifiable ordering.
        """
        # Mix transaction data with current PoH hash
        combined_data = self.current_hash + transaction_data
        self.current_hash = hashlib.sha256(combined_data.encode()).hexdigest()
        self.tick_count += 1
        self.stats["total_ticks"] += 1
        self.stats["transactions_sequenced"] += 1
        
        # Create PoH entry for this transaction
        entry = PoHEntry(
            hash=self.current_hash,
            tick=self.tick_count,
            transaction_data=transaction_data
        )
        
        self._add_entry(entry)
        
        logger.debug(f"Transaction sequenced at tick {self.tick_count}: {transaction_data[:50]}...")
    
    def _add_entry(self, entry: PoHEntry):
        """Add entry to PoH sequence with memory management"""
        self.entries.append(entry)
        self.stats["entries_created"] += 1
        
        # Memory management: keep only recent entries
        if len(self.entries) > self.max_entries_in_memory:
            # Remove oldest 20% of entries
            remove_count = self.max_entries_in_memory // 5
            self.entries = self.entries[remove_count:]
    
    def ingest_transaction(self, transaction) -> bool:
        """
        Ingest a transaction for PoH sequencing.
        Returns True if successfully queued for sequencing.
        """
        try:
            # Convert transaction to sequenceable data
            transaction_data = self._serialize_transaction(transaction)
            
            with self.lock:
                self.pending_transactions.append(transaction_data)
            
            logger.debug(f"Transaction queued for PoH sequencing: {transaction_data[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to ingest transaction for PoH: {e}")
            return False
    
    def _serialize_transaction(self, transaction) -> str:
        """Serialize transaction into a string for PoH sequencing"""
        # Create deterministic transaction representation
        tx_data = {
            "sender": transaction.sender_public_key,
            "receiver": transaction.receiver_public_key,
            "amount": transaction.amount,
            "type": transaction.type,
            "timestamp": transaction.timestamp
        }
        return BlockchainUtils.encode(tx_data).decode('utf-8')
    
    def get_sequenced_entries(self, since_tick: int = 0) -> List[PoHEntry]:
        """
        Get PoH entries since a specific tick.
        Used by block creation to get the ordered sequence.
        """
        with self.lock:
            return [entry for entry in self.entries if entry.tick > since_tick]
    
    def get_current_tick(self) -> int:
        """Get the current PoH tick count"""
        return self.tick_count
    
    def get_current_hash(self) -> str:
        """Get the current PoH hash"""
        return self.current_hash
    
    def create_block_sequence(self, start_tick: int, end_tick: int) -> List[PoHEntry]:
        """
        Create a block sequence from PoH entries between ticks.
        This creates the verifiable, ordered sequence for the block.
        """
        sequence = []
        
        with self.lock:
            for entry in self.entries:
                if start_tick <= entry.tick <= end_tick:
                    sequence.append(entry)
        
        logger.info(f"Created block sequence: ticks {start_tick}-{end_tick}, {len(sequence)} entries")
        return sequence
    
    def verify_poh_sequence(self, entries: List[PoHEntry]) -> bool:
        """
        Verify the integrity of a PoH sequence.
        Used by validators to verify block ordering.
        """
        if not entries:
            return True
        
        for i in range(1, len(entries)):
            prev_entry = entries[i-1]
            curr_entry = entries[i]
            
            # Verify hash chain continuity
            if curr_entry.transaction_data:
                # Transaction entry: hash should be sha256(prev_hash + tx_data)
                expected_hash = hashlib.sha256(
                    (prev_entry.hash + curr_entry.transaction_data).encode()
                ).hexdigest()
            else:
                # Regular tick: hash should be sha256(prev_hash)
                expected_hash = hashlib.sha256(prev_entry.hash.encode()).hexdigest()
            
            if curr_entry.hash != expected_hash:
                logger.warning(f"PoH verification failed at tick {curr_entry.tick}")
                return False
        
        logger.info(f"PoH sequence verified: {len(entries)} entries")
        return True
    
    def get_stats(self) -> Dict:
        """Get PoH generation statistics"""
        return {
            **self.stats,
            "current_tick": self.tick_count,
            "current_hash": self.current_hash[:16] + "...",
            "entries_in_memory": len(self.entries),
            "pending_transactions": len(self.pending_transactions),
            "is_running": self.running,
            "ticks_per_second_target": self.ticks_per_second,
            "actual_tick_interval": self.stats["average_tick_time"]
        }
