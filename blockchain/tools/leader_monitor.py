#!/usr/bin/env python3
"""
Leader Selection Monitor

This script demonstrates how to monitor current and upcoming leaders
through the blockchain API endpoints.

Usage:
    python tools/leader_monitor.py [base_port] [num_nodes]
    
Examples:
    python tools/leader_monitor.py 11000 5    # Monitor nodes 11000-11004
    python tools/leader_monitor.py            # Default: monitor nodes 11000-11004
"""

import requests
import json
import time
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

class LeaderMonitor:
    def __init__(self, base_port: int = 11000, num_nodes: int = 5):
        self.base_port = base_port
        self.num_nodes = num_nodes
        self.node_ports = [base_port + i for i in range(num_nodes)]
        
    def get_node_url(self, port: int, endpoint: str) -> str:
        """Construct API URL for a specific node and endpoint"""
        return f"http://localhost:{port}/api/v1/blockchain{endpoint}"
    
    def query_node(self, port: int, endpoint: str, timeout: int = 3) -> Optional[Dict]:
        """Query a specific node endpoint with error handling"""
        try:
            url = self.get_node_url(port, endpoint)
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}"}
        except requests.exceptions.RequestException as e:
            return {"error": f"Connection failed: {str(e)}"}
    
    def get_current_leader_status(self) -> Dict:
        """Get current leader status from all nodes"""
        results = {}
        
        for port in self.node_ports:
            node_id = f"Node_{port}"
            
            # Get current leader info
            current_leader = self.query_node(port, "/leader/current/")
            quantum_selection = self.query_node(port, "/leader/quantum-selection/")
            
            if current_leader and "error" not in current_leader:
                leader_info = current_leader.get("current_leader_info", {})
                consensus_context = current_leader.get("consensus_context", {})
                
                results[node_id] = {
                    "port": port,
                    "current_leader": leader_info.get("current_leader"),
                    "current_slot": leader_info.get("current_slot"),
                    "time_remaining_in_slot": leader_info.get("time_remaining_in_slot", 0),
                    "am_i_current_leader": current_leader.get("am_i_current_leader", False),
                    "total_nodes": consensus_context.get("total_nodes", 0),
                    "active_nodes": consensus_context.get("active_nodes", 0),
                    "gossip_peers": consensus_context.get("gossip_peers", 0),
                    "quantum_next_proposer": quantum_selection.get("next_quantum_proposer") if quantum_selection else None,
                    "node_scores_count": len(quantum_selection.get("node_scores", {})) if quantum_selection else 0,
                    "status": "online"
                }
            else:
                results[node_id] = {
                    "port": port,
                    "status": "offline",
                    "error": current_leader.get("error") if current_leader else "No response"
                }
        
        return results
    
    def get_upcoming_leaders_status(self) -> Dict:
        """Get upcoming leaders information from all nodes"""
        results = {}
        
        for port in self.node_ports:
            node_id = f"Node_{port}"
            
            # Get upcoming leaders info
            upcoming_leaders = self.query_node(port, "/leader/upcoming/")
            
            if upcoming_leaders and "error" not in upcoming_leaders:
                upcoming_list = upcoming_leaders.get("upcoming_leaders", [])
                my_upcoming = upcoming_leaders.get("my_upcoming_leadership")
                
                results[node_id] = {
                    "port": port,
                    "upcoming_leaders_count": len(upcoming_list),
                    "upcoming_leaders": upcoming_list[:3],  # Show first 3
                    "am_i_upcoming_leader": bool(my_upcoming),
                    "my_next_leadership_slot": my_upcoming.get("slot") if my_upcoming else None,
                    "my_next_leadership_time": my_upcoming.get("time_until_slot") if my_upcoming else None,
                    "current_epoch": upcoming_leaders.get("leader_schedule_epoch"),
                    "slot_duration": upcoming_leaders.get("slot_duration_seconds"),
                    "status": "online"
                }
            else:
                results[node_id] = {
                    "port": port,
                    "status": "offline",
                    "error": upcoming_leaders.get("error") if upcoming_leaders else "No response"
                }
        
        return results
    
    def get_full_leader_schedule(self, port: int) -> Optional[Dict]:
        """Get the full leader schedule from a specific node"""
        return self.query_node(port, "/leader/schedule/")
    
    def print_current_status(self, current_status: Dict):
        """Print formatted current leader status"""
        print(f"\n🎯 CURRENT LEADER STATUS - {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 80)
        
        online_nodes = [node for node, data in current_status.items() if data.get("status") == "online"]
        offline_nodes = [node for node, data in current_status.items() if data.get("status") == "offline"]
        
        print(f"📊 Network Overview: {len(online_nodes)}/{len(self.node_ports)} nodes online")
        
        if online_nodes:
            # Show consensus summary from first online node
            first_online = current_status[online_nodes[0]]
            print(f"🔗 Consensus: {first_online.get('total_nodes', 0)} total, {first_online.get('active_nodes', 0)} active, {first_online.get('gossip_peers', 0)} gossip peers")
            
            # Show current leader across all nodes
            leaders = set()
            current_leaders = {}
            for node_id in online_nodes:
                data = current_status[node_id]
                leader = data.get("current_leader")
                if leader:
                    leaders.add(leader)
                    if leader not in current_leaders:
                        current_leaders[leader] = []
                    current_leaders[leader].append(node_id)
            
            if current_leaders:
                print(f"\n👑 Current Leader(s):")
                for leader, nodes in current_leaders.items():
                    print(f"   {leader} (seen by: {', '.join(nodes)})")
                    
                    # Show time remaining in slot
                    for node_id in nodes:
                        time_remaining = current_status[node_id].get("time_remaining_in_slot", 0)
                        current_slot = current_status[node_id].get("current_slot", "?")
                        print(f"      Slot {current_slot}: {time_remaining:.1f}s remaining")
                        break  # Only show once
            else:
                print("👑 Current Leader: None assigned")
            
            # Show which nodes think they are leaders
            leader_nodes = [node_id for node_id in online_nodes 
                          if current_status[node_id].get("am_i_current_leader")]
            if leader_nodes:
                print(f"🏆 Nodes believing they are current leader: {', '.join(leader_nodes)}")
            
            # Show quantum consensus next proposer
            quantum_proposers = set()
            for node_id in online_nodes:
                proposer = current_status[node_id].get("quantum_next_proposer")
                if proposer and proposer != "None":
                    quantum_proposers.add(proposer)
            
            if quantum_proposers:
                print(f"🔮 Quantum Next Proposer: {', '.join(quantum_proposers)}")
        
        if offline_nodes:
            print(f"\n❌ Offline Nodes: {', '.join(offline_nodes)}")
    
    def print_upcoming_status(self, upcoming_status: Dict):
        """Print formatted upcoming leaders status"""
        print(f"\n📅 UPCOMING LEADERS STATUS")
        print("=" * 80)
        
        online_nodes = [node for node, data in upcoming_status.items() if data.get("status") == "online"]
        
        if online_nodes:
            # Show upcoming leadership summary
            total_upcoming = 0
            nodes_with_upcoming = []
            
            for node_id in online_nodes:
                data = upcoming_status[node_id]
                upcoming_count = data.get("upcoming_leaders_count", 0)
                total_upcoming += upcoming_count
                
                if data.get("am_i_upcoming_leader"):
                    slot = data.get("my_next_leadership_slot", "?")
                    time_until = data.get("my_next_leadership_time", 0)
                    nodes_with_upcoming.append(f"{node_id} (Slot {slot}, {time_until:.1f}s)")
            
            avg_upcoming = total_upcoming / len(online_nodes) if online_nodes else 0
            print(f"📊 Upcoming Leaders: {total_upcoming} total slots, {avg_upcoming:.1f} avg per node")
            
            if nodes_with_upcoming:
                print(f"🎯 Nodes with upcoming leadership:")
                for node_info in nodes_with_upcoming:
                    print(f"   {node_info}")
            else:
                print("🎯 No nodes have upcoming leadership slots")
            
            # Show sample upcoming leaders from first node
            first_online = upcoming_status[online_nodes[0]]
            sample_leaders = first_online.get("upcoming_leaders", [])
            if sample_leaders:
                print(f"\n📋 Next {min(3, len(sample_leaders))} Leader(s):")
                for i, leader_info in enumerate(sample_leaders[:3]):
                    slot = leader_info.get("slot", "?")
                    time_until = leader_info.get("time_until_slot", 0)
                    leader_key = leader_info.get("leader", "Unknown")[:30] + "..."
                    print(f"   {i+1}. Slot {slot}: {leader_key} ({time_until:.1f}s)")
        else:
            print("❌ No online nodes to query upcoming leaders")
    
    def print_detailed_schedule(self, port: int):
        """Print detailed leader schedule from a specific node"""
        schedule_data = self.get_full_leader_schedule(port)
        
        if not schedule_data or "error" in schedule_data:
            print(f"\n❌ Could not get leader schedule from Node_{port}")
            if schedule_data:
                print(f"   Error: {schedule_data.get('error')}")
            return
        
        print(f"\n📋 DETAILED LEADER SCHEDULE (Node_{port})")
        print("=" * 80)
        
        print(f"🕐 Current Epoch: {schedule_data.get('current_epoch', 'Unknown')}")
        print(f"🕐 Current Slot: {schedule_data.get('current_slot', 'Unknown')}")
        print(f"⏱️  Slot Duration: {schedule_data.get('slot_duration_seconds', 'Unknown')}s")
        print(f"📊 Current Schedule Size: {schedule_data.get('current_schedule_size', 0)}")
        print(f"📊 Next Schedule Size: {schedule_data.get('next_schedule_size', 0)}")
        
        # Show current schedule sample
        current_schedule = schedule_data.get("current_schedule", {})
        if current_schedule:
            print(f"\n📅 Current Schedule Sample (first 5 slots):")
            sorted_slots = sorted([int(slot) for slot in current_schedule.keys()])
            for slot in sorted_slots[:5]:
                leader = current_schedule[str(slot)]
                print(f"   Slot {slot}: {leader}")
        
        # Show next schedule sample
        next_schedule = schedule_data.get("next_schedule", {})
        if next_schedule:
            print(f"\n📅 Next Schedule Sample (first 5 slots):")
            sorted_slots = sorted([int(slot) for slot in next_schedule.keys()])
            for slot in sorted_slots[:5]:
                leader = next_schedule[str(slot)]
                print(f"   Slot {slot}: {leader}")
    
    def monitor_once(self, show_detailed_schedule: bool = False):
        """Run a single monitoring cycle"""
        print(f"\n🔍 BLOCKCHAIN LEADER MONITORING")
        print(f"📡 Monitoring {self.num_nodes} nodes on ports {self.base_port}-{self.base_port + self.num_nodes - 1}")
        
        # Get current status
        current_status = self.get_current_leader_status()
        self.print_current_status(current_status)
        
        # Get upcoming leaders
        upcoming_status = self.get_upcoming_leaders_status()
        self.print_upcoming_status(upcoming_status)
        
        # Show detailed schedule if requested
        if show_detailed_schedule:
            online_nodes = [node for node, data in current_status.items() if data.get("status") == "online"]
            if online_nodes:
                first_port = current_status[online_nodes[0]]["port"]
                self.print_detailed_schedule(first_port)
    
    def monitor_continuous(self, interval: int = 10, show_detailed: bool = False):
        """Run continuous monitoring with specified interval"""
        print(f"🔄 Starting continuous monitoring (interval: {interval}s)")
        print("Press Ctrl+C to stop...")
        
        try:
            while True:
                self.monitor_once(show_detailed_schedule=show_detailed)
                print(f"\n⏳ Waiting {interval}s for next update...")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped by user")


def main():
    """Main function with command line argument parsing"""
    base_port = 11000
    num_nodes = 5

    # Collect positional (non-flag) arguments
    positional = [a for a in sys.argv[1:] if not a.startswith("-")]

    if len(positional) > 0:
        try:
            base_port = int(positional[0])
        except ValueError:
            print("Error: base_port must be an integer")
            sys.exit(1)

    if len(positional) > 1:
        try:
            num_nodes = int(positional[1])
        except ValueError:
            print("Error: num_nodes must be an integer")
            sys.exit(1)
    
    monitor = LeaderMonitor(base_port, num_nodes)
    
    # Check for special command line flags
    if "--continuous" in sys.argv or "-c" in sys.argv:
        interval = 10
        if "--interval" in sys.argv:
            try:
                idx = sys.argv.index("--interval")
                interval = int(sys.argv[idx + 1])
            except (ValueError, IndexError):
                print("Error: --interval requires an integer value")
                sys.exit(1)
        
        detailed = "--detailed" in sys.argv or "-d" in sys.argv
        monitor.monitor_continuous(interval, detailed)
    else:
        detailed = "--detailed" in sys.argv or "-d" in sys.argv
        monitor.monitor_once(detailed)


if __name__ == "__main__":
    main()
