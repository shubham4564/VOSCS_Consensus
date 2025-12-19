import time
import hashlib
from typing import List, Dict, Optional
from blockchain.utils.logger import logger


class LeaderSchedule:
    """
    Solana-style leader schedule that pre-determines block proposers for extended periods.
    Similar to Solana's epoch system but adapted for quantum consensus.
    """
    
    def __init__(self, epoch_duration_hours=24):
        # Updated configuration as requested
        self.epoch_duration_seconds = 600  # 600 seconds (10 minutes)
        self.slot_duration_seconds = 0.45  # 450ms per slot for leader block production
        self.slots_per_epoch = int(self.epoch_duration_seconds / self.slot_duration_seconds)  # ~1333 slots per epoch
        self.leader_advance_time = 600  # Leaders known 600 seconds (10 minutes) in advance
        
        # Current epoch data
        self.current_epoch = 0
        self.epoch_start_time = time.time()
        self.current_schedule = {}  # slot_number -> leader_public_key
        self.next_schedule = {}     # Pre-computed next epoch schedule
        
        # Gulf Stream forwarding data
        self.gulf_stream_cache = {}  # Cache of upcoming leaders for forwarding
        self.last_schedule_update = 0
        
        logger.info({
            "message": "Leader schedule initialized",
            "epoch_duration_seconds": self.epoch_duration_seconds,
            "slot_duration_seconds": self.slot_duration_seconds,
            "slots_per_epoch": self.slots_per_epoch,
            "leader_advance_time_seconds": self.leader_advance_time
        })
    
    def generate_epoch_schedule(self, epoch_number: int, quantum_consensus, seed_hash: str) -> Dict[int, str]:
        """
        Generate leader schedule for an entire epoch using quantum consensus.
        Similar to Solana's leader selection but using our quantum annealing.
        """
        schedule = {}
        
        # Use epoch number and seed to create deterministic but unpredictable schedule
        epoch_seed = f"{epoch_number}_{seed_hash}"
        
        logger.info({
            "message": "Generating epoch leader schedule",
            "epoch": epoch_number,
            "slots_to_schedule": self.slots_per_epoch,
            "seed": epoch_seed[:32] + "..."
        })
        
        # Get all registered nodes for this epoch
        registered_nodes = list(quantum_consensus.nodes.keys()) if quantum_consensus.nodes else []
        
        if not registered_nodes:
            logger.warning("No registered nodes for leader schedule generation")
            return schedule
        
        # CRITICAL FIX: Get viable leaders (nodes with good scores)
        viable_leaders = []
        for node_id in registered_nodes:
            try:
                # Check if node has good effective score (>0.1 threshold)
                node_metrics = quantum_consensus.get_consensus_metrics()
                node_scores = node_metrics.get('node_scores', {})
                if node_id in node_scores:
                    effective_score = node_scores[node_id].get('effective_score', 0)
                    if effective_score > 0.1:  # Viable leader threshold
                        viable_leaders.append(node_id)
            except:
                # If scoring fails, include all nodes as fallback
                viable_leaders = registered_nodes
                break
        
        # Use viable leaders if available, otherwise fallback to all nodes
        leader_pool = viable_leaders if viable_leaders else registered_nodes
        
        logger.info({
            "message": "Leader pool analysis",
            "total_registered": len(registered_nodes),
            "viable_leaders": len(leader_pool),
            "leader_pool": [node[:20] + "..." for node in leader_pool[:3]]
        })
        
        # Generate schedule for each slot in the epoch
        for slot in range(self.slots_per_epoch):
            # Create unique seed for each slot
            slot_seed = hashlib.sha256(f"{epoch_seed}_{slot}".encode()).hexdigest()
            
            # CRITICAL FIX: Try quantum selection first, then fallback to viable leaders
            selected_leader = quantum_consensus.select_representative_node(slot_seed)
            
            if selected_leader and selected_leader in leader_pool:
                # Use quantum-selected leader if viable
                schedule[slot] = selected_leader
            elif leader_pool:
                # Fallback to round-robin from viable leaders
                schedule[slot] = leader_pool[slot % len(leader_pool)]
            else:
                # Final fallback to any registered node
                schedule[slot] = registered_nodes[slot % len(registered_nodes)]
        
        logger.info({
            "message": "Epoch leader schedule generated",
            "epoch": epoch_number,
            "total_slots": len(schedule),
            "unique_leaders": len(set(schedule.values())),
            "sample_leaders": [schedule[i][:20] + "..." for i in range(min(5, len(schedule)))]
        })
        
        return schedule
    
    def get_current_slot(self) -> int:
        """Get the current slot number within the current epoch"""
        current_time = time.time()
        time_in_epoch = current_time - self.epoch_start_time
        return int(time_in_epoch // self.slot_duration_seconds)
    
    def get_current_leader(self) -> Optional[str]:
        """Get the leader for the current slot"""
        current_slot = self.get_current_slot()
        return self.current_schedule.get(current_slot)
    
    def get_upcoming_leaders(self, num_slots: int = 200) -> List[tuple]:
        """
        Get upcoming leaders for the next N slots (default 200 = minimum buffer for Gulf Stream).
        Must maintain at least 200 slots ahead for proper transaction forwarding.
        Returns list of (slot_number, leader_public_key, absolute_time) tuples.
        Critical for Gulf Stream forwarding - transactions forwarded to upcoming leaders.
        """
        current_slot = self.get_current_slot()
        upcoming = []
        
        for i in range(1, num_slots + 1):
            future_slot = current_slot + i
            future_time = self.epoch_start_time + (future_slot * self.slot_duration_seconds)
            
            # Check if we're still in current epoch
            if future_slot < self.slots_per_epoch:
                leader = self.current_schedule.get(future_slot)
            else:
                # We've moved to next epoch
                next_epoch_slot = future_slot - self.slots_per_epoch
                leader = self.next_schedule.get(next_epoch_slot)
            
            if leader:
                upcoming.append((future_slot, leader, future_time))
        
        return upcoming
    
    def get_leader_for_time(self, target_time: float) -> Optional[str]:
        """
        Get the leader who will be active at a specific future time.
        Used for Gulf Stream transaction forwarding.
        """
        time_offset = target_time - self.epoch_start_time
        target_slot = int(time_offset // self.slot_duration_seconds)
        
        if target_slot < self.slots_per_epoch:
            return self.current_schedule.get(target_slot)
        else:
            # Next epoch
            next_epoch_slot = target_slot - self.slots_per_epoch
            return self.next_schedule.get(next_epoch_slot)
    
    def get_gulf_stream_targets(self) -> List[Dict]:
        """
        Get upcoming leaders for Gulf Stream forwarding with minimum 200 slot buffer.
        Ensures leaders have sufficient advance notice to prepare for transaction processing.
        Returns detailed info needed for transaction forwarding via TPU.
        """
        current_time = time.time()
        # Minimum 200 slots ahead to ensure proper forwarding buffer
        upcoming_leaders = self.get_upcoming_leaders(200)
        
        gulf_stream_targets = []
        for slot, leader, slot_time in upcoming_leaders:
            if slot_time > current_time:  # Only future slots
                gulf_stream_targets.append({
                    'slot': slot,
                    'leader': leader,
                    'slot_start_time': slot_time,
                    'slot_end_time': slot_time + self.slot_duration_seconds,
                    'time_until_slot': slot_time - current_time,
                    'tpu_port': self._calculate_tpu_port(leader)  # TPU port for direct forwarding
                })
        
        return gulf_stream_targets
    
    def should_forward_to_leader(self, leader_public_key: str, current_time: float) -> bool:
        """
        Check if transactions should be forwarded to this leader via TPU.
        Must ensure minimum 200 slot buffer before leader's turn.
        """
        upcoming_targets = self.get_gulf_stream_targets()
        
        for target in upcoming_targets:
            if target['leader'] == leader_public_key:
                # Ensure at least 200 slots (90 seconds) advance notice
                min_advance_time = 200 * self.slot_duration_seconds  # 200 * 0.45 = 90 seconds
                return target['time_until_slot'] >= min_advance_time
        
        return False
    
    def _calculate_tpu_port(self, leader_public_key: str) -> int:
        """
        Calculate TPU port for a leader based on their public key.
        TPU ports are used for direct transaction forwarding via UDP.
        """
        import hashlib
        key_hash = hashlib.sha256(leader_public_key.encode()).hexdigest()
        port_offset = int(key_hash[:8], 16) % 100  # 100 available TPU ports
        return 13000 + port_offset  # TPU port range: 13000-13099
    
    def is_epoch_transition_needed(self) -> bool:
        """Check if we need to transition to the next epoch"""
        current_slot = self.get_current_slot()
        return current_slot >= self.slots_per_epoch
    
    def transition_to_next_epoch(self):
        """Transition to the next epoch and update schedules"""
        self.current_epoch += 1
        self.epoch_start_time = time.time()
        self.current_schedule = self.next_schedule.copy()
        self.next_schedule = {}
        
        logger.info({
            "message": "Transitioned to next epoch",
            "new_epoch": self.current_epoch,
            "epoch_start_time": self.epoch_start_time,
            "current_schedule_size": len(self.current_schedule)
        })
    
    def update_schedule(self, quantum_consensus):
        """
        Update the leader schedule, handling epoch transitions.
        Should be called periodically by the blockchain.
        """
        # Check if we need to transition epochs
        if self.is_epoch_transition_needed():
            self.transition_to_next_epoch()
        
        # Generate next epoch schedule if we don't have it
        if not self.next_schedule:
            next_epoch = self.current_epoch + 1
            # Use current blockchain state as seed for next epoch
            seed_hash = hashlib.sha256(f"epoch_{next_epoch}_{time.time()}".encode()).hexdigest()
            self.next_schedule = self.generate_epoch_schedule(next_epoch, quantum_consensus, seed_hash)
        
        # Generate current epoch schedule if we don't have it (initialization)
        if not self.current_schedule:
            seed_hash = hashlib.sha256(f"epoch_{self.current_epoch}_{self.epoch_start_time}".encode()).hexdigest()
            self.current_schedule = self.generate_epoch_schedule(self.current_epoch, quantum_consensus, seed_hash)
    
    def get_schedule_info(self) -> Dict:
        """Get detailed information about current schedule state"""
        current_slot = self.get_current_slot()
        current_leader = self.get_current_leader()
        upcoming = self.get_upcoming_leaders(3)
        
        return {
            "current_epoch": self.current_epoch,
            "current_slot": current_slot,
            "slots_per_epoch": self.slots_per_epoch,
            "current_leader": current_leader[:30] + "..." if current_leader else None,
            "upcoming_leaders": [
                {
                    "slot": slot,
                    "leader": leader[:20] + "...",
                    "time_seconds": abs_time - time.time()
                }
                for slot, leader, abs_time in upcoming
            ],
            "epoch_progress": f"{current_slot}/{self.slots_per_epoch}",
            "schedule_health": {
                "current_schedule_size": len(self.current_schedule),
                "next_schedule_ready": len(self.next_schedule) > 0,
                "epoch_transition_needed": self.is_epoch_transition_needed()
            }
        }
