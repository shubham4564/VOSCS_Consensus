"""
Bloom Filter Implementation for Efficient Gossip Protocol Pull Requests
======================================================================

A probabilistic data structure that efficiently represents a set of hashes
for determining what data a peer is missing.
"""

import hashlib
from typing import Set, List
import math

class BloomFilter:
    """
    Bloom filter implementation for gossip protocol pull requests
    
    A space-efficient probabilistic data structure used to test whether 
    an element is in a set. False positives are possible but false negatives are not.
    """
    
    def __init__(self, expected_elements: int = 10000, false_positive_rate: float = 0.01):
        """
        Initialize bloom filter with optimal size and hash functions
        
        Args:
            expected_elements: Expected number of elements to be added
            false_positive_rate: Desired false positive rate (0.01 = 1%)
        """
        self.expected_elements = expected_elements
        self.false_positive_rate = false_positive_rate
        
        # Calculate optimal bit array size and number of hash functions
        self.bit_array_size = self._calculate_bit_array_size()
        self.num_hash_functions = self._calculate_num_hash_functions()
        
        # Initialize bit array
        self.bit_array = [False] * self.bit_array_size
        self.num_elements_added = 0
        
    def _calculate_bit_array_size(self) -> int:
        """Calculate optimal bit array size"""
        # m = -(n * ln(p)) / (ln(2)^2)
        # where n = expected elements, p = false positive rate
        m = -(self.expected_elements * math.log(self.false_positive_rate)) / (math.log(2) ** 2)
        return int(m)
    
    def _calculate_num_hash_functions(self) -> int:
        """Calculate optimal number of hash functions"""
        # k = (m / n) * ln(2)
        # where m = bit array size, n = expected elements
        k = (self.bit_array_size / self.expected_elements) * math.log(2)
        return max(1, int(k))
    
    def _hash(self, item: str, seed: int) -> int:
        """Generate hash with seed for multiple hash functions"""
        hash_input = f"{item}:{seed}".encode()
        hash_value = hashlib.sha256(hash_input).hexdigest()
        return int(hash_value[:8], 16) % self.bit_array_size
    
    def add(self, item: str):
        """Add an item to the bloom filter"""
        for i in range(self.num_hash_functions):
            index = self._hash(item, i)
            self.bit_array[index] = True
        self.num_elements_added += 1
    
    def contains(self, item: str) -> bool:
        """Check if an item might be in the set"""
        for i in range(self.num_hash_functions):
            index = self._hash(item, i)
            if not self.bit_array[index]:
                return False
        return True
    
    def add_multiple(self, items: List[str]):
        """Add multiple items to the bloom filter"""
        for item in items:
            self.add(item)
    
    def to_bytes(self) -> bytes:
        """Convert bloom filter to bytes for network transmission"""
        # Pack metadata
        metadata = {
            'bit_array_size': self.bit_array_size,
            'num_hash_functions': self.num_hash_functions,
            'num_elements_added': self.num_elements_added
        }
        
        # Convert bit array to bytes (pack 8 bits per byte)
        bit_bytes = bytearray()
        for i in range(0, len(self.bit_array), 8):
            byte_value = 0
            for j in range(8):
                if i + j < len(self.bit_array) and self.bit_array[i + j]:
                    byte_value |= (1 << j)
            bit_bytes.append(byte_value)
        
        # Combine metadata and bit array
        import json
        metadata_bytes = json.dumps(metadata).encode()
        metadata_length = len(metadata_bytes).to_bytes(4, 'big')
        
        return metadata_length + metadata_bytes + bytes(bit_bytes)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'BloomFilter':
        """Create bloom filter from bytes received over network"""
        import json
        
        # Extract metadata length
        metadata_length = int.from_bytes(data[:4], 'big')
        
        # Extract and parse metadata
        metadata_bytes = data[4:4 + metadata_length]
        metadata = json.loads(metadata_bytes.decode())
        
        # Create bloom filter with extracted parameters
        filter_obj = cls.__new__(cls)
        filter_obj.bit_array_size = metadata['bit_array_size']
        filter_obj.num_hash_functions = metadata['num_hash_functions']
        filter_obj.num_elements_added = metadata['num_elements_added']
        filter_obj.expected_elements = metadata['num_elements_added']  # Approximation
        filter_obj.false_positive_rate = 0.01  # Default
        
        # Extract bit array
        bit_bytes = data[4 + metadata_length:]
        filter_obj.bit_array = [False] * filter_obj.bit_array_size
        
        for byte_index, byte_value in enumerate(bit_bytes):
            for bit_index in range(8):
                array_index = byte_index * 8 + bit_index
                if array_index < filter_obj.bit_array_size:
                    filter_obj.bit_array[array_index] = bool(byte_value & (1 << bit_index))
        
        return filter_obj
    
    def get_stats(self) -> dict:
        """Get bloom filter statistics"""
        current_false_positive_rate = self._estimate_false_positive_rate()
        
        return {
            'bit_array_size': self.bit_array_size,
            'num_hash_functions': self.num_hash_functions,
            'elements_added': self.num_elements_added,
            'expected_elements': self.expected_elements,
            'target_false_positive_rate': self.false_positive_rate,
            'estimated_false_positive_rate': current_false_positive_rate,
            'bits_set': sum(self.bit_array),
            'memory_usage_bytes': len(self.bit_array) // 8
        }
    
    def _estimate_false_positive_rate(self) -> float:
        """Estimate current false positive rate"""
        if self.num_elements_added == 0:
            return 0.0
        
        # (1 - e^(-k*n/m))^k
        # where k = num_hash_functions, n = elements_added, m = bit_array_size
        try:
            exponent = -self.num_hash_functions * self.num_elements_added / self.bit_array_size
            rate = (1 - math.exp(exponent)) ** self.num_hash_functions
            return min(1.0, rate)
        except (OverflowError, ZeroDivisionError):
            return 1.0
