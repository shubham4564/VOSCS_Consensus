import hashlib
import time


class Message:
    def __init__(self, sender_connector, message_type, data):
        self.sender_connector = sender_connector
        self.message_type = message_type
        self.data = data
        self.timestamp = time.time()
        # Create message hash for deduplication
        self.message_id = self._generate_message_id()
    
    def _generate_message_id(self):
        """Generate unique message ID for deduplication"""
        content = f"{self.sender_connector.ip}:{self.sender_connector.port}:{self.message_type}:{self.timestamp}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def is_recent(self, max_age_seconds=300):
        """Check if message is recent (within max_age_seconds)"""
        return time.time() - self.timestamp <= max_age_seconds


class MessageType:
    """Bitcoin-style message types for efficient P2P communication"""
    # Legacy types
    DISCOVERY = "DISCOVERY"
    TRANSACTION = "TRANSACTION"  # Direct transaction broadcast (deprecated)
    BLOCK = "BLOCK"
    BLOCKCHAINREQUEST = "BLOCKCHAINREQUEST"
    BLOCKCHAIN = "BLOCKCHAIN"
    
    # New Bitcoin-style inventory system
    INV = "INV"              # Inventory announcement (transaction/block hashes)
    GETDATA = "GETDATA"      # Request for specific transaction/block data
    TX = "TX"                # Transaction data response
    BLOCK_DATA = "BLOCK_DATA" # Block data response
    
    # Ping/Pong for connection health
    PING = "PING"
    PONG = "PONG"


class InventoryItem:
    """Represents an item in an inventory message"""
    TYPE_TX = 1      # Transaction
    TYPE_BLOCK = 2   # Block
    
    def __init__(self, item_type, hash_value):
        self.type = item_type
        self.hash = hash_value
    
    def to_dict(self):
        return {
            'type': self.type,
            'hash': self.hash
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(data['type'], data['hash'])


class InventoryMessage:
    """Bitcoin-style INV message for announcing available data"""
    def __init__(self, inventory_items):
        self.inventory = inventory_items  # List of InventoryItem
        self.count = len(inventory_items)
    
    def to_dict(self):
        return {
            'count': self.count,
            'inventory': [item.to_dict() for item in self.inventory]
        }
    
    @classmethod
    def from_dict(cls, data):
        items = [InventoryItem.from_dict(item_data) for item_data in data['inventory']]
        return cls(items)


class GetDataMessage:
    """Bitcoin-style GETDATA message for requesting specific data"""
    def __init__(self, inventory_items):
        self.inventory = inventory_items  # List of InventoryItem
        self.count = len(inventory_items)
    
    def to_dict(self):
        return {
            'count': self.count,
            'inventory': [item.to_dict() for item in self.inventory]
        }
    
    @classmethod
    def from_dict(cls, data):
        items = [InventoryItem.from_dict(item_data) for item_data in data['inventory']]
        return cls(items)
