#!/usr/bin/env python3
"""
Test ECDSA P-256 implementation performance vs RSA 2048 performance.
This test will verify that ECDSA signing and verification work correctly
and measure the performance improvements.
"""

import os
import time
import sys


def _ensure_repo_root_on_path() -> None:
    current = os.path.abspath(os.path.dirname(__file__))
    for _ in range(6):
        if os.path.isfile(os.path.join(current, "blockchain", "__init__.py")):
            if current not in sys.path:
                sys.path.insert(0, current)
            return
        parent = os.path.dirname(current)
        if parent == current:
            return
        current = parent


_ensure_repo_root_on_path()
del _ensure_repo_root_on_path

from blockchain.quantum_consensus.quantum_annealing_consensus import QuantumAnnealingConsensus

def test_ecdsa_basic_functionality():
    """Test basic ECDSA signing and verification"""
    print("🧪 Testing ECDSA P-256 Basic Functionality")
    print("=" * 50)
    
    # Initialize consensus with ECDSA
    consensus = QuantumAnnealingConsensus(initialize_genesis=False)
    
    # Test key generation
    print("🔑 Testing key generation...")
    public_key, private_key = consensus.generate_node_keys("test_node")
    
    # Verify keys are generated
    assert "test_node" in consensus.node_keys
    assert public_key.startswith("-----BEGIN PUBLIC KEY-----")
    assert private_key.startswith("-----BEGIN PRIVATE KEY-----")
    print("✅ Key generation successful")
    
    # Test message signing
    print("✍️  Testing message signing...")
    test_message = b"Hello, ECDSA P-256!"
    signature = consensus.sign_message("test_node", test_message)
    
    # Verify signature format
    assert isinstance(signature, str)
    assert len(signature) > 0
    print(f"✅ Signature generated: {signature[:32]}...")
    
    # Test signature verification
    print("🔍 Testing signature verification...")
    is_valid = consensus.verify_signature("test_node", test_message, signature)
    assert is_valid, "Signature verification failed"
    print("✅ Signature verification successful")
    
    # Test verification with wrong message
    print("🚫 Testing verification with wrong message...")
    wrong_message = b"Wrong message"
    is_invalid = consensus.verify_signature("test_node", wrong_message, signature)
    assert not is_invalid, "Signature verification should fail for wrong message"
    print("✅ Wrong message correctly rejected")
    
    # Test verification with wrong signature
    print("🚫 Testing verification with wrong signature...")
    wrong_signature = "deadbeef" * 16  # Invalid signature
    is_invalid = consensus.verify_signature("test_node", test_message, wrong_signature)
    assert not is_invalid, "Signature verification should fail for wrong signature"
    print("✅ Wrong signature correctly rejected")
    
    print("\n✅ All ECDSA functionality tests passed!")

def test_ecdsa_performance():
    """Test ECDSA P-256 performance and compare with expected RSA performance"""
    print("\n🚀 Testing ECDSA P-256 Performance")
    print("=" * 50)
    
    # Initialize consensus
    consensus = QuantumAnnealingConsensus(initialize_genesis=False)
    
    # Generate test nodes
    test_nodes = []
    for i in range(5):
        node_id = f"perf_test_node_{i}"
        consensus.ensure_node_keys(node_id)
        test_nodes.append(node_id)
    
    print(f"🔑 Generated keys for {len(test_nodes)} test nodes")
    
    # Test message
    test_message = b"Performance test message for ECDSA P-256 signing"
    
    # Measure key loading + signing performance
    print("\n⏱️  Measuring signing performance...")
    signing_times = []
    
    for node_id in test_nodes:
        # Measure signing time (including key loading)
        start_time = time.time()
        signature = consensus.sign_message(node_id, test_message)
        signing_time = time.time() - start_time
        signing_times.append(signing_time)
        
        # Verify the signature works
        assert consensus.verify_signature(node_id, test_message, signature)
    
    avg_signing_time = sum(signing_times) * 1000 / len(signing_times)
    min_signing_time = min(signing_times) * 1000
    max_signing_time = max(signing_times) * 1000
    
    print(f"📊 Signing Performance Results:")
    print(f"   Average: {avg_signing_time:.3f}ms")
    print(f"   Min:     {min_signing_time:.3f}ms")
    print(f"   Max:     {max_signing_time:.3f}ms")
    
    # Measure verification performance
    print("\n⏱️  Measuring verification performance...")
    verification_times = []
    signatures = []
    
    # Generate signatures first
    for node_id in test_nodes:
        signature = consensus.sign_message(node_id, test_message)
        signatures.append((node_id, signature))
    
    # Measure verification times
    for node_id, signature in signatures:
        start_time = time.time()
        is_valid = consensus.verify_signature(node_id, test_message, signature)
        verification_time = time.time() - start_time
        verification_times.append(verification_time)
        assert is_valid
    
    avg_verification_time = sum(verification_times) * 1000 / len(verification_times)
    min_verification_time = min(verification_times) * 1000
    max_verification_time = max(verification_times) * 1000
    
    print(f"📊 Verification Performance Results:")
    print(f"   Average: {avg_verification_time:.3f}ms")
    print(f"   Min:     {min_verification_time:.3f}ms")
    print(f"   Max:     {max_verification_time:.3f}ms")
    
    # Compare with expected RSA performance
    print(f"\n📈 Performance Comparison (vs previous RSA 2048):")
    print(f"   RSA 2048 signing:      ~45ms (measured previously)")
    print(f"   ECDSA P-256 signing:   {avg_signing_time:.3f}ms")
    
    if avg_signing_time < 45:
        speedup = 45 / avg_signing_time
        print(f"   🚀 ECDSA is {speedup:.1f}x faster for signing!")
    
    print(f"   RSA 2048 verification: ~5ms (typical)")
    print(f"   ECDSA P-256 verify:    {avg_verification_time:.3f}ms")
    
    if avg_verification_time < 5:
        speedup = 5 / avg_verification_time
        print(f"   🚀 ECDSA is {speedup:.1f}x faster for verification!")
    
    return avg_signing_time, avg_verification_time

