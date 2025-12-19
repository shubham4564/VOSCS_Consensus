"""
Comprehensive Gossip Protocol Verification Suite
==============================================

Runs all three verification tests to ensure the gossip protocol
implementation works correctly and efficiently according to Solana specifications.

Test Suite:
1. Message Propagation Test - Verifies basic gossip functionality
2. Health-Based Pruning Test - Verifies unhealthy node management  
3. Performance & Efficiency Test - Verifies Solana-spec compliance

Requirements Verified:
✓ Push messages to ~6 nodes (fanout)
✓ Pull requests to single random peers
✓ Health-based pruning (not stake-based)
✓ Leader schedule distribution
✓ Network resilience and self-healing
✓ Performance within acceptable bounds
"""

import asyncio
import time
import logging
import sys
import os
from typing import List, Dict, Tuple

# Add parent directories to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

# Import verification tests
from test_1_message_propagation import GossipVerificationTest1
from test_2_health_pruning import GossipVerificationTest2
from test_3_performance_efficiency import GossipVerificationTest3

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('gossip_verification.log')
    ]
)
logger = logging.getLogger(__name__)

class ComprehensiveGossipVerification:
    """Comprehensive gossip protocol verification suite"""
    
    def __init__(self):
        self.test_results: Dict[str, Dict] = {}
        self.overall_success = False
        self.start_time = 0
        self.end_time = 0
    
    async def run_test_1(self) -> bool:
        """Run Test 1: Message Propagation"""
        logger.info("🧪 Starting Test 1: Message Propagation...")
        
        try:
            test = GossipVerificationTest1(num_nodes=8)
            success = await test.run_verification()
            
            self.test_results['test_1_message_propagation'] = {
                'success': success,
                'details': test.test_results,
                'description': 'Verifies basic message propagation through gossip network'
            }
            
            return success
            
        except Exception as e:
            logger.error(f"Test 1 failed with exception: {e}")
            self.test_results['test_1_message_propagation'] = {
                'success': False,
                'error': str(e),
                'description': 'Verifies basic message propagation through gossip network'
            }
            return False
    
    async def run_test_2(self) -> bool:
        """Run Test 2: Health-Based Pruning"""
        logger.info("🧪 Starting Test 2: Health-Based Pruning...")
        
        try:
            test = GossipVerificationTest2(num_healthy_nodes=6, num_unhealthy_nodes=4)
            success = await test.run_verification()
            
            self.test_results['test_2_health_pruning'] = {
                'success': success,
                'details': test.test_results,
                'description': 'Verifies health-based pruning removes unhealthy nodes'
            }
            
            return success
            
        except Exception as e:
            logger.error(f"Test 2 failed with exception: {e}")
            self.test_results['test_2_health_pruning'] = {
                'success': False,
                'error': str(e),
                'description': 'Verifies health-based pruning removes unhealthy nodes'
            }
            return False
    
    async def run_test_3(self) -> bool:
        """Run Test 3: Performance & Efficiency"""
        logger.info("🧪 Starting Test 3: Performance & Efficiency...")
        
        try:
            test = GossipVerificationTest3(num_nodes=10)
            success = await test.run_verification()
            
            self.test_results['test_3_performance_efficiency'] = {
                'success': success,
                'details': test.test_results,
                'description': 'Verifies Solana-spec compliance and performance'
            }
            
            return success
            
        except Exception as e:
            logger.error(f"Test 3 failed with exception: {e}")
            self.test_results['test_3_performance_efficiency'] = {
                'success': False,
                'error': str(e),
                'description': 'Verifies Solana-spec compliance and performance'
            }
            return False
    
    def print_comprehensive_results(self):
        """Print comprehensive test results"""
        print("\n" + "=" * 100)
        print("🔬 COMPREHENSIVE GOSSIP PROTOCOL VERIFICATION RESULTS")
        print("=" * 100)
        
        print(f"⏱️  Total Test Duration: {self.end_time - self.start_time:.1f} seconds")
        print(f"📊 Tests Run: {len(self.test_results)}")
        
        passed_tests = sum(1 for result in self.test_results.values() if result['success'])
        print(f"✅ Tests Passed: {passed_tests}/{len(self.test_results)}")
        
        print("\n📋 Individual Test Results:")
        print("-" * 100)
        
        for test_name, result in self.test_results.items():
            status = "✅ PASSED" if result['success'] else "❌ FAILED"
            test_display_name = test_name.replace('_', ' ').title()
            
            print(f"{status} | {test_display_name}")
            print(f"    📝 {result['description']}")
            
            if 'details' in result and isinstance(result['details'], dict):
                for key, value in result['details'].items():
                    if isinstance(value, bool):
                        status_icon = "✅" if value else "❌"
                        print(f"    {status_icon} {key.replace('_', ' ').title()}: {value}")
                    elif isinstance(value, (int, float, str)):
                        print(f"    📈 {key.replace('_', ' ').title()}: {value}")
            
            if 'error' in result:
                print(f"    ❌ Error: {result['error']}")
            
            print()
        
        print("=" * 100)
        
        # Overall assessment
        if self.overall_success:
            print("🎉 OVERALL VERIFICATION: ✅ ALL TESTS PASSED")
            print("   The gossip protocol implementation meets all Solana specifications!")
        else:
            print("🚨 OVERALL VERIFICATION: ❌ SOME TESTS FAILED")
            print("   The gossip protocol implementation needs improvements.")
        
        print("\n🔍 Key Solana Specifications Verified:")
        solana_specs = [
            ("Push Fanout", "Messages sent to ~6 peers maximum"),
            ("Pull Single Peer", "Pull requests sent to single random peer"),
            ("Health-Based Pruning", "Unhealthy nodes removed (not stake-based)"),
            ("Leader Schedule Distribution", "Leader info propagates to all nodes"),
            ("Bloom Filter Efficiency", "Pull requests use efficient bloom filters"),
            ("Network Convergence", "Information spreads within reasonable time"),
            ("Message Frequency", "Push/pull timing follows configuration"),
            ("Memory Efficiency", "Reasonable memory usage per node")
        ]
        
        for spec_name, spec_description in solana_specs:
            print(f"   📐 {spec_name}: {spec_description}")
        
        print("\n💡 Implementation Highlights:")
        highlights = [
            "🔄 CRDS (Contact Info and Replicated Data Store) implementation",
            "📡 UDP-based gossip messaging with async I/O",
            "🏥 Health tracking for smart pruning decisions",
            "🌸 Bloom filters for efficient pull request optimization",
            "⚡ Configurable timing for push/pull/prune operations",
            "📊 Comprehensive statistics and monitoring"
        ]
        
        for highlight in highlights:
            print(f"   {highlight}")
        
        print("\n" + "=" * 100)
    
    async def run_all_tests(self) -> bool:
        """Run all verification tests"""
        logger.info("🚀 Starting Comprehensive Gossip Protocol Verification Suite...")
        
        self.start_time = time.time()
        
        try:
            # Run all tests sequentially with delays between them
            test_results = []
            
            # Test 1: Message Propagation
            result1 = await self.run_test_1()
            test_results.append(result1)
            
            # Small delay between tests
            await asyncio.sleep(2)
            
            # Test 2: Health-Based Pruning
            result2 = await self.run_test_2()
            test_results.append(result2)
            
            # Small delay between tests
            await asyncio.sleep(2)
            
            # Test 3: Performance & Efficiency
            result3 = await self.run_test_3()
            test_results.append(result3)
            
            # Determine overall success
            self.overall_success = all(test_results)
            
            self.end_time = time.time()
            
            # Print comprehensive results
            self.print_comprehensive_results()
            
            return self.overall_success
            
        except Exception as e:
            logger.error(f"Verification suite failed: {e}")
            self.end_time = time.time()
            return False

async def main():
    """Main verification execution"""
    verification = ComprehensiveGossipVerification()
    
    print("🔬 Gossip Protocol Verification Suite")
    print("=====================================")
    print("Testing Solana-style gossip protocol implementation...")
    print("This will verify message propagation, health-based pruning, and performance.")
    print()
    
    success = await verification.run_all_tests()
    
    if success:
        print("🏆 SUCCESS: Gossip protocol implementation is verified and working correctly!")
        exit_code = 0
    else:
        print("⚠️  FAILURE: Some aspects of the gossip protocol need improvement.")
        exit_code = 1
    
    return exit_code

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
