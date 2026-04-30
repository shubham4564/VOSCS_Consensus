#!/usr/bin/env python3
"""Throughput and Finality Evaluation
======================================

This script evaluates transaction throughput, block production time, and 
transaction finality time across different consensus strategies.

Metrics measured:
- Transaction Throughput (TPS): transactions processed per second
- Block Production Time: time to produce each block
- Transaction Finality Time: time from transaction submission to finalization

Strategies evaluated:
- quantum: QuantumAnnealingConsensus (QUBO optimization + VRF + probe protocol)
- greedy_score: Single-metric greedy selection
- weighted_score: Probabilistic selection weighted by suitability
- round_robin: Rotating leader selection (Tendermint-style)
- pos_stake: Proof-of-Stake weighted lottery (Ouroboros-style)
- pow_hash: Proof-of-Work hash lottery (Bitcoin-style)

References:
- Round Robin: Buchman et al., "Tendermint: Byzantine Fault Tolerance" (2016)
- Weighted Selection: Gilad et al., "Algorand: Scaling Byzantine Agreements" (SOSP 2017)
- PoS: Kiayias et al., "Ouroboros Praos" (EUROCRYPT 2018)
- PoW: Nakamoto, "Bitcoin: A Peer-to-Peer Electronic Cash System" (2008)
- Recent: Buterin et al., "Combining GHOST and Casper" (2020)

Output: JSON metrics and comparison graphs.
"""

import hashlib
import hmac
import os
import sys
import time
import random
import json
import statistics
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import defaultdict


def _ensure_repo_root_on_path() -> None:
    """Ensure the repository root is on sys.path for local imports."""
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

import matplotlib.pyplot as plt

plt.rcParams.update(
    {
        "font.family": ["Nimbus Roman", "serif"],
        "font.serif": ["Nimbus Roman"],
        "axes.unicode_minus": False,
    }
)

from blockchain.quantum_consensus import QuantumAnnealingConsensus
from blockchain.transaction.wallet import Wallet
from blockchain.transaction.transaction import Transaction
from blockchain.blockchain import Blockchain
from blockchain.utils.result_layout import create_run_layout, write_run_metadata


@dataclass
class ThroughputConfig:
    """Configuration for throughput evaluation."""
    num_nodes: int = 50
    num_blocks: int = 100  # Number of blocks to produce
    transactions_per_block: int = 500  # Target transactions per block
    attacker_fraction: float = 0.2
    seed: int = 42
    output_dir: str = "reports"
    
    # Timing parameters (in seconds)
    base_block_time: float = 0.4  # Base time to produce a block
    network_latency: float = 0.05  # Network propagation delay
    finality_confirmations: int = 6  # Blocks needed for finality
    
    # Real transaction mode
    use_real_transactions: bool = False  # If True, create real signed transactions
    num_wallets: int = 20  # Number of test wallets for real transactions


@dataclass
class BlockMetrics:
    """Metrics for a single block."""
    block_number: int
    producer_id: str
    production_time: float  # Time to produce this block
    transactions_included: int
    propagation_time: float  # Time to propagate to network
    is_attacker: bool


@dataclass 
class ThroughputResults:
    """Aggregated throughput results for a strategy."""
    strategy_name: str
    
    # Throughput metrics
    total_transactions: int = 0
    total_time: float = 0.0
    mean_tps: float = 0.0
    peak_tps: float = 0.0
    min_tps: float = 0.0
    
    # Block production metrics
    mean_block_time: float = 0.0
    p50_block_time: float = 0.0
    p95_block_time: float = 0.0
    p99_block_time: float = 0.0
    
    # Finality metrics
    mean_finality_time: float = 0.0
    p50_finality_time: float = 0.0
    p95_finality_time: float = 0.0
    p99_finality_time: float = 0.0
    
    # Additional metrics
    blocks_produced: int = 0
    missed_blocks: int = 0
    attacker_blocks: int = 0


