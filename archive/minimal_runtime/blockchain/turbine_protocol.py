import json
import hashlib
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class Shred:
    """A single data packet for Turbine transmission"""
    
    def __init__(self, index: int, total_shreds: int, data: bytes, is_data_shred: bool, block_hash: str, original_data_shred_count: int = None):
        self.index = index
        self.total_shreds = total_shreds
        self.data = data
        self.is_data_shred = is_data_shred
        self.block_hash = block_hash
        self.original_data_shred_count = original_data_shred_count
    
    def to_bytes(self) -> bytes:
        """Serialize shred for network transmission"""
        header = {
            'index': self.index,
            'total_shreds': self.total_shreds,
            'is_data_shred': self.is_data_shred,
            'block_hash': self.block_hash,
            'original_data_shred_count': self.original_data_shred_count
        }
        header_bytes = json.dumps(header).encode()
        header_len = len(header_bytes).to_bytes(4, 'big')
        return header_len + header_bytes + self.data
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'Shred':
        """Deserialize shred from network transmission"""
        header_len = int.from_bytes(data[:4], 'big')
        header_bytes = data[4:4+header_len]
        header = json.loads(header_bytes.decode())
        shred_data = data[4+header_len:]
        
        return cls(
            index=header['index'],
            total_shreds=header['total_shreds'],
            data=shred_data,
            is_data_shred=header['is_data_shred'],
            block_hash=header['block_hash'],
            original_data_shred_count=header.get('original_data_shred_count')
        )

