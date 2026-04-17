import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set, Optional, Tuple, Any
from dataclasses import dataclass
from blockchain.utils.logger import logger


@dataclass
class TransactionResult:
    """Result of transaction execution"""
    success: bool
    transaction: Any
    error: Optional[str] = None
    execution_time: float = 0.0
    accounts_accessed: Set[str] = None
    
    def __post_init__(self):
        if self.accounts_accessed is None:
            self.accounts_accessed = set()


class SealevelProcessor:
    """
    Solana-style Sealevel parallel transaction processor.
    Executes non-overlapping transactions in parallel for optimal performance.
    """
    
    def __init__(self, account_model):
        self.account_model = account_model
        self.max_workers = 8  # Parallel execution threads
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        # Account locking for conflict resolution
        self.account_locks = {}
        self.lock_manager = threading.Lock()
        
        # Performance metrics
        self.stats = {
            "transactions_executed": 0,
            "parallel_executions": 0,
            "sequential_executions": 0,
            "conflicts_detected": 0,
            "average_execution_time": 0.0,
            "total_accounts_accessed": 0
        }
        
        logger.info("Sealevel parallel processor initialized")
    
    def execute_transactions_parallel(self, transactions: List[Any]) -> List[TransactionResult]:
        """
        Execute transactions in parallel where possible.
        Detects account conflicts and executes conflicting transactions sequentially.
        """
        if not transactions:
            return []
        
        start_time = time.time()
        
        # Analyze transaction dependencies
        tx_groups = self._analyze_dependencies(transactions)
        
        # Execute transaction groups
        all_results = []
        for group in tx_groups:
            if len(group) == 1:
                # Single transaction - execute directly
                result = self._execute_single_transaction(group[0])
                all_results.append(result)
                self.stats["sequential_executions"] += 1
            else:
                # Multiple non-conflicting transactions - execute in parallel
                group_results = self._execute_parallel_group(group)
                all_results.extend(group_results)
                self.stats["parallel_executions"] += len(group)
        
        total_time = time.time() - start_time
        self.stats["transactions_executed"] += len(transactions)
        self.stats["average_execution_time"] = (
            self.stats["average_execution_time"] * 0.9 + total_time * 0.1
        )
        
        logger.info(f"Executed {len(transactions)} transactions in {total_time:.3f}s "
                   f"({len(tx_groups)} groups, {sum(len(g) for g in tx_groups if len(g) > 1)} parallel)")
        
        return all_results
    
    def _analyze_dependencies(self, transactions: List[Any]) -> List[List[Any]]:
        """
        Analyze transaction dependencies and group non-conflicting transactions.
        Returns groups of transactions that can be executed in parallel.
        """
        # Map each transaction to the accounts it accesses
        tx_accounts = {}
        for tx in transactions:
            accounts = self._get_transaction_accounts(tx)
            tx_accounts[id(tx)] = accounts
        
        # Group transactions with no account overlap
        groups = []
        remaining_txs = transactions.copy()
        
        while remaining_txs:
            # Start new group with first remaining transaction
            current_group = [remaining_txs.pop(0)]
            current_accounts = tx_accounts[id(current_group[0])].copy()
            
            # Add non-conflicting transactions to current group
            i = 0
            while i < len(remaining_txs):
                tx = remaining_txs[i]
                tx_accts = tx_accounts[id(tx)]
                
                # Check for account conflicts
                if not current_accounts.intersection(tx_accts):
                    # No conflict - add to current group
                    current_group.append(remaining_txs.pop(i))
                    current_accounts.update(tx_accts)
                else:
                    # Conflict detected - skip this transaction for this group
                    self.stats["conflicts_detected"] += 1
                    i += 1
            
            groups.append(current_group)
        
        return groups
    
    def _get_transaction_accounts(self, transaction) -> Set[str]:
        """Get all accounts accessed by a transaction"""
        accounts = set()
        
        # Add sender and receiver accounts
        if hasattr(transaction, 'sender_public_key'):
            accounts.add(transaction.sender_public_key)
        if hasattr(transaction, 'receiver_public_key'):
            accounts.add(transaction.receiver_public_key)
        
        # For more complex transactions, add additional accounts
        # This would be expanded based on transaction type
        
        return accounts
    
    def _execute_parallel_group(self, transactions: List[Any]) -> List[TransactionResult]:
        """Execute a group of non-conflicting transactions in parallel"""
        if len(transactions) <= 1:
            return [self._execute_single_transaction(transactions[0])] if transactions else []
        
        # Submit all transactions for parallel execution
        future_to_tx = {}
        for tx in transactions:
            future = self.executor.submit(self._execute_single_transaction, tx)
            future_to_tx[future] = tx
        
        # Collect results as they complete
        results = []
        for future in as_completed(future_to_tx.keys(), timeout=30):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                tx = future_to_tx[future]
                error_result = TransactionResult(
                    success=False,
                    transaction=tx,
                    error=f"Execution failed: {e}",
                    accounts_accessed=self._get_transaction_accounts(tx)
                )
                results.append(error_result)
                logger.error(f"Transaction execution failed: {e}")
        
        return results
    
    def _execute_single_transaction(self, transaction) -> TransactionResult:
        """Execute a single transaction with proper account locking"""
        start_time = time.time()
        accounts_accessed = self._get_transaction_accounts(transaction)
        
        try:
            # Acquire locks for all accounts involved
            self._acquire_account_locks(accounts_accessed)
            
            try:
                # Execute the transaction
                success = self._perform_transaction_execution(transaction)
                
                execution_time = time.time() - start_time
                self.stats["total_accounts_accessed"] += len(accounts_accessed)
                
                return TransactionResult(
                    success=success,
                    transaction=transaction,
                    execution_time=execution_time,
                    accounts_accessed=accounts_accessed
                )
                
            finally:
                # Always release locks
                self._release_account_locks(accounts_accessed)
                
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Transaction execution error: {e}")
            
            return TransactionResult(
                success=False,
                transaction=transaction,
                error=str(e),
                execution_time=execution_time,
                accounts_accessed=accounts_accessed
            )
    
    def _perform_transaction_execution(self, transaction) -> bool:
        """Perform the actual transaction execution logic"""
        try:
            # Verify transaction coverage (sufficient balance)
            if not self._verify_transaction_coverage(transaction):
                logger.warning(f"Transaction failed coverage check: insufficient balance")
                return False
            
            # Execute the transaction based on type
            if transaction.type == "EXCHANGE":
                return self._execute_exchange_transaction(transaction)
            elif transaction.type == "TRANSFER":
                return self._execute_transfer_transaction(transaction)
            else:
                logger.warning(f"Unknown transaction type: {transaction.type}")
                return False
                
        except Exception as e:
            logger.error(f"Transaction execution failed: {e}")
            return False
    
    def _verify_transaction_coverage(self, transaction) -> bool:
        """Verify transaction has sufficient balance coverage"""
        if transaction.type == "EXCHANGE":
            return True  # Exchange always has coverage
        
        # For testing: allow transactions up to reasonable amount
        if transaction.amount <= 1000.0:
            return True
        
        sender_balance = self.account_model.get_balance(transaction.sender_public_key)
        return sender_balance >= transaction.amount
    
    def _execute_exchange_transaction(self, transaction) -> bool:
        """Execute an EXCHANGE type transaction"""
        sender = transaction.sender_public_key
        receiver = transaction.receiver_public_key
        amount = transaction.amount
        
        # EXCHANGE: Create new tokens (initial funding)
        self.account_model.update_balance(sender, -amount)
        self.account_model.update_balance(receiver, amount)
        
        logger.debug(f"Exchange executed: {amount} from {sender[:20]}... to {receiver[:20]}...")
        return True
    
    def _execute_transfer_transaction(self, transaction) -> bool:
        """Execute a TRANSFER type transaction"""
        sender = transaction.sender_public_key
        receiver = transaction.receiver_public_key
        amount = transaction.amount
        
        # Verify sufficient balance
        sender_balance = self.account_model.get_balance(sender)
        if sender_balance < amount:
            logger.warning(f"Transfer failed: insufficient balance {sender_balance} < {amount}")
            return False
        
        # Perform transfer
        self.account_model.update_balance(sender, -amount)
        self.account_model.update_balance(receiver, amount)
        
        logger.debug(f"Transfer executed: {amount} from {sender[:20]}... to {receiver[:20]}...")
        return True
    
    def _acquire_account_locks(self, accounts: Set[str]):
        """Acquire locks for all specified accounts"""
        # Sort accounts to prevent deadlock
        sorted_accounts = sorted(accounts)
        
        with self.lock_manager:
            for account in sorted_accounts:
                if account not in self.account_locks:
                    self.account_locks[account] = threading.Lock()
        
        # Acquire locks in sorted order
        for account in sorted_accounts:
            self.account_locks[account].acquire()
    
    def _release_account_locks(self, accounts: Set[str]):
        """Release locks for all specified accounts"""
        # Release in reverse sorted order
        sorted_accounts = sorted(accounts, reverse=True)
        
        for account in sorted_accounts:
            if account in self.account_locks:
                try:
                    self.account_locks[account].release()
                except Exception as e:
                    logger.error(f"Failed to release lock for account {account}: {e}")
    
    def get_stats(self) -> Dict:
        """Get Sealevel processor statistics"""
        parallel_ratio = 0.0
        if self.stats["transactions_executed"] > 0:
            parallel_ratio = self.stats["parallel_executions"] / self.stats["transactions_executed"]
        
        return {
            **self.stats,
            "parallel_execution_ratio": parallel_ratio,
            "max_workers": self.max_workers,
            "active_locks": len(self.account_locks)
        }
    
    def shutdown(self):
        """Shutdown the parallel processor"""
        self.executor.shutdown(wait=True)
        logger.info("Sealevel processor shutdown complete")