def _percentile(values: List[float], q: float) -> float:
    """Compute percentile q in [0, 100]."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * q / 100.0
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_vals) else f
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


class ThroughputEvaluator:
    """Evaluates throughput metrics for different consensus strategies."""
    
    def __init__(self, cfg: ThroughputConfig):
        self.cfg = cfg
        self.consensus: Optional[QuantumAnnealingConsensus] = None
        self.node_ids: List[str] = []
        self.ground_truth: Dict[str, float] = {}
        self.stake: Dict[str, float] = {}
        self.hash_power: Dict[str, float] = {}
        self.online_prob: Dict[str, float] = {}
        self.is_attacker: Dict[str, bool] = {}
        
        # Real transaction support
        self.wallets: List[Wallet] = []
        self.blockchain: Optional[Blockchain] = None
        self.pending_transactions: List[Transaction] = []
        
    def setup_environment(self) -> None:
        """Initialize consensus and node attributes."""
        random.seed(self.cfg.seed)
        
        self.consensus = QuantumAnnealingConsensus(
            initialize_genesis=False, 
            verbose=False
        )
        
        # Allow 0 attackers when attacker_fraction is 0
        num_attackers = int(self.cfg.num_nodes * self.cfg.attacker_fraction)
        attacker_ids = set(f"node_{i}" for i in range(num_attackers))
        
        for i in range(self.cfg.num_nodes):
            node_id = f"node_{i}"
            self.node_ids.append(node_id)
            
            attacker = node_id in attacker_ids
            base_capability = random.uniform(0.3, 1.0)
            
            if attacker:
                capability = max(0.1, base_capability - random.uniform(0.2, 0.5))
            else:
                capability = min(1.0, base_capability + random.uniform(0.0, 0.2))
            
            self.ground_truth[node_id] = capability
            self.is_attacker[node_id] = attacker
            self.stake[node_id] = max(0.1, capability * random.uniform(5.0, 15.0))
            self.hash_power[node_id] = max(0.1, capability * random.uniform(8.0, 20.0))
            self.online_prob[node_id] = min(0.98, 0.6 + 0.4 * capability)
            
            public_key, _ = self.consensus.ensure_node_keys(node_id)
            self.consensus.register_node(node_id, public_key)
            # Expose stake so both VRF-stake baseline and QUBO can use it
            if node_id in self.consensus.nodes:
                self.consensus.nodes[node_id]['stake_weight'] = self.stake[node_id]
        
        # Initialize wallets and blockchain for real transaction mode
        if self.cfg.use_real_transactions:
            self._setup_real_transaction_environment()
    
    def _setup_real_transaction_environment(self) -> None:
        """Initialize wallets and blockchain for real transactions."""
        self.wallets = [Wallet() for _ in range(self.cfg.num_wallets)]
        self.blockchain = Blockchain(self.wallets[0].public_key_string())
        self.pending_transactions = []
    
    def _create_real_transaction(self, tx_index: int) -> Transaction:
        """Create and sign a real transaction."""
        sender = self.wallets[tx_index % len(self.wallets)]
        receiver = self.wallets[(tx_index + 1) % len(self.wallets)]
        amount = 10.0 + (tx_index % 100)
        
        transaction = Transaction(
            sender.public_key_string(),
            receiver.public_key_string(),
            amount,
            "TRANSFER"
        )
        
        # Sign the transaction
        transaction_data = transaction.payload()
        signature = sender.sign(transaction_data)
        transaction.signature = signature
        
        return transaction
    
    def _create_transaction_batch(self, count: int, start_index: int = 0) -> List[Transaction]:
        """Create a batch of real transactions."""
        return [self._create_real_transaction(start_index + i) for i in range(count)]
    
    def _real_block_production(self, producer_id: str, block_idx: int) -> Tuple[float, int, bool]:
        """Produce a real block with actual transactions.
        
        Returns: (production_time, transactions_included, success)
        """
        if not self.blockchain:
            return 0.0, 0, False
        
        capability = self.ground_truth.get(producer_id, 0.5)
        
        # Create transactions for this block (scaled by capability)
        target_txs = max(10, int(self.cfg.transactions_per_block * capability))
        
        start_time = time.time()
        
        # Create and submit real transactions
        transactions = self._create_transaction_batch(target_txs, block_idx * target_txs)
        
        for tx in transactions:
            self.blockchain.submit_transaction(tx)
        
        # Create the block
        block_start = time.time()
        try:
            block = self.blockchain.create_block(self.wallets[0], use_gulf_stream=True)
            production_time = time.time() - start_time
            txs_included = len(block.transactions) if block else 0
            success = block is not None and txs_included > 0
        except Exception as e:
            production_time = time.time() - start_time
            txs_included = 0
            success = False
        
        return production_time, txs_included, success
    
    def _update_node_metrics(self) -> Dict[str, bool]:
        """Update node online status and metrics for current round."""
        online_state: Dict[str, bool] = {}
        now = time.time()
        
        for node_id in self.node_ids:
            node_data = self.consensus.nodes.get(node_id)
            if not node_data:
                continue
            
            is_online = random.random() < self.online_prob[node_id]
            online_state[node_id] = is_online
            
            if is_online:
                node_data["last_seen"] = now
                cap = self.ground_truth[node_id]
                
                # Latency based on capability
                base_latency = 0.15 - 0.10 * cap
                node_data["latency"] = max(0.01, base_latency + random.uniform(-0.02, 0.02))
                
                # Throughput based on capability
                base_tps = 5.0 + 45.0 * cap
                node_data["throughput"] = max(1.0, base_tps * random.uniform(0.8, 1.2))
            else:
                node_data["last_seen"] = now - (self.consensus.node_active_threshold + 10)
        
        self.consensus.node_performance_cache.clear()
        return online_state
    
    def _get_active_nodes(self, online_state: Dict[str, bool]) -> List[str]:
        """Get list of currently active nodes."""
        return [n for n in self.node_ids if online_state.get(n, False)]
    
    def _simulate_block_production(self, producer_id: str) -> Tuple[float, int, bool]:
        """Simulate block production by a node.
        
        Returns: (production_time, transactions_included, success)
        """
        capability = self.ground_truth[producer_id]
        
        # Block production time inversely related to capability
        base_time = self.cfg.base_block_time * (2.0 - capability)
        jitter = random.uniform(-0.05, 0.1)
        production_time = max(0.05, base_time + jitter)
        
        # Transactions included depends on capability (throughput)
        max_txs = int(self.cfg.transactions_per_block * capability)
        transactions = max(10, int(max_txs * random.uniform(0.8, 1.0)))
        
        # Success probability based on capability
        success = random.random() < (0.7 + 0.3 * capability)
        
        return production_time, transactions, success
    
    def _calculate_finality_time(
        self, 
        block_times: List[float],
        block_idx: int
    ) -> float:
        """Calculate finality time for a transaction in a given block.
        
        Finality = time until N confirmations (subsequent blocks).
        """
        confirmations_needed = self.cfg.finality_confirmations
        
        if block_idx + confirmations_needed > len(block_times):
            # Not enough blocks yet, estimate based on average
            avg_block_time = statistics.mean(block_times) if block_times else self.cfg.base_block_time
            remaining = confirmations_needed - (len(block_times) - block_idx)
            return sum(block_times[block_idx:]) + remaining * avg_block_time
        
        return sum(block_times[block_idx:block_idx + confirmations_needed])
    
    # =========================================================================
    # Selection Strategies
    # =========================================================================
    
    def _select_quantum(self, active_nodes: List[str], block_hash: str) -> Optional[str]:
        """Quantum annealing committee selection (VOSCS / QUBO-based).

        Uses select_committee to pick k members via the QUBO objective, then
        returns the derived primary leader as the block producer.  Falls back
        to a random active node if the committee call fails.
        """
        try:
            result = self.consensus.select_committee(
                vrf_output=block_hash,
                candidate_nodes=active_nodes,
                committee_k=min(5, len(active_nodes)),
                primary_leader_policy='highest_score',
            )
            if result and result.primary_leader and result.primary_leader in active_nodes:
                return result.primary_leader
        except Exception:
            pass
        return random.choice(active_nodes) if active_nodes else None
    
    def _select_greedy(self, active_nodes: List[str]) -> Optional[str]:
        """Greedy: pick node with highest single metric (uptime)."""
        if not active_nodes:
            return None
        
        now = time.time()
        best_node = None
        best_score = -float("inf")
        
        for node_id in active_nodes:
            node_data = self.consensus.nodes.get(node_id)
            if not node_data:
                continue
            last_seen = node_data.get("last_seen", 0)
            score = 1.0 / (1.0 + max(0, now - last_seen))
            if score > best_score:
                best_score = score
                best_node = node_id
        
        return best_node or random.choice(active_nodes)
    
    def _select_weighted(self, active_nodes: List[str]) -> Optional[str]:
        """Weighted random selection by suitability score."""
        if not active_nodes:
            return None
        
        scores = [max(0.01, self.consensus.calculate_suitability_score(n)) 
                  for n in active_nodes]
        total = sum(scores)
        weights = [s / total for s in scores]
        
        return random.choices(active_nodes, weights=weights, k=1)[0]
    
    def _select_round_robin(self, active_nodes: List[str], round_idx: int) -> Optional[str]:
        """Round-robin rotating selection (Tendermint-style)."""
        if not active_nodes:
            return None
        return active_nodes[round_idx % len(active_nodes)]
    
    def _select_pos_stake(self, active_nodes: List[str]) -> Optional[str]:
        """PoS stake-weighted lottery (Ouroboros-style)."""
        if not active_nodes:
            return None
        
        weights = [max(0.01, self.stake.get(n, 0.1)) for n in active_nodes]
        total = sum(weights)
        probs = [w / total for w in weights]
        
        return random.choices(active_nodes, weights=probs, k=1)[0]
    
    def _select_pow_hash(self, active_nodes: List[str]) -> Optional[str]:
        """PoW hash-power weighted lottery."""
        if not active_nodes:
            return None
        
        weights = [max(0.01, self.hash_power.get(n, 0.1)) for n in active_nodes]
        total = sum(weights)
        probs = [w / total for w in weights]
        
        return random.choices(active_nodes, weights=probs, k=1)[0]

    # =========================================================================
    # Table 2 committee-selection baselines
    # =========================================================================

    def _committee_primary(self, committee: List[str], scores: Dict[str, float]) -> Optional[str]:
        """Return the highest-scoring member as primary leader."""
        if not committee:
            return None
        return max(committee, key=lambda n: (scores.get(n, 0.0), n))

    def _select_vrf_stake(self, active_nodes: List[str], block_hash: str) -> Optional[str]:
        """Stake-weighted VRF sortition (Algorand/Ouroboros-style, Table 2 baseline)."""
        if not active_nodes:
            return None
        scores: Dict[str, float] = {}
        for node_id in active_nodes:
            vrf_bytes = hmac.new(block_hash.encode(), node_id.encode(), hashlib.sha256).digest()
            vrf_score = int.from_bytes(vrf_bytes[:4], "big") / 0xFFFF_FFFF
            # Use the evaluator's own stake dict (consensus nodes don't carry stake_weight)
            stake_w = self.stake.get(node_id, 1.0)
            scores[node_id] = max(0.001, stake_w * vrf_score)
        # weighted sample without replacement
        rng = random.Random(block_hash)
        k = min(5, len(active_nodes))
        remaining = list(active_nodes)
        committee: List[str] = []
        while remaining and len(committee) < k:
            weights = [max(0.001, scores.get(n, 0.0)) for n in remaining]
            total = sum(weights)
            draw = rng.random() * total
            cumul = 0.0
            chosen = remaining[-1]
            for idx, w in enumerate(weights):
                cumul += w
                if draw <= cumul:
                    chosen = remaining[idx]
                    break
            committee.append(chosen)
            remaining.remove(chosen)
        return self._committee_primary(committee, scores)

    def _select_reputation_only(self, active_nodes: List[str]) -> Optional[str]:
        """Reputation-only top-k (Table 2 baseline)."""
        if not active_nodes:
            return None
        now = time.time()
        scores: Dict[str, float] = {}
        for node_id in active_nodes:
            nd = self.consensus.nodes.get(node_id, {})
            uptime = self.consensus.calculate_uptime(node_id)
            past = nd.get("proposal_success_count", 0) - 2 * nd.get("proposal_failure_count", 0)
            scores[node_id] = 0.65 * max(0.0, float(past)) + 0.35 * uptime
        committee = sorted(active_nodes, key=lambda n: scores.get(n, 0.0), reverse=True)[:min(5, len(active_nodes))]
        return self._committee_primary(committee, scores)

    def _select_greedy_score_committee(self, active_nodes: List[str], block_hash: str) -> Optional[str]:
        """Score-only greedy top-k without pairwise/fairness (Table 2 baseline)."""
        if not active_nodes:
            return None
        try:
            _, _, _, effective_scores, _ = self.consensus.formulate_committee_qubo_problem(
                block_hash, active_nodes, committee_k=min(5, len(active_nodes))
            )
        except Exception:
            effective_scores = {n: self.consensus.calculate_suitability_score(n) for n in active_nodes}
        committee = sorted(active_nodes, key=lambda n: effective_scores.get(n, 0.0), reverse=True)[:min(5, len(active_nodes))]
        return self._committee_primary(committee, effective_scores)

    def _select_uniform_lottery(self, active_nodes: List[str], block_hash: str) -> Optional[str]:
        """Uniform exact-k lottery (Table 2 baseline)."""
        if not active_nodes:
            return None
        rng = random.Random(block_hash)
        committee = rng.sample(sorted(active_nodes), min(5, len(active_nodes)))
        # VRF tiebreak for leader
        return min(committee, key=lambda n: hashlib.sha256(f"{block_hash}:{n}".encode()).hexdigest())

    def _select_fairness_only(self, active_nodes: List[str]) -> Optional[str]:
        """Fairness-only (anti-concentration) top-k (Table 2 baseline)."""
        if not active_nodes:
            return None
        scores = {n: max(0.0, 1.0 - self.consensus.calculate_selection_frequency(n)) for n in active_nodes}
        committee = sorted(active_nodes, key=lambda n: scores.get(n, 0.0), reverse=True)[:min(5, len(active_nodes))]
        return self._committee_primary(committee, scores)
    
    def run_strategy(self, strategy_name: str) -> ThroughputResults:
        """Run evaluation for a single strategy."""
        results = ThroughputResults(strategy_name=strategy_name)
        
        block_times: List[float] = []
        tps_per_block: List[float] = []
        finality_times: List[float] = []
        
        total_txs = 0
        total_time = 0.0
        
        for block_idx in range(self.cfg.num_blocks):
            # Update network state
            online_state = self._update_node_metrics()
            active_nodes = self._get_active_nodes(online_state)
            
            if not active_nodes:
                results.missed_blocks += 1
                block_times.append(self.cfg.base_block_time * 2)  # Timeout
                continue
            
            # Select block producer based on strategy
            block_hash = f"block_{block_idx}"
            
            if strategy_name == "quantum":
                producer = self._select_quantum(active_nodes, block_hash)
            elif strategy_name == "greedy_score":
                producer = self._select_greedy(active_nodes)
            elif strategy_name == "weighted_score":
                producer = self._select_weighted(active_nodes)
            elif strategy_name == "round_robin":
                producer = self._select_round_robin(active_nodes, block_idx)
            elif strategy_name == "pos_stake":
                producer = self._select_pos_stake(active_nodes)
            elif strategy_name == "pow_hash":
                producer = self._select_pow_hash(active_nodes)
            elif strategy_name == "vrf_stake":
                producer = self._select_vrf_stake(active_nodes, block_hash)
            elif strategy_name == "reputation_only":
                producer = self._select_reputation_only(active_nodes)
            elif strategy_name == "uniform_lottery":
                producer = self._select_uniform_lottery(active_nodes, block_hash)
            elif strategy_name == "fairness_only":
                producer = self._select_fairness_only(active_nodes)
            else:
                producer = random.choice(active_nodes)
            
            if not producer:
                results.missed_blocks += 1
                block_times.append(self.cfg.base_block_time * 2)
                continue
            
            # Produce block (real or simulated)
            if self.cfg.use_real_transactions:
                prod_time, txs, success = self._real_block_production(producer, block_idx)
            else:
                prod_time, txs, success = self._simulate_block_production(producer)
            
            if not success:
                results.missed_blocks += 1
                block_times.append(prod_time + self.cfg.base_block_time)  # Retry cost
                # Update failure count so reputation/suitability scores evolve correctly
                node_data = self.consensus.nodes.get(producer)
                if node_data is not None:
                    node_data['proposal_failure_count'] += 1
                self.consensus.node_performance_cache.clear()
                continue
            
            # Successful block
            results.blocks_produced += 1
            
            # Record selection so selection_frequency and fairness signals evolve correctly
            self.consensus.record_leader_selection(block_idx, producer)
            node_data = self.consensus.nodes.get(producer)
            if node_data is not None:
                node_data['proposal_success_count'] += 1
            self.consensus.node_performance_cache.clear()
            
            if self.is_attacker.get(producer, False):
                results.attacker_blocks += 1
            
            # Add network propagation time
            prop_time = self.cfg.network_latency * random.uniform(0.8, 1.5)
            total_block_time = prod_time + prop_time
            
            block_times.append(total_block_time)
            total_txs += txs
            total_time += total_block_time
            
            # Calculate TPS for this block
            block_tps = txs / total_block_time if total_block_time > 0 else 0
            tps_per_block.append(block_tps)
        
        # Calculate finality times for each block
        for i in range(len(block_times)):
            finality = self._calculate_finality_time(block_times, i)
            finality_times.append(finality)
        
        # Aggregate results
        results.total_transactions = total_txs
        results.total_time = total_time
        
        if total_time > 0:
            results.mean_tps = total_txs / total_time
        
        if tps_per_block:
            results.peak_tps = max(tps_per_block)
            results.min_tps = min(tps_per_block)
        
        if block_times:
            results.mean_block_time = statistics.mean(block_times)
            results.p50_block_time = _percentile(block_times, 50)
            results.p95_block_time = _percentile(block_times, 95)
            results.p99_block_time = _percentile(block_times, 99)
        
        if finality_times:
            results.mean_finality_time = statistics.mean(finality_times)
            results.p50_finality_time = _percentile(finality_times, 50)
            results.p95_finality_time = _percentile(finality_times, 95)
            results.p99_finality_time = _percentile(finality_times, 99)
        
        return results

    def run_all_strategies(self, parallel: bool = True) -> Dict[str, ThroughputResults]:
        """Run evaluation for all strategies.
        
        Args:
            parallel: If True, run strategies in parallel using multiple processes.
        """
        strategies = [
            "quantum",
            "vrf_stake",
            "reputation_only",
            "uniform_lottery",
            "fairness_only",
        ]
        
        if parallel:
            return self._run_parallel(strategies)
        else:
            return self._run_sequential(strategies)
    
    def _run_sequential(self, strategies: List[str]) -> Dict[str, ThroughputResults]:
        """Run strategies sequentially."""
        results = {}
        for strategy in strategies:
            # Reset random seed for fair comparison
            random.seed(self.cfg.seed)
            self.setup_environment()
            
            print(f"  Running {strategy}...")
            results[strategy] = self.run_strategy(strategy)
        
        return results
    
    def _run_parallel(self, strategies: List[str]) -> Dict[str, ThroughputResults]:
        """Run strategies in parallel using multiple processes."""
        # Determine number of workers (use CPU count, but cap at strategy count)
        num_workers = min(len(strategies), multiprocessing.cpu_count())
        print(f"  Running {len(strategies)} strategies in parallel ({num_workers} workers)...")
        
        results = {}
        
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            # Submit all strategy evaluations
            future_to_strategy = {
                executor.submit(_run_single_strategy, self.cfg, strategy): strategy
                for strategy in strategies
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_strategy):
                strategy = future_to_strategy[future]
                try:
                    result = future.result()
                    results[strategy] = result
                    print(f"    ✓ {strategy} completed")
                except Exception as e:
                    print(f"    ✗ {strategy} failed: {e}")
        
        # Reorder results to match original strategy order
        ordered_results = {s: results[s] for s in strategies if s in results}
        return ordered_results


def _run_single_strategy(cfg: ThroughputConfig, strategy_name: str) -> ThroughputResults:
    """Standalone function to run a single strategy (for parallel execution).
    
    This function must be at module level for pickling by ProcessPoolExecutor.
    """
    # Each process gets its own evaluator with fresh random state
    random.seed(cfg.seed)
    
    evaluator = ThroughputEvaluator(cfg)
    evaluator.setup_environment()
    
    return evaluator.run_strategy(strategy_name)


def save_results_json(
    results: Dict[str, ThroughputResults], 
    cfg: ThroughputConfig,
    output_path: str
) -> None:
    """Save results to JSON file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    serializable = {
        "config": {
            "num_nodes": cfg.num_nodes,
            "num_blocks": cfg.num_blocks,
            "transactions_per_block": cfg.transactions_per_block,
            "attacker_fraction": cfg.attacker_fraction,
            "seed": cfg.seed,
            "base_block_time": cfg.base_block_time,
            "finality_confirmations": cfg.finality_confirmations,
            "use_real_transactions": cfg.use_real_transactions,
            "num_wallets": cfg.num_wallets if cfg.use_real_transactions else None,
        },
        "results": {}
    }
    
    for name, r in results.items():
        serializable["results"][name] = {
            "throughput": {
                "total_transactions": r.total_transactions,
                "total_time_seconds": round(r.total_time, 3),
                "mean_tps": round(r.mean_tps, 2),
                "peak_tps": round(r.peak_tps, 2),
                "min_tps": round(r.min_tps, 2),
            },
            "block_production": {
                "blocks_produced": r.blocks_produced,
                "missed_blocks": r.missed_blocks,
                "mean_block_time_ms": round(r.mean_block_time * 1000, 2),
                "p50_block_time_ms": round(r.p50_block_time * 1000, 2),
                "p95_block_time_ms": round(r.p95_block_time * 1000, 2),
                "p99_block_time_ms": round(r.p99_block_time * 1000, 2),
            },
            "finality": {
                "mean_finality_time_ms": round(r.mean_finality_time * 1000, 2),
                "p50_finality_time_ms": round(r.p50_finality_time * 1000, 2),
                "p95_finality_time_ms": round(r.p95_finality_time * 1000, 2),
                "p99_finality_time_ms": round(r.p99_finality_time * 1000, 2),
            },
            "security": {
                "attacker_blocks": r.attacker_blocks,
                "attacker_block_share": round(r.attacker_blocks / max(1, r.blocks_produced), 3),
            }
        }
    
    with open(output_path, "w") as f:
        json.dump(serializable, f, indent=2)


