"""
Account State Model for Sealevel Parallel Execution

This implements the account-based state model that tracks balances
and other account data, with thread-safe operations for parallel execution.
"""

import time
import threading
from typing import Dict, Optional, List, Tuple
from blockchain.utils.logger import logger


class Account:
    """Represents a single account in the blockchain state"""
    
    def __init__(self, public_key: str, balance: float = 0.0):
        self.public_key = public_key
        self.balance = balance
        self.nonce = 0  # Transaction counter for this account
        self.last_modified = time.time()
        self.lock = threading.RLock()  # Re-entrant lock for thread safety
    
    def get_balance(self) -> float:
        """Thread-safe balance getter"""
        with self.lock:
            return self.balance
    
    def update_balance(self, delta: float) -> bool:
        """Thread-safe balance update"""
        with self.lock:
            new_balance = self.balance + delta
            if new_balance < 0:
                return False  # Insufficient funds
            
            self.balance = new_balance
            self.last_modified = time.time()
            return True
    
    def set_balance(self, new_balance: float) -> bool:
        """Thread-safe balance setter"""
        with self.lock:
            if new_balance < 0:
                return False
            
            self.balance = new_balance
            self.last_modified = time.time()
            return True
    
    def increment_nonce(self):
        """Thread-safe nonce increment"""
        with self.lock:
            self.nonce += 1
            self.last_modified = time.time()
    
    def to_dict(self) -> Dict:
        """Convert account to dictionary representation"""
        with self.lock:
            return {
                'public_key': self.public_key,
                'balance': self.balance,
                'nonce': self.nonce,
                'last_modified': self.last_modified
            }


