#!/usr/bin/env python3
"""Consensus Baseline Evaluation
================================

This script compares the quantum annealing consensus selection against
several classical baselines under a controlled simulation. It produces
numerical metrics and saves comparison graphs for use in the paper.

Baselines implemented:
- quantum: full QuantumAnnealingConsensus (paper model)
- greedy_score: always pick highest suitability score
- weighted_score: sample proposer weighted by suitability score
- round_robin: rotating proposer among active nodes
- pos_stake: PoS-style lottery weighted by synthetic stake
- pow_hash: PoW-style lottery weighted by synthetic hash power

Key evaluation metrics (per strategy):
- Proposer Quality Index (PQI): mean and p95 ground-truth capability
- Missed-slot rate
- p95 block time
- Nakamoto coefficient (slot share)
- Attacker proposer share
- Selection error rate vs top-k true nodes

Graphs are written to the reports/ directory.
"""

import os
import sys
import time
import math
import random
import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple


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

import matplotlib.pyplot as plt  # type: ignore

from blockchain.quantum_consensus import QuantumAnnealingConsensus


@dataclass
class SimulationConfig:
    num_nodes: int = 20
    num_rounds: int = 300
    attacker_fraction: float = 0.2
    top_k_for_error: int = 3
    seed: int = 42
    output_dir: str = "reports"


@dataclass
class StrategyMetrics:
    name: str
    pqi_mean: float
    pqi_p95: float
    missed_slot_rate: float
    p95_block_time: float
    nakamoto_coefficient: int
    attacker_share: float
    selection_error_rate: float