def plot_results(
    results: Dict[str, ThroughputResults],
    output_prefix: str
) -> None:
    """Generate comparison plots."""
    os.makedirs(os.path.dirname(output_prefix), exist_ok=True)
    
    LABELS = {
        "quantum": "VOSCS (Ours)",
        "vrf_stake": "Stake-weighted VRF",
        "reputation_only": "Reputation-only",
        "uniform_lottery": "Uniform lottery",
        "fairness_only": "Fairness-only",
        # legacy single-node strategies kept for backward compat
        "greedy_score": "greedy_score",
        "weighted_score": "weighted_score",
        "round_robin": "round_robin",
        "pos_stake": "pos_stake",
        "pow_hash": "pow_hash",
    }
    strategies = list(results.keys())
    labels = [LABELS.get(s, s) for s in strategies]
    x = list(range(len(strategies)))
    width = 0.6
    
    # Plot 1: Transaction Throughput (TPS)
    fig, ax = plt.subplots(figsize=(10, 5))
    
    mean_tps = [results[s].mean_tps for s in strategies]
    bars = ax.bar(x, mean_tps, width, color='steelblue', label='Mean TPS')
    
    # Add value annotations
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:.0f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=9)
    
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel('Transactions per Second (TPS)')
    ax.set_title('Transaction Throughput by Consensus Strategy')
    ax.legend()
    plt.tight_layout()
    plt.savefig(f"{output_prefix}_throughput.png", dpi=150)
    plt.close(fig)
    
    # Plot 2: Block Production Time
    fig, ax = plt.subplots(figsize=(10, 5))
    
    mean_bt = [results[s].mean_block_time * 1000 for s in strategies]
    p95_bt = [results[s].p95_block_time * 1000 for s in strategies]
    
    bar_width = 0.35
    bars1 = ax.bar([i - bar_width/2 for i in x], mean_bt, bar_width, 
                   label='Mean', color='forestgreen')
    bars2 = ax.bar([i + bar_width/2 for i in x], p95_bt, bar_width,
                   label='P95', color='darkorange')
    
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.0f}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=8)
    
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel('Block Production Time (ms)')
    ax.set_title('Block Production Time by Consensus Strategy')
    ax.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(f"{output_prefix}_block_time.png", dpi=150)
    plt.close(fig)
    
    # Plot 3: Transaction Finality Time
    fig, ax = plt.subplots(figsize=(10, 5))
    
    mean_ft = [results[s].mean_finality_time * 1000 for s in strategies]
    p95_ft = [results[s].p95_finality_time * 1000 for s in strategies]
    
    bars1 = ax.bar([i - bar_width/2 for i in x], mean_ft, bar_width,
                   label='Mean', color='royalblue')
    bars2 = ax.bar([i + bar_width/2 for i in x], p95_ft, bar_width,
                   label='P95', color='crimson')
    
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.0f}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=8)
    
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel('Finality Time (ms)')
    ax.set_title('Transaction Finality Time by Consensus Strategy')
    ax.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(f"{output_prefix}_finality.png", dpi=150)
    plt.close(fig)
    
    # Plot 4: Combined comparison (normalized)
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Normalize metrics to [0, 1] for comparison (higher is better)
    max_tps = max(r.mean_tps for r in results.values()) or 1
    max_bt = max(r.mean_block_time for r in results.values()) or 1
    max_ft = max(r.mean_finality_time for r in results.values()) or 1
    
    norm_tps = [results[s].mean_tps / max_tps for s in strategies]
    norm_bt = [1 - results[s].mean_block_time / max_bt for s in strategies]  # Invert: lower is better
    norm_ft = [1 - results[s].mean_finality_time / max_ft for s in strategies]  # Invert: lower is better
    
    bar_width = 0.25
    bars1 = ax.bar([i - bar_width for i in x], norm_tps, bar_width, label='Throughput', color='steelblue')
    bars2 = ax.bar(x, norm_bt, bar_width, label='Block Speed', color='forestgreen')
    bars3 = ax.bar([i + bar_width for i in x], norm_ft, bar_width, label='Finality Speed', color='darkorange')
    
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel('Normalized Score (higher is better)')
    ax.set_ylim(0, 1.15)
    ax.set_title('Normalized Performance Comparison')
    ax.legend()
    plt.tight_layout()
    plt.savefig(f"{output_prefix}_comparison.png", dpi=150)
    plt.close(fig)


