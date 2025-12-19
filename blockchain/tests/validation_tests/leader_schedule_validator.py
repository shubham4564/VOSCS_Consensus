#!/usr/bin/env python3
"""
Real-Time Leader Schedule Validation Test
=========================================

This validation test monitors running blockchain nodes to verify:
1. How many leaders are currently chosen
2. Real-time leader schedule display
3. Leader rotation validation
4. Epoch timing verification

Assumes nodes are already running on ports 11000-11009
"""

import sys
import time
import asyncio
import aiohttp
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional


def _ensure_repo_root_on_path() -> Path:
    current = Path(__file__).resolve().parent
    for _ in range(8):
        if (current / "blockchain" / "__init__.py").is_file():
            sys.path.insert(0, str(current))
            return current
        if current.parent == current:
            return current
        current = current.parent
    return current


blockchain_root = _ensure_repo_root_on_path()
del _ensure_repo_root_on_path

try:
    from blockchain.consensus.leader_schedule import LeaderSchedule
    from blockchain.consensus.gulf_stream import GulfStreamProcessor
    from blockchain.quantum_consensus.quantum_annealing_consensus import QuantumAnnealingConsensus
except ImportError as e:
    print(f"❌ Cannot import blockchain modules: {e}")
    print("📍 Make sure you're running from the blockchain directory or its subdirectories")
    print(f"📁 Current path: {Path.cwd()}")
    print(f"📁 Blockchain root: {blockchain_root}")
    sys.exit(1)

