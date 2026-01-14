#!/usr/bin/env python3
"""
Slot-based block production implementation for Solana-style timing
"""

import time
import threading
from blockchain.utils.logger import logger

class SlotBasedBlockProducer:
    """
    Manages slot-based block production similar to Solana.
    Ensures blocks are produced exactly at slot boundaries.
    """
    
    def __init__(self, node, slot_duration_seconds=10):
        self.node = node
        self.slot_duration_seconds = slot_duration_seconds
        self.running = False
        self.slot_thread = None
        self.last_slot_produced = -1
        
    def start_slot_production(self):
        """Start the slot-based block production timer"""
        if self.running:
            return
            
        self.running = True
        self.slot_thread = threading.Thread(target=self._slot_production_loop, daemon=True)
        self.slot_thread.start()
        
        logger.info({
            "message": "Slot-based block production started",
            "slot_duration_seconds": self.slot_duration_seconds
        })
    
    def stop_slot_production(self):
        """Stop the slot-based block production timer"""
        self.running = False
        if self.slot_thread:
            self.slot_thread.join(timeout=1.0)
        
        logger.info("Slot-based block production stopped")
    
    def _slot_production_loop(self):
        """Main loop that triggers block production at slot boundaries"""
        while self.running:
            try:
                current_slot = self.node.blockchain.leader_schedule.get_current_slot()
                current_leader = self.node.blockchain.leader_schedule.get_current_leader()
                my_public_key = self.node.wallet.public_key_string()

                def _norm(k: str) -> str:
                    return "".join(str(k or "").split())
                
                # Check if we should produce a block this slot
                if (current_slot != self.last_slot_produced and 
                    current_leader and _norm(current_leader) == _norm(my_public_key)):
                    
                    logger.info({
                        "message": "Slot boundary reached - attempting block production",
                        "slot": current_slot,
                        "leader": current_leader[:20] + "..." if current_leader else None,
                        "am_leader": True
                    })
                    
                    # Produce block for this slot
                    self._produce_block_for_slot(current_slot)
                    self.last_slot_produced = current_slot
                    
                elif current_slot != self.last_slot_produced:
                    logger.debug({
                        "message": "Slot boundary reached - not my turn",
                        "slot": current_slot,
                        "leader": current_leader[:20] + "..." if current_leader else None,
                        "am_leader": False
                    })
                
                # Wait until next slot boundary
                self._wait_for_next_slot()
                
            except Exception as e:
                logger.error(f"Error in slot production loop: {e}")
                time.sleep(1)  # Prevent tight error loop
    
    def _produce_block_for_slot(self, slot_number):
        """Produce a block for the given slot using node's proposer logic"""
        try:
            start_time = time.time()
            
            logger.info({
                "message": "Producing block for slot via node.propose_block",
                "slot": slot_number
            })
            
            # Delegate actual block creation to the node's proposer
            # This uses the Solana-style Gulf Stream + PoH pipeline
            self.node.propose_block()
            
            production_time = time.time() - start_time
            
            logger.info({
                "message": "Slot production attempt completed",
                "slot": slot_number,
                "production_time_ms": round(production_time * 1000, 2)
            })
            
        except Exception as e:
            logger.error({
                "message": "Failed to produce block for slot",
                "slot": slot_number,
                "error": str(e)
            })
    
    def _wait_for_next_slot(self):
        """Wait until the next slot boundary"""
        current_time = time.time()
        epoch_start = self.node.blockchain.leader_schedule.epoch_start_time
        time_in_epoch = current_time - epoch_start
        
        # Calculate time to next slot boundary
        current_slot_start = int(time_in_epoch // self.slot_duration_seconds) * self.slot_duration_seconds
        next_slot_start = current_slot_start + self.slot_duration_seconds
        time_to_next_slot = next_slot_start - time_in_epoch
        
        # Add small buffer to ensure we're past the boundary
        time_to_wait = time_to_next_slot + 0.1
        
        if time_to_wait > 0:
            time.sleep(min(time_to_wait, self.slot_duration_seconds))
    
    def get_slot_info(self):
        """Get current slot timing information"""
        current_slot = self.node.blockchain.leader_schedule.get_current_slot()
        current_leader = self.node.blockchain.leader_schedule.get_current_leader()
        
        current_time = time.time()
        epoch_start = self.node.blockchain.leader_schedule.epoch_start_time
        time_in_epoch = current_time - epoch_start
        time_in_slot = time_in_epoch % self.slot_duration_seconds
        time_remaining = self.slot_duration_seconds - time_in_slot
        
        return {
            "current_slot": current_slot,
            "current_leader": current_leader[:20] + "..." if current_leader else None,
            "time_in_slot_seconds": round(time_in_slot, 2),
            "time_remaining_seconds": round(time_remaining, 2),
            "slot_progress_percent": round((time_in_slot / self.slot_duration_seconds) * 100, 1),
            "last_slot_produced": self.last_slot_produced,
            "production_active": self.running
        }