def _save_fig(fig: plt.Figure, base_path: str) -> None:
    """Save a figure as both PNG and SVG."""
    os.makedirs(os.path.dirname(base_path), exist_ok=True)
    for ext in (".png", ".svg"):
        fig.savefig(base_path + ext, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_paper_figures(
    results: Dict[str, ThroughputResults],
    output_dir: str,
) -> None:
    """Generate two separate publication-style figures.

    Figure 2a: Transaction throughput (TPS) — single blue bar chart.
    Figure 2b: Block production and finality times — 4-metric grouped bars.
    Saves each as both PNG and SVG.
    """
    os.makedirs(output_dir, exist_ok=True)

    LABELS = {
        "quantum": "VOSCS\n(Ours)",
        "vrf_stake": "Stake-\nweighted VRF",
        "reputation_only": "Reputation-\nonly",
        "greedy_score_committee": "Score-only\nGreedy",
        "uniform_lottery": "Uniform\nLottery",
        "fairness_only": "Fairness-\nonly",
        # legacy
        "greedy_score": "Greedy\nScore",
        "weighted_score": "Weighted\nScore",
        "round_robin": "Round\nRobin",
        "pos_stake": "PoS",
        "pow_hash": "PoW",
    }

    strategies = list(results.keys())
    labels = [LABELS.get(s, s) for s in strategies]
    x = list(range(len(strategies)))

    COLOR_TPS = "#4472C4"
    COLOR_MEAN_BT = "#4472C4"
    COLOR_P95_BT = "#ED7D31"
    COLOR_MEAN_FT = "#A5A5A5"
    COLOR_P95_FT = "#FFC000"

    FS_TICK  = 13   # x/y tick labels
    FS_LABEL = 14   # axis labels
    FS_ANNOT = 12   # bar value annotations
    FS_LEGEND = 13  # legend

    # ── Figure 2a: Transaction Throughput ────────────────────────────────────
    fig_a, ax_a = plt.subplots(figsize=(7, 5))

    tps_values = [results[s].mean_tps for s in strategies]
    bars = ax_a.bar(x, tps_values, color=COLOR_TPS, edgecolor="white", linewidth=0.5)
    for bar in bars:
        h = bar.get_height()
        ax_a.annotate(
            f"{h:.0f}",
            xy=(bar.get_x() + bar.get_width() / 2, h),
            xytext=(0, 3), textcoords="offset points",
            ha="center", va="bottom", fontsize=FS_ANNOT,
        )
    ax_a.set_xticks(x)
    ax_a.set_xticklabels(labels, ha="center", fontsize=FS_TICK)
    ax_a.set_ylabel("Transactions per second (TPS)", fontsize=FS_LABEL)
    ax_a.tick_params(axis="y", labelsize=FS_TICK)
    ax_a.set_ylim(0, max(tps_values) * 1.18)
    ax_a.spines["top"].set_visible(False)
    ax_a.spines["right"].set_visible(False)

    _save_fig(fig_a, os.path.join(output_dir, "throughput"))

    # ── Figure 2b: Block + Finality Times ────────────────────────────────────
    fig_b, ax_b = plt.subplots(figsize=(7, 5))

    bw = 0.18
    offsets = [-1.5 * bw, -0.5 * bw, 0.5 * bw, 1.5 * bw]

    mean_bt = [results[s].mean_block_time * 1000 for s in strategies]
    p95_bt  = [results[s].p95_block_time  * 1000 for s in strategies]
    mean_ft = [results[s].mean_finality_time * 1000 for s in strategies]
    p95_ft  = [results[s].p95_finality_time  * 1000 for s in strategies]

    ax_b.bar([xi + offsets[0] for xi in x], mean_bt, bw, label="Mean Block Time (ms)",    color=COLOR_MEAN_BT, edgecolor="white", linewidth=0.4)
    ax_b.bar([xi + offsets[1] for xi in x], p95_bt,  bw, label="P95 Block Time (ms)",     color=COLOR_P95_BT,  edgecolor="white", linewidth=0.4)
    ax_b.bar([xi + offsets[2] for xi in x], mean_ft, bw, label="Mean Finality Time (ms)", color=COLOR_MEAN_FT, edgecolor="white", linewidth=0.4)
    ax_b.bar([xi + offsets[3] for xi in x], p95_ft,  bw, label="P95 Finality Time (ms)",  color=COLOR_P95_FT,  edgecolor="white", linewidth=0.4)

    ax_b.set_xticks(x)
    ax_b.set_xticklabels(labels, ha="center", fontsize=FS_TICK)
    ax_b.set_ylabel("Time (ms)", fontsize=FS_LABEL)
    ax_b.tick_params(axis="y", labelsize=FS_TICK)
    ax_b.spines["top"].set_visible(False)
    ax_b.spines["right"].set_visible(False)
    ax_b.legend(loc="upper left", ncol=1, fontsize=FS_LEGEND, frameon=False)

    _save_fig(fig_b, os.path.join(output_dir, "block_finality"))


def main() -> None:
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Evaluate throughput, block time, and finality across consensus strategies"
    )
    parser.add_argument("--nodes", type=int, default=50, help="Number of nodes")
    parser.add_argument("--blocks", type=int, default=100, help="Number of blocks to produce")
    parser.add_argument("--txs-per-block", type=int, default=500, help="Target transactions per block")
    parser.add_argument("--attackers", type=float, default=0.2, help="Attacker fraction [0,1]")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output-dir", type=str, default="reports", help="Output directory")
    parser.add_argument("--real", action="store_true", 
                        help="Use real transactions (create, sign, submit to blockchain)")
    parser.add_argument("--wallets", type=int, default=20, 
                        help="Number of test wallets for real transaction mode")
    parser.add_argument("--sequential", action="store_true",
                        help="Run strategies sequentially instead of parallel")
    
    args = parser.parse_args()
    
    cfg = ThroughputConfig(
        num_nodes=args.nodes,
        num_blocks=args.blocks,
        transactions_per_block=args.txs_per_block,
        attacker_fraction=args.attackers,
        seed=args.seed,
        output_dir=args.output_dir,
        use_real_transactions=args.real,
        num_wallets=args.wallets,
    )
    run_name = "throughput_evaluation_real" if cfg.use_real_transactions else "throughput_evaluation"
    run_layout = create_run_layout(cfg.output_dir, run_name)
    cfg.output_dir = run_layout.root_dir
    write_run_metadata(
        run_layout,
        {
            "tool": "throughput_evaluation",
            "layout": run_layout.to_dict(),
            "config": cfg.__dict__,
            "parallel_requested": not args.sequential,
        },
    )
    
    mode = "REAL transactions" if cfg.use_real_transactions else "SIMULATED"
    print("🚀 Running throughput evaluation...")
    print(f"   Mode: {mode}")
    print(f"   Nodes: {cfg.num_nodes}, Blocks: {cfg.num_blocks}, TXs/block: {cfg.transactions_per_block}")
    print(f"   Output: {run_layout.root_dir}")
    if cfg.use_real_transactions:
        print(f"   Wallets: {cfg.num_wallets}")
    
    evaluator = ThroughputEvaluator(cfg)
    
    # Real transaction mode must run sequentially (shared blockchain state)
    parallel = not args.sequential and not cfg.use_real_transactions
    if cfg.use_real_transactions and not args.sequential:
        print("   Note: Real transaction mode runs sequentially (shared blockchain state)")
    
    results = evaluator.run_all_strategies(parallel=parallel)
    
    prefix = os.path.join(run_layout.figures_dir, "throughput")
    
    # Print summary
    print("\n📊 Results Summary:")
    print("-" * 90)
    print(f"{'Strategy':<15} {'Mean TPS':>10} {'Block Time (ms)':>18} {'Finality (ms)':>15} {'Attacker %':>12}")
    print("-" * 90)
    
    for name, r in results.items():
        attacker_pct = (r.attacker_blocks / max(1, r.blocks_produced)) * 100
        print(f"{name:<15} {r.mean_tps:>10.1f} {r.mean_block_time*1000:>18.1f} "
              f"{r.mean_finality_time*1000:>15.1f} {attacker_pct:>11.1f}%")
    
    print("-" * 90)
    
    # Save outputs
    metrics_path = os.path.join(run_layout.data_dir, "throughput_metrics.json")
    save_results_json(results, cfg, metrics_path)
    plot_results(results, prefix)

    paper_figs_dir = run_layout.figures_dir
    plot_paper_figures(results, paper_figs_dir)

    print(f"\n💾 Metrics saved to: {metrics_path}")
    print(f"📈 Plots saved with prefix: {prefix}_*.png")
    print(f"📄 Paper figures saved to: {paper_figs_dir}/throughput.{{png,svg}} and block_finality.{{png,svg}}")


if __name__ == "__main__":
    main()