class BlockShredder:
    """Handles block shredding and erasure coding for Turbine protocol"""
    
    def __init__(self, shred_size: int = 1024, redundancy_ratio: float = 0.3):
        self.shred_size = shred_size
        self.redundancy_ratio = redundancy_ratio
    
    def shred_block(self, block) -> List[Shred]:
        """
        Shred a block into fixed-size packets with Reed-Solomon style erasure coding.
        
        Args:
            block: Block to shred
            
        Returns:
            List of shreds (data + recovery shreds)
        """
        # Serialize block to bytes
        block_data = json.dumps(block.to_dict()).encode()
        block_hash = hashlib.sha256(block_data).hexdigest()
        
        # Split into data shreds
        data_shreds = []
        for i in range(0, len(block_data), self.shred_size):
            chunk = block_data[i:i + self.shred_size]
            # Pad last chunk if necessary
            if len(chunk) < self.shred_size:
                chunk += b'\x00' * (self.shred_size - len(chunk))
            
            shred = Shred(
                index=len(data_shreds),
                total_shreds=0,  # Will be set after calculating recovery shreds
                data=chunk,
                is_data_shred=True,
                block_hash=block_hash,
                original_data_shred_count=None  # Will be set after calculating recovery shreds
            )
            data_shreds.append(shred)
        
        # Generate recovery shreds using Reed-Solomon style erasure coding
        recovery_shreds = self._generate_recovery_shreds(data_shreds, block_hash)
        
        # Store the original data shred count for reconstruction
        self.original_data_shred_count = len(data_shreds)
        print(f"DEBUG shred_block: Set original_data_shred_count to {self.original_data_shred_count}, total_shreds: {len(data_shreds) + len(recovery_shreds)}")
        
        # Update total shred count and original data shred count
        total_shreds = len(data_shreds) + len(recovery_shreds)
        for shred in data_shreds + recovery_shreds:
            shred.total_shreds = total_shreds
            shred.original_data_shred_count = self.original_data_shred_count
        
        return data_shreds + recovery_shreds
    
    def _generate_recovery_shreds(self, data_shreds: List[Shred], block_hash: str) -> List[Shred]:
        """
        Generate recovery shreds using improved erasure coding.
        
        This implements a more robust erasure coding scheme that provides
        better fault tolerance and reconstruction capabilities.
        """
        num_recovery = max(1, int(len(data_shreds) * self.redundancy_ratio))
        recovery_shreds = []
        
        # Improved erasure coding using systematic approach
        for i in range(num_recovery):
            recovery_data = bytearray(self.shred_size)
            
            # Use rotating XOR pattern for better distribution
            for j, data_shred in enumerate(data_shreds):
                # Apply different XOR patterns for each recovery shred
                pattern_offset = (i * 7 + j * 3) % len(data_shred.data)
                
                for k in range(len(data_shred.data)):
                    # Rotate the XOR pattern to create diverse recovery data
                    source_index = (k + pattern_offset) % len(data_shred.data)
                    recovery_data[k] ^= data_shred.data[source_index]
                
                # Apply additional mixing based on shred index
                mixing_factor = (j + 1) * (i + 1)
                for k in range(0, len(recovery_data), 4):
                    if k + 3 < len(recovery_data):
                        # Mix bytes using the shred indices
                        recovery_data[k] ^= (mixing_factor >> 24) & 0xFF
                        recovery_data[k+1] ^= (mixing_factor >> 16) & 0xFF
                        recovery_data[k+2] ^= (mixing_factor >> 8) & 0xFF
                        recovery_data[k+3] ^= mixing_factor & 0xFF
            
            # Add block hash signature to recovery data for integrity
            hash_bytes = bytes.fromhex(block_hash)[:min(32, len(recovery_data))]
            for j in range(len(hash_bytes)):
                recovery_data[j] ^= hash_bytes[j]
            
            recovery_shred = Shred(
                index=len(data_shreds) + i,
                total_shreds=0,  # Will be set later
                data=bytes(recovery_data),
                is_data_shred=False,
                block_hash=block_hash,
                original_data_shred_count=None  # Will be set later
            )
            recovery_shreds.append(recovery_shred)
        
        return recovery_shreds
    
    def reconstruct_block(self, shreds: List[Shred]):
        """
        Reconstruct a block from received shreds using Reed-Solomon style reconstruction.
        
        Args:
            shreds: List of received shreds
            
        Returns:
            Reconstructed block data or None if insufficient shreds
        """
        if not shreds:
            return None
        
        # Separate data and recovery shreds
        data_shreds = [s for s in shreds if s.is_data_shred]
        recovery_shreds = [s for s in shreds if not s.is_data_shred]
        
        # Sort data shreds by index
        data_shreds.sort(key=lambda x: x.index)
        
        # Calculate expected number of data shreds based on Reed-Solomon properties
        # Use the original_data_shred_count from the shred itself (set by leader)
        total_shreds = shreds[0].total_shreds
        
        if shreds[0].original_data_shred_count is not None:
            expected_data_shreds = shreds[0].original_data_shred_count
            print(f"DEBUG reconstruct_block: Using shred's original_data_shred_count: {expected_data_shreds}")
        elif hasattr(self, 'original_data_shred_count') and self.original_data_shred_count:
            expected_data_shreds = self.original_data_shred_count
            print(f"DEBUG reconstruct_block: Using local original_data_shred_count: {expected_data_shreds}")
        else:
            # Fallback to calculation (should rarely be used now)
            expected_data_shreds = round(total_shreds / (1 + self.redundancy_ratio))
            print(f"DEBUG reconstruct_block: Using calculated expected_data_shreds: {expected_data_shreds}")
        
        print(f"DEBUG reconstruct_block: Total shreds available: {len(shreds)}, Expected data shreds: {expected_data_shreds}")
        print(f"DEBUG reconstruct_block: Data shreds: {len(data_shreds)}, Recovery shreds: {len(recovery_shreds)}")
        
        # Reed-Solomon rule: Need at least as many shreds as original data shreds
        # Can be any combination of data + recovery shreds
        if len(shreds) >= expected_data_shreds:
            # Try direct reconstruction first if we have enough consecutive data shreds
            if len(data_shreds) >= expected_data_shreds and self._has_consecutive_data_shreds(data_shreds, expected_data_shreds):
                return self._reconstruct_from_data_shreds(data_shreds, expected_data_shreds)
            elif len(shreds) >= expected_data_shreds:
                return self._reconstruct_with_erasure_coding(data_shreds, recovery_shreds, expected_data_shreds)
        
        return None
    
    def _has_consecutive_data_shreds(self, data_shreds: List[Shred], expected_count: int) -> bool:
        """Check if we have consecutive data shreds from 0 to expected_count-1"""
        if len(data_shreds) < expected_count:
            return False
        
        indices = [s.index for s in data_shreds]
        return all(i in indices for i in range(expected_count))
    
    def _reconstruct_from_data_shreds(self, data_shreds: List[Shred], expected_count: int):
        """Reconstruct block from data shreds only"""
        if len(data_shreds) < expected_count:
            return None
        
        # Concatenate data from shreds
        block_data = b''
        for i in range(expected_count):
            shred = next((s for s in data_shreds if s.index == i), None)
            if shred is None:
                return None
            block_data += shred.data
        
        # Remove padding and deserialize
        block_data = block_data.rstrip(b'\x00')
        
        try:
            block_dict = json.loads(block_data.decode())
            return block_dict
        except Exception as e:
            return None
    
    def _reconstruct_with_erasure_coding(self, data_shreds: List[Shred], recovery_shreds: List[Shred], expected_count: int):
        """
        Reconstruct missing data shreds using recovery shreds with improved algorithm.
        
        This implements the reverse of the improved erasure coding to recover
        missing data shreds from available recovery shreds.
        """
        if len(data_shreds) + len(recovery_shreds) < expected_count:
            return None
        
        # Create a map of available data shreds
        available_data = {shred.index: shred for shred in data_shreds}
        missing_indices = [i for i in range(expected_count) if i not in available_data]
        
        if not missing_indices or not recovery_shreds:
            # Try direct reconstruction if we have enough data shreds
            return self._reconstruct_from_data_shreds(data_shreds, expected_count)
        
        # Attempt to recover missing data shreds using recovery shreds
        # This is a simplified recovery algorithm - in production, use Reed-Solomon
        
        # For each missing data shred, try to reconstruct using recovery data
        for missing_index in missing_indices[:len(recovery_shreds)]:
            if missing_index >= expected_count:
                continue
                
            # Use the first available recovery shred to reconstruct
            recovery_shred = recovery_shreds[0]
            reconstructed_data = bytearray(recovery_shred.data)
            
            # Reverse the erasure coding process
            # XOR with all available data shreds
            for available_shred in data_shreds:
                pattern_offset = (0 * 7 + available_shred.index * 3) % len(available_shred.data)
                
                for k in range(len(available_shred.data)):
                    source_index = (k + pattern_offset) % len(available_shred.data)
                    reconstructed_data[k] ^= available_shred.data[source_index]
                
                # Remove the mixing factor
                mixing_factor = (available_shred.index + 1) * (0 + 1)
                for k in range(0, len(reconstructed_data), 4):
                    if k + 3 < len(reconstructed_data):
                        reconstructed_data[k] ^= (mixing_factor >> 24) & 0xFF
                        reconstructed_data[k+1] ^= (mixing_factor >> 16) & 0xFF
                        reconstructed_data[k+2] ^= (mixing_factor >> 8) & 0xFF
                        reconstructed_data[k+3] ^= mixing_factor & 0xFF
            
            # Remove block hash signature
            block_hash = recovery_shreds[0].block_hash
            hash_bytes = bytes.fromhex(block_hash)[:min(32, len(reconstructed_data))]
            for j in range(len(hash_bytes)):
                reconstructed_data[j] ^= hash_bytes[j]
            
            # Create reconstructed shred
            reconstructed_shred = Shred(
                index=missing_index,
                total_shreds=recovery_shred.total_shreds,
                data=bytes(reconstructed_data),
                is_data_shred=True,
                block_hash=block_hash,
                original_data_shred_count=recovery_shred.original_data_shred_count
            )
            
            # Add to available data
            available_data[missing_index] = reconstructed_shred
            data_shreds.append(reconstructed_shred)
            
            # Check if we now have enough data shreds
            if len(available_data) >= expected_count:
                break
        
        # Try reconstruction again with recovered shreds
        return self._reconstruct_from_data_shreds(data_shreds, expected_count)