def test_file_loading_performance():
    """Test loading ECDSA keys from files"""
    print("\n📁 Testing ECDSA Key File Loading Performance")
    print("=" * 50)
    
    consensus = QuantumAnnealingConsensus(initialize_genesis=False)
    
    # Test loading existing keys from files
    existing_nodes = ["genesis", "node2", "node3", "node4", "node5"]
    loading_times = []
    
    for node_id in existing_nodes:
        start_time = time.time()
        public_key, private_key = consensus.load_node_keys_from_file(node_id)
        loading_time = time.time() - start_time
        loading_times.append(loading_time)
        
        # Verify the loaded keys work
        test_message = b"File loading test"
        signature = consensus.sign_message(node_id, test_message)
        assert consensus.verify_signature(node_id, test_message, signature)
    
    avg_loading_time = sum(loading_times) * 1000 / len(loading_times)
    print(f"📊 Key Loading Performance:")
    print(f"   Average: {avg_loading_time:.3f}ms")
    print(f"   RSA loading was: ~42ms (measured previously)")
    
    if avg_loading_time < 42:
        speedup = 42 / avg_loading_time
        print(f"   🚀 ECDSA file loading is {speedup:.1f}x faster!")
    
    return avg_loading_time

def simulate_probe_operations():
    """Simulate probe operations with ECDSA to estimate total performance improvement"""
    print("\n🔍 Simulating Probe Operations with ECDSA")
    print("=" * 50)
    
    consensus = QuantumAnnealingConsensus(initialize_genesis=False)
    
    # Setup test nodes
    nodes = ["node2", "node3", "node4", "node5"]
    for node_id in nodes:
        consensus.ensure_node_keys(node_id)
        consensus.register_node(node_id, consensus.node_keys[node_id][0])
    
    # Simulate a single probe operation timing
    print("⏱️  Simulating single probe operation...")
    
    start_time = time.time()
    
    # Execute one probe (source=node2, target=node3, witnesses=[node4, node5])
    source = "node2"
    target = "node3"
    witnesses = ["node4", "node5"]
    
    probe_result = consensus.execute_probe_protocol(source, target, witnesses)
    
    probe_time = time.time() - start_time
    
    print(f"📊 Single Probe Operation Results:")
    print(f"   Total time: {probe_time * 1000:.3f}ms")
    print(f"   Previous RSA time: ~360ms")
    
    if probe_time < 0.360:
        speedup = 0.360 / probe_time
        print(f"   🚀 ECDSA probe is {speedup:.1f}x faster!")
    
    # Estimate 5-node consensus performance
    estimated_consensus_time = probe_time * 20  # 5 nodes × 4 probes each
    print(f"\n📈 Estimated 5-node consensus performance:")
    print(f"   Previous RSA: ~7.5 seconds")
    print(f"   New ECDSA:    {estimated_consensus_time:.3f} seconds")
    
    if estimated_consensus_time < 7.5:
        speedup = 7.5 / estimated_consensus_time
        print(f"   🚀 Overall consensus {speedup:.1f}x faster!")
    
    return probe_time, estimated_consensus_time

def main():
    """Run all ECDSA tests"""
    print("🔐 ECDSA P-256 Implementation Testing")
    print("=" * 60)
    
    try:
        # Test basic functionality
        test_ecdsa_basic_functionality()
        
        # Test performance
        signing_time, verification_time = test_ecdsa_performance()
        
        # Test file loading
        loading_time = test_file_loading_performance()
        
        # Simulate probe operations
        probe_time, consensus_time = simulate_probe_operations()
        
        # Final summary
        print("\n🎉 ECDSA P-256 Implementation Summary")
        print("=" * 60)
        print(f"✅ All functionality tests passed")
        print(f"📊 Performance improvements:")
        print(f"   - Signing:     {signing_time:.3f}ms (vs ~45ms RSA)")
        print(f"   - Verification: {verification_time:.3f}ms (vs ~5ms RSA)")
        print(f"   - File loading: {loading_time:.3f}ms (vs ~42ms RSA)")
        print(f"   - Single probe: {probe_time * 1000:.3f}ms (vs ~360ms RSA)")
        print(f"   - Full consensus: {consensus_time:.3f}s (vs ~7.5s RSA)")
        print("\n🚀 ECDSA P-256 implementation successful!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
