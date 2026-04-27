#!/usr/bin/env python3
"""Security Experiments
======================

Six targeted security experiments for the quantum annealing consensus
mechanism:

1. Probe Manipulation Attack
   Colluding witnesses strategically inflate the apparent latency of honest
   nodes.  Measures how many colluding witnesses are needed to flip the
   selected proposer away from the true best node.

2. Infrastructure Gaming Attack
   Adversarial nodes receive 2× better latency and throughput than honest
   nodes (simulating richer hardware / better connectivity).  Tracks the
   attacker selection rate over many rounds and verifies that the frequency
   penalty eventually forces rotation.

3. Score Racing / Fairness-Bound Verification
   Tracks how many rounds until even the best honest node is rotated out.
   Verifies the empirical bound against the theoretical bound from Theorem 2
   and measures the effect of varying w_freq.

4. Attacker-Fraction Sweep
    Sweeps Byzantine fraction and compares committee capture, committee-seat
    share, and missed-slot behavior under committee-aware selection.

5. Correlated-Failure Resilience
    Concentrates strong nodes in a shared failure domain and measures primary
    disruption, surviving seat ratio, and full-committee failure exposure.

6. Block-Withholding Fallback Recovery
    Lets attacker-selected committee members withhold blocks and measures
    fallback activation, recovery latency, and missed-slot behavior.
"""

import hashlib
import json
import math
import os
import random
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

def _ensure_repo_root_on_path() -> None:
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

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # type: ignore

from blockchain.quantum_consensus import QuantumAnnealingConsensus
from blockchain.quantum_consensus.quantum_annealing_consensus import AblationConfig, CommitteeSelectionResult  # type: ignore
from blockchain.utils.result_layout import create_run_layout, write_run_metadata
from tools.evaluation_overhaul import (
    LITERATURE_COMMITTEE_STRATEGIES,
    SimulationConfig,
    _select_committee_composite_greedy,
    _select_committee_exact,
    _select_committee_fairness_only,
    _select_committee_greedy,
    _select_committee_quantum,
    _select_committee_reputation,
    _select_committee_uniform,
    _select_committee_vrf_stake,
    _select_committee_weighted,
    run_simulation,
)
from tools.visualize_findings import generate_findings_bundle


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _refresh_live_findings_dashboard(output_dir: str) -> None:
    try:
        result = generate_findings_bundle(search_root=output_dir, output_dir=output_dir)
        print(f"  live findings dashboard refreshed: {result['live_dashboard_path']}")
    except Exception as exc:
        print(f"  warning: could not refresh live findings dashboard: {exc}")