class TurbinePropagationTree:
    """Manages the tree structure for Turbine block propagation"""
    
    def __init__(self, fanout: int = 200):
        self.fanout = fanout
        self.nodes = {}  # node_id -> node_info
        self.tree_structure = {}  # node_id -> [child_node_ids]
    
    def register_node(self, node_id: str, stake_weight: float = 1.0, network_address: str = None):
        """Register a node in the propagation tree"""
        self.nodes[node_id] = {
            'stake_weight': stake_weight,
            'network_address': network_address,
            'children': []
        }
        self._rebuild_tree()
    
    def _rebuild_tree(self):
        """Rebuild the propagation tree based on stake weights"""
        if not self.nodes:
            return
        
        # Sort nodes by stake weight (descending)
        sorted_nodes = sorted(self.nodes.items(), key=lambda x: x[1]['stake_weight'], reverse=True)
        
        # Build tree structure
        self.tree_structure = {node_id: [] for node_id, _ in sorted_nodes}
        
        # Assign children based on fanout
        for i, (parent_id, _) in enumerate(sorted_nodes):
            start_child = i * self.fanout + 1
            end_child = min(start_child + self.fanout, len(sorted_nodes))
            
            for j in range(start_child, end_child):
                if j < len(sorted_nodes):
                    child_id = sorted_nodes[j][0]
                    self.tree_structure[parent_id].append(child_id)
                    self.nodes[parent_id]['children'].append(child_id)
    
    def get_children(self, node_id: str) -> List[str]:
        """Get the children of a node in the propagation tree"""
        return self.tree_structure.get(node_id, [])
    
    def get_propagation_path(self, from_node: str) -> List[str]:
        """Get the propagation path from a node to all its descendants"""
        path = []
        to_visit = [from_node]
        
        while to_visit:
            current = to_visit.pop(0)
            if current != from_node:
                path.append(current)
            children = self.get_children(current)
            to_visit.extend(children)
        
        return path

