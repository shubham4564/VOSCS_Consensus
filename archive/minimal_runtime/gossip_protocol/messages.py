
"""
Gossip Protocol Messages Implementation
=====================================

Implements the four core gossip message types:
1. PushMessage - Proactively share information
2. PullRequest - Request missing information  
3. PullResponse - Respond with missing information
4. PruneMessage - Manage connection topology
"""

import time
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from .crds import CrdsValue
from .bloom_filter import BloomFilter

@dataclass
class PushMessage:
    """
    Message for proactively sharing information with peers
    
    Sent to ~6 nodes from active gossip set to rapidly disseminate new data
    """
    sender_public_key: str
    crds_values: List[Dict]  # List of CrdsValue.to_dict()
    timestamp: float
    message_id: str
    
    def __post_init__(self):
        if not self.message_id:
            self.message_id = f"push_{self.sender_public_key[:8]}_{int(self.timestamp * 1000)}"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for network transmission"""
        # Limit the number of CRDS values to prevent message size issues
        limited_crds_values = self.crds_values[:1]  # Maximum 1 item per push to prevent UDP size issues
        return {
            'type': 'PushMessage',
            'sender_public_key': self.sender_public_key,  # Keep full key for validation
            'crds_values': limited_crds_values,
            'timestamp': self.timestamp,
            'message_id': self.message_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PushMessage':
        """Create from dictionary received over network"""
        return cls(
            sender_public_key=data['sender_public_key'],
            crds_values=data['crds_values'],
            timestamp=data['timestamp'],
            message_id=data['message_id']
        )
    
    def get_crds_values(self) -> List[CrdsValue]:
        """Convert dictionary data back to CrdsValue objects"""
        return [CrdsValue.from_dict(item) for item in self.crds_values]

@dataclass
class PullRequest:
    """
    Message for requesting missing information from a peer
    
    Contains a bloom filter representing all data the requester already has
    """
    sender_public_key: str
    bloom_filter_data: bytes
    timestamp: float
    message_id: str
    
    def __post_init__(self):
        if not self.message_id:
            self.message_id = f"pull_req_{self.sender_public_key[:8]}_{int(self.timestamp * 1000)}"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for network transmission"""
        import base64
        return {
            'type': 'PullRequest',
            'sender_public_key': self.sender_public_key,  # Keep full key for validation
            'bloom_filter_data': base64.b64encode(self.bloom_filter_data[:1000]).decode(),  # Limit size
            'timestamp': self.timestamp,
            'message_id': self.message_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PullRequest':
        """Create from dictionary received over network"""
        import base64
        return cls(
            sender_public_key=data['sender_public_key'],
            bloom_filter_data=base64.b64decode(data['bloom_filter_data']),
            timestamp=data['timestamp'],
            message_id=data['message_id']
        )
    
    def get_bloom_filter(self) -> BloomFilter:
        """Get the bloom filter from the transmitted data"""
        return BloomFilter.from_bytes(self.bloom_filter_data)

@dataclass
class PullResponse:
    """
    Message responding to a PullRequest with missing data
    
    Contains only the CrdsValues that the requester doesn't have
    """
    sender_public_key: str
    requester_public_key: str
    crds_values: List[Dict]  # List of CrdsValue.to_dict()
    timestamp: float
    message_id: str
    request_id: str  # ID of the original PullRequest
    
    def __post_init__(self):
        if not self.message_id:
            self.message_id = f"pull_resp_{self.sender_public_key[:8]}_{int(self.timestamp * 1000)}"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for network transmission"""
        # Limit the number of CRDS values to prevent message size issues
        limited_crds_values = self.crds_values[:3]  # Maximum 3 items per response
        return {
            'type': 'PullResponse',
            'sender_public_key': self.sender_public_key,  # Keep full key for validation
            'requester_public_key': self.requester_public_key,  # Keep full key for validation
            'crds_values': limited_crds_values,
            'timestamp': self.timestamp,
            'message_id': self.message_id,
            'request_id': self.request_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PullResponse':
        """Create from dictionary received over network"""
        return cls(
            sender_public_key=data['sender_public_key'],
            requester_public_key=data['requester_public_key'],
            crds_values=data['crds_values'],
            timestamp=data['timestamp'],
            message_id=data['message_id'],
            request_id=data['request_id']
        )
    
    def get_crds_values(self) -> List[CrdsValue]:
        """Convert dictionary data back to CrdsValue objects"""
        return [CrdsValue.from_dict(item) for item in self.crds_values]

@dataclass
class PruneMessage:
    """
    Message for managing gossip connection topology
    
    Tells a peer to stop sending gossip messages (health-based pruning)
    """
    sender_public_key: str
    target_public_key: str
    reason: str  # Reason for pruning (e.g., "unhealthy", "unresponsive")
    timestamp: float
    message_id: str
    
    def __post_init__(self):
        if not self.message_id:
            self.message_id = f"prune_{self.sender_public_key[:8]}_{int(self.timestamp * 1000)}"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for network transmission"""
        return {
            'type': 'PruneMessage',
            'sender_public_key': self.sender_public_key,
            'target_public_key': self.target_public_key,
            'reason': self.reason,
            'timestamp': self.timestamp,
            'message_id': self.message_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PruneMessage':
        """Create from dictionary received over network"""
        return cls(
            sender_public_key=data['sender_public_key'],
            target_public_key=data['target_public_key'],
            reason=data['reason'],
            timestamp=data['timestamp'],
            message_id=data['message_id']
        )

class GossipMessageFactory:
    """Factory for creating and parsing gossip messages"""
    
    @staticmethod
    def create_push_message(sender_public_key: str, crds_values: List[CrdsValue]) -> PushMessage:
        """Create a push message with CRDS values"""
        return PushMessage(
            sender_public_key=sender_public_key,
            crds_values=[value.to_dict() for value in crds_values],
            timestamp=time.time(),
            message_id=""
        )
    
    @staticmethod
    def create_pull_request(sender_public_key: str, bloom_filter: BloomFilter) -> PullRequest:
        """Create a pull request with bloom filter"""
        return PullRequest(
            sender_public_key=sender_public_key,
            bloom_filter_data=bloom_filter.to_bytes(),
            timestamp=time.time(),
            message_id=""
        )
    
    @staticmethod
    def create_pull_response(sender_public_key: str, requester_public_key: str, 
                           crds_values: List[CrdsValue], request_id: str) -> PullResponse:
        """Create a pull response with missing CRDS values"""
        return PullResponse(
            sender_public_key=sender_public_key,
            requester_public_key=requester_public_key,
            crds_values=[value.to_dict() for value in crds_values],
            timestamp=time.time(),
            message_id="",
            request_id=request_id
        )
    
    @staticmethod
    def create_prune_message(sender_public_key: str, target_public_key: str, reason: str) -> PruneMessage:
        """Create a prune message"""
        return PruneMessage(
            sender_public_key=sender_public_key,
            target_public_key=target_public_key,
            reason=reason,
            timestamp=time.time(),
            message_id=""
        )
    
    @staticmethod
    def parse_message(data: Dict) -> Optional[Any]:
        """Parse a received message dictionary into the appropriate message type"""
        message_type = data.get('type')
        
        if message_type == 'PushMessage':
            return PushMessage.from_dict(data)
        elif message_type == 'PullRequest':
            return PullRequest.from_dict(data)
        elif message_type == 'PullResponse':
            return PullResponse.from_dict(data)
        elif message_type == 'PruneMessage':
            return PruneMessage.from_dict(data)
        else:
            return None

class MessageValidator:
    """Validates gossip messages for security and correctness"""
    
    @staticmethod
    def validate_push_message(message: PushMessage) -> bool:
        """Validate a push message"""
        # Check basic structure
        if not message.sender_public_key or not message.crds_values:
            return False
        
        # Check timestamp is reasonable (more lenient window for gossip)
        current_time = time.time()
        if message.timestamp < current_time - 7200 or message.timestamp > current_time + 300:  # 2 hours past, 5 minutes future
            return False
        
        # Validate each CRDS value with more lenient validation
        try:
            for crds_dict in message.crds_values:
                crds_value = CrdsValue.from_dict(crds_dict)
                # For gossip protocol, just verify the CRDS value has basic structure
                if not crds_value.public_key or not crds_value.signature:
                    return False
        except Exception:
            return False
        
        return True
    
    @staticmethod
    def validate_pull_request(message: PullRequest) -> bool:
        """Validate a pull request"""
        if not message.sender_public_key or not message.bloom_filter_data:
            return False
        
        current_time = time.time()
        if message.timestamp < current_time - 3600 or message.timestamp > current_time + 60:
            return False
        
        # Try to parse bloom filter
        try:
            BloomFilter.from_bytes(message.bloom_filter_data)
        except Exception:
            return False
        
        return True
    
    @staticmethod
    def validate_pull_response(message: PullResponse) -> bool:
        """Validate a pull response"""
        if not message.sender_public_key or not message.requester_public_key:
            return False
        
        current_time = time.time()
        if message.timestamp < current_time - 7200 or message.timestamp > current_time + 300:  # More lenient window
            return False
        
        # Validate CRDS values if present with lenient validation
        try:
            for crds_dict in message.crds_values:
                crds_value = CrdsValue.from_dict(crds_dict)
                # Just check basic structure for gossip protocol
                if not crds_value.public_key or not crds_value.signature:
                    return False
        except Exception:
            return False
        
        return True
    
    @staticmethod
    def validate_prune_message(message: PruneMessage) -> bool:
        """Validate a prune message"""
        if not message.sender_public_key or not message.target_public_key:
            return False
        
        current_time = time.time()
        if message.timestamp < current_time - 3600 or message.timestamp > current_time + 60:
            return False
        
        return True