class AccountModel:
    """
    Thread-safe account state model for parallel transaction execution.
    
    This manages all account balances and provides atomic operations
    for the Sealevel parallel executor.
    """
    
    def __init__(self, genesis_accounts: Optional[Dict[str, float]] = None):
        self.accounts: Dict[str, Account] = {}
        self.global_lock = threading.RLock()
        self.stats = {
            'total_accounts': 0,
            'total_transactions_processed': 0,
            'last_state_update': time.time()
        }
        
        # Initialize with genesis accounts if provided
        if genesis_accounts:
            for public_key, balance in genesis_accounts.items():
                self.create_account(public_key, balance)
        
        logger.info(f"AccountModel initialized with {len(self.accounts)} genesis accounts")
    
    def create_account(self, public_key: str, initial_balance: float = 0.0) -> Account:
        """Create a new account with thread safety"""
        with self.global_lock:
            if public_key in self.accounts:
                return self.accounts[public_key]
            
            account = Account(public_key, initial_balance)
            self.accounts[public_key] = account
            self.stats['total_accounts'] += 1
            
            logger.debug(f"Created account {public_key[:20]}... with balance {initial_balance}")
            return account
    
    def get_account(self, public_key: str) -> Optional[Account]:
        """Get account by public key (thread-safe)"""
        with self.global_lock:
            return self.accounts.get(public_key)
    
    def get_balance(self, public_key: str) -> float:
        """Get account balance, creating account if it doesn't exist"""
        account = self.get_account(public_key)
        if account is None:
            # Auto-create account with zero balance
            account = self.create_account(public_key, 0.0)
        
        return account.get_balance()
    
    def update_balance(self, public_key: str, delta: float) -> bool:
        """Update account balance by delta amount"""
        account = self.get_account(public_key)
        if account is None:
            # Auto-create account if it doesn't exist
            if delta >= 0:  # Only allow positive initial balances
                account = self.create_account(public_key, delta)
                return True
            else:
                return False  # Can't create account with negative balance
        
        success = account.update_balance(delta)
        if success:
            self.stats['total_transactions_processed'] += 1
            self.stats['last_state_update'] = time.time()
        
        return success
    
    def set_balance(self, public_key: str, new_balance: float) -> bool:
        """Set account balance to specific amount"""
        account = self.get_account(public_key)
        if account is None:
            # Auto-create account with the specified balance
            account = self.create_account(public_key, new_balance)
            return True
        
        success = account.set_balance(new_balance)
        if success:
            self.stats['last_state_update'] = time.time()
        
        return success
    
    def transfer(self, from_public_key: str, to_public_key: str, amount: float) -> bool:
        """
        Atomic transfer between accounts.
        
        This is thread-safe and ensures either both accounts are updated
        or neither is updated (atomicity).
        """
        if amount <= 0:
            return False
        
        # Get or create accounts
        from_account = self.get_account(from_public_key)
        if from_account is None:
            return False  # Sender must exist
        
        to_account = self.get_account(to_public_key)
        if to_account is None:
            to_account = self.create_account(to_public_key, 0.0)
        
        # Atomic transfer using proper lock ordering to prevent deadlocks
        # Always acquire locks in consistent order (by public key)
        if from_public_key < to_public_key:
            first_account, second_account = from_account, to_account
        else:
            first_account, second_account = to_account, from_account
        
        with first_account.lock:
            with second_account.lock:
                # Check sender has sufficient balance
                if from_account.balance < amount:
                    return False
                
                # Perform atomic transfer
                from_account.balance -= amount
                to_account.balance += amount
                
                # Update timestamps
                current_time = time.time()
                from_account.last_modified = current_time
                to_account.last_modified = current_time
                
                # Update stats
                self.stats['total_transactions_processed'] += 1
                self.stats['last_state_update'] = current_time
                
                return True
    
    def get_all_balances(self) -> Dict[str, float]:
        """Get all account balances (thread-safe snapshot)"""
        with self.global_lock:
            balances = {}
            for public_key, account in self.accounts.items():
                balances[public_key] = account.get_balance()
            return balances
    
    @property
    def balances(self) -> Dict[str, float]:
        """Property access to all balances for compatibility"""
        return self.get_all_balances()
    
    @balances.setter
    def balances(self, new_balances: Dict[str, float]):
        """Property setter for balances - updates all account balances"""
        with self.global_lock:
            for public_key, balance in new_balances.items():
                if public_key in self.accounts:
                    self.accounts[public_key].set_balance(balance)
                else:
                    # Create new account with the balance
                    self.create_account(public_key, balance)
    
    def get_total_supply(self) -> float:
        """Calculate total supply across all accounts"""
        total = 0.0
        with self.global_lock:
            for account in self.accounts.values():
                total += account.get_balance()
        return total
    
    def get_account_count(self) -> int:
        """Get total number of accounts"""
        with self.global_lock:
            return len(self.accounts)
    
    def get_state_snapshot(self) -> Dict:
        """Get complete state snapshot for debugging"""
        with self.global_lock:
            snapshot = {
                'accounts': {},
                'stats': self.stats.copy(),
                'total_supply': self.get_total_supply(),
                'account_count': len(self.accounts),
                'snapshot_time': time.time()
            }
            
            for public_key, account in self.accounts.items():
                snapshot['accounts'][public_key] = account.to_dict()
            
            return snapshot
    
    def validate_state_consistency(self) -> Dict:
        """Validate that the account state is consistent"""
        with self.global_lock:
            issues = []
            total_balance = 0.0
            
            for public_key, account in self.accounts.items():
                balance = account.get_balance()
                
                # Check for negative balances
                if balance < 0:
                    issues.append(f"Account {public_key[:20]}... has negative balance: {balance}")
                
                total_balance += balance
            
            # Additional consistency checks could be added here
            
            return {
                'is_consistent': len(issues) == 0,
                'issues': issues,
                'total_accounts': len(self.accounts),
                'total_balance': total_balance,
                'validation_time': time.time()
            }
    
    def cleanup_empty_accounts(self) -> int:
        """Remove accounts with zero balance and no recent activity"""
        with self.global_lock:
            current_time = time.time()
            cleanup_threshold = current_time - (24 * 60 * 60)  # 24 hours
            
            accounts_to_remove = []
            for public_key, account in self.accounts.items():
                if (account.get_balance() == 0.0 and 
                    account.last_modified < cleanup_threshold and
                    account.nonce == 0):
                    accounts_to_remove.append(public_key)
            
            for public_key in accounts_to_remove:
                del self.accounts[public_key]
                self.stats['total_accounts'] -= 1
            
            logger.info(f"Cleaned up {len(accounts_to_remove)} empty accounts")
            return len(accounts_to_remove)