class TurbineProtocol:
    """Main Turbine protocol implementation for block propagation"""
    
    def __init__(self, fanout: int = 200, shred_size: int = 1024):
        self.shredder = BlockShredder(shred_size=shred_size)
        self.propagation_tree = TurbinePropagationTree(fanout=fanout)
        self.received_shreds = {}  # block_hash -> List[Shred]
        self.reconstructed_blocks = {}  # block_hash -> block_data
    
    def register_validator(self, validator_id: str, stake_weight: float = 1.0, network_address: str = None):
        """Register a validator in the Turbine network"""
        self.propagation_tree.register_node(validator_id, stake_weight, network_address)
    
    def broadcast_block(self, block, leader_id: str) -> List[Dict]:
        """
        Broadcast a block using Turbine protocol.
        
        In proper Turbine, all validators eventually receive all shreds through gossip.
        This simulates the gossip propagation by sending all shreds to all validators.
        
        Returns list of transmission tasks for the network layer.
        """
        # Shred the block
        shreds = self.shredder.shred_block(block)
        
        # Get direct children of the leader
        children = self.propagation_tree.get_children(leader_id)
        
        # In Turbine, shreds are gossiped across the network so all validators
        # eventually receive all shreds. For simulation, send all shreds to all children.
        transmission_tasks = []
        for child_id in children:
            transmission_tasks.append({
                'target_node': child_id,
                'shreds': shreds,  # Send ALL shreds to each validator
                'action': 'send_shreds'
            })
        
        return transmission_tasks
    
    def receive_shred(self, shred: Shred, receiving_node_id: str) -> List[Dict]:
        """
        Process a received shred and forward it if necessary.
        
        Returns list of forwarding tasks.
        """
        block_hash = shred.block_hash
        
        # Store the shred
        if block_hash not in self.received_shreds:
            self.received_shreds[block_hash] = []
        self.received_shreds[block_hash].append(shred)
        
        # Try to reconstruct the block
        if block_hash not in self.reconstructed_blocks:
            reconstructed = self.shredder.reconstruct_block(self.received_shreds[block_hash])
            if reconstructed:
                self.reconstructed_blocks[block_hash] = reconstructed
        
        # Forward the shred to children
        children = self.propagation_tree.get_children(receiving_node_id)
        forwarding_tasks = []
        
        for child_id in children:
            forwarding_tasks.append({
                'target_node': child_id,
                'shreds': [shred],
                'action': 'forward_shred'
            })
        
        return forwarding_tasks
    
    def get_block_reconstruction_status(self, block_hash: str) -> Dict:
        """Get the status of block reconstruction"""
        received_count = len(self.received_shreds.get(block_hash, []))
        is_reconstructed = block_hash in self.reconstructed_blocks
        
        return {
            'block_hash': block_hash,
            'shreds_received': received_count,
            'is_reconstructed': is_reconstructed,
            'block_data': self.reconstructed_blocks.get(block_hash)
        }
