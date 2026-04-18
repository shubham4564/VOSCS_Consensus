#!/usr/bin/env python3
"""
🔍 QUANTUM BLOCKCHAIN NODE HEALTH CHECKER
========================================
Comprehensive tool to check if blockchain nodes are alive and healthy.
"""

import requests
import subprocess
import json
import time
from datetime import datetime
import sys
import os

class NodeHealthChecker:
    def __init__(self, port_range=(11000, 11100)):
        self.start_port, self.end_port = port_range
        self.healthy_nodes = []
        self.unhealthy_nodes = []
        self.offline_nodes = []

    def check_process_running(self, port):
        """Check if a process is running on the given port"""
        try:
            result = subprocess.run(['lsof', '-i', f':{port}'], 
                                  capture_output=True, text=True, timeout=5)
            return len(result.stdout.strip()) > 0
        except:
            return False

    def check_api_response(self, port):
        """Check if the node API is responding"""
        try:
            response = requests.get(f'http://localhost:{port}/api/v1/blockchain/', 
                                  timeout=3)
            return response.status_code == 200, response.json() if response.status_code == 200 else None
        except:
            return False, None

    def check_quantum_metrics(self, port):
        """Check quantum consensus health"""
        try:
            response = requests.get(f'http://localhost:{port}/api/v1/blockchain/quantum-metrics/', 
                                  timeout=3)
            return response.status_code == 200, response.json() if response.status_code == 200 else None
        except:
            return False, None

    def get_node_info(self, port):
        """Get comprehensive node information"""
        node_info = {
            'port': port,
            'node_id': port - 11000,
            'process_running': False,
            'api_responding': False,
            'quantum_healthy': False,
            'blockchain_data': None,
            'quantum_data': None,
            'status': 'offline'
        }

        # Check if process is running
        node_info['process_running'] = self.check_process_running(port)
        
        if not node_info['process_running']:
            node_info['status'] = 'offline'
            return node_info

        # Check API response
        api_ok, blockchain_data = self.check_api_response(port)
        node_info['api_responding'] = api_ok
        node_info['blockchain_data'] = blockchain_data

        if not api_ok:
            node_info['status'] = 'process_running_api_failed'
            return node_info

        # Check quantum metrics
        quantum_ok, quantum_data = self.check_quantum_metrics(port)
        node_info['quantum_healthy'] = quantum_ok
        node_info['quantum_data'] = quantum_data

        if api_ok and quantum_ok:
            node_info['status'] = 'healthy'
        elif api_ok:
            node_info['status'] = 'api_only'
        else:
            node_info['status'] = 'degraded'

        return node_info

    def check_all_nodes(self):
        """Check all nodes in the port range"""
        print("🔍 CHECKING BLOCKCHAIN NODE HEALTH")
        print("=" * 50)
        print(f"Scanning ports {self.start_port}-{self.end_port-1}...")
        print()

        all_nodes = []
        
        for port in range(self.start_port, self.end_port):
            node_info = self.get_node_info(port)
            all_nodes.append(node_info)

            # Categorize nodes
            if node_info['status'] == 'healthy':
                self.healthy_nodes.append(node_info)
            elif node_info['status'] in ['process_running_api_failed', 'api_only', 'degraded']:
                self.unhealthy_nodes.append(node_info)
            else:
                self.offline_nodes.append(node_info)

        return all_nodes

    def print_summary(self):
        """Print health check summary"""
        total_checked = self.end_port - self.start_port
        
        print(f"📊 HEALTH CHECK SUMMARY")
        print("-" * 30)
        print(f"   Total Ports Checked: {total_checked}")
        print(f"   ✅ Healthy Nodes: {len(self.healthy_nodes)}")
        print(f"   ⚠️  Unhealthy Nodes: {len(self.unhealthy_nodes)}")
        print(f"   ❌ Offline Nodes: {len(self.offline_nodes)}")
        print()

        if self.healthy_nodes:
            print("✅ HEALTHY NODES")
            print("-" * 20)
            for node in self.healthy_nodes:
                blocks = len(node['blockchain_data']['blocks']) if node['blockchain_data'] else 0
                active_nodes = node['quantum_data'].get('active_nodes', 0) if node['quantum_data'] else 0
                total_nodes = node['quantum_data'].get('total_nodes', 0) if node['quantum_data'] else 0
                print(f"   Node {node['node_id']:2d} (port {node['port']}): {blocks} blocks, "
                      f"Quantum: {active_nodes}/{total_nodes} nodes")

        if self.unhealthy_nodes:
            print("\n⚠️  UNHEALTHY NODES")
            print("-" * 20)
            for node in self.unhealthy_nodes:
                print(f"   Node {node['node_id']:2d} (port {node['port']}): {node['status']}")

        if self.offline_nodes:
            print(f"\n❌ OFFLINE NODES")
            print("-" * 15)
            offline_node_ids = [node['node_id'] for node in self.offline_nodes]
            print(f"   Node IDs: {offline_node_ids}")

    def print_detailed_status(self):
        """Print detailed status for each node"""
        print("\n🔬 DETAILED NODE STATUS")
        print("=" * 40)
        
        for port in range(self.start_port, self.end_port):
            node_info = self.get_node_info(port)
            node_id = port - 11000
            
            status_icon = {
                'healthy': '✅',
                'api_only': '⚠️ ',
                'degraded': '⚠️ ',
                'process_running_api_failed': '❌',
                'offline': '❌'
            }.get(node_info['status'], '❓')
            
            print(f"\n{status_icon} Node {node_id:2d} (port {port})")
            print(f"   Status: {node_info['status']}")
            print(f"   Process Running: {'✅' if node_info['process_running'] else '❌'}")
            print(f"   API Responding: {'✅' if node_info['api_responding'] else '❌'}")
            print(f"   Quantum Healthy: {'✅' if node_info['quantum_healthy'] else '❌'}")
            
            if node_info['blockchain_data']:
                blocks = len(node_info['blockchain_data']['blocks'])
                print(f"   Blocks: {blocks}")
                
            if node_info['quantum_data']:
                active = node_info['quantum_data'].get('active_nodes', 0)
                total = node_info['quantum_data'].get('total_nodes', 0)
                probes = node_info['quantum_data'].get('probe_count', 0)
                print(f"   Quantum: {active}/{total} nodes, {probes} probes")