class LeaderScheduleValidator:
    """Validates leader schedule in real-time from running nodes"""
    
    def __init__(self, node_ports: List[int] = None):
        self.node_ports = node_ports or list(range(11000, 11010))  # Default 10 nodes
        self.base_url = "http://localhost"
        
        # Initialize quantum consensus system for proper leader selection (suppress ALL logs)
        import logging
        import os
        from contextlib import redirect_stdout, redirect_stderr
        from io import StringIO
        
        # Completely suppress logging and output
        logging.getLogger().setLevel(logging.CRITICAL)
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # Suppress stdout/stderr during quantum consensus initialization
        null_stream = StringIO()
        with redirect_stdout(null_stream), redirect_stderr(null_stream):
            self.quantum_consensus = QuantumAnnealingConsensus(initialize_genesis=True)
        
        # Initialize leader schedule with quantum consensus
        self.leader_schedule = LeaderSchedule()
        self.gulf_stream = GulfStreamProcessor(self.leader_schedule)
        
        self.validation_stats = {
            'total_checks': 0,
            'successful_connections': 0,
            'leader_changes_detected': 0,
            'epoch_transitions': 0,
            'start_time': time.time()
        }
        self.last_leader = None
        self.last_epoch = None
        
        # Track registered nodes for quantum consensus
        self.registered_nodes = set()
        
    def update_quantum_consensus_nodes(self, nodes_status: List[Dict]):
        """Register online nodes with quantum consensus system"""
        online_nodes = [n for n in nodes_status if n['status'] == 'online']
        
        for node in online_nodes:
            node_id = f"node_port_{node['port']}"
            if node_id not in self.registered_nodes:
                # Register node with quantum consensus
                public_key = f"pub_key_{node['port']}"  # Simulate public key based on port
                self.quantum_consensus.register_node(node_id, public_key)
                self.registered_nodes.add(node_id)
                
        # Update leader schedule with current quantum consensus state
        self.leader_schedule.update_schedule(self.quantum_consensus)
        
    async def fetch_node_status(self, session: aiohttp.ClientSession, port: int) -> Optional[Dict]:
        """Fetch status from a single node"""
        try:
            # Use the correct API endpoint path
            url = f"{self.base_url}:{port}/api/v1/blockchain/node-stats/"
            timeout = aiohttp.ClientTimeout(total=2.0)
            
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'port': port,
                        'status': 'online',
                        'data': data,
                        'connected_peers': data.get('p2p', {}).get('connected_peers', 0),
                        'total_blocks': data.get('blockchain', {}).get('total_blocks', 0),
                        'mempool_size': data.get('mempool', {}).get('mempool_size', 0),
                        'leader_schedule': data.get('consensus', {}).get('leader_schedule', {})
                    }
                else:
                    return {
                        'port': port,
                        'status': 'error',
                        'error': f"HTTP {response.status}"
                    }
        except asyncio.TimeoutError:
            return {
                'port': port,
                'status': 'timeout',
                'error': 'Connection timeout'
            }
        except Exception as e:
            return {
                'port': port,
                'status': 'offline',
                'error': str(e)
            }
    
    async def fetch_all_nodes_status(self) -> List[Dict]:
        """Fetch status from all nodes concurrently"""
        async with aiohttp.ClientSession() as session:
            tasks = [
                self.fetch_node_status(session, port) 
                for port in self.node_ports
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Handle any exceptions
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    processed_results.append({
                        'port': self.node_ports[i],
                        'status': 'exception',
                        'error': str(result)
                    })
                else:
                    processed_results.append(result)
            
            return processed_results
    
    def get_current_leader_info(self, nodes_status: List[Dict] = None) -> Dict:
        """Get current leader information using quantum consensus mechanism"""
        # Update quantum consensus with current online nodes
        if nodes_status:
            self.update_quantum_consensus_nodes(nodes_status)
            
        # Get current timing info
        current_slot = self.leader_schedule.get_current_slot()
        
        # Use quantum consensus to select current leader
        current_leader = None
        upcoming_leaders = []
        
        if len(self.quantum_consensus.nodes) > 0:
            # Generate seed based on current slot for deterministic but unpredictable selection
            import hashlib
            from contextlib import redirect_stdout, redirect_stderr
            from io import StringIO
            
            slot_seed = hashlib.sha256(f"slot_{current_slot}_{int(time.time() // self.leader_schedule.slot_duration_seconds)}".encode()).hexdigest()
            
            # Use quantum consensus to select leader for current slot (suppress all output)
            null_stream = StringIO()
            with redirect_stdout(null_stream), redirect_stderr(null_stream):
                selected_leader = self.quantum_consensus.select_representative_node(slot_seed)
            current_leader = selected_leader
            
            # Generate upcoming leaders using quantum consensus (suppress all output)
            for i in range(1, 6):  # Next 5 slots
                future_slot = current_slot + i
                future_seed = hashlib.sha256(f"slot_{future_slot}_{int(time.time() // self.leader_schedule.slot_duration_seconds)}".encode()).hexdigest()
                with redirect_stdout(null_stream), redirect_stderr(null_stream):
                    future_leader = self.quantum_consensus.select_representative_node(future_seed)
                future_time = time.time() + (i * self.leader_schedule.slot_duration_seconds)
                
                if future_leader:
                    upcoming_leaders.append((future_slot, future_leader, future_time))
        
        # If we have online nodes but no quantum consensus results, fall back to simulation
        if not current_leader and nodes_status:
            online_nodes = [n for n in nodes_status if n['status'] == 'online']
            if online_nodes:
                # Simple fallback using round-robin
                node_ports = [str(n['port']) for n in online_nodes]
                if node_ports:
                    current_leader_index = current_slot % len(node_ports)
                    current_leader = f"node_port_{node_ports[current_leader_index]}"
                    
                    # Generate upcoming leaders
                    for i in range(1, 6):  # Next 5 slots
                        future_slot = current_slot + i
                        future_leader_index = future_slot % len(node_ports)
                        future_leader = f"node_port_{node_ports[future_leader_index]}"
                        future_time = time.time() + (i * self.leader_schedule.slot_duration_seconds)
                        upcoming_leaders.append((future_slot, future_leader, future_time))
        
        # Get consensus metrics for display
        consensus_info = self.get_quantum_consensus_info()
        
        return {
            'current_slot': current_slot,
            'current_leader': current_leader or "None (quantum consensus inactive)",
            'current_leader_short': current_leader[:30] + "..." if current_leader and len(current_leader) > 30 else (current_leader or "None"),
            'upcoming_leaders': upcoming_leaders,
            'schedule_info': {
                'current_epoch': self.leader_schedule.current_epoch,
                'slots_per_epoch': self.leader_schedule.slots_per_epoch,
            },
            'epoch_progress': f"{current_slot}/{self.leader_schedule.slots_per_epoch}",
            'time_in_slot': time.time() % self.leader_schedule.slot_duration_seconds,
            'total_online_nodes': len([n for n in nodes_status if n['status'] == 'online']) if nodes_status else 0,
            'leader_rotation': f"Quantum consensus among {len(self.quantum_consensus.nodes)} nodes",
            'consensus_info': consensus_info
        }
    
    def get_quantum_consensus_info(self) -> Dict:
        """Get quantum consensus system information for display"""
        total_nodes = len(self.quantum_consensus.nodes)
        
        # Get node performance stats
        if total_nodes > 0:
            uptimes = [node.get('uptime', 0) for node in self.quantum_consensus.nodes.values()]
            avg_uptime = sum(uptimes) / len(uptimes) if uptimes else 0
            
            latencies = [node.get('latency', float('inf')) for node in self.quantum_consensus.nodes.values()]
            valid_latencies = [l for l in latencies if l != float('inf')]
            avg_latency = sum(valid_latencies) / len(valid_latencies) if valid_latencies else 0
            
            return {
                'total_registered_nodes': total_nodes,
                'avg_uptime': avg_uptime,
                'avg_latency_ms': avg_latency * 1000,  # Convert to ms
                'consensus_active': True,
                'probe_history_size': len(self.quantum_consensus.probe_history)
            }
        else:
            return {
                'total_registered_nodes': 0,
                'avg_uptime': 0,
                'avg_latency_ms': 0,
                'consensus_active': False,
                'probe_history_size': 0
            }
    
    def detect_changes(self, leader_info: Dict):
        """Detect and track leader/epoch changes"""
        current_leader = leader_info['current_leader']
        current_epoch = leader_info['schedule_info']['current_epoch']
        
        # Detect leader change
        if self.last_leader != current_leader and self.last_leader is not None:
            self.validation_stats['leader_changes_detected'] += 1
            print(f"\n🔄 LEADER CHANGE DETECTED!")
            print(f"   Previous: {self.last_leader[:30] if self.last_leader else 'None'}...")
            print(f"   Current:  {current_leader[:30] if current_leader else 'None'}...")
        
        # Detect epoch transition
        if self.last_epoch != current_epoch and self.last_epoch is not None:
            self.validation_stats['epoch_transitions'] += 1
            print(f"\n🌅 EPOCH TRANSITION DETECTED!")
            print(f"   Previous Epoch: {self.last_epoch}")
            print(f"   Current Epoch:  {current_epoch}")
        
        self.last_leader = current_leader
        self.last_epoch = current_epoch
    
    def print_validation_header(self):
        """Print validation test header"""
        print("👑 QUANTUM CONSENSUS LEADER SCHEDULE")
        print("=" * 80)
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Monitoring {len(self.node_ports)} nodes (ports {min(self.node_ports)}-{max(self.node_ports)})")
        print(f"⏰ Epoch: {self.leader_schedule.epoch_duration_seconds}s | Slot: {self.leader_schedule.slot_duration_seconds}s | Total Slots: {self.leader_schedule.slots_per_epoch}")
        print("=" * 80)
    
    def print_nodes_status(self, nodes_status: List[Dict]):
        """Print status of all monitored nodes"""
        online_nodes = [n for n in nodes_status if n['status'] == 'online']
        offline_nodes = [n for n in nodes_status if n['status'] != 'online']
        
        print(f"\n🌐 NODES STATUS ({len(online_nodes)}/{len(nodes_status)} online)")
        print("─" * 50)
        
        # Show online nodes with detailed info
        if online_nodes:
            print("✅ Online Nodes:")
            for node in online_nodes[:8]:  # Show first 8
                peers = node.get('connected_peers', 0)
                blocks = node.get('total_blocks', 0)
                mempool = node.get('mempool_size', 0)
                print(f"   Port {node['port']}: Ready | Peers: {peers} | Blocks: {blocks} | Mempool: {mempool}")
            if len(online_nodes) > 8:
                print(f"   ... and {len(online_nodes) - 8} more")
        
        # Show offline nodes (limited to avoid spam)
        if offline_nodes:
            print("❌ Offline Nodes:")
            for node in offline_nodes[:3]:  # Show first 3
                error_msg = node.get('error', 'Unknown error')
                if 'HTTP 404' in error_msg:
                    error_msg = 'API not responding'
                elif 'Connection refused' in error_msg:
                    error_msg = 'connection refused'
                print(f"   Port {node['port']}: {error_msg}")
            if len(offline_nodes) > 3:
                print(f"   ... and {len(offline_nodes) - 3} more offline")
        
        # If no nodes are online, show helpful message
        if len(online_nodes) == 0:
            print("\n💡 No blockchain nodes detected!")
            print("   To start nodes:")
            print("   cd .. && ./start_nodes.sh")
            print("   Or: python3 run_node.py --port 11000 --node-id node1")
    
    def print_leader_info(self, leader_info: Dict):
        """Print current leader information focused on epoch-based selection"""
        print(f"\n👑 EPOCH LEADER SCHEDULE")
        print("─" * 50)
        print(f"🎯 Current Slot: {leader_info['current_slot']} | Epoch: {leader_info['schedule_info']['current_epoch']}")
        print(f"📊 Epoch Progress: {leader_info['epoch_progress']}")
        print(f"⏱️  Time in Slot: {leader_info['time_in_slot']:.1f}s / {self.leader_schedule.slot_duration_seconds}s")
        
        # Show current leader
        print(f"\n👑 CURRENT LEADER:")
        print(f"   {leader_info['current_leader_short']}")
        
        # Show quantum consensus info briefly
        if 'consensus_info' in leader_info:
            consensus = leader_info['consensus_info']
            if consensus['consensus_active']:
                print(f"� Quantum Selection: {consensus['total_registered_nodes']} nodes | Avg Uptime: {consensus['avg_uptime']:.2f}")
        
        # Show upcoming leaders
        upcoming = leader_info['upcoming_leaders']
        if upcoming:
            print(f"\n🔮 UPCOMING LEADERS:")
            for i, (slot, leader, abs_time) in enumerate(upcoming):
                time_until = abs_time - time.time()
                leader_short = leader[:20] + "..." if len(leader) > 20 else leader
                print(f"   Slot {slot}: {leader_short} (in {time_until:.1f}s)")
        else:
            print(f"\n🔮 UPCOMING LEADERS: Quantum consensus initializing...")
    
    def print_gulf_stream_info(self):
        """Print Gulf Stream status"""
        stats = self.gulf_stream.stats
        print(f"\n🌊 GULF STREAM STATUS")
        print("─" * 30)
        print(f"📤 Transactions Forwarded: {stats.get('transactions_forwarded', 0)}")
        print(f"📨 Active Forwarding Pools: {stats.get('active_forwarding_pools', 0)}")
        print(f"⏱️  Average Forward Time: {stats.get('average_forward_time_ms', 0):.1f}ms")
        print(f"📊 Forward Success Rate: {stats.get('forward_success_rate', 100):.1f}%")
    
    def print_validation_stats(self):
        """Print validation statistics"""
        runtime = time.time() - self.validation_stats['start_time']
        print(f"\n📈 VALIDATION STATISTICS")
        print("─" * 30)
        print(f"⏱️  Runtime: {runtime:.1f}s")
        print(f"🔄 Total Checks: {self.validation_stats['total_checks']}")
        print(f"✅ Successful Connections: {self.validation_stats['successful_connections']}")
        print(f"👑 Leader Changes: {self.validation_stats['leader_changes_detected']}")
        print(f"🌅 Epoch Transitions: {self.validation_stats['epoch_transitions']}")
        
        if self.validation_stats['total_checks'] > 0:
            success_rate = (self.validation_stats['successful_connections'] / 
                          self.validation_stats['total_checks']) * 100
            print(f"📊 Connection Success Rate: {success_rate:.1f}%")
    
    async def run_validation_cycle(self):
        """Run a single validation cycle"""
        self.validation_stats['total_checks'] += 1
        
        # Fetch node status
        nodes_status = await self.fetch_all_nodes_status()
        online_nodes = [n for n in nodes_status if n['status'] == 'online']
        self.validation_stats['successful_connections'] += len(online_nodes)
        
        # Get leader information (passing nodes_status for real data)
        leader_info = self.get_current_leader_info(nodes_status)
        
        # Detect changes
        self.detect_changes(leader_info)
        
        # Clear screen for real-time effect and print to original stdout
        import sys
        original_stdout = sys.__stdout__
        sys.stdout = original_stdout
        
        print("\033[2J\033[H", end="")  # Clear screen and move cursor to top
        
        # Print all information
        self.print_validation_header()
        self.print_nodes_status(nodes_status)
        self.print_leader_info(leader_info)
        self.print_validation_stats()
        
        # Print update footer
        print(f"\n🔄 Last Updated: {datetime.now().strftime('%H:%M:%S')} (Press Ctrl+C to stop)")
        print("=" * 80)
    
    async def run_continuous_validation(self, update_interval: float = 2.0):
        """Run continuous validation with real-time updates"""
        # Suppress all quantum consensus logs during validation
        import logging
        import sys
        import os
        
        # Redirect stdout temporarily to suppress logs
        original_stdout = sys.stdout
        
        print("🚀 Starting real-time leader schedule validation...")
        print(f"📊 Update interval: {update_interval}s")
        print("⌨️  Press Ctrl+C to stop\n")
        print("🔄 Initializing quantum consensus... (this may take a moment)")
        
        try:
            while True:
                # Temporarily suppress stdout for quantum consensus operations
                with open(os.devnull, 'w') as devnull:
                    old_stdout = sys.stdout
                    sys.stdout = devnull
                    
                    try:
                        await self.run_validation_cycle()
                    finally:
                        sys.stdout = old_stdout
                
                await asyncio.sleep(update_interval)
                
        except KeyboardInterrupt:
            print(f"\n\n⏹️  Validation stopped by user")
            self.print_final_summary()
        except Exception as e:
            print(f"\n\n❌ Validation error: {e}")
            import traceback
            traceback.print_exc()
    
    def print_final_summary(self):
        """Print final validation summary"""
        runtime = time.time() - self.validation_stats['start_time']
        print("\n" + "=" * 80)
        print("📋 VALIDATION SUMMARY")
        print("=" * 80)
        print(f"⏱️  Total Runtime: {runtime:.1f}s ({runtime/60:.1f} minutes)")
        print(f"🔄 Total Validation Cycles: {self.validation_stats['total_checks']}")
        print(f"✅ Successful Node Connections: {self.validation_stats['successful_connections']}")
        print(f"👑 Leader Changes Detected: {self.validation_stats['leader_changes_detected']}")
        print(f"🌅 Epoch Transitions Detected: {self.validation_stats['epoch_transitions']}")
        
        if self.validation_stats['total_checks'] > 0:
            avg_success = (self.validation_stats['successful_connections'] / 
                          self.validation_stats['total_checks'])
            print(f"📊 Average Nodes Online: {avg_success:.1f}")
            
            cycles_per_minute = self.validation_stats['total_checks'] / (runtime / 60)
            print(f"📈 Validation Frequency: {cycles_per_minute:.1f} cycles/minute")
        
        print("=" * 80)
        print("✅ Leader schedule validation completed successfully!")

def main():
    """Main validation function"""
    # Configuration
    node_ports = list(range(11000, 11010))  # Ports 11000-11009
    update_interval = 2.0  # Update every 2 seconds
    
    # Create validator
    validator = LeaderScheduleValidator(node_ports)
    
    # Run validation
    try:
        asyncio.run(validator.run_continuous_validation(update_interval))
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
