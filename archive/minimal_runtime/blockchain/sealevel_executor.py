"""
Sealevel-style Parallel Transaction Executor

This implements Solana's parallel execution model where transactions
that don't access overlapping state can be executed concurrently.
"""

import time
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set, Tuple, Optional
from blockchain.utils.logger import logger


class AccountAccess:
    """Represents how a transaction accesses an account"""
    READ = "read"
    WRITE = "write"
    
    def __init__(self, account_id: str, access_type: str):
        self.account_id = account_id
        self.access_type = access_type
    
    def __repr__(self):
        return f"AccountAccess({self.account_id}, {self.access_type})"


class TransactionDependency:
    """Analyzes transaction dependencies for parallel execution"""
    
    def __init__(self, transaction):
        self.transaction = transaction
        self.account_accesses = self._analyze_account_access(transaction)
        self.read_accounts = {acc.account_id for acc in self.account_accesses if acc.access_type == AccountAccess.READ}
        self.write_accounts = {acc.account_id for acc in self.account_accesses if acc.access_type == AccountAccess.WRITE}
        self.all_accounts = self.read_accounts | self.write_accounts
    
    def _analyze_account_access(self, transaction) -> List[AccountAccess]:
        """
        Analyze which accounts a transaction will read from and write to.
        
        In a full implementation, this would parse the transaction's program instructions.
        For now, we analyze basic transfer transactions.
        """
        accesses = []
        
        # Sender account (read balance, write new balance)
        accesses.append(AccountAccess(transaction.sender_public_key, AccountAccess.READ))
        accesses.append(AccountAccess(transaction.sender_public_key, AccountAccess.WRITE))
        
        # Receiver account (read balance, write new balance) 
        accesses.append(AccountAccess(transaction.receiver_public_key, AccountAccess.READ))
        accesses.append(AccountAccess(transaction.receiver_public_key, AccountAccess.WRITE))
        
        # For more complex transactions, this would analyze:
        # - Smart contract state access patterns
        # - System program calls
        # - Cross-program invocations
        
        return accesses
    
    def conflicts_with(self, other: 'TransactionDependency') -> bool:
        """
        Check if this transaction conflicts with another transaction.
        
        Conflicts occur when:
        1. Both transactions write to the same account
        2. One writes and the other reads the same account
        """
        # Write-Write conflict
        if self.write_accounts & other.write_accounts:
            return True
        
        # Read-Write conflict (either direction)
        if (self.write_accounts & other.read_accounts) or (self.read_accounts & other.write_accounts):
            return True
        
        return False


class ParallelExecutionBatch:
    """A batch of transactions that can be executed in parallel"""
    
    def __init__(self, batch_id: int):
        self.batch_id = batch_id
        self.transactions = []
        self.dependencies = []
        self.execution_results = {}
        self.start_time = None
        self.end_time = None
    
    def add_transaction(self, transaction, dependency: TransactionDependency):
        """Add a transaction to this parallel batch"""
        self.transactions.append(transaction)
        self.dependencies.append(dependency)
    
    def can_add_transaction(self, dependency: TransactionDependency) -> bool:
        """Check if a transaction can be added to this batch without conflicts"""
        for existing_dep in self.dependencies:
            if dependency.conflicts_with(existing_dep):
                return False
        return True
    
    def execute_batch(self, account_model) -> Dict:
        """Execute all transactions in this batch in parallel"""
        self.start_time = time.time()
        
        logger.info(f"Executing parallel batch {self.batch_id} with {len(self.transactions)} transactions")
        
        # Create a copy of account state for atomic execution
        batch_account_state = {}
        
        # Execute transactions in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(len(self.transactions), 8)) as executor:
            # Submit all transactions for parallel execution
            future_to_tx = {}
            for i, (transaction, dependency) in enumerate(zip(self.transactions, self.dependencies)):
                future = executor.submit(self._execute_single_transaction, 
                                       transaction, dependency, account_model, i)
                future_to_tx[future] = (transaction, i)
            
            # Collect results as they complete
            execution_results = {}
            for future in as_completed(future_to_tx):
                transaction, tx_index = future_to_tx[future]
                try:
                    result = future.result()
                    execution_results[tx_index] = result
                    logger.debug(f"Transaction {tx_index} in batch {self.batch_id} executed successfully")
                except Exception as e:
                    logger.error(f"Transaction {tx_index} in batch {self.batch_id} failed: {e}")
                    execution_results[tx_index] = {'success': False, 'error': str(e)}
        
        self.end_time = time.time()
        execution_time = (self.end_time - self.start_time) * 1000
        
        self.execution_results = execution_results
        
        return {
            'batch_id': self.batch_id,
            'transaction_count': len(self.transactions),
            'execution_time_ms': execution_time,
            'successful_executions': sum(1 for r in execution_results.values() if r.get('success', False)),
            'failed_executions': sum(1 for r in execution_results.values() if not r.get('success', False)),
            'results': execution_results
        }
    
    def _execute_single_transaction(self, transaction, dependency: TransactionDependency, 
                                   account_model, tx_index: int) -> Dict:
        """Execute a single transaction within the parallel batch"""
        try:
            # Simulate transaction execution
            # In a real implementation, this would:
            # 1. Load account states for all accessed accounts
            # 2. Execute the transaction's program instructions
            # 3. Apply state changes
            # 4. Return the state delta
            
            start_time = time.time()
            
            # For basic transfers, execute the balance changes
            sender = transaction.sender_public_key
            receiver = transaction.receiver_public_key
            amount = transaction.amount
            
            # Get current balances (thread-safe read)
            sender_balance = account_model.get_balance(sender)
            receiver_balance = account_model.get_balance(receiver)
            
            # Validate sufficient balance
            if sender_balance < amount:
                return {
                    'success': False,
                    'error': f'Insufficient balance: {sender_balance} < {amount}',
                    'execution_time_ms': (time.time() - start_time) * 1000
                }
            
            # Calculate state changes (don't apply yet - that's done atomically later)
            state_changes = {
                'account_deltas': {
                    sender: -amount,
                    receiver: amount
                },
                'transaction_id': transaction.id,
                'execution_time_ms': (time.time() - start_time) * 1000
            }
            
            return {
                'success': True,
                'state_changes': state_changes,
                'execution_time_ms': (time.time() - start_time) * 1000
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'execution_time_ms': (time.time() - start_time) * 1000
            }


