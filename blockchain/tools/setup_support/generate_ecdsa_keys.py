#!/usr/bin/env python3
"""
Generate ECDSA P-256 keys to replace RSA keys for all nodes.
This script will create new ECDSA keys while keeping the same naming convention.
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
    """Generate ECDSA keys for all existing nodes"""
    
    keys_dir = "./keys"
    
    # Backup existing RSA keys
    backup_dir = "./keys_rsa_backup"
    if os.path.exists(keys_dir):
        print(f"🔄 Backing up existing RSA keys to {backup_dir}")
        os.makedirs(backup_dir, exist_ok=True)
        
        for filename in os.listdir(keys_dir):
            if filename.endswith('.pem'):
                src = os.path.join(keys_dir, filename)
                dst = os.path.join(backup_dir, filename)
                os.rename(src, dst)
        print(f"✅ RSA keys backed up to {backup_dir}")
    
    # List of nodes to generate keys for
    nodes = []
    
    # Add genesis node
    nodes.append("genesis")
    
    # Add numbered nodes (node2 through node100)
    for i in range(2, 101):
        nodes.append(f"node{i}")
    
    print(f"🔑 Generating ECDSA P-256 keys for {len(nodes)} nodes...")
    
    # Generate ECDSA keys for all nodes
    for node_id in nodes:
        try:
            generate_ecdsa_key_pair(node_id, keys_dir)
        except Exception as e:
            print(f"❌ Error generating keys for {node_id}: {e}")
    
    print(f"\n✅ Successfully generated ECDSA P-256 keys for all nodes")
    print(f"📁 Keys location: {os.path.abspath(keys_dir)}")
    print(f"📁 RSA backup: {os.path.abspath(backup_dir)}")
    
    # Display key info for genesis node
    try:
        genesis_private_path = os.path.join(keys_dir, "genesis_private_key.pem")
        genesis_public_path = os.path.join(keys_dir, "genesis_public_key.pem")
        
        if os.path.exists(genesis_private_path):
            with open(genesis_private_path, 'rb') as f:
                private_key = serialization.load_pem_private_key(f.read(), password=None)
            
            print(f"\n📊 Genesis key info:")
            print(f"   Algorithm: ECDSA")
            print(f"   Curve: P-256 (secp256r1)")
            print(f"   Key size: 256 bits")
            print(f"   Private key: {genesis_private_path}")
            print(f"   Public key: {genesis_public_path}")
            
    except Exception as e:
        print(f"⚠️  Could not display genesis key info: {e}")

if __name__ == "__main__":
    main()