def main():
    print("🌌 QUANTUM BLOCKCHAIN NODE HEALTH CHECKER")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Parse command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--detailed':
            detailed = True
        elif sys.argv[1] == '--help':
            print("Usage:")
            print("  python check_node_health.py           # Quick summary")
            print("  python check_node_health.py --detailed # Detailed status")
            print("  python check_node_health.py --help    # This help")
            return
        else:
            detailed = False
    else:
        detailed = False

    # Initialize checker
    checker = NodeHealthChecker()
    
    # Check all nodes
    all_nodes = checker.check_all_nodes()
    
    # Print summary
    checker.print_summary()
    
    # Print detailed status if requested
    if detailed:
        checker.print_detailed_status()
    
    # Quick commands help
    print(f"\n🚀 QUICK COMMANDS")
    print("-" * 20)
    if checker.healthy_nodes:
        first_healthy = checker.healthy_nodes[0]['port']
        print(f"   Test API: curl http://localhost:{first_healthy}/api/v1/blockchain/")
        print(f"   Quantum metrics: curl http://localhost:{first_healthy}/api/v1/blockchain/quantum-metrics/")
    
    if checker.offline_nodes:
        print(f"   Start nodes: ./start_nodes.sh 5")
    
    print(f"   Stop all: pkill -f 'run_node.py'")
    print(f"   Detailed check: python check_node_health.py --detailed")
    
    # Exit with appropriate code
    if checker.healthy_nodes:
        print(f"\n🎉 Health check complete - {len(checker.healthy_nodes)} healthy nodes found!")
        sys.exit(0)
    else:
        print(f"\n⚠️  No healthy nodes found!")
        sys.exit(1)

if __name__ == "__main__":
    main()
