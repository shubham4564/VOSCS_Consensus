"""
Block configuration settings for the quantum annealing blockchain.

This module provides flexible configuration for block size limits and related parameters.
These settings can be easily adjusted based on network requirements and performance needs.
"""


class BlockConfig:
    """Block configuration constants and utilities."""
    
    # Block size limits (in bytes) - Updated for 10 MB default
    DEFAULT_MAX_BLOCK_SIZE = 10 * 1024 * 1024  # 10MB - new default maximum block size
    MIN_BLOCK_SIZE = 200                       # Minimum block size to prevent tiny blocks
    MAX_BLOCK_SIZE = 12 * 1024 * 1024          # 12MB - absolute maximum to allow some flexibility
    
    # Common block size presets (in bytes)
    BLOCK_SIZE_PRESETS = {
        'tiny': 512,              # 512 bytes
        'small': 1024,            # 1KB
        'medium': 4096,           # 4KB
        'large': 16384,           # 16KB
        'xlarge': 65536,          # 64KB
        'xxlarge': 262144,        # 256KB
        'default': 10 * 1024 * 1024,  # 10MB - new default
        'max': 12 * 1024 * 1024,      # 12MB - maximum
    }
    
    # Block overhead estimation (bytes)
    BLOCK_HEADER_OVERHEAD = 200        # Estimated bytes for block metadata
    TRANSACTION_OVERHEAD = 50          # Estimated bytes per transaction overhead
    
    @classmethod
    def get_preset_size(cls, preset_name):
        """
        Get block size for a preset configuration.
        
        Args:
            preset_name (str): Name of the preset ('tiny', 'small', 'medium', etc.)
            
        Returns:
            int: Block size in bytes
            
        Raises:
            ValueError: If preset_name is not recognized
        """
        if preset_name not in cls.BLOCK_SIZE_PRESETS:
            available_presets = ', '.join(cls.BLOCK_SIZE_PRESETS.keys())
            raise ValueError(f"Unknown preset '{preset_name}'. Available presets: {available_presets}")
        
        return cls.BLOCK_SIZE_PRESETS[preset_name]
    
    @classmethod
    def validate_block_size(cls, size_bytes):
        """
        Validate that a block size is within acceptable limits.
        
        Args:
            size_bytes (int): Block size in bytes
            
        Returns:
            bool: True if valid, False otherwise
        """
        return cls.MIN_BLOCK_SIZE <= size_bytes <= cls.MAX_BLOCK_SIZE
    
    @classmethod
    def format_size(cls, size_bytes):
        """
        Format block size in human-readable format.
        
        Args:
            size_bytes (int): Size in bytes
            
        Returns:
            str: Formatted size string
        """
        if size_bytes < 1024:
            return f"{size_bytes} bytes"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
    
    @classmethod
    def estimate_transactions_per_block(cls, block_size_bytes, avg_transaction_size_bytes=300):
        """
        Estimate how many transactions can fit in a block of given size.
        
        Args:
            block_size_bytes (int): Block size in bytes
            avg_transaction_size_bytes (int): Average transaction size in bytes
            
        Returns:
            int: Estimated number of transactions
        """
        available_space = block_size_bytes - cls.BLOCK_HEADER_OVERHEAD
        effective_transaction_size = avg_transaction_size_bytes + cls.TRANSACTION_OVERHEAD
        
        return max(1, available_space // effective_transaction_size)


# Create a global configuration instance
block_config = BlockConfig()
