import logging

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from blockchain.block import Block
from blockchain.transaction.transaction import Transaction
from blockchain.utils.helpers import BlockchainUtils


class Wallet:
    def __init__(self):
        self.key_pair = ec.generate_private_key(ec.SECP256R1())

    def from_key(self, key_input):
        """
        Load private key from file path or private key string.
        
        Args:
            key_input: Either a file path to a PEM file or a PEM-formatted private key string
        """
        try:
            # First try as a file path
            with open(key_input, "rb") as key_file:
                key_data = key_file.read()
            
            key = serialization.load_pem_private_key(
                key_data,
                password=None,
            )
            self.key_pair = key
        except (FileNotFoundError, OSError):
            # If file not found, try as a private key string
            try:
                if isinstance(key_input, str):
                    key_data = key_input.encode('utf-8')
                else:
                    key_data = key_input
                
                key = serialization.load_pem_private_key(
                    key_data,
                    password=None,
                )
                self.key_pair = key
            except Exception as e:
                logging.error(f"Failed to load private key from string: {e}")
                raise ValueError(f"Invalid private key format: {e}")

    def sign(self, data):
        data_hash = BlockchainUtils.hash(data)
        signature = self.key_pair.sign(
            data_hash,
            ec.ECDSA(hashes.SHA256())
        )
        return signature.hex()

    @staticmethod
    def signature_valid(data, signature, public_key_string):
        signature = bytes.fromhex(signature)
        data_hash = BlockchainUtils.hash(data)
        public_key = serialization.load_pem_public_key(
            bytes(public_key_string, "utf-8")
        )

        try:
            public_key.verify(
                signature,
                data_hash,
                ec.ECDSA(hashes.SHA256())
            )
            return True
        except InvalidSignature:
            logging.error(f"Invalid signature, data hash: {data_hash}")

        return False

    def public_key_string(self):
        public_key_pem = self.key_pair.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return public_key_pem.decode("utf-8")

    def get_private_key_pem(self):
        """Export private key in PEM format for genesis configuration."""
        from cryptography.hazmat.primitives import serialization
        
        private_key_pem = self.key_pair.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        return private_key_pem.decode("utf-8")

    def create_transaction(self, receiver, amount, type):
        transaction = Transaction(self.public_key_string(), receiver, amount, type)
        signature = self.sign(transaction.payload())
        transaction.sign(signature)
        return transaction

    def create_block(self, transactions, last_hash, block_count):
        block = Block(transactions, last_hash, self.public_key_string(), block_count)
        signature = self.sign(block.payload())
        block.sign(signature)
        return block
