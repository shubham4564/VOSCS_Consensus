import hashlib
import time
from typing import List, Optional

class PoHEntry:
    def __init__(self, hash_value: str, transaction=None, timestamp=None):
        self.hash_value = hash_value
        self.transaction = transaction  # Can be None for tick entries
        self.timestamp = timestamp or time.time()

    def to_dict(self):
        return {
            'hash': self.hash_value,
            'transaction': self.transaction.to_dict() if self.transaction else None,
            'timestamp': self.timestamp
        }

class PoHSequencer:
    """
    Simple Proof of History (PoH) sequencer using SHA256 as a VDF.
    Continuously hashes its own output, and can mix in transactions to create a verifiable order.
    """
    def __init__(self, initial_hash: Optional[str] = None):
        self.current_hash = initial_hash or hashlib.sha256(b'genesis').hexdigest()
        self.entries: List[PoHEntry] = []
        self.tick_interval = 0.5  # seconds between ticks (can be tuned)
        self.last_tick = time.time()

    def tick(self):
        now = time.time()
        if now - self.last_tick >= self.tick_interval:
            self.current_hash = hashlib.sha256(self.current_hash.encode()).hexdigest()
            self.entries.append(PoHEntry(self.current_hash, transaction=None, timestamp=now))
            self.last_tick = now

    def ingest_transaction(self, transaction):
        # Mix transaction data into the PoH stream
        tx_data = str(transaction.payload()).encode()
        combined = self.current_hash.encode() + tx_data
        self.current_hash = hashlib.sha256(combined).hexdigest()
        self.entries.append(PoHEntry(self.current_hash, transaction=transaction, timestamp=time.time()))

    def get_sequence(self):
        return self.entries

    def reset(self, initial_hash: Optional[str] = None):
        self.current_hash = initial_hash or hashlib.sha256(b'genesis').hexdigest()
        self.entries = []
        self.last_tick = time.time()