class SealevelExecutor:
    """
    Solana-style parallel transaction executor.
    
    This is the core of Solana's performance - the ability to execute
    non-conflicting transactions in parallel across multiple CPU cores.
    """
    
    def __init__(self, max_workers: int = 8):
        self.max_workers = max_workers
        self.execution_stats = {
            'total_batches': 0,
            'total_transactions': 0,
            'total_execution_time_ms': 0,
            'parallel_efficiency': 0,
            'conflict_rate': 0
        }
    
    def execute_transactions_parallel(self, transactions: List, account_model) -> Dict:
        """
        Execute transactions in parallel using dependency analysis.
        
        This is the main entry point that implements Solana's parallel execution model.
        """
        if not transactions:
            return {
                'batches': [],
                'total_transactions': 0,
                'total_execution_time_ms': 0,
                'parallel_efficiency': 100,
                'state_root_hash': self._compute_state_root_hash(account_model)
            }
        
        start_time = time.time()
        
        logger.info(f"Starting parallel execution of {len(transactions)} transactions")
        
        # Step 1: Analyze dependencies for all transactions
        dependencies = []
        for transaction in transactions:
            dep = TransactionDependency(transaction)
            dependencies.append(dep)
        
        # Step 2: Group transactions into parallel batches
        batches = self._create_parallel_batches(transactions, dependencies)
        
        logger.info(f"Created {len(batches)} parallel execution batches")
        
        # Step 3: Execute batches sequentially (transactions within each batch run in parallel)
        batch_results = []
        total_conflicts = 0
        
        for batch in batches:
            batch_result = batch.execute_batch(account_model)
            batch_results.append(batch_result)
            
            # Apply state changes atomically after parallel execution
            self._apply_batch_state_changes(batch, account_model)
        
        total_time = (time.time() - start_time) * 1000
        
        # Calculate efficiency metrics
        sequential_estimate = len(transactions) * 5  # Assume 5ms per transaction sequentially
        parallel_efficiency = min(100, (sequential_estimate / total_time) * 100) if total_time > 0 else 100
        
        # Update stats
        self.execution_stats['total_batches'] += len(batches)
        self.execution_stats['total_transactions'] += len(transactions)
        self.execution_stats['total_execution_time_ms'] += total_time
        self.execution_stats['parallel_efficiency'] = parallel_efficiency
        
        # Compute final state root hash
        state_root_hash = self._compute_state_root_hash(account_model)
        
        result = {
            'batches': batch_results,
            'total_transactions': len(transactions),
            'total_execution_time_ms': total_time,
            'parallel_efficiency': parallel_efficiency,
            'sequential_estimate_ms': sequential_estimate,
            'speedup_factor': sequential_estimate / total_time if total_time > 0 else 1,
            'state_root_hash': state_root_hash,
            'batch_count': len(batches),
            'avg_batch_size': len(transactions) / len(batches) if batches else 0
        }
        
        logger.info(f"Parallel execution completed: {len(transactions)} transactions in {total_time:.2f}ms "
                   f"({parallel_efficiency:.1f}% efficiency, {result['speedup_factor']:.1f}x speedup)")
        
        return result
    
    def _create_parallel_batches(self, transactions: List, dependencies: List[TransactionDependency]) -> List[ParallelExecutionBatch]:
        """
        Group transactions into batches that can be executed in parallel.
        
        Uses a greedy algorithm to maximize parallelism while respecting dependencies.
        """
        batches = []
        remaining_transactions = list(zip(transactions, dependencies))
        batch_id = 0
        
        while remaining_transactions:
            # Create a new batch
            current_batch = ParallelExecutionBatch(batch_id)
            batch_id += 1
            
            # Try to add as many non-conflicting transactions as possible to this batch
            transactions_added = []
            
            for i, (transaction, dependency) in enumerate(remaining_transactions):
                if current_batch.can_add_transaction(dependency):
                    current_batch.add_transaction(transaction, dependency)
                    transactions_added.append(i)
            
            # Remove added transactions from remaining list (in reverse order to maintain indices)
            for i in reversed(transactions_added):
                remaining_transactions.pop(i)
            
            if current_batch.transactions:
                batches.append(current_batch)
            else:
                # This shouldn't happen unless there's a bug
                logger.error("Failed to create batch - possible dependency analysis error")
                break
        
        return batches
    
    def _apply_batch_state_changes(self, batch: ParallelExecutionBatch, account_model):
        """
        Atomically apply all state changes from a parallel batch.
        
        This ensures that all transactions in the batch appear to execute simultaneously.
        """
        for i, transaction in enumerate(batch.transactions):
            result = batch.execution_results.get(i, {})
            if result.get('success') and 'state_changes' in result:
                state_changes = result['state_changes']
                
                # Apply account balance deltas
                for account_id, delta in state_changes.get('account_deltas', {}).items():
                    account_model.update_balance(account_id, delta)
    
    def _compute_state_root_hash(self, account_model) -> str:
        """
        Compute a cryptographic hash of the entire account state.
        
        This is equivalent to Solana's state root hash that proves the
        state after all transactions have been executed.
        """
        try:
            # Get all account balances using the proper method
            all_accounts = account_model.get_all_balances()
            
            # Sort accounts for deterministic hashing
            sorted_accounts = sorted(all_accounts.items())
            
            # Create state string for hashing (deterministic - no timestamp)
            state_string = ""
            for account_id, balance in sorted_accounts:
                state_string += f"{account_id}:{balance};"
            
            # Remove trailing semicolon for cleaner hash
            if state_string.endswith(';'):
                state_string = state_string[:-1]
            
            # Compute SHA-256 hash (deterministic)
            state_hash = hashlib.sha256(state_string.encode()).hexdigest()
            
            logger.debug(f"Computed state root hash: {state_hash[:16]}... from {len(sorted_accounts)} accounts")
            
            return state_hash
            
        except Exception as e:
            logger.error(f"Failed to compute state root hash: {e}")
            # Return a fallback hash
            return hashlib.sha256(f"fallback:{time.time()}".encode()).hexdigest()
            state_string = ""
            for account_id, balance in sorted_accounts:
                state_string += f"{account_id}:{balance};"
            
            # Remove trailing semicolon for cleaner hash
            if state_string.endswith(';'):
                state_string = state_string[:-1]
            
            # Compute SHA-256 hash (deterministic)
            state_hash = hashlib.sha256(state_string.encode()).hexdigest()
            
            logger.debug(f"Computed state root hash: {state_hash[:16]}... from {len(sorted_accounts)} accounts")
            
            return state_hash
            
        except Exception as e:
            logger.error(f"Failed to compute state root hash: {e}")
            # Return a deterministic fallback hash
            return hashlib.sha256("fallback:empty_state".encode()).hexdigest()
    
    def get_execution_stats(self) -> Dict:
        """Get comprehensive statistics about parallel execution performance"""
        return {
            'executor_stats': self.execution_stats.copy(),
            'configuration': {
                'max_workers': self.max_workers
            },
            'performance_metrics': {
                'avg_execution_time_ms': (
                    self.execution_stats['total_execution_time_ms'] / 
                    max(1, self.execution_stats['total_batches'])
                ),
                'avg_transactions_per_batch': (
                    self.execution_stats['total_transactions'] / 
                    max(1, self.execution_stats['total_batches'])
                ),
                'total_processed': self.execution_stats['total_transactions']
            }
        }
