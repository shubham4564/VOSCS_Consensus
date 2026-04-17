import copy
import time
import json


class Block:
    def __init__(self, transactions, last_hash, block_proposer, block_count):
        self.transactions = transactions
        self.last_hash = last_hash
        self.forger = block_proposer  # Field name kept as 'forger' for compatibility, but represents block proposer
        self.block_count = block_count
        self.timestamp = time.time()
        self.signature = ""

    @staticmethod
    def genesis():
        genesis_block = Block([], "genesis_hash", "genesis", 0)
        genesis_block.timestamp = 0
        return genesis_block

    def to_dict(self):
        data = copy.deepcopy(self.__dict__)
        transactions_readable = []
        for transaction in data["transactions"]:
            transactions_readable.append(transaction.to_dict())
        data["transactions"] = transactions_readable
        return data

    def payload(self):
        """
        Generate the block payload for signing/verification.
        Only includes core fields that existed when the block was originally signed.
        Excludes metadata fields added after block creation.
        """
        # Core fields that are part of the original block structure
        core_payload = {
            "transactions": [],
            "last_hash": self.last_hash,
            "forger": self.forger,
            "block_count": self.block_count,
            "timestamp": self.timestamp,
            "signature": ""  # Always empty for payload generation
        }
        
        # Convert transactions to dictionary format
        for transaction in self.transactions:
            core_payload["transactions"].append(transaction.to_dict())
            
        return core_payload

    def sign(self, signature):
        self.signature = signature

    def calculate_size(self):
        """
        Calculate the size of the block in bytes.
        Returns the size of the JSON representation of the block.
        """
        try:
            block_dict = self.to_dict()
            block_json = json.dumps(block_dict, separators=(',', ':'))
            return len(block_json.encode('utf-8'))
        except Exception:
            # Fallback: estimate size if JSON serialization fails
            base_size = 200  # Base block overhead
            transaction_size = len(self.transactions) * 300  # Estimate ~300 bytes per transaction
            return base_size + transaction_size

    def is_within_size_limit(self, max_size_bytes):
        """
        Check if the block is within the specified size limit.
        
        Args:
            max_size_bytes (int): Maximum allowed block size in bytes
            
        Returns:
            bool: True if block is within size limit, False otherwise
        """
        return self.calculate_size() <= max_size_bytes