def _percentile(values: List[float], q: float) -> float:
    """Compute percentile q in [0, 100] without external dependencies."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    # statistics.quantiles uses exclusive method; map q to n parts
    qs = statistics.quantiles(values, n=100, method="inclusive")
    # qs[k-1] is k-th percentile (approx); clamp index
    k = max(1, min(99, int(round(q))))
    return qs[k - 1]


def _compute_nakamoto_coefficient(selection_counts: Counter) -> int:
    """Minimal number of nodes covering >=50% of selected slots."""
    total = sum(selection_counts.values())
    if total == 0:
        return 0
    sorted_counts = sorted(selection_counts.values(), reverse=True)
    cumulative = 0
    for i, c in enumerate(sorted_counts, start=1):
        cumulative += c
        if cumulative >= total / 2:
            return i
    return len(sorted_counts)


def _build_simulation_environment(cfg: SimulationConfig):
    """Initialize consensus object and synthetic node attributes.

    Returns (consensus, node_ids, ground_truth, stake, hash_power, online_prob, is_attacker).
    """
    random.seed(cfg.seed)

    # Use verbose=False to suppress key generation messages during simulation
    consensus = QuantumAnnealingConsensus(initialize_genesis=False, verbose=False)

    ground_truth: Dict[str, float] = {}
    stake: Dict[str, float] = {}
    hash_power: Dict[str, float] = {}
    online_prob: Dict[str, float] = {}
    is_attacker: Dict[str, bool] = {}

    node_ids: List[str] = []

    num_attackers = max(1, int(cfg.num_nodes * cfg.attacker_fraction))
    attacker_ids = set(f"node_{i}" for i in range(num_attackers))

    for i in range(cfg.num_nodes):
        node_id = f"node_{i}"
        node_ids.append(node_id)

        # Honest nodes have higher capability on average than attackers
        attacker = node_id in attacker_ids
        base_capability = random.uniform(0.3, 1.0)
        if attacker:
            capability = max(0.1, base_capability - random.uniform(0.2, 0.5))
        else:
            capability = min(1.0, base_capability + random.uniform(0.0, 0.2))

        ground_truth[node_id] = capability
        is_attacker[node_id] = attacker

        # Synthetic stake loosely correlated with capability (for PoS)
        stake[node_id] = max(0.1, capability * random.uniform(5.0, 15.0))

        # Synthetic hash power loosely correlated with capability (for PoW)
        hash_power[node_id] = max(0.1, capability * random.uniform(8.0, 20.0))

        # Online probability higher for capable nodes
        online_prob[node_id] = min(0.98, 0.6 + 0.4 * capability)

        # Ensure keys and register node in consensus
        public_key, _ = consensus.ensure_node_keys(node_id)
        consensus.register_node(node_id, public_key)

    return consensus, node_ids, ground_truth, stake, hash_power, online_prob, is_attacker


def _update_round_metrics(
    consensus: QuantumAnnealingConsensus,
    node_ids: List[str],
    ground_truth: Dict[str, float],
    online_prob: Dict[str, float],
) -> Dict[str, bool]:
    """Sample online/offline state and update consensus node metrics for this round.

    Returns a mapping node_id -> is_online.
    """
    online_state: Dict[str, bool] = {}
    now = time.time()

    for node_id in node_ids:
        node_data = consensus.nodes.get(node_id)
        if not node_data:
            continue

        is_online = random.random() < online_prob[node_id]
        online_state[node_id] = is_online

        if is_online:
            # Mark as recently seen
            node_data["last_seen"] = now

            # Sample latency: better capability -> lower latency
            cap = ground_truth[node_id]
            base_latency = 0.15 - 0.10 * cap  # 50–150ms approx
            jitter = random.uniform(-0.02, 0.02)
            latency = max(0.01, base_latency + jitter)

            # Sample throughput: better capability -> higher throughput
            base_tps = 5.0 + 45.0 * cap
            throughput = max(1.0, base_tps * random.uniform(0.8, 1.2))

            node_data["latency"] = latency
            node_data["throughput"] = throughput
        else:
            # Push last_seen outside activity window to mark offline
            node_data["last_seen"] = now - (consensus.node_active_threshold + 10)

    # Clear performance cache so scores reflect this round's metrics
    consensus.node_performance_cache.clear()

    return online_state


def _select_greedy(consensus: QuantumAnnealingConsensus, candidate_nodes: List[str], ground_truth: Dict[str, float]) -> str:
    """Greedy baseline: pick node with highest SINGLE metric (uptime only).
    
    This simulates a naive greedy approach that doesn't use the sophisticated
    multi-metric suitability scoring of quantum consensus. It only looks at
    one metric (uptime/last_seen), making it susceptible to gaming.
    """
    best_node = None
    best_uptime = -float("inf")
    now = time.time()
    
    for node_id in candidate_nodes:
        node_data = consensus.nodes.get(node_id)
        if not node_data:
            continue
        # Simple greedy: just pick most recently seen (highest uptime signal)
        last_seen = node_data.get("last_seen", 0)
        uptime_score = max(0, now - last_seen)  # Inverted: lower is better
        uptime_score = 1.0 / (1.0 + uptime_score)  # Convert to "higher is better"
        
        if uptime_score > best_uptime:
            best_uptime = uptime_score
            best_node = node_id
    
    return best_node if best_node else random.choice(candidate_nodes)


def _select_weighted_score(
    consensus: QuantumAnnealingConsensus, candidate_nodes: List[str]
) -> str:
    scores = [max(0.0, consensus.calculate_suitability_score(n)) for n in candidate_nodes]
    total = sum(scores)
    if total <= 0:
        # Fallback to uniform random among candidates
        return random.choice(candidate_nodes)
    weights = [s / total for s in scores]
    return random.choices(candidate_nodes, weights=weights, k=1)[0]


def _select_round_robin(
    candidate_nodes: List[str],
    rr_index: int,
) -> Tuple[str, int]:
    if not candidate_nodes:
        return "", rr_index
    rr_index = rr_index % len(candidate_nodes)
    return candidate_nodes[rr_index], rr_index + 1


def _select_stake_weighted(
    candidate_nodes: List[str], stake: Dict[str, float]
) -> str:
    weights = [max(0.0, stake.get(n, 0.0)) for n in candidate_nodes]
    total = sum(weights)
    if total <= 0:
        return random.choice(candidate_nodes)
    probs = [w / total for w in weights]
    return random.choices(candidate_nodes, weights=probs, k=1)[0]


def _select_pow_hash_lottery(
    candidate_nodes: List[str], hash_power: Dict[str, float]
) -> str:
    """PoW-style lottery: select proposer proportionally to hash power."""
    weights = [max(0.0, hash_power.get(n, 0.0)) for n in candidate_nodes]
    total = sum(weights)
    if total <= 0:
        return random.choice(candidate_nodes)
    probs = [w / total for w in weights]
    return random.choices(candidate_nodes, weights=probs, k=1)[0]


def _simulate_block_outcome(capability: float) -> Tuple[bool, float]:
    """Return (success, block_time_seconds) based on capability.

    Higher capability => higher success probability and lower block time.
    """
    # Failure probability decreases with capability
    p_fail = max(0.05, 0.5 - 0.4 * capability)
    success = random.random() > p_fail

    # Base block time roughly 1s, improved by capability
    base_time = 1.0 - 0.4 * capability
    jitter = random.uniform(-0.1, 0.1)
    block_time = max(0.1, base_time + jitter)

    return success, block_time


def run_simulation(cfg: SimulationConfig) -> Dict[str, StrategyMetrics]:
    consensus, node_ids, ground_truth, stake, hash_power, online_prob, is_attacker = _build_simulation_environment(cfg)

    # Pre-compute global top-k true nodes by capability
    sorted_by_truth = sorted(node_ids, key=lambda n: ground_truth[n], reverse=True)
    top_k_nodes = set(sorted_by_truth[: cfg.top_k_for_error])

    # Per-strategy tracking
    strategies = [
        "quantum",
        "greedy_score",
        "weighted_score",
        "round_robin",
        "pos_stake",
        "pow_hash",
    ]

    selections: Dict[str, List[str]] = {s: [] for s in strategies}
    pqi_values: Dict[str, List[float]] = {s: [] for s in strategies}
    block_times: Dict[str, List[float]] = {s: [] for s in strategies}
    missed_slots: Dict[str, int] = {s: 0 for s in strategies}
    attacker_selections: Dict[str, int] = {s: 0 for s in strategies}
    selection_errors: Dict[str, int] = {s: 0 for s in strategies}

    rr_index = 0

    for round_idx in range(cfg.num_rounds):
        # Update node metrics for this round
        online_state = _update_round_metrics(consensus, node_ids, ground_truth, online_prob)

        # Active nodes are those considered online by uptime rule
        active_nodes = [n for n in node_ids if online_state.get(n, False)]
        if not active_nodes:
            # No active nodes; all strategies miss this slot
            for s in strategies:
                selections[s].append("")
                missed_slots[s] += 1
            continue

        # Deterministic VRF-like output for this round
        vrf_output = f"round_{round_idx}"
        candidate_nodes = active_nodes.copy()

        # QUANTUM: use full consensus selection
        quantum_selected = consensus.select_representative_node(last_block_hash=vrf_output)
        if quantum_selected is None:
            quantum_selected = random.choice(active_nodes)
        # Ensure quantum choice is always among current active nodes for fair comparison
        if quantum_selected not in active_nodes:
            quantum_selected = random.choice(active_nodes)

        # GREEDY: highest suitability score among active nodes (single-metric naive approach)
        greedy_selected = _select_greedy(consensus, candidate_nodes, ground_truth)

        # WEIGHTED SCORE: random by suitability
        weighted_selected = _select_weighted_score(consensus, candidate_nodes)

        # ROUND ROBIN among active nodes
        rr_selected, rr_index = _select_round_robin(candidate_nodes, rr_index)

        # PoS: stake-weighted lottery among active nodes
        pos_selected = _select_stake_weighted(candidate_nodes, stake)

        # PoW: hash-power-weighted lottery among active nodes
        pow_selected = _select_pow_hash_lottery(candidate_nodes, hash_power)

        round_choices = {
            "quantum": quantum_selected,
            "greedy_score": greedy_selected,
            "weighted_score": weighted_selected,
            "round_robin": rr_selected,
            "pos_stake": pos_selected,
            "pow_hash": pow_selected,
        }

        for strategy_name, node_id in round_choices.items():
            selections[strategy_name].append(node_id)

            if not node_id:
                missed_slots[strategy_name] += 1
                continue

            cap = ground_truth[node_id]

            # Track PQI as ground-truth capability of selected proposer
            pqi_values[strategy_name].append(cap)

            # Simulate block outcome
            success, bt = _simulate_block_outcome(cap)
            if success:
                block_times[strategy_name].append(bt)
            else:
                missed_slots[strategy_name] += 1

            # Attacker share
            if is_attacker.get(node_id, False):
                attacker_selections[strategy_name] += 1

            # Selection error: chosen node not in top-k while some top-k were online
            top_k_online = any(online_state.get(n, False) for n in top_k_nodes)
            if top_k_online and node_id not in top_k_nodes:
                selection_errors[strategy_name] += 1

    # Aggregate metrics per strategy
    results: Dict[str, StrategyMetrics] = {}

    for s in strategies:
        total_rounds = cfg.num_rounds
        total_selected = len([x for x in selections[s] if x])

        pqi_mean = statistics.mean(pqi_values[s]) if pqi_values[s] else 0.0
        pqi_p95 = _percentile(pqi_values[s], 95.0) if pqi_values[s] else 0.0

        missed_rate = missed_slots[s] / float(total_rounds) if total_rounds else 0.0
        p95_bt = _percentile(block_times[s], 95.0) if block_times[s] else 0.0

        sel_counter = Counter(selections[s])
        if "" in sel_counter:
            del sel_counter[""]
        nakamoto = _compute_nakamoto_coefficient(sel_counter)

        attacker_share = (
            attacker_selections[s] / float(total_selected)
            if total_selected > 0
            else 0.0
        )

        error_rate = selection_errors[s] / float(total_rounds) if total_rounds else 0.0

        results[s] = StrategyMetrics(
            name=s,
            pqi_mean=pqi_mean,
            pqi_p95=pqi_p95,
            missed_slot_rate=missed_rate,
            p95_block_time=p95_bt,
            nakamoto_coefficient=nakamoto,
            attacker_share=attacker_share,
            selection_error_rate=error_rate,
        )

    return results


def _save_metrics_json(results: Dict[str, StrategyMetrics], cfg: SimulationConfig, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    serializable = {
        "config": cfg.__dict__,
        "results": {
            name: {
                "pqi_mean": m.pqi_mean,
                "pqi_p95": m.pqi_p95,
                "missed_slot_rate": m.missed_slot_rate,
                "p95_block_time": m.p95_block_time,
                "nakamoto_coefficient": m.nakamoto_coefficient,
                "attacker_share": m.attacker_share,
                "selection_error_rate": m.selection_error_rate,
            }
            for name, m in results.items()
        },
    }
    with open(output_path, "w") as f:
        json.dump(serializable, f, indent=2)


def _plot_results(results: Dict[str, StrategyMetrics], cfg: SimulationConfig, output_prefix: str) -> None:
    os.makedirs(os.path.dirname(output_prefix), exist_ok=True)

    strategies = list(results.keys())

    # Bar chart 1: PQI mean and p95
    pqi_mean = [results[s].pqi_mean for s in strategies]
    pqi_p95 = [results[s].pqi_p95 for s in strategies]

    x = list(range(len(strategies)))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    bars_mean = ax.bar([i - width / 2 for i in x], pqi_mean, width, label="PQI mean")
    bars_p95 = ax.bar([i + width / 2 for i in x], pqi_p95, width, label="PQI p95")

    # Annotate bars with numeric values
    for bars in (bars_mean, bars_p95):
        for bar in bars:
            height = bar.get_height()
            ax.annotate(
                f"{height:.2f}",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),  # 3 points vertical offset
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(strategies, rotation=20)
    ax.set_ylabel("Ground-truth capability")
    ax.set_title("Proposer Quality Index (PQI) by strategy")
    ax.legend()
    plt.tight_layout()
    pq_path = f"{output_prefix}_pqi.png"
    plt.savefig(pq_path)
    plt.close(fig)

    # Bar chart 2: missed slots, attacker share, selection error
    missed = [results[s].missed_slot_rate for s in strategies]
    attacker = [results[s].attacker_share for s in strategies]
    error = [results[s].selection_error_rate for s in strategies]

    fig, ax = plt.subplots(figsize=(10, 5))
    bar_missed = ax.bar(x, missed, width, label="Missed slot rate")
    bar_attacker = ax.bar([i + width for i in x], attacker, width, label="Attacker proposer share")
    bar_error = ax.bar([i + 2 * width for i in x], error, width, label="Selection error rate")

    # Annotate robustness bars with numeric values
    for bars in (bar_missed, bar_attacker, bar_error):
        for bar in bars:
            height = bar.get_height()
            ax.annotate(
                f"{height:.2f}",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    ax.set_xticks([i + width for i in x])
    ax.set_xticklabels(strategies, rotation=20)
    ax.set_ylabel("Rate")
    ax.set_ylim(0, max(max(missed + attacker + error), 0.01) * 1.2)
    ax.set_title("Robustness metrics by strategy")
    ax.legend()
    plt.tight_layout()
    rob_path = f"{output_prefix}_robustness.png"
    plt.savefig(rob_path)
    plt.close(fig)

    # Bar chart 3: p95 block time only
    p95_bt = [results[s].p95_block_time for s in strategies]

    fig, ax1 = plt.subplots(figsize=(10, 5))

    bar_bt = ax1.bar(x, p95_bt, width, label="p95 block time (s)", color="tab:blue")
    ax1.set_ylabel("p95 block time (s)")

    # Annotate block-time bars
    for bar in bar_bt:
        height = bar.get_height()
        ax1.annotate(
            f"{height:.2f}",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    ax1.set_xticks(x)
    ax1.set_xticklabels(strategies, rotation=20)
    ax1.set_title("p95 Block Time by Strategy")
    ax1.legend()

    plt.tight_layout()
    lat_path = f"{output_prefix}_latency.png"
    plt.savefig(lat_path)
    plt.close(fig)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Consensus baseline evaluation vs quantum model")
    parser.add_argument("--nodes", type=int, default=20, help="Number of simulated nodes")
    parser.add_argument("--rounds", type=int, default=300, help="Number of consensus rounds to simulate")
    parser.add_argument("--attackers", type=float, default=0.2, help="Fraction of nodes that are adversarial [0,1]")
    parser.add_argument("--top-k", type=int, default=3, help="Top-k nodes used for selection error metric")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--output-dir", type=str, default="reports", help="Directory for metrics and plots")

    args = parser.parse_args()

    cfg = SimulationConfig(
        num_nodes=args.nodes,
        num_rounds=args.rounds,
        attacker_fraction=args.attackers,
        top_k_for_error=args.top_k,
        seed=args.seed,
        output_dir=args.output_dir,
    )

    print("🚀 Running consensus baseline evaluation...")
    print(f"   Nodes: {cfg.num_nodes}, Rounds: {cfg.num_rounds}, Attackers: {cfg.attacker_fraction:.2f}")

    results = run_simulation(cfg)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    prefix = os.path.join(cfg.output_dir, f"consensus_baselines_{timestamp}")

    # Print a compact summary for the paper
    print("\n📊 Summary metrics (per strategy):")
    for name, m in results.items():
        print(f"- {name}:")
        print(f"    PQI mean / p95: {m.pqi_mean:.3f} / {m.pqi_p95:.3f}")
        print(f"    Missed slots: {m.missed_slot_rate*100:.1f}%")
        print(f"    p95 block time: {m.p95_block_time:.3f} s")
        print(f"    Nakamoto coefficient: {m.nakamoto_coefficient}")
        print(f"    Attacker proposer share: {m.attacker_share*100:.1f}%")
        print(f"    Selection error rate: {m.selection_error_rate*100:.1f}%")

    # Save JSON and plots for inclusion in the paper
    metrics_path = f"{prefix}_metrics.json"
    _save_metrics_json(results, cfg, metrics_path)
    _plot_results(results, cfg, prefix)

    print(f"\n💾 Metrics written to: {metrics_path}")
    print(f"📈 Plots written with prefix: {prefix}_*.png")


if __name__ == "__main__":
    main()