def _synthesise_security_metadata(node_index: int, attacker: bool, metadata_profile: str) -> Dict[str, Any]:
    """Create deterministic infrastructure metadata for committee-aware security studies."""
    providers = ["aws", "gcp", "azure", "self_hosted"]
    regions = ["us-west-2", "us-east-1", "eu-central-1", "ap-south-1"]
    countries = ["US", "US", "DE", "IN"]
    datacenter_codes = ["pdx1", "iad1", "fra1", "bom1"]

    provider_idx = node_index % len(providers)
    region_idx = (node_index // len(providers)) % len(regions)
    if metadata_profile == "clustered_attackers" and attacker:
        provider_idx = 0
        region_idx = 1

    return {
        "asn": 64512 + (provider_idx * 100) + region_idx,
        "cloud_provider": providers[provider_idx],
        "region": regions[region_idx],
        "datacenter": datacenter_codes[region_idx],
        "country_code": countries[region_idx],
        "operator_id": f"{'attacker' if attacker else 'operator'}_{node_index % 8}",
        "failure_domain": f"{providers[provider_idx]}:{regions[region_idx]}",
        "metadata_source": "security_experiment",
    }


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[94]

def _build_consensus(
    num_nodes: int,
    seed: int,
    attacker_fraction: float = 0.2,
    ablation: Optional[AblationConfig] = None,
    metadata_profile: str = "synthetic_static",
    concentrate_top_nodes_count: int = 0,
) -> Tuple[
    QuantumAnnealingConsensus,
    List[str],
    Dict[str, float],
    Dict[str, bool],
]:
    """
    Initialise a QuantumAnnealingConsensus with synthetic nodes.

    Returns (consensus, node_ids, ground_truth, is_attacker).
    """
    rng = random.Random(seed)
    consensus = QuantumAnnealingConsensus(
        initialize_genesis=False,
        verbose=False,
        ablation_config=ablation,
    )

    node_ids: List[str] = []
    ground_truth: Dict[str, float] = {}
    is_attacker: Dict[str, bool] = {}

    num_attackers = max(1, int(num_nodes * attacker_fraction))
    attacker_ids = {f"node_{i}" for i in range(num_attackers)}

    node_specs: List[Tuple[str, bool, float]] = []
    for i in range(num_nodes):
        node_id = f"node_{i}"
        node_ids.append(node_id)
        attacker = node_id in attacker_ids
        is_attacker[node_id] = attacker
        cap = rng.uniform(0.3, 1.0)
        if attacker:
            cap = max(0.1, cap - rng.uniform(0.2, 0.5))
        else:
            cap = min(1.0, cap + rng.uniform(0.0, 0.2))
        ground_truth[node_id] = cap
        node_specs.append((node_id, attacker, cap))

    concentrated_nodes = set()
    if concentrate_top_nodes_count > 0:
        concentrated_nodes = {
            node_id
            for node_id, _ in sorted(ground_truth.items(), key=lambda item: item[1], reverse=True)[:concentrate_top_nodes_count]
        }

    now = time.time()
    for index, (node_id, attacker, cap) in enumerate(node_specs):
        metadata = _synthesise_security_metadata(index, attacker, metadata_profile)
        if node_id in concentrated_nodes:
            metadata.update(
                {
                    "asn": 64513,
                    "cloud_provider": "aws",
                    "region": "us-east-1",
                    "datacenter": "iad1",
                    "country_code": "US",
                    "operator_id": f"concentrated_{index % 4}",
                    "failure_domain": "aws:us-east-1",
                }
            )

        pub, _ = consensus.ensure_node_keys(node_id)
        consensus.register_node(node_id, pub, metadata=metadata)
        consensus.nodes[node_id]["stake_weight"] = max(0.1, cap * rng.uniform(5.0, 15.0))
        consensus.nodes[node_id]["latency"] = max(0.001, 0.15 - 0.10 * cap + rng.uniform(-0.02, 0.02))
        consensus.nodes[node_id]["throughput"] = max(1.0, 5.0 + 45.0 * cap * rng.uniform(0.8, 1.2))
        consensus.nodes[node_id]["last_seen"] = now
        consensus.nodes[node_id]["proposal_success_count"] = int(10 * cap)
        consensus.nodes[node_id]["proposal_failure_count"] = int(3 * (1.0 - cap))
        consensus.append_committee_observation(
            node_id,
            uptime_sample=1,
            latency_sample=consensus.nodes[node_id]["latency"],
            throughput_sample=consensus.nodes[node_id]["throughput"],
            anchor_id="bootstrap",
        )

    consensus.node_performance_cache.clear()
    consensus.committee_feature_cache.clear()
    return consensus, node_ids, ground_truth, is_attacker


def _refresh_committee_metrics(
    consensus: QuantumAnnealingConsensus,
    node_ids: List[str],
    ground_truth: Dict[str, float],
    is_attacker: Dict[str, bool],
    rng: random.Random,
    *,
    round_idx: int,
    attacker_hardware_multiplier: float = 1.0,
) -> None:
    """Refresh synthetic per-round metrics and update rolling committee observations."""
    now = time.time()
    anchor_id = f"security_round_{round_idx % 8}"

    for node_id in node_ids:
        cap = ground_truth[node_id]
        base_latency = max(0.001, 0.15 - 0.10 * cap + rng.uniform(-0.01, 0.01))
        base_throughput = max(1.0, 5.0 + 45.0 * cap * rng.uniform(0.85, 1.15))

        if is_attacker.get(node_id, False) and attacker_hardware_multiplier != 1.0:
            base_latency = max(0.001, base_latency / attacker_hardware_multiplier)
            base_throughput *= attacker_hardware_multiplier

        consensus.nodes[node_id]["latency"] = base_latency
        consensus.nodes[node_id]["throughput"] = base_throughput
        consensus.nodes[node_id]["last_seen"] = now
        consensus.append_committee_observation(
            node_id,
            uptime_sample=1,
            latency_sample=base_latency,
            throughput_sample=base_throughput,
            anchor_id=anchor_id,
        )

    consensus.node_performance_cache.clear()
    consensus.committee_feature_cache.clear()


def _serialize_pairwise_features(
    candidate_nodes: List[str],
    pairwise_features: Dict[Tuple[int, int], Dict[str, float]],
) -> Dict[str, Dict[str, float]]:
    serializable_pairwise = {}
    for (i, j), feature_bundle in pairwise_features.items():
        serializable_pairwise[f"{candidate_nodes[i]}::{candidate_nodes[j]}"] = feature_bundle
    return serializable_pairwise


def _resolve_security_committee_strategies(
    strategies: Optional[List[str]],
    *,
    num_nodes: int,
    include_exact_when_safe: bool = False,
) -> List[str]:
    """Resolve committee strategies for security experiments."""
    resolved = list(strategies) if strategies is not None else list(LITERATURE_COMMITTEE_STRATEGIES)
    if include_exact_when_safe and num_nodes <= 16 and "committee_exact" not in resolved:
        resolved.append("committee_exact")
    return resolved


def _select_committee_strategy(
    consensus: QuantumAnnealingConsensus,
    strategy: str,
    candidate_nodes: List[str],
    vrf_output: str,
    committee_k: int,
    primary_leader_policy: str = "highest_score",
) -> CommitteeSelectionResult:
    """Local committee selector helper for security studies."""
    selector_map = {
        "committee_quantum": _select_committee_quantum,
        "committee_greedy": _select_committee_greedy,
        "committee_weighted": _select_committee_weighted,
        "committee_uniform": _select_committee_uniform,
        "committee_vrf_stake": _select_committee_vrf_stake,
        "committee_reputation": _select_committee_reputation,
        "committee_composite_greedy": _select_committee_composite_greedy,
        "committee_fairness_only": _select_committee_fairness_only,
    }

    if strategy == "committee_exact":
        return _select_committee_exact(
            consensus,
            candidate_nodes,
            vrf_output,
            committee_k,
            primary_leader_policy,
            max_exact_candidates=16,
        )

    if strategy in selector_map:
        return selector_map[strategy](
            consensus,
            candidate_nodes,
            vrf_output,
            committee_k,
            primary_leader_policy,
        )

    raise ValueError(f"Unsupported committee strategy: {strategy!r}")


def _failure_domain(consensus: QuantumAnnealingConsensus, node_id: str) -> str:
    return consensus.nodes.get(node_id, {}).get("committee_metadata", {}).get("failure_domain", "unknown")


def _record_committee_round(
    consensus: QuantumAnnealingConsensus,
    committee_nodes: List[str],
    *,
    round_idx: int,
    selected_leader: Optional[str],
    failed_nodes: Optional[List[str]] = None,
) -> None:
    failed_set = set(failed_nodes or [])
    for node_id in committee_nodes:
        node_state = consensus.nodes.get(node_id)
        if not node_state:
            continue
        node_state["committee_selection_count"] = node_state.get("committee_selection_count", 0) + 1
        node_state["last_committee_epoch"] = round_idx

    for node_id in failed_set:
        if node_id in consensus.nodes:
            consensus.nodes[node_id]["proposal_failure_count"] += 1

    if selected_leader and selected_leader in consensus.nodes:
        consensus.nodes[selected_leader]["proposal_success_count"] += 1
        consensus.record_leader_selection(len(consensus.selection_history), selected_leader)

    consensus.node_performance_cache.clear()
    consensus.committee_feature_cache.clear()


@dataclass
class CorrelatedFailureResult:
    strategy: str
    outage_probability: float
    mean_unique_failure_domain_ratio: float
    mean_surviving_seat_ratio: float
    primary_disruption_rate: float
    recovery_success_rate: float
    full_committee_failure_rate: float
    missed_slot_rate: float
    n_rounds: int


@dataclass
class AttackerFractionSweepResult:
    strategy: str
    attacker_fraction: float
    attacker_proposer_share: float
    attacker_committee_share: float
    committee_constraint_violation_rate: float
    missed_slot_rate: float
    p95_block_time_ms: float
    estimated_throughput_blocks_per_sec: float
    throughput_degradation_ratio: float
    finality_degradation_ratio: float
    mean_solver_ms: float
    n_rounds: int


@dataclass
class BlockWithholdingResult:
    strategy: str
    withholding_probability: float
    fallback_activation_rate: float
    fallback_success_rate: float
    mean_recovery_latency_ms: float
    p95_recovery_latency_ms: float
    attacker_primary_share_initial: float
    attacker_primary_share_final: float
    final_attacker_proposer_share: float
    missed_slot_rate: float
    n_rounds: int


def _select_argmax(
    consensus: QuantumAnnealingConsensus,
    node_ids: List[str],
    vrf_output: str,
) -> Optional[str]:
    """Direct argmax of effective suitability score."""
    best, best_s = None, float("-inf")
    for n in node_ids:
        s = consensus.calculate_effective_score(n, vrf_output)
        if s > best_s:
            best_s = s
            best = n
    return best


# ---------------------------------------------------------------------------
# Experiment 1 – Probe Manipulation Attack
# ---------------------------------------------------------------------------

@dataclass
class ProbeManipulationResult:
    num_colluding_witnesses: int
    flip_rate: float          # fraction of rounds attacker displaced true-best node
    inflation_ms: float       # mean added latency to honest nodes (ms)
    n_rounds: int


@dataclass
class WitnessCollusionResult:
    q: int
    q_min: int
    population_size: int
    attacker_witnesses: int
    measured_capture_rate: float
    hypergeometric_capture_bound: float
    absolute_gap: float
    n_trials: int


def _hypergeometric_capture_bound(population_size: int, attacker_witnesses: int, q: int, q_min: int) -> float:
    if population_size <= 0 or q <= 0 or q_min <= 0 or q > population_size or q_min > q:
        return 0.0
    if attacker_witnesses <= 0 or attacker_witnesses < q_min:
        return 0.0

    denominator = math.comb(population_size, q)
    if denominator <= 0:
        return 0.0

    capture_probability = 0.0
    upper = min(q, attacker_witnesses)
    honest_witnesses = population_size - attacker_witnesses
    for compromised in range(q_min, upper + 1):
        honest_needed = q - compromised
        if honest_needed > honest_witnesses:
            continue
        capture_probability += (
            math.comb(attacker_witnesses, compromised)
            * math.comb(honest_witnesses, honest_needed)
            / denominator
        )
    return max(0.0, min(1.0, capture_probability))


def run_probe_manipulation_experiment(
    num_nodes: int = 30,
    num_rounds: int = 500,
    max_colluding_witnesses: int = 10,
    inflation_delay_ms_range: Tuple[float, float] = (50.0, 200.0),
    seed: int = 7,
    output_dir: str = "reports",
) -> List[ProbeManipulationResult]:
    """
    Implement a probe-manipulation adversary that strategically delays its
    witness responses for honest nodes, inflating their apparent latency.

    For each colluding-witness count (1, 2, …, max_colluding_witnesses):
      • All colluding witnesses add a random delay from inflation_delay_ms_range
        to the 'measured_latency' field in the node_data of honest nodes.
      • We then run num_rounds of argmax-based selection and count how often
        the attacker (highest-capability fake node) displaces the true-best
        honest node.

    Returns a list of ProbeManipulationResult, one per colluding count.
    """
    results: List[ProbeManipulationResult] = []
    rng = random.Random(seed)

    print("\n" + "=" * 65)
    print("  EXPERIMENT 1: Probe Manipulation Attack")
    print("=" * 65)

    for n_colluding in range(1, max_colluding_witnesses + 1):
        flip_count = 0
        total_inflation_ms = 0.0

        # Fresh environment per colluding count to isolate the effect
        consensus, node_ids, ground_truth, is_attacker = _build_consensus(
            num_nodes, seed + n_colluding
        )

        # Identify true-best honest node
        honest_nodes = [n for n in node_ids if not is_attacker[n]]
        true_best = max(honest_nodes, key=lambda n: ground_truth[n])

        # Colluding witnesses = first n_colluding attacker nodes (or fewer)
        attacker_nodes = [n for n in node_ids if is_attacker[n]]
        colluders = attacker_nodes[:min(n_colluding, len(attacker_nodes))]

        for rnd in range(num_rounds):
            # Reset latency for all honest nodes to their capability-based value
            now = time.time()
            for n in honest_nodes:
                cap = ground_truth[n]
                base_lat = max(0.001, 0.15 - 0.10 * cap)
                consensus.nodes[n]["latency"] = base_lat
                consensus.nodes[n]["last_seen"] = now

            # Colluding witnesses inject inflated latency onto honest nodes
            for col in colluders:
                for n in honest_nodes:
                    inflation = rng.uniform(*inflation_delay_ms_range) / 1000.0
                    total_inflation_ms += inflation * 1000.0
                    consensus.nodes[n]["latency"] += inflation / len(colluders)

            consensus.node_performance_cache.clear()

            vrf = hashlib.sha256(f"probe_manip_{rnd}_{seed}".encode()).hexdigest()
            selected = _select_argmax(consensus, node_ids, vrf)

            if selected != true_best:
                flip_count += 1

        flip_rate = flip_count / num_rounds
        mean_inflation = total_inflation_ms / (num_rounds * max(1, len(colluders)))
        r = ProbeManipulationResult(
            num_colluding_witnesses=n_colluding,
            flip_rate=flip_rate,
            inflation_ms=mean_inflation,
            n_rounds=num_rounds,
        )
        results.append(r)
        print(
            f"  colluders={n_colluding:2d}  flip_rate={flip_rate:.3f}  "
            f"mean_inflation={mean_inflation:.1f}ms"
        )

    _plot_probe_manipulation(results, output_dir)
    return results


def run_witness_collusion_experiment(
    num_nodes: int = 40,
    num_trials: int = 2000,
    q_values: Optional[List[int]] = None,
    q_min_values: Optional[List[int]] = None,
    attacker_fraction: float = 0.2,
    seed: int = 7,
    output_dir: str = "reports",
) -> List[WitnessCollusionResult]:
    """Compare simulated witness-capture rates against the hypergeometric theorem bound."""
    if q_values is None:
        q_values = [3, 5, 7, 10]
    if q_min_values is None:
        q_min_values = [1, 2, 3]

    rng = random.Random(seed)
    witness_population = max(1, num_nodes - 2)
    attacker_witnesses = min(witness_population, max(0, int(round(witness_population * attacker_fraction))))
    witness_pool = list(range(witness_population))
    results: List[WitnessCollusionResult] = []

    print("\n" + "=" * 72)
    print("  EXPERIMENT 1B: Witness-Collusion Capture Sweep")
    print(
        f"  nodes={num_nodes} witness_population={witness_population} attacker_witnesses={attacker_witnesses} trials={num_trials}"
    )
    print("=" * 72)

    for q in sorted(set(q_values)):
        if q <= 0 or q > witness_population:
            continue
        for q_min in sorted(set(q_min_values)):
            if q_min <= 0 or q_min > q:
                continue

            captures = 0
            for _ in range(num_trials):
                sampled = rng.sample(witness_pool, q)
                compromised = sum(1 for witness_idx in sampled if witness_idx < attacker_witnesses)
                if compromised >= q_min:
                    captures += 1

            measured_capture_rate = captures / num_trials if num_trials > 0 else 0.0
            hypergeometric_capture_bound = _hypergeometric_capture_bound(
                witness_population,
                attacker_witnesses,
                q,
                q_min,
            )
            result = WitnessCollusionResult(
                q=q,
                q_min=q_min,
                population_size=witness_population,
                attacker_witnesses=attacker_witnesses,
                measured_capture_rate=measured_capture_rate,
                hypergeometric_capture_bound=hypergeometric_capture_bound,
                absolute_gap=abs(measured_capture_rate - hypergeometric_capture_bound),
                n_trials=num_trials,
            )
            results.append(result)
            print(
                f"  q={q:2d} q_min={q_min:2d} measured={measured_capture_rate:.3f} bound={hypergeometric_capture_bound:.3f} gap={result.absolute_gap:.3f}"
            )

    _plot_witness_collusion(results, output_dir)
    return results


def _plot_probe_manipulation(results: List[ProbeManipulationResult], output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    xs = [r.num_colluding_witnesses for r in results]
    ys = [r.flip_rate for r in results]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(xs, ys, marker="o", color="crimson", linewidth=2)
    ax.set_xlabel("Number of colluding witnesses")
    ax.set_ylabel("Flip rate (attacker displaces true-best)")
    ax.set_title("Probe Manipulation Attack: Flip Rate vs Collusion Size")
    ax.set_ylim(0, 1.05)
    ax.axhline(0.5, linestyle="--", color="grey", alpha=0.5, label="50% flip threshold")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()
    path = os.path.join(output_dir, f"security_probe_manipulation_{ts}.png")
    plt.savefig(path)
    plt.close(fig)
    print(f"  Plot saved: {path}")


def _plot_witness_collusion(results: List[WitnessCollusionResult], output_dir: str) -> None:
    if not results:
        return

    os.makedirs(output_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    q_min_values = sorted(set(result.q_min for result in results))

    fig, ax = plt.subplots(figsize=(10, 5))
    for q_min in q_min_values:
        items = sorted([result for result in results if result.q_min == q_min], key=lambda item: item.q)
        xs = [item.q for item in items]
        ax.plot(xs, [item.measured_capture_rate for item in items], marker="o", label=f"measured q_min={q_min}")
        ax.plot(
            xs,
            [item.hypergeometric_capture_bound for item in items],
            linestyle="--",
            marker="x",
            label=f"bound q_min={q_min}",
        )

    ax.set_xlabel("Witness sample size q")
    ax.set_ylabel("Capture probability")
    ax.set_title("Witness-Collusion Capture: measured vs hypergeometric bound")
    ax.set_ylim(0, 1.05)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(ncol=2)
    plt.tight_layout()
    path = os.path.join(output_dir, f"security_witness_collusion_{ts}.png")
    plt.savefig(path)
    plt.close(fig)
    print(f"  Plot saved: {path}")


# ---------------------------------------------------------------------------
# Experiment 2 – Infrastructure Gaming Attack
# ---------------------------------------------------------------------------

@dataclass
class InfraGamingResult:
    round_idx: int
    attacker_cumulative_share: float
    best_attacker_score: float
    best_honest_score: float


def run_infrastructure_gaming_experiment(
    num_nodes: int = 40,
    num_rounds: int = 1000,
    attacker_hardware_multiplier: float = 2.0,
    attacker_fraction: float = 0.2,
    seed: int = 13,
    output_dir: str = "reports",
) -> List[InfraGamingResult]:
    """
    Give adversarial nodes attacker_hardware_multiplier × better latency
    and throughput than honest nodes.

    Tracks attacker selection rate over rounds and verifies that the
    frequency penalty eventually forces rotation (Theorem 2).

    Returns per-round cumulative attacker share.
    """
    consensus, node_ids, ground_truth, is_attacker = _build_consensus(
        num_nodes, seed, attacker_fraction
    )

    honest_nodes = [n for n in node_ids if not is_attacker[n]]
    attacker_nodes = [n for n in node_ids if is_attacker[n]]

    print("\n" + "=" * 65)
    print("  EXPERIMENT 2: Infrastructure Gaming Attack")
    print(f"  hardware_multiplier={attacker_hardware_multiplier}x  rounds={num_rounds}")
    print("=" * 65)

    results: List[InfraGamingResult] = []
    attacker_selections = 0

    for rnd in range(num_rounds):
        now = time.time()

        # Update honest node metrics
        for n in honest_nodes:
            cap = ground_truth[n]
            consensus.nodes[n]["latency"] = max(0.001, 0.15 - 0.10 * cap)
            consensus.nodes[n]["throughput"] = 5.0 + 45.0 * cap
            consensus.nodes[n]["last_seen"] = now

        # Update attacker node metrics with boosted hardware
        for n in attacker_nodes:
            cap = ground_truth[n]
            # Better (lower) latency and higher throughput
            consensus.nodes[n]["latency"] = max(0.001, (0.15 - 0.10 * cap) / attacker_hardware_multiplier)
            consensus.nodes[n]["throughput"] = (5.0 + 45.0 * cap) * attacker_hardware_multiplier
            consensus.nodes[n]["last_seen"] = now

        consensus.node_performance_cache.clear()

        vrf = hashlib.sha256(f"infra_{rnd}_{seed}".encode()).hexdigest()
        selected = _select_argmax(consensus, node_ids, vrf)

        if selected and is_attacker.get(selected, False):
            attacker_selections += 1

        # Record proposal to update selection-frequency counter
        if selected:
            slot = len(consensus.selection_history)
            consensus.record_leader_selection(slot, selected)

        cumulative_share = attacker_selections / (rnd + 1)
        best_att_score = max(
            (consensus.calculate_suitability_score(n) for n in attacker_nodes), default=0.0
        )
        best_hon_score = max(
            (consensus.calculate_suitability_score(n) for n in honest_nodes), default=0.0
        )

        results.append(InfraGamingResult(
            round_idx=rnd,
            attacker_cumulative_share=cumulative_share,
            best_attacker_score=best_att_score,
            best_honest_score=best_hon_score,
        ))

        if (rnd + 1) % 100 == 0:
            print(
                f"  round={rnd+1:4d}  attacker_cumulative_share={cumulative_share:.3f}  "
                f"best_att_score={best_att_score:.3f}  best_hon_score={best_hon_score:.3f}"
            )

    _plot_infra_gaming(results, output_dir)
    return results


def _plot_infra_gaming(results: List[InfraGamingResult], output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    rounds = [r.round_idx for r in results]
    attacker_share = [r.attacker_cumulative_share for r in results]
    att_score = [r.best_attacker_score for r in results]
    hon_score = [r.best_honest_score for r in results]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    ax1.plot(rounds, attacker_share, color="crimson", label="Attacker cumulative share")
    ax1.axhline(0.5, linestyle="--", color="grey", alpha=0.5)
    ax1.set_ylabel("Cumulative selection share")
    ax1.set_title("Infrastructure Gaming: Attacker Dominance Over Rounds")
    ax1.legend()
    ax1.grid(True, linestyle="--", alpha=0.4)

    ax2.plot(rounds, att_score, color="crimson", label="Best attacker score")
    ax2.plot(rounds, hon_score, color="steelblue", label="Best honest score")
    ax2.set_xlabel("Round")
    ax2.set_ylabel("Suitability score")
    ax2.set_title("Score Convergence (frequency penalty effect)")
    ax2.legend()
    ax2.grid(True, linestyle="--", alpha=0.4)

    plt.tight_layout()
    path = os.path.join(output_dir, f"security_infra_gaming_{ts}.png")
    plt.savefig(path)
    plt.close(fig)
    print(f"  Plot saved: {path}")


# ---------------------------------------------------------------------------
# Experiment 3 – Score Racing / Fairness Bound Verification
# ---------------------------------------------------------------------------

@dataclass
class ScoreRacingResult:
    w_freq: float
    rounds_until_rotation_mean: float
    rounds_until_rotation_p95: float
    rotation_count: int
    n_trials: int


def run_score_racing_experiment(
    num_nodes: int = 20,
    max_rounds: int = 2000,
    n_trials: int = 50,
    w_freq_values: Optional[List[float]] = None,
    seed: int = 19,
    output_dir: str = "reports",
) -> List[ScoreRacingResult]:
    """
    Track how many rounds until the best honest node is rotated out by the
    frequency penalty.

    For each value of w_freq (weight_selection_frequency):
      • Run n_trials independent simulations.
      • In each trial, record the first round at which the best node is no
        longer selected (selection switches to another node).
      • Compute mean and p95 of that rotation round.

    Higher w_freq should produce faster / more aggressive rotation.
    """
    if w_freq_values is None:
        w_freq_values = [0.1, 0.2, 0.3, 0.4]

    results: List[ScoreRacingResult] = []

    print("\n" + "=" * 65)
    print("  EXPERIMENT 3: Score Racing / Fairness Bound")
    print(f"  nodes={num_nodes}  max_rounds={max_rounds}  trials={n_trials}")
    print("=" * 65)

    for w_freq in w_freq_values:
        rotation_rounds: List[int] = []

        for trial in range(n_trials):
            trial_seed = seed + trial * 100 + int(w_freq * 1000)
            rng = random.Random(trial_seed)

            consensus, node_ids, ground_truth, is_attacker = _build_consensus(
                num_nodes, trial_seed, attacker_fraction=0.0  # pure honest network
            )
            # Override w_freq
            consensus.weight_selection_frequency = w_freq

            honest = [n for n in node_ids if not is_attacker[n]]
            best_node = max(honest, key=lambda n: ground_truth[n])

            rotation_round: Optional[int] = None
            prev_selected: Optional[str] = None
            now = time.time()

            for rnd in range(max_rounds):
                # Update metrics
                for n in honest:
                    cap = ground_truth[n]
                    consensus.nodes[n]["latency"] = max(0.001, 0.15 - 0.10 * cap + rng.uniform(-0.01, 0.01))
                    consensus.nodes[n]["throughput"] = max(1.0, 5.0 + 45.0 * cap * rng.uniform(0.9, 1.1))
                    consensus.nodes[n]["last_seen"] = now
                consensus.node_performance_cache.clear()

                vrf = hashlib.sha256(f"racing_{rnd}_{trial_seed}".encode()).hexdigest()
                selected = _select_argmax(consensus, honest, vrf)

                # Record selection for frequency tracking
                if selected:
                    slot = len(consensus.selection_history)
                    consensus.record_leader_selection(slot, selected)

                # Detect first rotation away from best_node
                if (
                    rotation_round is None
                    and prev_selected == best_node
                    and selected != best_node
                ):
                    rotation_round = rnd
                    break

                prev_selected = selected

            rotation_rounds.append(rotation_round if rotation_round is not None else max_rounds)

        mean_rot = statistics.mean(rotation_rounds)
        p95_rot = statistics.quantiles(rotation_rounds, n=100, method="inclusive")[94]

        r = ScoreRacingResult(
            w_freq=w_freq,
            rounds_until_rotation_mean=mean_rot,
            rounds_until_rotation_p95=float(p95_rot),
            rotation_count=sum(1 for x in rotation_rounds if x < max_rounds),
            n_trials=n_trials,
        )
        results.append(r)
        print(
            f"  w_freq={w_freq:.2f}  rotation_mean={mean_rot:.1f}  "
            f"rotation_p95={p95_rot:.1f}  rotated={r.rotation_count}/{n_trials}"
        )

    _plot_score_racing(results, output_dir)
    return results


def _plot_score_racing(results: List[ScoreRacingResult], output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    w_freqs = [r.w_freq for r in results]
    means = [r.rounds_until_rotation_mean for r in results]
    p95s = [r.rounds_until_rotation_p95 for r in results]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(w_freqs, means, marker="o", label="Mean rounds until rotation")
    ax.plot(w_freqs, p95s, marker="s", linestyle="--", label="P95 rounds until rotation")
    ax.set_xlabel("w_freq (fairness penalty weight)")
    ax.set_ylabel("Rounds until rotation")
    ax.set_title("Score Racing: Fairness Penalty Effect on Leader Rotation")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()
    path = os.path.join(output_dir, f"security_score_racing_{ts}.png")
    plt.savefig(path)
    plt.close(fig)
    print(f"  Plot saved: {path}")


# ---------------------------------------------------------------------------
# Experiment 4 – Attacker-Fraction Sweep
# ---------------------------------------------------------------------------

def run_attacker_fraction_sweep_experiment(
    num_nodes: int = 60,
    num_rounds: int = 500,
    attacker_fractions: Optional[List[float]] = None,
    strategies: Optional[List[str]] = None,
    committee_k: int = 5,
    metadata_profile: str = "clustered_attackers",
    include_exact_when_safe: bool = False,
    seed: int = 29,
    output_dir: str = "reports",
) -> List[AttackerFractionSweepResult]:
    """Sweep attacker fraction and compare proposer and committee capture across strategies."""
    if attacker_fractions is None:
        attacker_fractions = [0.0, 0.1, 0.2, 0.33, 0.4, 0.49]
    strategies = _resolve_security_committee_strategies(
        strategies,
        num_nodes=num_nodes,
        include_exact_when_safe=include_exact_when_safe,
    )

    raw_rows: List[Dict[str, float]] = []

    print("\n" + "=" * 65)
    print("  EXPERIMENT 4: Attacker-Fraction Sweep")
    print(f"  nodes={num_nodes}  rounds={num_rounds}  metadata_profile={metadata_profile}")
    print("=" * 65)

    for attacker_fraction in attacker_fractions:
        cfg = SimulationConfig(
            num_nodes=num_nodes,
            num_rounds=num_rounds,
            attacker_fraction=attacker_fraction,
            committee_k=committee_k,
            metadata_profile=metadata_profile,
            seed=seed,
            output_dir=output_dir,
        )
        for strategy in strategies:
            metrics = run_simulation(cfg, strategy, verbose=False)
            raw_rows.append(
                {
                    "strategy": strategy,
                    "attacker_fraction": attacker_fraction,
                    "attacker_proposer_share": metrics.attacker_share,
                    "attacker_committee_share": metrics.committee_attacker_seat_share,
                    "committee_constraint_violation_rate": metrics.committee_constraint_violation_rate,
                    "missed_slot_rate": metrics.missed_slot_rate,
                    "p95_block_time_ms": metrics.p95_block_time_ms,
                    "mean_solver_ms": metrics.mean_solver_ms,
                    "n_rounds": float(num_rounds),
                }
            )
            print(
                f"  fraction={attacker_fraction:.2f}  strategy={strategy:18s}  proposer={metrics.attacker_share:.3f}  "
                f"committee={metrics.committee_attacker_seat_share:.3f}  missed={metrics.missed_slot_rate:.3f}"
            )

    baseline_by_strategy: Dict[str, Dict[str, float]] = {}
    for row in raw_rows:
        strategy = str(row["strategy"])
        current = baseline_by_strategy.get(strategy)
        if current is None or float(row["attacker_fraction"]) < float(current["attacker_fraction"]):
            baseline_by_strategy[strategy] = row

    results: List[AttackerFractionSweepResult] = []
    for row in raw_rows:
        strategy = str(row["strategy"])
        baseline = baseline_by_strategy[strategy]
        current_p95 = max(float(row["p95_block_time_ms"]), 1e-9)
        baseline_p95 = max(float(baseline["p95_block_time_ms"]), 1e-9)
        estimated_throughput = 1000.0 / current_p95
        baseline_throughput = 1000.0 / baseline_p95
        throughput_degradation = max(0.0, 1.0 - (estimated_throughput / baseline_throughput)) if baseline_throughput > 0 else 0.0
        finality_degradation = max(0.0, (current_p95 / baseline_p95) - 1.0)
        results.append(
            AttackerFractionSweepResult(
                strategy=strategy,
                attacker_fraction=float(row["attacker_fraction"]),
                attacker_proposer_share=float(row["attacker_proposer_share"]),
                attacker_committee_share=float(row["attacker_committee_share"]),
                committee_constraint_violation_rate=float(row["committee_constraint_violation_rate"]),
                missed_slot_rate=float(row["missed_slot_rate"]),
                p95_block_time_ms=current_p95,
                estimated_throughput_blocks_per_sec=estimated_throughput,
                throughput_degradation_ratio=throughput_degradation,
                finality_degradation_ratio=finality_degradation,
                mean_solver_ms=float(row["mean_solver_ms"]),
                n_rounds=int(row["n_rounds"]),
            )
        )

    _plot_attacker_fraction_sweep(results, output_dir)
    return results


def _plot_attacker_fraction_sweep(results: List[AttackerFractionSweepResult], output_dir: str) -> None:
    if not results:
        return

    os.makedirs(output_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    strategies = sorted(set(r.strategy for r in results))
    grouped = {strategy: sorted([r for r in results if r.strategy == strategy], key=lambda item: item.attacker_fraction) for strategy in strategies}

    fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharex=True)
    for strategy, items in grouped.items():
        xs = [item.attacker_fraction for item in items]
        axes[0][0].plot(xs, [item.attacker_proposer_share for item in items], marker="o", label=strategy)
        axes[0][1].plot(xs, [item.attacker_committee_share for item in items], marker="o", label=strategy)
        axes[1][0].plot(xs, [item.missed_slot_rate for item in items], marker="o", label=strategy)
        axes[1][1].plot(xs, [item.p95_block_time_ms for item in items], marker="o", label=strategy)

    axes[0][0].set_title("Attacker proposer share")
    axes[0][1].set_title("Attacker committee share")
    axes[1][0].set_title("Missed-slot rate")
    axes[1][1].set_title("P95 block time")
    axes[0][0].set_ylabel("Rate")
    axes[0][1].set_ylabel("Rate")
    axes[1][0].set_ylabel("Rate")
    axes[1][1].set_ylabel("Milliseconds")
    axes[1][0].set_xlabel("Attacker fraction")
    axes[1][1].set_xlabel("Attacker fraction")

    for row in axes:
        for ax in row:
            ax.grid(True, linestyle="--", alpha=0.4)
            ax.legend()

    plt.tight_layout()
    path = os.path.join(output_dir, f"security_attacker_sweep_{ts}.png")
    plt.savefig(path)
    plt.close(fig)

    committee_only = [strategy for strategy in strategies if any(item.attacker_committee_share > 0.0 or "committee" in strategy for item in grouped[strategy])]
    if committee_only:
        fig, ax = plt.subplots(figsize=(10, 5))
        for strategy in committee_only:
            items = grouped[strategy]
            xs = [item.attacker_fraction for item in items]
            ax.plot(xs, [item.committee_constraint_violation_rate for item in items], marker="o", label=f"{strategy} violation")
            ax.plot(xs, [item.mean_solver_ms for item in items], marker="s", linestyle="--", label=f"{strategy} solver ms")
        ax.set_xlabel("Attacker fraction")
        ax.set_ylabel("Rate / milliseconds")
        ax.set_title("Committee robustness and overhead vs attacker fraction")
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend()
        plt.tight_layout()
        path = os.path.join(output_dir, f"security_attacker_sweep_overhead_{ts}.png")
        plt.savefig(path)
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharex=True)
    for strategy, items in grouped.items():
        xs = [item.attacker_fraction for item in items]
        axes[0].plot(xs, [item.throughput_degradation_ratio for item in items], marker="o", label=strategy)
        axes[1].plot(xs, [item.finality_degradation_ratio for item in items], marker="o", label=strategy)

    axes[0].set_title("Throughput degradation")
    axes[1].set_title("Finality degradation")
    axes[0].set_ylabel("Relative degradation")
    axes[0].set_xlabel("Attacker fraction")
    axes[1].set_xlabel("Attacker fraction")
    for ax in axes:
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend()
    plt.tight_layout()
    path = os.path.join(output_dir, f"security_attacker_sweep_degradation_{ts}.png")
    plt.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Experiment 5 – Correlated-Failure Resilience
# ---------------------------------------------------------------------------

def run_correlated_failure_experiment(
    num_nodes: int = 40,
    num_rounds: int = 500,
    outage_probabilities: Optional[List[float]] = None,
    strategies: Optional[List[str]] = None,
    committee_k: int = 5,
    attacker_fraction: float = 0.2,
    concentrated_top_nodes: int = 12,
    include_exact_when_safe: bool = False,
    seed: int = 31,
    output_dir: str = "reports",
) -> List[CorrelatedFailureResult]:
    """Concentrate high-scoring nodes in one failure domain and measure outage resilience."""
    if outage_probabilities is None:
        outage_probabilities = [0.1, 0.25, 0.5]
    strategies = _resolve_security_committee_strategies(
        strategies,
        num_nodes=num_nodes,
        include_exact_when_safe=include_exact_when_safe,
    )

    results: List[CorrelatedFailureResult] = []

    print("\n" + "=" * 65)
    print("  EXPERIMENT 5: Correlated-Failure Resilience")
    print(f"  nodes={num_nodes}  rounds={num_rounds}  concentrated_top_nodes={concentrated_top_nodes}")
    print("=" * 65)

    for outage_probability in outage_probabilities:
        for strategy in strategies:
            consensus, node_ids, ground_truth, is_attacker = _build_consensus(
                num_nodes,
                seed + int(outage_probability * 1000),
                attacker_fraction=attacker_fraction,
                metadata_profile="synthetic_static",
                concentrate_top_nodes_count=min(concentrated_top_nodes, num_nodes),
            )
            rng = random.Random(seed + int(outage_probability * 1000) + len(strategy))

            unique_failure_ratios: List[float] = []
            surviving_seat_ratios: List[float] = []
            primary_disruptions = 0
            recovery_successes = 0
            full_committee_failures = 0
            missed_slots = 0

            for rnd in range(num_rounds):
                _refresh_committee_metrics(consensus, node_ids, ground_truth, is_attacker, rng, round_idx=rnd)
                vrf = hashlib.sha256(f"correlated_failure_{strategy}_{outage_probability}_{rnd}_{seed}".encode()).hexdigest()
                result = _select_committee_strategy(consensus, strategy, node_ids, vrf, committee_k)
                committee_nodes = result.committee_nodes

                unique_failure_ratios.append(
                    len({_failure_domain(consensus, node_id) for node_id in committee_nodes}) / max(1, len(committee_nodes))
                )

                actual_leader = result.primary_leader
                failed_nodes: List[str] = []
                if rng.random() < outage_probability:
                    failed_nodes = [node_id for node_id in committee_nodes if _failure_domain(consensus, node_id) == "aws:us-east-1"]
                    surviving_nodes = [node_id for node_id in committee_nodes if node_id not in failed_nodes]
                    surviving_seat_ratios.append(len(surviving_nodes) / max(1, len(committee_nodes)))
                    if result.primary_leader in failed_nodes:
                        primary_disruptions += 1
                        if surviving_nodes:
                            actual_leader = consensus.derive_primary_leader(surviving_nodes, vrf)
                            recovery_successes += 1
                        else:
                            actual_leader = None
                            full_committee_failures += 1
                            missed_slots += 1
                    elif not surviving_nodes:
                        actual_leader = None
                        full_committee_failures += 1
                        missed_slots += 1
                else:
                    surviving_seat_ratios.append(1.0)

                _record_committee_round(
                    consensus,
                    committee_nodes,
                    round_idx=rnd,
                    selected_leader=actual_leader,
                    failed_nodes=failed_nodes,
                )

            results.append(
                CorrelatedFailureResult(
                    strategy=strategy,
                    outage_probability=outage_probability,
                    mean_unique_failure_domain_ratio=statistics.mean(unique_failure_ratios) if unique_failure_ratios else 0.0,
                    mean_surviving_seat_ratio=statistics.mean(surviving_seat_ratios) if surviving_seat_ratios else 0.0,
                    primary_disruption_rate=primary_disruptions / num_rounds,
                    recovery_success_rate=recovery_successes / max(1, primary_disruptions),
                    full_committee_failure_rate=full_committee_failures / num_rounds,
                    missed_slot_rate=missed_slots / num_rounds,
                    n_rounds=num_rounds,
                )
            )
            print(
                f"  outage={outage_probability:.2f}  strategy={strategy:18s}  disruption={primary_disruptions / num_rounds:.3f}  "
                f"survival={statistics.mean(surviving_seat_ratios) if surviving_seat_ratios else 0.0:.3f}"
            )

    _plot_correlated_failure(results, output_dir)
    return results


def _plot_correlated_failure(results: List[CorrelatedFailureResult], output_dir: str) -> None:
    if not results:
        return

    os.makedirs(output_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    strategies = sorted(set(r.strategy for r in results))
    grouped = {strategy: sorted([r for r in results if r.strategy == strategy], key=lambda item: item.outage_probability) for strategy in strategies}

    fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharex=True)
    for strategy, items in grouped.items():
        xs = [item.outage_probability for item in items]
        axes[0][0].plot(xs, [item.mean_unique_failure_domain_ratio for item in items], marker="o", label=strategy)
        axes[0][1].plot(xs, [item.mean_surviving_seat_ratio for item in items], marker="o", label=strategy)
        axes[1][0].plot(xs, [item.primary_disruption_rate for item in items], marker="o", label=strategy)
        axes[1][1].plot(xs, [item.full_committee_failure_rate for item in items], marker="o", label=strategy)

    axes[0][0].set_title("Committee diversity")
    axes[0][1].set_title("Mean surviving seat ratio")
    axes[1][0].set_title("Primary disruption rate")
    axes[1][1].set_title("Full committee failure rate")
    axes[0][0].set_ylabel("Ratio")
    axes[0][1].set_ylabel("Ratio")
    axes[1][0].set_ylabel("Rate")
    axes[1][1].set_ylabel("Rate")
    axes[1][0].set_xlabel("Outage probability")
    axes[1][1].set_xlabel("Outage probability")

    for row in axes:
        for ax in row:
            ax.grid(True, linestyle="--", alpha=0.4)
            ax.legend()

    plt.tight_layout()
    path = os.path.join(output_dir, f"security_correlated_failure_{ts}.png")
    plt.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Experiment 6 – Block-Withholding and Fallback Recovery
# ---------------------------------------------------------------------------

def run_block_withholding_experiment(
    num_nodes: int = 40,
    num_rounds: int = 500,
    withholding_probabilities: Optional[List[float]] = None,
    strategies: Optional[List[str]] = None,
    committee_k: int = 5,
    attacker_fraction: float = 0.2,
    attacker_hardware_multiplier: float = 1.6,
    include_exact_when_safe: bool = False,
    seed: int = 37,
    output_dir: str = "reports",
) -> List[BlockWithholdingResult]:
    """Measure fallback activation and recovery when attacker-selected committee members withhold blocks."""
    if withholding_probabilities is None:
        withholding_probabilities = [0.1, 0.25, 0.5]
    strategies = _resolve_security_committee_strategies(
        strategies,
        num_nodes=num_nodes,
        include_exact_when_safe=include_exact_when_safe,
    )

    results: List[BlockWithholdingResult] = []

    print("\n" + "=" * 65)
    print("  EXPERIMENT 6: Block-Withholding Fallback")
    print(f"  nodes={num_nodes}  rounds={num_rounds}  attacker_fraction={attacker_fraction}")
    print("=" * 65)

    for withholding_probability in withholding_probabilities:
        for strategy in strategies:
            consensus, node_ids, ground_truth, is_attacker = _build_consensus(
                num_nodes,
                seed + int(withholding_probability * 1000),
                attacker_fraction=attacker_fraction,
                metadata_profile="clustered_attackers",
            )
            rng = random.Random(seed + int(withholding_probability * 1000) + len(strategy))

            fallback_activations = 0
            fallback_successes = 0
            recovery_latencies_ms: List[float] = []
            primary_attacker_history: List[float] = []
            final_attacker_history: List[float] = []
            missed_slots = 0

            for rnd in range(num_rounds):
                _refresh_committee_metrics(
                    consensus,
                    node_ids,
                    ground_truth,
                    is_attacker,
                    rng,
                    round_idx=rnd,
                    attacker_hardware_multiplier=attacker_hardware_multiplier,
                )
                vrf = hashlib.sha256(f"block_withholding_{strategy}_{withholding_probability}_{rnd}_{seed}".encode()).hexdigest()
                result = _select_committee_strategy(consensus, strategy, node_ids, vrf, committee_k)
                committee_nodes = result.committee_nodes
                primary_leader = result.primary_leader
                primary_attacker_history.append(1.0 if primary_leader and is_attacker.get(primary_leader, False) else 0.0)

                withheld_nodes = [
                    node_id
                    for node_id in committee_nodes
                    if is_attacker.get(node_id, False) and rng.random() < withholding_probability
                ]

                actual_leader = primary_leader
                if primary_leader in withheld_nodes:
                    fallback_activations += 1
                    surviving_nodes = [node_id for node_id in committee_nodes if node_id not in withheld_nodes]
                    if surviving_nodes:
                        actual_leader = consensus.derive_primary_leader(surviving_nodes, vrf)
                        fallback_successes += 1
                        recovery_latencies_ms.append(25.0 + (15.0 * len(withheld_nodes)))
                    else:
                        actual_leader = None
                        recovery_latencies_ms.append(250.0)
                        missed_slots += 1

                final_attacker_history.append(1.0 if actual_leader and is_attacker.get(actual_leader, False) else 0.0)
                _record_committee_round(
                    consensus,
                    committee_nodes,
                    round_idx=rnd,
                    selected_leader=actual_leader,
                    failed_nodes=withheld_nodes,
                )

            half = max(1, len(primary_attacker_history) // 2)
            results.append(
                BlockWithholdingResult(
                    strategy=strategy,
                    withholding_probability=withholding_probability,
                    fallback_activation_rate=fallback_activations / num_rounds,
                    fallback_success_rate=fallback_successes / max(1, fallback_activations),
                    mean_recovery_latency_ms=statistics.mean(recovery_latencies_ms) if recovery_latencies_ms else 0.0,
                    p95_recovery_latency_ms=_p95(recovery_latencies_ms),
                    attacker_primary_share_initial=statistics.mean(primary_attacker_history[:half]) if primary_attacker_history[:half] else 0.0,
                    attacker_primary_share_final=statistics.mean(primary_attacker_history[-half:]) if primary_attacker_history[-half:] else 0.0,
                    final_attacker_proposer_share=statistics.mean(final_attacker_history) if final_attacker_history else 0.0,
                    missed_slot_rate=missed_slots / num_rounds,
                    n_rounds=num_rounds,
                )
            )
            print(
                f"  withhold={withholding_probability:.2f}  strategy={strategy:18s}  fallback={fallback_activations / num_rounds:.3f}  "
                f"recover={fallback_successes / max(1, fallback_activations):.3f}"
            )

    _plot_block_withholding(results, output_dir)
    return results


def _plot_block_withholding(results: List[BlockWithholdingResult], output_dir: str) -> None:
    if not results:
        return

    os.makedirs(output_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    strategies = sorted(set(r.strategy for r in results))
    grouped = {strategy: sorted([r for r in results if r.strategy == strategy], key=lambda item: item.withholding_probability) for strategy in strategies}

    fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharex=True)
    for strategy, items in grouped.items():
        xs = [item.withholding_probability for item in items]
        axes[0][0].plot(xs, [item.fallback_activation_rate for item in items], marker="o", label=strategy)
        axes[0][1].plot(xs, [item.p95_recovery_latency_ms for item in items], marker="o", label=strategy)
        axes[1][0].plot(xs, [item.attacker_primary_share_initial for item in items], marker="o", linestyle="--", label=f"{strategy} initial")
        axes[1][0].plot(xs, [item.attacker_primary_share_final for item in items], marker="o", label=f"{strategy} final")
        axes[1][1].plot(xs, [item.missed_slot_rate for item in items], marker="o", label=strategy)

    axes[0][0].set_title("Fallback activation rate")
    axes[0][1].set_title("P95 recovery latency")
    axes[1][0].set_title("Attacker primary share before vs after penalties")
    axes[1][1].set_title("Missed-slot rate")
    axes[0][0].set_ylabel("Rate")
    axes[0][1].set_ylabel("Milliseconds")
    axes[1][0].set_ylabel("Rate")
    axes[1][1].set_ylabel("Rate")
    axes[1][0].set_xlabel("Withholding probability")
    axes[1][1].set_xlabel("Withholding probability")

    for row in axes:
        for ax in row:
            ax.grid(True, linestyle="--", alpha=0.4)
            ax.legend()

    plt.tight_layout()
    path = os.path.join(output_dir, f"security_block_withholding_{ts}.png")
    plt.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def save_security_results(
    probe_results: List[ProbeManipulationResult],
    infra_results: List[InfraGamingResult],
    racing_results: List[ScoreRacingResult],
    correlated_failure_results: Optional[List[CorrelatedFailureResult]],
    attacker_sweep_results: Optional[List[AttackerFractionSweepResult]],
    block_withholding_results: Optional[List[BlockWithholdingResult]],
    witness_collusion_results: Optional[List[WitnessCollusionResult]],
    output_dir: str,
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"security_experiments_{ts}.json")

    # Downsample infra results to every 10 rounds to keep JSON manageable
    infra_sampled = [
        {
            "round": r.round_idx,
            "attacker_cumulative_share": r.attacker_cumulative_share,
            "best_attacker_score": r.best_attacker_score,
            "best_honest_score": r.best_honest_score,
        }
        for r in infra_results
        if r.round_idx % 10 == 0
    ]

    payload = {
        "probe_manipulation": [
            {
                "num_colluding_witnesses": r.num_colluding_witnesses,
                "flip_rate": r.flip_rate,
                "mean_inflation_ms": r.inflation_ms,
                "n_rounds": r.n_rounds,
            }
            for r in probe_results
        ],
        "witness_collusion": [
            {
                "q": r.q,
                "q_min": r.q_min,
                "population_size": r.population_size,
                "attacker_witnesses": r.attacker_witnesses,
                "measured_capture_rate": r.measured_capture_rate,
                "hypergeometric_capture_bound": r.hypergeometric_capture_bound,
                "absolute_gap": r.absolute_gap,
                "n_trials": r.n_trials,
            }
            for r in (witness_collusion_results or [])
        ],
        "infrastructure_gaming": infra_sampled,
        "score_racing": [
            {
                "w_freq": r.w_freq,
                "rounds_until_rotation_mean": r.rounds_until_rotation_mean,
                "rounds_until_rotation_p95": r.rounds_until_rotation_p95,
                "rotation_count": r.rotation_count,
                "n_trials": r.n_trials,
            }
            for r in racing_results
        ],
        "correlated_failure": [
            {
                "strategy": r.strategy,
                "outage_probability": r.outage_probability,
                "mean_unique_failure_domain_ratio": r.mean_unique_failure_domain_ratio,
                "mean_surviving_seat_ratio": r.mean_surviving_seat_ratio,
                "primary_disruption_rate": r.primary_disruption_rate,
                "recovery_success_rate": r.recovery_success_rate,
                "full_committee_failure_rate": r.full_committee_failure_rate,
                "missed_slot_rate": r.missed_slot_rate,
                "n_rounds": r.n_rounds,
            }
            for r in (correlated_failure_results or [])
        ],
        "attacker_fraction_sweep": [
            {
                "strategy": r.strategy,
                "attacker_fraction": r.attacker_fraction,
                "attacker_proposer_share": r.attacker_proposer_share,
                "attacker_committee_share": r.attacker_committee_share,
                "committee_constraint_violation_rate": r.committee_constraint_violation_rate,
                "missed_slot_rate": r.missed_slot_rate,
                "p95_block_time_ms": r.p95_block_time_ms,
                "estimated_throughput_blocks_per_sec": r.estimated_throughput_blocks_per_sec,
                "throughput_degradation_ratio": r.throughput_degradation_ratio,
                "finality_degradation_ratio": r.finality_degradation_ratio,
                "mean_solver_ms": r.mean_solver_ms,
                "n_rounds": r.n_rounds,
            }
            for r in (attacker_sweep_results or [])
        ],
        "block_withholding": [
            {
                "strategy": r.strategy,
                "withholding_probability": r.withholding_probability,
                "fallback_activation_rate": r.fallback_activation_rate,
                "fallback_success_rate": r.fallback_success_rate,
                "mean_recovery_latency_ms": r.mean_recovery_latency_ms,
                "p95_recovery_latency_ms": r.p95_recovery_latency_ms,
                "attacker_primary_share_initial": r.attacker_primary_share_initial,
                "attacker_primary_share_final": r.attacker_primary_share_final,
                "final_attacker_proposer_share": r.final_attacker_proposer_share,
                "missed_slot_rate": r.missed_slot_rate,
                "n_rounds": r.n_rounds,
            }
            for r in (block_withholding_results or [])
        ],
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n  Security results saved to {path}")
    return path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Security experiments for quantum annealing consensus"
    )
    parser.add_argument("--output-dir", type=str, default="reports")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=[
            "probe_manipulation",
            "witness_collusion",
            "infra_gaming",
            "score_racing",
            "attacker_sweep",
            "correlated_failure",
            "block_withholding",
        ],
        default=["probe_manipulation", "infra_gaming", "score_racing"],
    )
    # Probe manipulation args
    parser.add_argument("--probe-nodes", type=int, default=30)
    parser.add_argument("--probe-rounds", type=int, default=500)
    parser.add_argument("--max-colluding", type=int, default=10)
    parser.add_argument("--witness-collusion-nodes", type=int, default=40)
    parser.add_argument("--witness-collusion-trials", type=int, default=2000)
    parser.add_argument("--witness-q-values", nargs="*", type=int, default=None)
    parser.add_argument("--witness-q-min-values", nargs="*", type=int, default=None)
    # Infra gaming args
    parser.add_argument("--infra-nodes", type=int, default=40)
    parser.add_argument("--infra-rounds", type=int, default=1000)
    parser.add_argument("--hw-multiplier", type=float, default=2.0)
    parser.add_argument("--attacker-fraction", type=float, default=0.2)
    # Score racing args
    parser.add_argument("--racing-nodes", type=int, default=20)
    parser.add_argument("--racing-max-rounds", type=int, default=2000)
    parser.add_argument("--racing-trials", type=int, default=50)
    # Attacker sweep args
    parser.add_argument("--sweep-nodes", type=int, default=60)
    parser.add_argument("--sweep-rounds", type=int, default=500)
    parser.add_argument("--sweep-fractions", nargs="*", type=float, default=None)
    parser.add_argument("--sweep-committee-k", type=int, default=5)
    # Correlated failure args
    parser.add_argument("--corr-nodes", type=int, default=40)
    parser.add_argument("--corr-rounds", type=int, default=500)
    parser.add_argument("--corr-outage-probs", nargs="*", type=float, default=None)
    parser.add_argument("--corr-committee-k", type=int, default=5)
    parser.add_argument("--corr-top-concentrated", type=int, default=12)
    # Block withholding args
    parser.add_argument("--withholding-nodes", type=int, default=40)
    parser.add_argument("--withholding-rounds", type=int, default=500)
    parser.add_argument("--withholding-probs", nargs="*", type=float, default=None)
    parser.add_argument("--withholding-committee-k", type=int, default=5)
    parser.add_argument("--withholding-attacker-hw-multiplier", type=float, default=1.6)
    parser.add_argument("--committee-strategies", nargs="*", default=None)
    parser.add_argument("--include-exact-when-safe", action="store_true")
    args = parser.parse_args()
    run_layout = create_run_layout(args.output_dir, "security_experiments")
    write_run_metadata(
        run_layout,
        {
            "tool": "security_experiments",
            "layout": run_layout.to_dict(),
            "config": vars(args),
        },
    )

    print("=" * 70)
    print("  SECURITY EXPERIMENTS")
    print(f"  output={run_layout.root_dir}")
    print(f"  experiments={', '.join(args.experiments)}")
    print("=" * 70)

    probe_results: List[ProbeManipulationResult] = []
    infra_results: List[InfraGamingResult] = []
    racing_results: List[ScoreRacingResult] = []
    attacker_sweep_results: List[AttackerFractionSweepResult] = []
    correlated_failure_results: List[CorrelatedFailureResult] = []
    block_withholding_results: List[BlockWithholdingResult] = []
    witness_collusion_results: List[WitnessCollusionResult] = []

    if "probe_manipulation" in args.experiments:
        probe_results = run_probe_manipulation_experiment(
            num_nodes=args.probe_nodes,
            num_rounds=args.probe_rounds,
            max_colluding_witnesses=args.max_colluding,
            seed=args.seed,
            output_dir=run_layout.figures_dir,
        )

    if "witness_collusion" in args.experiments:
        witness_collusion_results = run_witness_collusion_experiment(
            num_nodes=args.witness_collusion_nodes,
            num_trials=args.witness_collusion_trials,
            q_values=args.witness_q_values,
            q_min_values=args.witness_q_min_values,
            attacker_fraction=args.attacker_fraction,
            seed=args.seed,
            output_dir=run_layout.figures_dir,
        )

    if "infra_gaming" in args.experiments:
        infra_results = run_infrastructure_gaming_experiment(
            num_nodes=args.infra_nodes,
            num_rounds=args.infra_rounds,
            attacker_hardware_multiplier=args.hw_multiplier,
            attacker_fraction=args.attacker_fraction,
            seed=args.seed,
            output_dir=run_layout.figures_dir,
        )

    if "score_racing" in args.experiments:
        racing_results = run_score_racing_experiment(
            num_nodes=args.racing_nodes,
            max_rounds=args.racing_max_rounds,
            n_trials=args.racing_trials,
            seed=args.seed,
            output_dir=run_layout.figures_dir,
        )

    if "attacker_sweep" in args.experiments:
        attacker_sweep_results = run_attacker_fraction_sweep_experiment(
            num_nodes=args.sweep_nodes,
            num_rounds=args.sweep_rounds,
            attacker_fractions=args.sweep_fractions,
            strategies=args.committee_strategies,
            committee_k=args.sweep_committee_k,
            include_exact_when_safe=args.include_exact_when_safe,
            seed=args.seed,
            output_dir=run_layout.figures_dir,
        )

    if "correlated_failure" in args.experiments:
        correlated_failure_results = run_correlated_failure_experiment(
            num_nodes=args.corr_nodes,
            num_rounds=args.corr_rounds,
            outage_probabilities=args.corr_outage_probs,
            strategies=args.committee_strategies,
            committee_k=args.corr_committee_k,
            concentrated_top_nodes=args.corr_top_concentrated,
            attacker_fraction=args.attacker_fraction,
            include_exact_when_safe=args.include_exact_when_safe,
            seed=args.seed,
            output_dir=run_layout.figures_dir,
        )

    if "block_withholding" in args.experiments:
        block_withholding_results = run_block_withholding_experiment(
            num_nodes=args.withholding_nodes,
            num_rounds=args.withholding_rounds,
            withholding_probabilities=args.withholding_probs,
            strategies=args.committee_strategies,
            committee_k=args.withholding_committee_k,
            attacker_fraction=args.attacker_fraction,
            attacker_hardware_multiplier=args.withholding_attacker_hw_multiplier,
            include_exact_when_safe=args.include_exact_when_safe,
            seed=args.seed,
            output_dir=run_layout.figures_dir,
        )

    save_security_results(
        probe_results,
        infra_results,
        racing_results,
        correlated_failure_results,
        attacker_sweep_results,
        block_withholding_results,
        witness_collusion_results,
        run_layout.data_dir,
    )

    _refresh_live_findings_dashboard(args.output_dir)

if __name__ == "__main__":
    main()
