"""
Solana-style Genesis Block Configuration System

This module implements the complete Solana genesis block creation process:
1. Generate foundational keypairs (faucet, bootstrap validator)
2. Define cluster configuration parameters
3. Allocate initial token supply (airdrop)
4. Compile genesis.bin file that all nodes must share

This ensures 100% network consensus from block 0.
"""

import json
import time
import hashlib
from typing import Dict, List, Optional
from pathlib import Path
from blockchain.transaction.wallet import Wallet
from blockchain.utils.logger import logger


class GenesisConfig:
    """
    Solana-style genesis configuration manager.
    
    This class handles the complete genesis block creation process
    ensuring all nodes start with identical blockchain state.
    """
    
    def __init__(self, config_dir: str = "genesis_config"):
        """
        Initialize genesis configuration system.
        
        Args:
            config_dir: Directory to store genesis configuration files
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        # Solana-style cluster parameters - Updated for TPU/Gulf Stream implementation
        self.cluster_config = {
            "hashes_per_tick": 12500,  # PoH hashes between ticks
            "ticks_per_slot": 64,      # Ticks per block production slot
            "slot_duration_seconds": 0.45,  # 450ms per leader slot (Solana-style fast blocks)
            "epoch_duration_seconds": 600,  # 10 minutes per epoch
            "slots_per_epoch": 1333,   # ~1333 slots per epoch (600s / 0.45s)
            "leader_advance_time_seconds": 600,  # Leaders known 10 minutes in advance
            "target_lamports_per_signature": 5000,  # Transaction fee
            "epoch_warmup": True,
            "tpu_config": {
                "enabled": True,
                "port_range_start": 13000,
                "port_range_end": 13099,
                "max_packet_size": 1024
            },
            "gulf_stream_config": {
                "enabled": True,
                "min_buffer_slots": 200,
                "max_forwarding_slots": 200,
                "transaction_lifetime_seconds": 90
            },
            "quantum_consensus_config": {
                "enabled": True,
                "leader_selection_algorithm": "quantum_annealing",
                "viable_leader_threshold": 0.1
            },
            "inflation": {
                "initial": 0.08,  # 8% initial inflation
                "terminal": 0.015,  # 1.5% terminal inflation
                "taper": 0.15     # 15% taper rate
            },
            "cluster_type": "Development"
        }
        
        # Network identity hash (like Solana's network identifier)
        self.network_id = self._generate_network_id()
        
        # Genesis accounts and allocations
        self.genesis_accounts = {}
        self.initial_allocations = {}
        
        # Keypairs for foundational accounts
        self.faucet_keypair = None
        self.bootstrap_validator_keypair = None
        self.bootstrap_vote_keypair = None
        
    def _generate_network_id(self) -> str:
        """
        Generate a unique network identifier hash.
        
        This is like Solana's network hash that prevents nodes from
        accidentally connecting to different networks.
        """
        network_seed = f"ProofWithQuantumAnnealing_Network_{int(time.time())}"
        return hashlib.sha256(network_seed.encode()).hexdigest()
    
    def generate_foundational_keypairs(self) -> Dict[str, str]:
        """
        Generate the foundational keypairs for the network.
        
        Similar to:
        - solana-keygen new --outfile faucet.json
        - solana-keygen new --outfile bootstrap-validator-identity.json
        - solana-keygen new --outfile bootstrap-validator-vote-account.json
        
        Returns:
            Dict mapping keypair types to their public keys
        """
        logger.info("Generating foundational keypairs for genesis block...")
        
        # 1. Faucet/Mint Authority Keypair
        self.faucet_keypair = Wallet()
        faucet_public_key = self.faucet_keypair.public_key_string()
        
        # Save faucet private key
        faucet_private_pem = self.faucet_keypair.get_private_key_pem()
        with open(self.config_dir / "faucet_private_key.pem", "w") as f:
            f.write(faucet_private_pem)
        
        # 2. Bootstrap Validator Identity Keypair
        self.bootstrap_validator_keypair = Wallet()
        validator_public_key = self.bootstrap_validator_keypair.public_key_string()
        
        validator_private_pem = self.bootstrap_validator_keypair.get_private_key_pem()
        with open(self.config_dir / "bootstrap_validator_private_key.pem", "w") as f:
            f.write(validator_private_pem)
        
        # 3. Bootstrap Vote Account Keypair
        self.bootstrap_vote_keypair = Wallet()
        vote_public_key = self.bootstrap_vote_keypair.public_key_string()
        
        vote_private_pem = self.bootstrap_vote_keypair.get_private_key_pem()
        with open(self.config_dir / "bootstrap_vote_private_key.pem", "w") as f:
            f.write(vote_private_pem)
        
        keypairs = {
            "faucet": faucet_public_key,
            "bootstrap_validator": validator_public_key,
            "bootstrap_vote": vote_public_key
        }
        
        logger.info({
            "message": "Foundational keypairs generated",
            "faucet": faucet_public_key[:20] + "...",
            "bootstrap_validator": validator_public_key[:20] + "...",
            "bootstrap_vote": vote_public_key[:20] + "...",
            "network_id": self.network_id[:16] + "..."
        })
        
        return keypairs
    
    def allocate_initial_supply(self, total_supply: int = 1000000000) -> Dict[str, int]:
        """
        Allocate initial token supply (airdrop) to foundational accounts.
        
        Args:
            total_supply: Total initial token supply (in lamports)
            
        Returns:
            Dict mapping public keys to their initial balances
        """
        if not self.faucet_keypair:
            raise ValueError("Must generate foundational keypairs first")
        
        logger.info(f"Allocating initial supply: {total_supply:,} lamports")
        
        # Allocate 90% to faucet for distribution
        faucet_allocation = int(total_supply * 0.9)
        
        # Allocate 5% to bootstrap validator for operations
        validator_allocation = int(total_supply * 0.05)
        
        # Allocate 5% to vote account for staking
        vote_allocation = int(total_supply * 0.05)
        
        self.initial_allocations = {
            self.faucet_keypair.public_key_string(): faucet_allocation,
            self.bootstrap_validator_keypair.public_key_string(): validator_allocation,
            self.bootstrap_vote_keypair.public_key_string(): vote_allocation
        }
        
        logger.info({
            "message": "Initial supply allocated",
            "total_supply": f"{total_supply:,}",
            "faucet_allocation": f"{faucet_allocation:,}",
            "validator_allocation": f"{validator_allocation:,}",
            "vote_allocation": f"{vote_allocation:,}"
        })
        
        return self.initial_allocations
    
    def set_cluster_parameters(self, **kwargs) -> Dict:
        """
        Set cluster configuration parameters.
        
        Args:
            **kwargs: Cluster parameters to override
            
        Returns:
            Updated cluster configuration
        """
        self.cluster_config.update(kwargs)
        
        logger.info({
            "message": "Cluster parameters updated",
            "hashes_per_tick": self.cluster_config["hashes_per_tick"],
            "ticks_per_slot": self.cluster_config["ticks_per_slot"],
            "target_lamports_per_signature": self.cluster_config["target_lamports_per_signature"]
        })
        
        return self.cluster_config
    
    def compile_genesis_data(self) -> Dict:
        """
        Compile all genesis information into a single data structure.
        
        This is like Solana's genesis.bin compilation step.
        
        Returns:
            Complete genesis block data
        """
        if not self.faucet_keypair or not self.initial_allocations:
            raise ValueError("Must generate keypairs and allocate supply first")
        
        # Create deterministic genesis hash
        genesis_timestamp = 1640995200  # Fixed timestamp: Jan 1, 2022 00:00:00 UTC
        
        # Deterministic last_hash for genesis block
        genesis_seed = f"{self.network_id}_{genesis_timestamp}_{self.cluster_config['hashes_per_tick']}"
        genesis_last_hash = hashlib.sha256(genesis_seed.encode()).hexdigest()
        
        genesis_data = {
            "version": "1.0.0",
            "creation_time": genesis_timestamp,
            "network_id": self.network_id,
            "cluster_config": self.cluster_config,
            "accounts": self.initial_allocations,
            "bootstrap_validator": self.bootstrap_validator_keypair.public_key_string(),
            "bootstrap_vote": self.bootstrap_vote_keypair.public_key_string(),
            "faucet": self.faucet_keypair.public_key_string(),
            "genesis_hash": genesis_last_hash,
            "block_height": 0,
            "slot": 0,
            "epoch": 0
        }
        
        logger.info({
            "message": "Genesis data compiled",
            "network_id": self.network_id[:16] + "...",
            "genesis_hash": genesis_last_hash[:16] + "...",
            "total_accounts": len(self.initial_allocations),
            "bootstrap_validator": self.bootstrap_validator_keypair.public_key_string()[:20] + "..."
        })
        
        return genesis_data
    
    def save_genesis_config(self, filename: str = "genesis.json") -> str:
        """
        Save the complete genesis configuration to file.
        
        This is the equivalent of Solana's genesis.bin file that
        must be distributed to all validators.
        
        Args:
            filename: Name of the genesis configuration file
            
        Returns:
            Path to the saved genesis file
        """
        genesis_data = self.compile_genesis_data()
        
        genesis_file_path = self.config_dir / filename
        with open(genesis_file_path, "w") as f:
            json.dump(genesis_data, f, indent=2)
        
        logger.info({
            "message": "Genesis configuration saved",
            "file_path": str(genesis_file_path),
            "file_size": genesis_file_path.stat().st_size,
            "network_id": self.network_id[:16] + "..."
        })
        
        return str(genesis_file_path)
    
    @classmethod
    def load_genesis_config(cls, genesis_file: str) -> Dict:
        """
        Load genesis configuration from file.
        
        This is how all nodes will load the identical genesis block.
        
        Args:
            genesis_file: Path to the genesis configuration file
            
        Returns:
            Genesis block data
        """
        with open(genesis_file, "r") as f:
            genesis_data = json.load(f)
        
        logger.info({
            "message": "Genesis configuration loaded",
            "file_path": genesis_file,
            "network_id": genesis_data["network_id"][:16] + "...",
            "genesis_hash": genesis_data["genesis_hash"][:16] + "...",
            "total_accounts": len(genesis_data["accounts"])
        })
        
        return genesis_data
    
    def create_complete_genesis_setup(self, total_supply: int = 1000000000) -> str:
        """
        Complete end-to-end genesis setup.
        
        This performs all steps:
        1. Generate foundational keypairs
        2. Allocate initial supply
        3. Compile genesis data
        4. Save genesis file
        
        Args:
            total_supply: Total initial token supply
            
        Returns:
            Path to the genesis configuration file
        """
        logger.info("Starting complete Solana-style genesis setup...")
        
        # Step 1: Generate foundational keypairs
        keypairs = self.generate_foundational_keypairs()
        
        # Step 2: Allocate initial supply
        allocations = self.allocate_initial_supply(total_supply)
        
        # Step 3: Save genesis configuration
        genesis_file = self.save_genesis_config()
        
        logger.info({
            "message": "Complete genesis setup finished",
            "genesis_file": genesis_file,
            "network_id": self.network_id,
            "total_supply": f"{total_supply:,}",
            "foundational_accounts": len(keypairs)
        })
        
        return genesis_file


def main():
    """Command-line interface for genesis creation."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Create Solana-style genesis configuration")
    parser.add_argument("--supply", type=int, default=1000000000, help="Total initial supply")
    parser.add_argument("--config-dir", default="genesis_config", help="Genesis config directory")
    
    args = parser.parse_args()
    
    # Create genesis configuration
    genesis_config = GenesisConfig(args.config_dir)
    genesis_file = genesis_config.create_complete_genesis_setup(args.supply)
    
    print(f"✅ Genesis configuration created: {genesis_file}")
    print(f"📄 Network ID: {genesis_config.network_id}")
    print(f"💰 Total Supply: {args.supply:,} lamports")
    print(f"🔑 Foundational keypairs saved in: {args.config_dir}/")
    print(f"\n🚀 Distribute {genesis_file} to all validators before network start!")


if __name__ == "__main__":
    main()
