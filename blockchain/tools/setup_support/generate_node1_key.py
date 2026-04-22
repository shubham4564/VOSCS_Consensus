#!/usr/bin/env python3
"""
Generate ECDSA P-256 key for node1 (missing from the original key generation).
"""

import os
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

def generate_ecdsa_key_pair(node_id: str, keys_dir: str = "./keys"):
    """Generate ECDSA P-256 key pair for a node"""
    
    # Generate ECDSA P-256 private key
    private_key = ec.generate_private_key(ec.SECP256R1())
    
    # Serialize private key to PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # Get public key and serialize to PEM format
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # Create keys directory if it doesn't exist
    os.makedirs(keys_dir, exist_ok=True)
    
    # Write private key
    private_key_path = os.path.join(keys_dir, f"{node_id}_private_key.pem")
    with open(private_key_path, 'wb') as f:
        f.write(private_pem)
    
    # Write public key
    public_key_path = os.path.join(keys_dir, f"{node_id}_public_key.pem")
    with open(public_key_path, 'wb') as f:
        f.write(public_pem)
    
    print(f"✅ Generated ECDSA P-256 keys for {node_id}")
    return private_key_path, public_key_path

def main():
    """Generate ECDSA key for node1"""
    
    print("🔑 Generating missing ECDSA P-256 key for node1...")
    
    # Generate node1 key
    try:
        generate_ecdsa_key_pair("node1", "./keys")
        print("✅ Successfully generated node1 ECDSA P-256 key")
        
        # Verify the key works
        node1_private_path = "./keys/node1_private_key.pem"
        with open(node1_private_path, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        
        print(f"📊 node1 key info:")
        print(f"   Algorithm: ECDSA")
        print(f"   Curve: P-256 (secp256r1)")
        print(f"   Key size: 256 bits")
        print(f"   Private key: {node1_private_path}")
        print(f"   Public key: ./keys/node1_public_key.pem")
        
    except Exception as e:
        print(f"❌ Error generating node1 key: {e}")

if __name__ == "__main__":
    main()
