#!/usr/bin/env python3
"""Evaluation Overhaul
====================

Rebuilt evaluation harness for quantum annealing consensus.

Scale
-----
- 100–1000 nodes (at least one experiment at ≥ 1 000 nodes)
- 1 000+ consensus rounds minimum
- Emulated network with lognormal delay distributions
- Configurable measurement noise and churn

Baselines (9 total)
-------------------
quantum          – full QuantumAnnealingConsensus (paper model)
exact_argmax     – direct argmax of suitability scores (no solver)
exact_ilp        – OR-Tools CP-SAT (solution-quality upper bound)
vrf_weighted     – VRF-weighted random selection (current PoS best practice)
hotstuff_rr      – HotStuff-style BFT with round-robin leader rotation
greedy_score     – always pick highest single-metric (uptime) node
weighted_score   – random selection weighted by suitability scores
round_robin      – rotating proposer among active nodes
pos_stake        – PoS-style lottery weighted by synthetic stake
pow_hash         – PoW-style lottery weighted by synthetic hash power

Ablations (15 experiments)
---------------------------
See run_ablations() docstring for the full list.

New metrics
-----------
- Gini coefficient of proposer selection
- Score-to-selection Spearman correlation
- Agreement rate (5 virtual independent nodes)
- Adversarial inflation success rate (from security module)
- Per-strategy Solver time
"""

import hashlib
import hmac
import json
import math
import os
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from contextlib import redirect_stdout as _redirect_stdout
from dataclasses import dataclass, field, replace
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
from tools.visualize_findings import generate_findings_bundle

# Optional OR-Tools for ILP baseline
try:
    from ortools.sat.python import cp_model as _cp_model  # type: ignore
    _ORTOOLS_AVAILABLE = True
except ImportError:
    _ORTOOLS_AVAILABLE = False


def _refresh_live_findings_dashboard(output_dir: str) -> None:
    try:
        result = generate_findings_bundle(search_root=output_dir, output_dir=output_dir)
        print(f"  live findings dashboard refreshed: {result['live_dashboard_path']}")
    except Exception as exc:
        print(f"  warning: could not refresh live findings dashboard: {exc}")


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SimulationConfig:
    num_nodes: int = 100
    num_rounds: int = 1000
    attacker_fraction: float = 0.20
    top_k_for_error: int = 3
    seed: int = 42
    output_dir: str = "reports"
    # Network emulation
    network_delay_model: str = "lognormal"   # "lognormal" | "uniform" | "none"
    network_delay_mean_ms: float = 50.0      # mean RTT in ms
    network_delay_sigma: float = 0.5         # lognormal sigma (log-scale)
    # Churn
    churn_rate: float = 0.0                  # fraction of nodes replaced per round
    # Measurement noise
    measurement_noise: float = 0.0           # multiplicative ±noise fraction
    # QUBO candidate cap
    max_candidate_nodes: int = 100
    # Committee-selection rollout parameters
    committee_k: int = 5
    primary_leader_policy: str = "highest_score"
    metadata_profile: str = "synthetic_static"
    metadata_manifest: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    exact_oracle_max_candidates: int = 16
    solver_study_candidate_sizes: List[int] = field(default_factory=lambda: [6, 8, 10, 12, 14, 16])
    solver_study_seed_count: int = 5


@dataclass
class StrategyMetrics:
    name: str
    pqi_mean: float
    pqi_p95: float
    missed_slot_rate: float
    p95_block_time_ms: float
    nakamoto_coefficient: int
    attacker_share: float
    selection_error_rate: float
    gini_coefficient: float
    selection_entropy: float
    selection_concentration: float
    score_selection_spearman: float
    agreement_rate: float
    mean_solver_ms: float
    view_change_rate: float = 0.0  # HotStuff only
    committee_size: int = 1
    committee_constraint_violation_rate: float = 0.0
    committee_mean_unique_failure_domain_ratio: float = 0.0
    committee_attacker_seat_share: float = 0.0
    committee_fallback_rate: float = 0.0
    committee_objective_mean: float = 0.0
    committee_raw_objective_mean: float = 0.0
    committee_candidate_count_mean: float = 0.0
    proposer_share_trace: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SolverComparisonMetrics:
    candidate_count: int
    committee_k: int
    n_trials: int
    exact_objective_mean: float
    quantum_objective_mean: float
    greedy_objective_mean: float
    weighted_objective_mean: float
    quantum_optimality_gap_mean: float
    greedy_optimality_gap_mean: float
    weighted_optimality_gap_mean: float
    quantum_disagreement_rate: float
    greedy_disagreement_rate: float
    weighted_disagreement_rate: float
    quantum_solver_ms_mean: float
    exact_solver_ms_mean: float
    greedy_solver_ms_mean: float
    weighted_solver_ms_mean: float


@dataclass
class MeasurementOverheadMetrics:
    strategy: str
    num_nodes: int
    num_rounds: int
    window_rounds: int
    num_windows: int
    mean_active_nodes: float
    probe_messages_per_window: float
    probe_bytes_per_window: float
    score_construction_cpu_ms: float
    optimization_latency_ms: float
    end_to_end_selection_ms: float


@dataclass
class CommitteeAblationDefinition:
    strategy: str
    ablation_config: Optional[AblationConfig]
    cfg_overrides: Dict[str, Any] = field(default_factory=dict)
    label: str = ""


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _percentile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    qs = statistics.quantiles(values, n=100, method="inclusive")
    k = max(1, min(99, int(round(q))))
    return qs[k - 1]


def _compute_nakamoto_coefficient(selection_counts: Counter) -> int:
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


def _compute_gini(selection_counts: Counter, num_nodes: int) -> float:
    """Gini coefficient over proposer selection frequency distribution."""
    counts = [selection_counts.get(f"node_{i}", 0) for i in range(num_nodes)]
    n = len(counts)
    if n == 0 or sum(counts) == 0:
        return 0.0
    sorted_counts = sorted(counts)
    total = sum(sorted_counts)
    cumulative = 0.0
    weighted_sum = 0.0
    for i, c in enumerate(sorted_counts, start=1):
        cumulative += c
        weighted_sum += cumulative
    # Gini = (2 * sum(i * x_i)) / (n * sum(x_i)) - (n+1)/n
    gini = (2.0 * weighted_sum) / (n * total) - (n + 1.0) / n
    return max(0.0, min(1.0, gini))


def _compute_selection_entropy(selection_counts: Counter, num_nodes: int) -> float:
    """Normalized Shannon entropy over proposer selection shares."""
    counts = [selection_counts.get(f"node_{i}", 0) for i in range(num_nodes)]
    total = sum(counts)
    if num_nodes <= 1 or total == 0:
        return 0.0

    probabilities = [count / total for count in counts if count > 0]
    entropy = -sum(probability * math.log(probability) for probability in probabilities)
    normalized = entropy / math.log(num_nodes)
    return max(0.0, min(1.0, normalized))


def _compute_selection_concentration(selection_counts: Counter, num_nodes: int) -> float:
    """Largest proposer share observed so far."""
    counts = [selection_counts.get(f"node_{i}", 0) for i in range(num_nodes)]
    total = sum(counts)
    if total == 0:
        return 0.0
    return max(counts) / total


def _spearman_correlation(xs: List[float], ys: List[float]) -> float:
    """Spearman rank correlation without scipy."""
    n = len(xs)
    if n < 2:
        return 0.0

    def _rank(vals: List[float]) -> List[float]:
        indexed = sorted(range(n), key=lambda i: vals[i])
        ranks = [0.0] * n
        for rank, idx in enumerate(indexed, start=1):
            ranks[idx] = float(rank)
        return ranks

    rx = _rank(xs)
    ry = _rank(ys)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    num = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    den_x = math.sqrt(sum((rx[i] - mean_rx) ** 2 for i in range(n)))
    den_y = math.sqrt(sum((ry[i] - mean_ry) ** 2 for i in range(n)))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


# ---------------------------------------------------------------------------
# Network emulator
# ---------------------------------------------------------------------------

class NetworkSimulator:
    """Per-link latency sampler using a lognormal (or uniform) distribution."""

    def __init__(self, model: str = "lognormal", mean_ms: float = 50.0, sigma: float = 0.5, seed: int = 0):
        self._model = model
        self._rng = random.Random(seed)
        if model == "lognormal":
            # lognormal parameterised so that the median ≈ mean_ms ms
            # median of LogN(mu, sigma) = exp(mu)  →  mu = ln(mean_ms/1000)
            self._mu = math.log(max(1.0, mean_ms) / 1000.0)
            self._sigma = sigma
        elif model == "uniform":
            self._lo = max(1.0, mean_ms * 0.5) / 1000.0
            self._hi = max(1.0, mean_ms * 1.5) / 1000.0
        # "none" → 0 ms

    def sample_latency(self, _src: str = "", _dst: str = "") -> float:
        """Return a sampled one-way latency in seconds."""
        if self._model == "lognormal":
            val = self._rng.lognormvariate(self._mu, self._sigma)
            return max(0.001, min(val, 2.0))
        elif self._model == "uniform":
            return self._rng.uniform(self._lo, self._hi)
        return 0.0


# ---------------------------------------------------------------------------
# Simulation environment builder
# ---------------------------------------------------------------------------

def _synthesise_node_metadata(
    cfg: SimulationConfig,
    node_id: str,
    node_index: int,
    attacker: bool,
) -> Dict[str, Any]:
    """Return deterministic infrastructure metadata for committee-constraint experiments."""
    if node_id in cfg.metadata_manifest:
        return dict(cfg.metadata_manifest[node_id])

    providers = ["aws", "gcp", "azure", "self_hosted"]
    regions = ["us-west-2", "us-east-1", "eu-central-1", "ap-south-1"]
    countries = ["US", "US", "DE", "IN"]
    datacenter_codes = ["pdx1", "iad1", "fra1", "bom1"]

    provider_idx = node_index % len(providers)
    region_idx = (node_index // len(providers)) % len(regions)

    if cfg.metadata_profile == "clustered_attackers" and attacker:
        provider_idx = 0
        region_idx = 1

    metadata = {
        "asn": 64512 + (provider_idx * 100) + region_idx,
        "cloud_provider": providers[provider_idx],
        "region": regions[region_idx],
        "datacenter": datacenter_codes[region_idx],
        "country_code": countries[region_idx],
        "operator_id": f"{'attacker' if attacker else 'operator'}_{node_index % 8}",
        "failure_domain": f"{providers[provider_idx]}:{regions[region_idx]}",
        "metadata_source": "synthetic_manifest",
    }
    cfg.metadata_manifest[node_id] = metadata
    return dict(metadata)

def _build_simulation_environment(
    cfg: SimulationConfig,
    ablation_cfg: Optional[AblationConfig] = None,
):
    """
    Initialise QuantumAnnealingConsensus and synthetic per-node attributes.

    Returns:
        (consensus, node_ids, ground_truth, stake, hash_power, online_prob, is_attacker)
    """
    random.seed(cfg.seed)

    consensus = QuantumAnnealingConsensus(
        initialize_genesis=False,
        verbose=False,
        ablation_config=ablation_cfg,
    )
    consensus.max_candidate_nodes = cfg.max_candidate_nodes

    ground_truth: Dict[str, float] = {}
    stake: Dict[str, float] = {}
    hash_power: Dict[str, float] = {}
    online_prob: Dict[str, float] = {}
    is_attacker: Dict[str, bool] = {}
    node_ids: List[str] = []

    num_attackers = max(1, int(cfg.num_nodes * cfg.attacker_fraction))
    attacker_ids = {f"node_{i}" for i in range(num_attackers)}

    for i in range(cfg.num_nodes):
        node_id = f"node_{i}"
        node_ids.append(node_id)

        attacker = node_id in attacker_ids
        base_cap = random.uniform(0.3, 1.0)
        capability = (
            max(0.1, base_cap - random.uniform(0.2, 0.5))
            if attacker
            else min(1.0, base_cap + random.uniform(0.0, 0.2))
        )

        ground_truth[node_id] = capability
        is_attacker[node_id] = attacker
        stake[node_id] = max(0.1, capability * random.uniform(5.0, 15.0))
        hash_power[node_id] = max(0.1, capability * random.uniform(8.0, 20.0))
        online_prob[node_id] = min(0.98, 0.6 + 0.4 * capability)

        public_key, _ = consensus.ensure_node_keys(node_id)
        consensus.register_node(
            node_id,
            public_key,
            metadata=_synthesise_node_metadata(cfg, node_id, i, attacker),
        )
        consensus.nodes[node_id]["stake_weight"] = stake[node_id]
        consensus.nodes[node_id]["hash_power_weight"] = hash_power[node_id]

    return consensus, node_ids, ground_truth, stake, hash_power, online_prob, is_attacker


def _update_round_metrics(
    consensus: QuantumAnnealingConsensus,
    node_ids: List[str],
    ground_truth: Dict[str, float],
    online_prob: Dict[str, float],
    net_sim: NetworkSimulator,
    cfg: SimulationConfig,
) -> Dict[str, bool]:
    """
    Sample online/offline state and update consensus node metrics for this round.

    Applies network-simulated latency and configurable measurement noise.
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
            node_data["last_seen"] = now
            cap = ground_truth[node_id]

            # Network-emulated latency
            sampled_latency = net_sim.sample_latency(node_id, "leader")
            base_latency = max(0.001, sampled_latency)

            # Capability-based throughput
            base_tps = 5.0 + 45.0 * cap

            # Apply measurement noise
            if cfg.measurement_noise > 0.0:
                noise_l = 1.0 + random.uniform(-cfg.measurement_noise, cfg.measurement_noise)
                noise_t = 1.0 + random.uniform(-cfg.measurement_noise, cfg.measurement_noise)
                base_latency = max(0.001, base_latency * noise_l)
                base_tps = max(0.1, base_tps * noise_t)

            node_data["latency"] = base_latency
            node_data["throughput"] = base_tps
            consensus.append_committee_observation(
                node_id,
                uptime_sample=1,
                latency_sample=base_latency,
                throughput_sample=base_tps,
                anchor_id="leader",
            )
        else:
            node_data["last_seen"] = now - (consensus.node_active_threshold + 10)
            consensus.append_committee_observation(node_id, uptime_sample=0)

    consensus.node_performance_cache.clear()
    return online_state


def _apply_churn(
    consensus: QuantumAnnealingConsensus,
    node_ids: List[str],
    ground_truth: Dict[str, float],
    online_prob: Dict[str, float],
    stake: Dict[str, float],
    hash_power: Dict[str, float],
    is_attacker: Dict[str, bool],
    cfg: SimulationConfig,
    rng_seed: int,
) -> None:
    """Replace a fraction of nodes with freshly registered ones."""
    if cfg.churn_rate <= 0.0:
        return
    rng = random.Random(rng_seed)
    n_churn = max(1, int(cfg.churn_rate * len(node_ids)))
    leave_indices = rng.sample(range(len(node_ids)), min(n_churn, len(node_ids)))

    for idx in leave_indices:
        old_id = node_ids[idx]
        new_id = f"{old_id}_r{rng_seed}"

        # Remove old node from consensus state
        consensus.nodes.pop(old_id, None)
        if old_id in consensus.node_keys:
            del consensus.node_keys[old_id]

        # Register fresh node
        cap = rng.uniform(0.3, 1.0)
        ground_truth[new_id] = cap
        online_prob[new_id] = min(0.98, 0.6 + 0.4 * cap)
        stake[new_id] = max(0.1, cap * rng.uniform(5.0, 15.0))
        hash_power[new_id] = max(0.1, cap * rng.uniform(8.0, 20.0))
        is_attacker[new_id] = False

        pub_key, _ = consensus.ensure_node_keys(new_id)
        consensus.register_node(
            new_id,
            pub_key,
            metadata=_synthesise_node_metadata(cfg, new_id, idx + rng_seed, False),
        )

        node_ids[idx] = new_id


def _evaluate_committee_round(
    consensus: QuantumAnnealingConsensus,
    committee_nodes: List[str],
    is_attacker: Dict[str, bool],
) -> Dict[str, float]:
    """Compute committee-level security and diversity signals for one round."""
    if not committee_nodes:
        return {
            'has_constraint_violation': 1.0,
            'unique_failure_domain_ratio': 0.0,
            'attacker_seat_share': 0.0,
        }

    metadata = [
        consensus.nodes.get(node_id, {}).get('committee_metadata', {})
        for node_id in committee_nodes
    ]
    unique_failure_domains = {
        entry.get('failure_domain', 'unknown')
        for entry in metadata
    }

    has_conflict = 0.0
    for i in range(len(metadata)):
        for j in range(i + 1, len(metadata)):
            if metadata[i].get('asn') == metadata[j].get('asn'):
                has_conflict = 1.0
                break
        if has_conflict:
            break

    attacker_seat_share = sum(1 for node_id in committee_nodes if is_attacker.get(node_id, False)) / len(committee_nodes)
    return {
        'has_constraint_violation': has_conflict,
        'unique_failure_domain_ratio': len(unique_failure_domains) / len(committee_nodes),
        'attacker_seat_share': attacker_seat_share,
    }


def _record_simulation_selection_feedback(
    consensus: QuantumAnnealingConsensus,
    *,
    selected: Optional[str],
    committee_nodes: Optional[List[str]] = None,
) -> None:
    """Feed simulated selections back into consensus state for dynamic baselines."""
    for node_id in committee_nodes or []:
        node_state = consensus.nodes.get(node_id)
        if not node_state:
            continue
        node_state["committee_selection_count"] = node_state.get("committee_selection_count", 0) + 1

    if selected and selected in consensus.nodes:
        consensus.nodes[selected]["proposal_success_count"] = (
            consensus.nodes[selected].get("proposal_success_count", 0) + 1
        )
        consensus.record_leader_selection(len(consensus.selection_history), selected)

    consensus.node_performance_cache.clear()
    consensus.committee_feature_cache.clear()


# ---------------------------------------------------------------------------
# Baseline selector functions
# ---------------------------------------------------------------------------

def _select_quantum(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
) -> Tuple[Optional[str], float]:
    """Full quantum QUBO pipeline over candidate_nodes. Returns (node_id, solver_ms)."""
    import io
    t0 = time.perf_counter()
    if not candidate_nodes:
        return None, 0.0

    _null = io.StringIO()
    with _redirect_stdout(_null):
        linear, quadratic, _ = consensus.formulate_qubo_problem(vrf_output, candidate_nodes)
        solution = consensus.simulate_quantum_annealer(linear, quadratic, candidate_nodes)

    selected = None
    for i, val in enumerate(solution):
        if val == 1 and i < len(candidate_nodes):
            selected = candidate_nodes[i]
            break
    if selected is None and candidate_nodes:
        selected = candidate_nodes[0]

    return selected, (time.perf_counter() - t0) * 1000.0


def _select_committee_quantum(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
    committee_k: int,
    primary_leader_policy: str,
):
    """Committee QUBO strategy returning a structured committee result."""
    import io

    t0 = time.perf_counter()
    if not candidate_nodes:
        return consensus.select_committee(vrf_output, candidate_nodes=[], committee_k=committee_k)

    _null = io.StringIO()
    with _redirect_stdout(_null):
        result = consensus.select_committee(
            vrf_output,
            candidate_nodes=candidate_nodes,
            committee_k=committee_k,
            primary_leader_policy=primary_leader_policy,
        )

    # Preserve the wall-clock harness timing rather than the inner solver-only timing.
    result.solver_time_ms = (time.perf_counter() - t0) * 1000.0
    return result


def _serialize_pairwise_features(
    candidate_nodes: List[str],
    pairwise_features: Dict[Tuple[int, int], Dict[str, float]],
) -> Dict[str, Dict[str, float]]:
    """Convert indexed pairwise bundles into a JSON-friendly mapping."""
    serializable_pairwise = {}
    for (i, j), feature_bundle in pairwise_features.items():
        serializable_pairwise[f"{candidate_nodes[i]}::{candidate_nodes[j]}"] = feature_bundle
    return serializable_pairwise


def _build_committee_result(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    committee_nodes: List[str],
    vrf_output: str,
    committee_k: int,
    primary_leader_policy: str,
    *,
    solver_time_ms: float,
    used_fallback: bool,
    raw_committee_nodes: Optional[List[str]] = None,
    fallback_reason: Optional[str] = None,
    selection_scores: Optional[Dict[str, float]] = None,
    primary_leader: Optional[str] = None,
) -> CommitteeSelectionResult:
    """Build a structured committee result for non-QUBO baselines using the shared objective."""
    (
        _,
        _,
        _,
        effective_scores,
        pairwise_features,
    ) = consensus.formulate_committee_qubo_problem(
        vrf_output,
        candidate_nodes,
        committee_k=committee_k,
    )
    selected_scores = selection_scores or {
        node_id: effective_scores[node_id]
        for node_id in committee_nodes
    }
    if primary_leader is None:
        primary_leader = consensus.derive_primary_leader(
            committee_nodes,
            vrf_output,
            effective_scores=selected_scores,
            policy=primary_leader_policy,
        )

    raw_nodes = list(raw_committee_nodes) if raw_committee_nodes is not None else list(committee_nodes)
    objective_breakdown = consensus.evaluate_committee_selection(
        vrf_output,
        committee_nodes,
        candidate_nodes=candidate_nodes,
        committee_k=committee_k,
        effective_scores=effective_scores,
        pairwise_features=pairwise_features,
    )
    raw_objective_breakdown = consensus.evaluate_committee_selection(
        vrf_output,
        raw_nodes,
        candidate_nodes=candidate_nodes,
        committee_k=committee_k,
        effective_scores=effective_scores,
        pairwise_features=pairwise_features,
    )

    return CommitteeSelectionResult(
        committee_nodes=list(committee_nodes),
        primary_leader=primary_leader,
        effective_scores={node_id: selected_scores.get(node_id, 0.0) for node_id in committee_nodes},
        pairwise_features=_serialize_pairwise_features(candidate_nodes, pairwise_features),
        solver_time_ms=solver_time_ms,
        used_fallback=used_fallback,
        candidate_count=len(candidate_nodes),
        raw_committee_nodes=raw_nodes,
        objective_value=objective_breakdown['total_objective'],
        raw_objective_value=raw_objective_breakdown['total_objective'],
        objective_breakdown=objective_breakdown,
        raw_objective_breakdown=raw_objective_breakdown,
        fallback_reason=fallback_reason,
    )


def _select_committee_greedy(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
    committee_k: int,
    primary_leader_policy: str,
):
    """Greedy score-only top-k committee baseline."""
    t0 = time.perf_counter()
    (
        _,
        _,
        _,
        effective_scores,
        _,
    ) = consensus.formulate_committee_qubo_problem(
        vrf_output,
        candidate_nodes,
        committee_k=committee_k,
    )
    committee_nodes = sorted(
        candidate_nodes,
        key=lambda node_id: (effective_scores[node_id], node_id),
        reverse=True,
    )[:max(1, min(committee_k, len(candidate_nodes)))]
    return _build_committee_result(
        consensus,
        candidate_nodes,
        committee_nodes,
        vrf_output,
        committee_k,
        primary_leader_policy,
        solver_time_ms=(time.perf_counter() - t0) * 1000.0,
        used_fallback=False,
        selection_scores=effective_scores,
    )


def _select_committee_weighted(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
    committee_k: int,
    primary_leader_policy: str,
) -> CommitteeSelectionResult:
    """Weighted committee baseline using suitability scores without exact optimization."""
    t0 = time.perf_counter()
    (
        _,
        _,
        _,
        effective_scores,
        _,
    ) = consensus.formulate_committee_qubo_problem(
        vrf_output,
        candidate_nodes,
        committee_k=committee_k,
    )

    rng = random.Random(vrf_output)
    remaining_nodes = list(candidate_nodes)
    committee_nodes: List[str] = []
    target_size = max(1, min(committee_k, len(remaining_nodes)))

    while remaining_nodes and len(committee_nodes) < target_size:
        weights = [max(0.001, effective_scores[node_id]) for node_id in remaining_nodes]
        total_weight = sum(weights)
        draw = rng.random() * total_weight
        cumulative = 0.0
        selected_node = remaining_nodes[-1]
        for index, weight in enumerate(weights):
            cumulative += weight
            if draw <= cumulative:
                selected_node = remaining_nodes[index]
                break
        committee_nodes.append(selected_node)
        remaining_nodes.remove(selected_node)

    return _build_committee_result(
        consensus,
        candidate_nodes,
        committee_nodes,
        vrf_output,
        committee_k,
        primary_leader_policy,
        solver_time_ms=(time.perf_counter() - t0) * 1000.0,
        used_fallback=False,
        selection_scores=effective_scores,
    )


def _select_committee_exact(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
    committee_k: int,
    primary_leader_policy: str,
    max_exact_candidates: int,
) -> CommitteeSelectionResult:
    """Small-candidate exact committee oracle baseline."""
    import io

    t0 = time.perf_counter()
    _null = io.StringIO()
    with _redirect_stdout(_null):
        result = consensus.select_committee_exact(
            vrf_output,
            candidate_nodes=candidate_nodes,
            committee_k=committee_k,
            primary_leader_policy=primary_leader_policy,
            max_exact_candidates=max_exact_candidates,
        )

    result.solver_time_ms = (time.perf_counter() - t0) * 1000.0
    return result


def _normalize_positive(value: float, min_val: float, max_val: float) -> float:
    if max_val == min_val:
        return 1.0
    return (value - min_val) / (max_val - min_val)


def _normalize_negative(value: float, min_val: float, max_val: float) -> float:
    if max_val == min_val:
        return 1.0
    return (max_val - value) / (max_val - min_val)


def _build_candidate_metric_view(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
) -> Dict[str, Dict[str, float]]:
    """Return normalized candidate metrics for baseline selectors."""
    if not candidate_nodes:
        return {}

    uptimes = {node_id: consensus.calculate_uptime(node_id) for node_id in candidate_nodes}
    throughputs = {
        node_id: consensus.nodes.get(node_id, {}).get("throughput", 0.0)
        for node_id in candidate_nodes
    }
    past_performance = {
        node_id: (
            consensus.nodes.get(node_id, {}).get("proposal_success_count", 0)
            - 2 * consensus.nodes.get(node_id, {}).get("proposal_failure_count", 0)
        )
        for node_id in candidate_nodes
    }

    valid_latencies = [
        consensus.nodes.get(node_id, {}).get("latency", float("inf"))
        for node_id in candidate_nodes
        if consensus.nodes.get(node_id, {}).get("latency", float("inf")) != float("inf")
    ]
    fallback_latency = max(valid_latencies) if valid_latencies else 1.0
    latencies = {
        node_id: (
            consensus.nodes.get(node_id, {}).get("latency", float("inf"))
            if consensus.nodes.get(node_id, {}).get("latency", float("inf")) != float("inf")
            else fallback_latency
        )
        for node_id in candidate_nodes
    }

    min_uptime, max_uptime = min(uptimes.values()), max(uptimes.values())
    min_latency, max_latency = min(latencies.values()), max(latencies.values())
    min_throughput, max_throughput = min(throughputs.values()), max(throughputs.values())
    min_past, max_past = min(past_performance.values()), max(past_performance.values())

    return {
        node_id: {
            "uptime": _normalize_positive(uptimes[node_id], min_uptime, max_uptime),
            "latency": _normalize_negative(latencies[node_id], min_latency, max_latency),
            "throughput": _normalize_positive(
                throughputs[node_id],
                min_throughput,
                max_throughput,
            ),
            "past_performance": _normalize_positive(
                past_performance[node_id],
                min_past,
                max_past,
            ),
            "selection_frequency": consensus.calculate_selection_frequency(node_id),
            "stake_weight": consensus.nodes.get(node_id, {}).get("stake_weight", 1.0),
        }
        for node_id in candidate_nodes
    }


def _history_only_scores(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
) -> Dict[str, float]:
    metric_view = _build_candidate_metric_view(consensus, candidate_nodes)
    return {
        node_id: 0.65 * metrics["past_performance"] + 0.35 * metrics["uptime"]
        for node_id, metrics in metric_view.items()
    }


def _composite_committee_scores(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
) -> Dict[str, float]:
    metric_view = _build_candidate_metric_view(consensus, candidate_nodes)
    return {
        node_id: 0.25 * (
            metrics["uptime"]
            + metrics["latency"]
            + metrics["throughput"]
            + metrics["past_performance"]
        )
        for node_id, metrics in metric_view.items()
    }


def _fairness_only_scores(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
) -> Dict[str, float]:
    metric_view = _build_candidate_metric_view(consensus, candidate_nodes)
    return {
        node_id: max(0.0, 1.0 - metrics["selection_frequency"])
        for node_id, metrics in metric_view.items()
    }


def _vrf_stake_scores(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for node_id in candidate_nodes:
        vrf_bytes = hmac.new(vrf_output.encode(), node_id.encode(), hashlib.sha256).digest()
        vrf_score = int.from_bytes(vrf_bytes[:4], "big") / 0xFFFF_FFFF
        stake_weight = consensus.nodes.get(node_id, {}).get("stake_weight", 1.0)
        scores[node_id] = max(0.001, stake_weight * vrf_score)
    return scores


def _weighted_sample_without_replacement(
    items: List[str],
    score_lookup: Dict[str, float],
    target_size: int,
    rng: random.Random,
) -> List[str]:
    remaining_items = list(items)
    selected_items: List[str] = []

    while remaining_items and len(selected_items) < target_size:
        weights = [max(0.001, score_lookup.get(item, 0.0)) for item in remaining_items]
        total_weight = sum(weights)
        draw = rng.random() * total_weight
        cumulative = 0.0
        selected_item = remaining_items[-1]
        for index, weight in enumerate(weights):
            cumulative += weight
            if draw <= cumulative:
                selected_item = remaining_items[index]
                break
        selected_items.append(selected_item)
        remaining_items.remove(selected_item)

    return selected_items


def _select_committee_uniform(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
    committee_k: int,
    primary_leader_policy: str,
) -> CommitteeSelectionResult:
    """Uniform exact-k committee lottery."""
    t0 = time.perf_counter()
    if not candidate_nodes:
        return _build_committee_result(
            consensus,
            candidate_nodes,
            [],
            vrf_output,
            committee_k,
            primary_leader_policy,
            solver_time_ms=(time.perf_counter() - t0) * 1000.0,
            used_fallback=False,
        )

    target_size = max(1, min(committee_k, len(candidate_nodes)))
    rng = random.Random(vrf_output)
    committee_nodes = rng.sample(sorted(candidate_nodes), target_size)
    primary_leader = min(
        committee_nodes,
        key=lambda node_id: hashlib.sha256(f"{vrf_output}:{node_id}".encode()).hexdigest(),
    )
    return _build_committee_result(
        consensus,
        candidate_nodes,
        committee_nodes,
        vrf_output,
        committee_k,
        primary_leader_policy,
        solver_time_ms=(time.perf_counter() - t0) * 1000.0,
        used_fallback=False,
        selection_scores={node_id: 1.0 for node_id in committee_nodes},
        primary_leader=primary_leader,
    )


def _select_committee_vrf_stake(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
    committee_k: int,
    primary_leader_policy: str,
) -> CommitteeSelectionResult:
    """Stake-weighted VRF committee sortition baseline."""
    t0 = time.perf_counter()
    target_size = max(1, min(committee_k, len(candidate_nodes)))
    score_lookup = _vrf_stake_scores(consensus, candidate_nodes, vrf_output)
    committee_nodes = _weighted_sample_without_replacement(
        candidate_nodes,
        score_lookup,
        target_size,
        random.Random(vrf_output),
    )
    return _build_committee_result(
        consensus,
        candidate_nodes,
        committee_nodes,
        vrf_output,
        committee_k,
        primary_leader_policy,
        solver_time_ms=(time.perf_counter() - t0) * 1000.0,
        used_fallback=False,
        selection_scores=score_lookup,
    )


def _select_committee_reputation(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
    committee_k: int,
    primary_leader_policy: str,
) -> CommitteeSelectionResult:
    """History-dominant reputation committee baseline."""
    t0 = time.perf_counter()
    score_lookup = _history_only_scores(consensus, candidate_nodes)
    committee_nodes = sorted(
        candidate_nodes,
        key=lambda node_id: (score_lookup.get(node_id, 0.0), node_id),
        reverse=True,
    )[:max(1, min(committee_k, len(candidate_nodes)))]
    return _build_committee_result(
        consensus,
        candidate_nodes,
        committee_nodes,
        vrf_output,
        committee_k,
        primary_leader_policy,
        solver_time_ms=(time.perf_counter() - t0) * 1000.0,
        used_fallback=False,
        selection_scores=score_lookup,
    )


def _select_committee_composite_greedy(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
    committee_k: int,
    primary_leader_policy: str,
) -> CommitteeSelectionResult:
    """Multi-factor greedy committee baseline with no pairwise optimization."""
    t0 = time.perf_counter()
    score_lookup = _composite_committee_scores(consensus, candidate_nodes)
    committee_nodes = sorted(
        candidate_nodes,
        key=lambda node_id: (score_lookup.get(node_id, 0.0), node_id),
        reverse=True,
    )[:max(1, min(committee_k, len(candidate_nodes)))]
    return _build_committee_result(
        consensus,
        candidate_nodes,
        committee_nodes,
        vrf_output,
        committee_k,
        primary_leader_policy,
        solver_time_ms=(time.perf_counter() - t0) * 1000.0,
        used_fallback=False,
        selection_scores=score_lookup,
    )


def _select_committee_fairness_only(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
    committee_k: int,
    primary_leader_policy: str,
) -> CommitteeSelectionResult:
    """Anti-concentration-only committee baseline."""
    t0 = time.perf_counter()
    score_lookup = _fairness_only_scores(consensus, candidate_nodes)
    committee_nodes = sorted(
        candidate_nodes,
        key=lambda node_id: (score_lookup.get(node_id, 0.0), node_id),
        reverse=True,
    )[:max(1, min(committee_k, len(candidate_nodes)))]
    return _build_committee_result(
        consensus,
        candidate_nodes,
        committee_nodes,
        vrf_output,
        committee_k,
        primary_leader_policy,
        solver_time_ms=(time.perf_counter() - t0) * 1000.0,
        used_fallback=False,
        selection_scores=score_lookup,
    )


def _select_exact_argmax(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
) -> Tuple[Optional[str], float]:
    """Direct argmax of suitability scores. No solver."""
    t0 = time.perf_counter()
    best_node: Optional[str] = None
    best_score = float("-inf")
    for node_id in candidate_nodes:
        s = consensus.calculate_effective_score(node_id, vrf_output)
        if s > best_score:
            best_score = s
            best_node = node_id
    return best_node, (time.perf_counter() - t0) * 1000.0


def _select_exact_ilp(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
) -> Tuple[Optional[str], float]:
    """OR-Tools CP-SAT ILP: maximise sum(score_i * x_i) s.t. sum(x_i)==1."""
    t0 = time.perf_counter()
    if not _ORTOOLS_AVAILABLE or not candidate_nodes:
        # Fallback to argmax
        node, ms = _select_exact_argmax(consensus, candidate_nodes, vrf_output)
        return node, ms

    scores = {n: consensus.calculate_effective_score(n, vrf_output) for n in candidate_nodes}
    # Scale to integers (multiply by 1e6 and round)
    scale = 1_000_000
    int_scores = {n: max(1, int(s * scale + 1e-9)) for n, s in scores.items()}

    model = _cp_model.CpModel()
    x = {n: model.NewBoolVar(f"x_{n}") for n in candidate_nodes}
    model.Add(sum(x.values()) == 1)
    model.Maximize(sum(int_scores[n] * x[n] for n in candidate_nodes))

    solver = _cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    status = solver.Solve(model)

    selected = None
    if status in (_cp_model.OPTIMAL, _cp_model.FEASIBLE):
        for n in candidate_nodes:
            if solver.Value(x[n]) == 1:
                selected = n
                break
    if selected is None and candidate_nodes:
        selected = max(candidate_nodes, key=lambda n: scores[n])

    return selected, (time.perf_counter() - t0) * 1000.0


def _select_vrf_weighted(
    candidate_nodes: List[str],
    stake: Dict[str, float],
    epoch_seed: str,
) -> Tuple[Optional[str], float]:
    """VRF-weighted random selection: weight = stake * VRF_normalised."""
    t0 = time.perf_counter()
    if not candidate_nodes:
        return None, 0.0

    weights: List[float] = []
    for n in candidate_nodes:
        vrf_bytes = hmac.new(epoch_seed.encode(), n.encode(), hashlib.sha256).digest()
        vrf_score = int.from_bytes(vrf_bytes[:4], "big") / 0xFFFF_FFFF
        weights.append(max(0.001, stake.get(n, 1.0) * vrf_score))

    total = sum(weights)
    r = random.random() * total
    cumulative = 0.0
    selected = candidate_nodes[-1]
    for i, w in enumerate(weights):
        cumulative += w
        if r <= cumulative:
            selected = candidate_nodes[i]
            break

    return selected, (time.perf_counter() - t0) * 1000.0


def _select_hotstuff_rr(
    candidate_nodes: List[str],
    online_state: Dict[str, bool],
    round_idx: int,
) -> Tuple[Optional[str], float, bool]:
    """
    HotStuff-style BFT with round-robin leader rotation.

    Returns (node_id, solver_ms, view_changed).
    """
    t0 = time.perf_counter()
    if not candidate_nodes:
        return None, 0.0, False

    view_changed = False
    n = len(candidate_nodes)
    leader_idx = round_idx % n
    leader = candidate_nodes[leader_idx]

    # If leader is offline, advance (view change)
    attempts = 0
    while not online_state.get(leader, True) and attempts < n:
        leader_idx = (leader_idx + 1) % n
        leader = candidate_nodes[leader_idx]
        view_changed = True
        attempts += 1

    if attempts >= n:
        leader = None

    return leader, (time.perf_counter() - t0) * 1000.0, view_changed


def _select_greedy_score(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
) -> Tuple[Optional[str], float]:
    """Greedy single-metric (uptime/last_seen) baseline."""
    t0 = time.perf_counter()
    best_node: Optional[str] = None
    best_uptime = float("-inf")
    now = time.time()
    for node_id in candidate_nodes:
        node_data = consensus.nodes.get(node_id)
        if not node_data:
            continue
        uptime_score = now - node_data.get("last_seen", 0)
        uptime_score = -uptime_score  # smaller gap = better
        if uptime_score > best_uptime:
            best_uptime = uptime_score
            best_node = node_id
    return best_node, (time.perf_counter() - t0) * 1000.0


def _select_weighted_score(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
) -> Tuple[Optional[str], float]:
    """Weighted random selection using suitability scores."""
    t0 = time.perf_counter()
    if not candidate_nodes:
        return None, 0.0
    scores = [max(0.001, consensus.calculate_effective_score(n, vrf_output)) for n in candidate_nodes]
    total = sum(scores)
    r = random.random() * total
    cumulative = 0.0
    selected = candidate_nodes[-1]
    for i, s in enumerate(scores):
        cumulative += s
        if r <= cumulative:
            selected = candidate_nodes[i]
            break
    return selected, (time.perf_counter() - t0) * 1000.0


def _select_round_robin(
    candidate_nodes: List[str],
    round_idx: int,
) -> Tuple[Optional[str], float]:
    """Simple round-robin rotation."""
    t0 = time.perf_counter()
    if not candidate_nodes:
        return None, 0.0
    return candidate_nodes[round_idx % len(candidate_nodes)], (time.perf_counter() - t0) * 1000.0


def _select_pos_stake(
    candidate_nodes: List[str],
    stake: Dict[str, float],
) -> Tuple[Optional[str], float]:
    """PoS lottery weighted by stake."""
    t0 = time.perf_counter()
    if not candidate_nodes:
        return None, 0.0
    weights = [max(0.001, stake.get(n, 1.0)) for n in candidate_nodes]
    total = sum(weights)
    r = random.random() * total
    cumulative = 0.0
    selected = candidate_nodes[-1]
    for i, w in enumerate(weights):
        cumulative += w
        if r <= cumulative:
            selected = candidate_nodes[i]
            break
    return selected, (time.perf_counter() - t0) * 1000.0


def _select_pow_hash(
    candidate_nodes: List[str],
    hash_power: Dict[str, float],
) -> Tuple[Optional[str], float]:
    """PoW lottery weighted by hash power."""
    t0 = time.perf_counter()
    if not candidate_nodes:
        return None, 0.0
    weights = [max(0.001, hash_power.get(n, 1.0)) for n in candidate_nodes]
    total = sum(weights)
    r = random.random() * total
    cumulative = 0.0
    selected = candidate_nodes[-1]
    for i, w in enumerate(weights):
        cumulative += w
        if r <= cumulative:
            selected = candidate_nodes[i]
            break
    return selected, (time.perf_counter() - t0) * 1000.0


def _strategy_correlation_signal(
    consensus: QuantumAnnealingConsensus,
    strategy: str,
    node_ids: List[str],
) -> Dict[str, float]:
    """Return the baseline-specific signal used for score-selection correlation."""
    if not node_ids:
        return {}

    if strategy in {
        "quantum",
        "exact_argmax",
        "exact_ilp",
        "weighted_score",
        "committee_quantum",
        "committee_greedy",
        "committee_weighted",
        "committee_exact",
    }:
        return {node_id: consensus.calculate_suitability_score(node_id) for node_id in node_ids}

    if strategy in {"vrf_weighted", "pos_stake", "committee_vrf_stake"}:
        return {
            node_id: consensus.nodes.get(node_id, {}).get("stake_weight", 1.0)
            for node_id in node_ids
        }

    if strategy == "pow_hash":
        return {
            node_id: consensus.nodes.get(node_id, {}).get("hash_power_weight", 1.0)
            for node_id in node_ids
        }

    if strategy == "greedy_score":
        now = time.time()
        return {
            node_id: -max(0.0, now - consensus.nodes.get(node_id, {}).get("last_seen", 0.0))
            for node_id in node_ids
        }

    if strategy == "committee_reputation":
        return _history_only_scores(consensus, node_ids)

    if strategy == "committee_composite_greedy":
        return _composite_committee_scores(consensus, node_ids)

    if strategy == "committee_fairness_only":
        return _fairness_only_scores(consensus, node_ids)

    if strategy in {"round_robin", "hotstuff_rr", "committee_uniform"}:
        return {}

    return {node_id: consensus.calculate_suitability_score(node_id) for node_id in node_ids}


# ---------------------------------------------------------------------------
# Agreement rate helper
# ---------------------------------------------------------------------------

def _compute_agreement_rate(
    consensus: QuantumAnnealingConsensus,
    candidate_nodes: List[str],
    vrf_output: str,
    n_virtual: int = 5,
) -> float:
    """
    Run n_virtual independent argmax selections using the same vrf_output but
    slightly varied perturbation seeds.  Returns fraction of runs that agree.
    (For deterministic tie-breaking the rate should be 1.0.)
    """
    if not candidate_nodes:
        return 1.0
    selections = []
    for v in range(n_virtual):
        vrf_v = hashlib.sha256(f"{vrf_output}_virtual_{v}".encode()).hexdigest()
        node, _ = _select_exact_argmax(consensus, candidate_nodes, vrf_v)
        selections.append(node)
    most_common = max(set(selections), key=selections.count)
    return selections.count(most_common) / n_virtual


def _prepare_solver_study_candidates(
    cfg: SimulationConfig,
    study_seed: int,
) -> Tuple[QuantumAnnealingConsensus, List[str]]:
    """Build a deterministic small-candidate committee environment for solver-quality comparisons."""
    study_cfg = SimulationConfig(
        num_nodes=cfg.num_nodes,
        num_rounds=1,
        attacker_fraction=cfg.attacker_fraction,
        top_k_for_error=cfg.top_k_for_error,
        seed=study_seed,
        output_dir=cfg.output_dir,
        network_delay_model=cfg.network_delay_model,
        network_delay_mean_ms=cfg.network_delay_mean_ms,
        network_delay_sigma=cfg.network_delay_sigma,
        churn_rate=cfg.churn_rate,
        measurement_noise=cfg.measurement_noise,
        max_candidate_nodes=cfg.max_candidate_nodes,
        committee_k=cfg.committee_k,
        primary_leader_policy=cfg.primary_leader_policy,
        metadata_profile=cfg.metadata_profile,
        metadata_manifest={},
        exact_oracle_max_candidates=cfg.exact_oracle_max_candidates,
        solver_study_candidate_sizes=list(cfg.solver_study_candidate_sizes),
        solver_study_seed_count=cfg.solver_study_seed_count,
    )
    (
        consensus,
        node_ids,
        ground_truth,
        _stake,
        _hash_power,
        _online_prob,
        _is_attacker,
    ) = _build_simulation_environment(study_cfg)

    rng = random.Random(study_seed)
    now = time.time()
    for node_id in node_ids:
        capability = ground_truth[node_id]
        node_state = consensus.nodes[node_id]
        latency = max(0.001, 0.15 - 0.10 * capability + rng.uniform(-0.01, 0.01))
        throughput = max(1.0, 5.0 + 45.0 * capability * rng.uniform(0.8, 1.2))
        node_state['last_seen'] = now
        node_state['latency'] = latency
        node_state['throughput'] = throughput
        consensus.append_committee_observation(
            node_id,
            uptime_sample=1,
            latency_sample=latency,
            throughput_sample=throughput,
            anchor_id='solver_quality',
        )

    consensus.node_performance_cache.clear()
    return consensus, node_ids


def run_solver_comparison_study(
    cfg: SimulationConfig,
    candidate_sizes: Optional[List[int]] = None,
    seed_count: Optional[int] = None,
) -> List[SolverComparisonMetrics]:
    """Compare committee_quantum against an exact oracle and lightweight baselines on small candidate sets."""
    chosen_sizes = candidate_sizes or list(cfg.solver_study_candidate_sizes)
    trials = seed_count or cfg.solver_study_seed_count
    results: List[SolverComparisonMetrics] = []

    for candidate_count in chosen_sizes:
        if candidate_count > cfg.exact_oracle_max_candidates:
            raise ValueError(
                f"candidate size {candidate_count} exceeds exact oracle limit {cfg.exact_oracle_max_candidates}"
            )

        committee_k = max(1, min(cfg.committee_k, candidate_count))
        exact_objectives: List[float] = []
        quantum_objectives: List[float] = []
        greedy_objectives: List[float] = []
        weighted_objectives: List[float] = []
        quantum_gaps: List[float] = []
        greedy_gaps: List[float] = []
        weighted_gaps: List[float] = []
        quantum_solver_ms: List[float] = []
        exact_solver_ms: List[float] = []
        greedy_solver_ms: List[float] = []
        weighted_solver_ms: List[float] = []
        quantum_disagreements = 0
        greedy_disagreements = 0
        weighted_disagreements = 0

        print(f"\n{'=' * 60}")
        print(f"  Solver study: M={candidate_count}, k={committee_k}, trials={trials}")
        print(f"{'=' * 60}")

        for trial_index in range(trials):
            study_seed = cfg.seed + trial_index
            study_cfg = SimulationConfig(
                num_nodes=candidate_count,
                num_rounds=1,
                attacker_fraction=cfg.attacker_fraction,
                top_k_for_error=cfg.top_k_for_error,
                seed=study_seed,
                output_dir=cfg.output_dir,
                network_delay_model=cfg.network_delay_model,
                network_delay_mean_ms=cfg.network_delay_mean_ms,
                network_delay_sigma=cfg.network_delay_sigma,
                churn_rate=cfg.churn_rate,
                measurement_noise=cfg.measurement_noise,
                max_candidate_nodes=cfg.max_candidate_nodes,
                committee_k=committee_k,
                primary_leader_policy=cfg.primary_leader_policy,
                metadata_profile=cfg.metadata_profile,
                metadata_manifest={},
                exact_oracle_max_candidates=cfg.exact_oracle_max_candidates,
                solver_study_candidate_sizes=list(cfg.solver_study_candidate_sizes),
                solver_study_seed_count=cfg.solver_study_seed_count,
            )
            consensus, node_ids = _prepare_solver_study_candidates(study_cfg, study_seed)
            vrf_output = hashlib.sha256(f"solver_study_{candidate_count}_{study_seed}".encode()).hexdigest()

            exact_result = consensus.select_committee_exact(
                vrf_output,
                candidate_nodes=node_ids,
                committee_k=committee_k,
                primary_leader_policy=cfg.primary_leader_policy,
                max_exact_candidates=cfg.exact_oracle_max_candidates,
            )
            quantum_result = _select_committee_quantum(
                consensus,
                node_ids,
                vrf_output,
                committee_k,
                cfg.primary_leader_policy,
            )
            greedy_result = _select_committee_greedy(
                consensus,
                node_ids,
                vrf_output,
                committee_k,
                cfg.primary_leader_policy,
            )
            weighted_result = _select_committee_weighted(
                consensus,
                node_ids,
                vrf_output,
                committee_k,
                cfg.primary_leader_policy,
            )

            exact_objectives.append(exact_result.objective_value)
            quantum_objectives.append(quantum_result.objective_value)
            greedy_objectives.append(greedy_result.objective_value)
            weighted_objectives.append(weighted_result.objective_value)

            quantum_gaps.append(max(0.0, quantum_result.objective_value - exact_result.objective_value))
            greedy_gaps.append(max(0.0, greedy_result.objective_value - exact_result.objective_value))
            weighted_gaps.append(max(0.0, weighted_result.objective_value - exact_result.objective_value))

            exact_solver_ms.append(exact_result.solver_time_ms)
            quantum_solver_ms.append(quantum_result.solver_time_ms)
            greedy_solver_ms.append(greedy_result.solver_time_ms)
            weighted_solver_ms.append(weighted_result.solver_time_ms)

            exact_committee = set(exact_result.committee_nodes)
            if set(quantum_result.committee_nodes) != exact_committee:
                quantum_disagreements += 1
            if set(greedy_result.committee_nodes) != exact_committee:
                greedy_disagreements += 1
            if set(weighted_result.committee_nodes) != exact_committee:
                weighted_disagreements += 1

        result = SolverComparisonMetrics(
            candidate_count=candidate_count,
            committee_k=committee_k,
            n_trials=trials,
            exact_objective_mean=statistics.mean(exact_objectives),
            quantum_objective_mean=statistics.mean(quantum_objectives),
            greedy_objective_mean=statistics.mean(greedy_objectives),
            weighted_objective_mean=statistics.mean(weighted_objectives),
            quantum_optimality_gap_mean=statistics.mean(quantum_gaps),
            greedy_optimality_gap_mean=statistics.mean(greedy_gaps),
            weighted_optimality_gap_mean=statistics.mean(weighted_gaps),
            quantum_disagreement_rate=quantum_disagreements / trials,
            greedy_disagreement_rate=greedy_disagreements / trials,
            weighted_disagreement_rate=weighted_disagreements / trials,
            quantum_solver_ms_mean=statistics.mean(quantum_solver_ms),
            exact_solver_ms_mean=statistics.mean(exact_solver_ms),
            greedy_solver_ms_mean=statistics.mean(greedy_solver_ms),
            weighted_solver_ms_mean=statistics.mean(weighted_solver_ms),
        )
        results.append(result)
        print(
            f"  exact_obj={result.exact_objective_mean:.3f}  quantum_gap={result.quantum_optimality_gap_mean:.3f}  "
            f"greedy_gap={result.greedy_optimality_gap_mean:.3f}  weighted_gap={result.weighted_optimality_gap_mean:.3f}"
        )

    return results


# ---------------------------------------------------------------------------
# Main simulation loop
# ---------------------------------------------------------------------------

def run_simulation(
    cfg: SimulationConfig,
    strategy: str,
    ablation_cfg: Optional[AblationConfig] = None,
    verbose: bool = False,
    trace_interval: int = 0,
) -> StrategyMetrics:
    """
    Run a full simulation for a single strategy.

    strategy must be one of:
      quantum | exact_argmax | exact_ilp | vrf_weighted | hotstuff_rr |
            greedy_score | weighted_score | round_robin | pos_stake | pow_hash |
            committee_quantum | committee_greedy | committee_uniform |
            committee_vrf_stake | committee_reputation |
            committee_composite_greedy | committee_fairness_only |
            committee_weighted | committee_exact
    """
    random.seed(cfg.seed)

    (
        consensus,
        node_ids,
        ground_truth,
        stake,
        hash_power,
        online_prob,
        is_attacker,
    ) = _build_simulation_environment(cfg, ablation_cfg=ablation_cfg)

    net_sim = NetworkSimulator(
        model=cfg.network_delay_model,
        mean_ms=cfg.network_delay_mean_ms,
        sigma=cfg.network_delay_sigma,
        seed=cfg.seed,
    )

    # Sorted top-k for selection-error tracking
    top_k_ids = set(
        sorted(ground_truth, key=ground_truth.get, reverse=True)[: cfg.top_k_for_error]
    )

    # Per-round tracking
    pqi_values: List[float] = []
    block_times_ms: List[float] = []
    selection_counts: Counter = Counter()
    attacker_selected: int = 0
    missed_slots: int = 0
    selection_errors: int = 0
    solver_times_ms: List[float] = []
    view_changes: int = 0
    agreement_scores: List[float] = []
    committee_constraint_violations: List[float] = []
    committee_unique_failure_ratios: List[float] = []
    committee_attacker_seat_shares: List[float] = []
    committee_fallbacks: int = 0
    committee_objective_values: List[float] = []
    committee_raw_objective_values: List[float] = []
    committee_candidate_counts: List[float] = []
    proposer_share_trace: List[Dict[str, Any]] = []

    if verbose:
        print(f"  Running {cfg.num_rounds} rounds with strategy={strategy}, N={cfg.num_nodes}")

    for rnd in range(cfg.num_rounds):
        # Update node metrics
        online_state = _update_round_metrics(
            consensus, node_ids, ground_truth, online_prob, net_sim, cfg
        )

        # Apply churn
        _apply_churn(
            consensus, node_ids, ground_truth, online_prob,
            stake, hash_power, is_attacker, cfg, rng_seed=cfg.seed + rnd,
        )

        active_nodes = [n for n in node_ids if online_state.get(n, False)]
        if not active_nodes:
            missed_slots += 1
            continue

        vrf_output = hashlib.sha256(f"round_{rnd}_{cfg.seed}".encode()).hexdigest()
        epoch_seed = f"epoch_{rnd // 100}_{cfg.seed}"

        # Select leader
        selected: Optional[str] = None
        solver_ms: float = 0.0
        view_changed: bool = False
        committee_nodes: List[str] = []

        t_block_start = time.perf_counter()

        if strategy == "quantum":
            selected, solver_ms = _select_quantum(consensus, active_nodes, vrf_output)
        elif strategy == "exact_argmax":
            selected, solver_ms = _select_exact_argmax(consensus, active_nodes, vrf_output)
        elif strategy == "exact_ilp":
            selected, solver_ms = _select_exact_ilp(consensus, active_nodes, vrf_output)
        elif strategy == "vrf_weighted":
            selected, solver_ms = _select_vrf_weighted(active_nodes, stake, epoch_seed)
        elif strategy == "hotstuff_rr":
            selected, solver_ms, view_changed = _select_hotstuff_rr(active_nodes, online_state, rnd)
        elif strategy == "greedy_score":
            selected, solver_ms = _select_greedy_score(consensus, active_nodes)
        elif strategy == "weighted_score":
            selected, solver_ms = _select_weighted_score(consensus, active_nodes, vrf_output)
        elif strategy == "round_robin":
            selected, solver_ms = _select_round_robin(active_nodes, rnd)
        elif strategy == "pos_stake":
            selected, solver_ms = _select_pos_stake(active_nodes, stake)
        elif strategy == "pow_hash":
            selected, solver_ms = _select_pow_hash(active_nodes, hash_power)
        elif strategy == "committee_quantum":
            committee_result = _select_committee_quantum(
                consensus,
                active_nodes,
                vrf_output,
                cfg.committee_k,
                cfg.primary_leader_policy,
            )
            selected = committee_result.primary_leader
            solver_ms = committee_result.solver_time_ms
            committee_nodes = committee_result.committee_nodes
            if committee_result.used_fallback:
                committee_fallbacks += 1
        elif strategy == "committee_greedy":
            committee_result = _select_committee_greedy(
                consensus,
                active_nodes,
                vrf_output,
                cfg.committee_k,
                cfg.primary_leader_policy,
            )
            selected = committee_result.primary_leader
            solver_ms = committee_result.solver_time_ms
            committee_nodes = committee_result.committee_nodes
        elif strategy == "committee_weighted":
            committee_result = _select_committee_weighted(
                consensus,
                active_nodes,
                vrf_output,
                cfg.committee_k,
                cfg.primary_leader_policy,
            )
            selected = committee_result.primary_leader
            solver_ms = committee_result.solver_time_ms
            committee_nodes = committee_result.committee_nodes
        elif strategy == "committee_uniform":
            committee_result = _select_committee_uniform(
                consensus,
                active_nodes,
                vrf_output,
                cfg.committee_k,
                cfg.primary_leader_policy,
            )
            selected = committee_result.primary_leader
            solver_ms = committee_result.solver_time_ms
            committee_nodes = committee_result.committee_nodes
        elif strategy == "committee_vrf_stake":
            committee_result = _select_committee_vrf_stake(
                consensus,
                active_nodes,
                vrf_output,
                cfg.committee_k,
                cfg.primary_leader_policy,
            )
            selected = committee_result.primary_leader
            solver_ms = committee_result.solver_time_ms
            committee_nodes = committee_result.committee_nodes
        elif strategy == "committee_reputation":
            committee_result = _select_committee_reputation(
                consensus,
                active_nodes,
                vrf_output,
                cfg.committee_k,
                cfg.primary_leader_policy,
            )
            selected = committee_result.primary_leader
            solver_ms = committee_result.solver_time_ms
            committee_nodes = committee_result.committee_nodes
        elif strategy == "committee_composite_greedy":
            committee_result = _select_committee_composite_greedy(
                consensus,
                active_nodes,
                vrf_output,
                cfg.committee_k,
                cfg.primary_leader_policy,
            )
            selected = committee_result.primary_leader
            solver_ms = committee_result.solver_time_ms
            committee_nodes = committee_result.committee_nodes
        elif strategy == "committee_fairness_only":
            committee_result = _select_committee_fairness_only(
                consensus,
                active_nodes,
                vrf_output,
                cfg.committee_k,
                cfg.primary_leader_policy,
            )
            selected = committee_result.primary_leader
            solver_ms = committee_result.solver_time_ms
            committee_nodes = committee_result.committee_nodes
        elif strategy == "committee_exact":
            committee_result = _select_committee_exact(
                consensus,
                active_nodes,
                vrf_output,
                cfg.committee_k,
                cfg.primary_leader_policy,
                cfg.exact_oracle_max_candidates,
            )
            selected = committee_result.primary_leader
            solver_ms = committee_result.solver_time_ms
            committee_nodes = committee_result.committee_nodes
        else:
            raise ValueError(f"Unknown strategy: {strategy!r}")

        block_time_ms = (time.perf_counter() - t_block_start) * 1000.0

        if selected is None:
            missed_slots += 1
            continue

        # Record selection
        selection_counts[selected] += 1
        if view_changed:
            view_changes += 1

        # PQI
        pqi = ground_truth.get(selected, 0.0)
        pqi_values.append(pqi)

        # Block time
        block_times_ms.append(block_time_ms)

        # Attacker share
        if is_attacker.get(selected, False):
            attacker_selected += 1

        # Selection error
        if selected not in top_k_ids:
            selection_errors += 1

        # Solver time
        solver_times_ms.append(solver_ms)

        if committee_nodes:
            committee_round = _evaluate_committee_round(consensus, committee_nodes, is_attacker)
            committee_constraint_violations.append(committee_round['has_constraint_violation'])
            committee_unique_failure_ratios.append(committee_round['unique_failure_domain_ratio'])
            committee_attacker_seat_shares.append(committee_round['attacker_seat_share'])
            committee_objective_values.append(committee_result.objective_value)
            committee_raw_objective_values.append(committee_result.raw_objective_value)
            committee_candidate_counts.append(float(committee_result.candidate_count))

        _record_simulation_selection_feedback(
            consensus,
            selected=selected,
            committee_nodes=committee_nodes,
        )

        if trace_interval > 0 and ((rnd + 1) % trace_interval == 0 or rnd == cfg.num_rounds - 1):
            completed_rounds = rnd + 1
            total_selected_so_far = sum(selection_counts.values())
            total_selected_safe = max(1, total_selected_so_far)
            proposer_share_trace.append(
                {
                    "round": completed_rounds,
                    "attacker_share": attacker_selected / total_selected_safe,
                    "gini_coefficient": _compute_gini(selection_counts, cfg.num_nodes),
                    "selection_entropy": _compute_selection_entropy(selection_counts, cfg.num_nodes),
                    "selection_concentration": _compute_selection_concentration(selection_counts, cfg.num_nodes),
                    "nakamoto_coefficient": _compute_nakamoto_coefficient(selection_counts),
                    "missed_slot_rate": missed_slots / completed_rounds,
                    "selected_rounds": total_selected_so_far,
                }
            )

        # Agreement rate (sampled every 50 rounds for performance)
        if strategy in ("quantum", "exact_argmax", "exact_ilp") and rnd % 50 == 0:
            agr = _compute_agreement_rate(consensus, active_nodes[:20], vrf_output)
            agreement_scores.append(agr)
        elif strategy == "committee_quantum" and rnd % 50 == 0 and committee_nodes:
            agreement_scores.append(1.0)

    # --- Aggregate metrics ---
    total_valid = cfg.num_rounds - missed_slots
    if total_valid == 0:
        total_valid = 1

    missed_slot_rate = missed_slots / cfg.num_rounds
    attacker_share = attacker_selected / total_valid
    sel_error_rate = selection_errors / total_valid

    pqi_mean = statistics.mean(pqi_values) if pqi_values else 0.0
    pqi_p95 = _percentile(pqi_values, 95)
    p95_block_time = _percentile(block_times_ms, 95)

    nakamoto = _compute_nakamoto_coefficient(selection_counts)
    gini = _compute_gini(selection_counts, cfg.num_nodes)
    selection_entropy = _compute_selection_entropy(selection_counts, cfg.num_nodes)
    selection_concentration = _compute_selection_concentration(selection_counts, cfg.num_nodes)
    mean_solver_ms = statistics.mean(solver_times_ms) if solver_times_ms else 0.0

    # Score-to-selection Spearman correlation
    node_list = list(selection_counts.keys()) if selection_counts else node_ids[:10]
    vrf_last = hashlib.sha256(f"final_{cfg.seed}".encode()).hexdigest()
    correlation_signal = _strategy_correlation_signal(consensus, strategy, node_list)
    if correlation_signal:
        score_list = [correlation_signal.get(n, 0.0) for n in node_list]
        count_list = [selection_counts.get(n, 0) for n in node_list]
        spearman = _spearman_correlation(score_list, count_list)
    else:
        spearman = 0.0

    agreement_rate = statistics.mean(agreement_scores) if agreement_scores else 1.0
    view_change_rate = view_changes / total_valid if strategy == "hotstuff_rr" else 0.0
    committee_size = cfg.committee_k if strategy.startswith("committee_") else 1
    committee_constraint_violation_rate = (
        statistics.mean(committee_constraint_violations) if committee_constraint_violations else 0.0
    )
    committee_mean_unique_failure_domain_ratio = (
        statistics.mean(committee_unique_failure_ratios) if committee_unique_failure_ratios else 0.0
    )
    committee_attacker_seat_share = (
        statistics.mean(committee_attacker_seat_shares) if committee_attacker_seat_shares else 0.0
    )
    committee_fallback_rate = (
        committee_fallbacks / total_valid if strategy == "committee_quantum" and total_valid > 0 else 0.0
    )
    committee_objective_mean = statistics.mean(committee_objective_values) if committee_objective_values else 0.0
    committee_raw_objective_mean = statistics.mean(committee_raw_objective_values) if committee_raw_objective_values else 0.0
    committee_candidate_count_mean = statistics.mean(committee_candidate_counts) if committee_candidate_counts else 0.0

    return StrategyMetrics(
        name=strategy,
        pqi_mean=pqi_mean,
        pqi_p95=pqi_p95,
        missed_slot_rate=missed_slot_rate,
        p95_block_time_ms=p95_block_time,
        nakamoto_coefficient=nakamoto,
        attacker_share=attacker_share,
        selection_error_rate=sel_error_rate,
        gini_coefficient=gini,
        selection_entropy=selection_entropy,
        selection_concentration=selection_concentration,
        score_selection_spearman=spearman,
        agreement_rate=agreement_rate,
        mean_solver_ms=mean_solver_ms,
        view_change_rate=view_change_rate,
        committee_size=committee_size,
        committee_constraint_violation_rate=committee_constraint_violation_rate,
        committee_mean_unique_failure_domain_ratio=committee_mean_unique_failure_domain_ratio,
        committee_attacker_seat_share=committee_attacker_seat_share,
        committee_fallback_rate=committee_fallback_rate,
        committee_objective_mean=committee_objective_mean,
        committee_raw_objective_mean=committee_raw_objective_mean,
        committee_candidate_count_mean=committee_candidate_count_mean,
        proposer_share_trace=proposer_share_trace,
    )


# ---------------------------------------------------------------------------
# Full strategy comparison
# ---------------------------------------------------------------------------

ALL_STRATEGIES = [
    "quantum",
    "exact_argmax",
    "exact_ilp",
    "vrf_weighted",
    "hotstuff_rr",
    "greedy_score",
    "weighted_score",
    "round_robin",
    "pos_stake",
    "pow_hash",
    "committee_quantum",
    "committee_greedy",
    "committee_weighted",
    "committee_uniform",
    "committee_vrf_stake",
    "committee_reputation",
    "committee_composite_greedy",
    "committee_fairness_only",
]

COMMITTEE_BASELINE_STRATEGIES = [
    "committee_quantum",
    "committee_greedy",
    "committee_weighted",
    "committee_uniform",
    "committee_vrf_stake",
    "committee_reputation",
    "committee_composite_greedy",
    "committee_fairness_only",
]

LITERATURE_COMMITTEE_STRATEGIES = [
    "committee_quantum",
    "committee_vrf_stake",
    "committee_reputation",
    "committee_composite_greedy",
    "committee_uniform",
    "committee_fairness_only",
]


def resolve_strategy_preset(
    preset: str,
    cfg: SimulationConfig,
) -> List[str]:
    """Resolve a human-friendly strategy preset into strategy ids."""
    if preset == "all":
        return list(ALL_STRATEGIES)
    if preset == "committee-all":
        return list(COMMITTEE_BASELINE_STRATEGIES)
    if preset == "literature":
        return list(LITERATURE_COMMITTEE_STRATEGIES)
    if preset == "reduced":
        return [
            "committee_quantum",
            "committee_vrf_stake",
            "committee_reputation",
            "committee_composite_greedy",
            "committee_uniform",
            "committee_fairness_only",
        ]
    if preset == "reduced-with-exact":
        strategies = resolve_strategy_preset("reduced", cfg)
        if cfg.num_nodes <= cfg.exact_oracle_max_candidates:
            strategies.append("committee_exact")
        else:
            print(
                "  Skipping committee_exact in preset: "
                f"num_nodes={cfg.num_nodes} exceeds exact_oracle_max_candidates={cfg.exact_oracle_max_candidates}"
            )
        return strategies
    raise ValueError(f"Unknown strategy preset: {preset!r}")


_PROBE_BASED_STRATEGIES = {
    "quantum",
    "exact_argmax",
    "exact_ilp",
    "greedy_score",
    "weighted_score",
    "committee_quantum",
    "committee_greedy",
    "committee_weighted",
    "committee_exact",
    "committee_reputation",
    "committee_composite_greedy",
    "committee_fairness_only",
}


def _estimate_probe_exchange_bytes(witness_count: int) -> int:
    probe_request = {
        "source_id": "node_source",
        "target_id": "node_target",
        "timestamp": 1234567890.123,
        "nonce": "a" * 64,
        "request_signature": "b" * 128,
    }
    target_receipt = {
        "original_request": "probe_request_hash",
        "receipt_time": 1234567890.456,
        "target_id": "node_target",
        "target_signature": "c" * 128,
    }
    witness_receipt = {
        "witness_id": "node_witness",
        "observed_request": "probe_request_hash",
        "witness_timestamp": 1234567890.789,
        "target_receipt_observed": "target_receipt_hash",
        "latency_observation": 12.34,
        "witness_signature": "d" * 128,
    }
    return (
        len(json.dumps(probe_request, sort_keys=True).encode("utf-8"))
        + len(json.dumps(target_receipt, sort_keys=True).encode("utf-8"))
        + witness_count * len(json.dumps(witness_receipt, sort_keys=True).encode("utf-8"))
    )


def _estimate_probe_overhead_for_round(
    consensus: QuantumAnnealingConsensus,
    strategy: str,
    active_nodes: List[str],
) -> Tuple[float, float]:
    if strategy not in _PROBE_BASED_STRATEGIES or len(active_nodes) < 2:
        return 0.0, 0.0

    targets_per_source = min(consensus.probe_sample_size, max(1, len(active_nodes) - 1))
    witness_count = min(consensus.witness_quorum_size, max(0, len(active_nodes) - 2))
    probe_count = len(active_nodes) * targets_per_source
    message_count = probe_count * (2 + witness_count)
    byte_count = probe_count * _estimate_probe_exchange_bytes(witness_count)
    return float(message_count), float(byte_count)


def _measure_score_construction_cpu_ms(
    consensus: QuantumAnnealingConsensus,
    strategy: str,
    active_nodes: List[str],
) -> float:
    if not active_nodes:
        return 0.0

    consensus.node_performance_cache.clear()
    consensus.committee_feature_cache.clear()
    t0 = time.perf_counter()
    _strategy_correlation_signal(consensus, strategy, active_nodes)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    consensus.node_performance_cache.clear()
    consensus.committee_feature_cache.clear()
    return elapsed_ms


def _select_committee_strategy_for_overhead(
    consensus: QuantumAnnealingConsensus,
    strategy: str,
    active_nodes: List[str],
    vrf_output: str,
    cfg: SimulationConfig,
) -> CommitteeSelectionResult:
    if strategy == "committee_quantum":
        return _select_committee_quantum(consensus, active_nodes, vrf_output, cfg.committee_k, cfg.primary_leader_policy)
    if strategy == "committee_greedy":
        return _select_committee_greedy(consensus, active_nodes, vrf_output, cfg.committee_k, cfg.primary_leader_policy)
    if strategy == "committee_weighted":
        return _select_committee_weighted(consensus, active_nodes, vrf_output, cfg.committee_k, cfg.primary_leader_policy)
    if strategy == "committee_uniform":
        return _select_committee_uniform(consensus, active_nodes, vrf_output, cfg.committee_k, cfg.primary_leader_policy)
    if strategy == "committee_vrf_stake":
        return _select_committee_vrf_stake(consensus, active_nodes, vrf_output, cfg.committee_k, cfg.primary_leader_policy)
    if strategy == "committee_reputation":
        return _select_committee_reputation(consensus, active_nodes, vrf_output, cfg.committee_k, cfg.primary_leader_policy)
    if strategy == "committee_composite_greedy":
        return _select_committee_composite_greedy(consensus, active_nodes, vrf_output, cfg.committee_k, cfg.primary_leader_policy)
    if strategy == "committee_fairness_only":
        return _select_committee_fairness_only(consensus, active_nodes, vrf_output, cfg.committee_k, cfg.primary_leader_policy)
    if strategy == "committee_exact":
        return _select_committee_exact(
            consensus,
            active_nodes,
            vrf_output,
            cfg.committee_k,
            cfg.primary_leader_policy,
            cfg.exact_oracle_max_candidates,
        )
    raise ValueError(f"Unsupported overhead-study strategy: {strategy!r}")


def run_measurement_overhead_study(
    cfg: SimulationConfig,
    *,
    node_counts: Optional[List[int]] = None,
    num_rounds: int = 100,
    window_rounds: int = 25,
    strategies: Optional[List[str]] = None,
) -> List[MeasurementOverheadMetrics]:
    """Measure per-window probe traffic and CPU overhead for committee-selection strategies."""
    selected_strategies = list(strategies) if strategies is not None else [
        "committee_quantum",
        "committee_greedy",
        "committee_vrf_stake",
        "committee_reputation",
        "committee_composite_greedy",
        "committee_uniform",
        "committee_fairness_only",
    ]
    selected_node_counts = list(node_counts) if node_counts is not None else [40, 100, 200]

    results: List[MeasurementOverheadMetrics] = []
    for num_nodes in selected_node_counts:
        local_cfg = replace(cfg, num_nodes=num_nodes, num_rounds=num_rounds)
        for strategy in selected_strategies:
            if strategy == "committee_exact" and num_nodes > local_cfg.exact_oracle_max_candidates:
                continue

            consensus, node_ids, ground_truth, stake, hash_power, online_prob, is_attacker = _build_simulation_environment(local_cfg)
            net_sim = NetworkSimulator(
                model=local_cfg.network_delay_model,
                mean_ms=local_cfg.network_delay_mean_ms,
                sigma=local_cfg.network_delay_sigma,
                seed=local_cfg.seed,
            )

            window_probe_messages = 0.0
            window_probe_bytes = 0.0
            window_score_cpu_ms = 0.0
            window_optimization_ms = 0.0
            window_end_to_end_ms = 0.0
            current_window_rounds = 0

            active_node_counts: List[float] = []
            probe_windows: List[float] = []
            byte_windows: List[float] = []
            score_windows: List[float] = []
            optimization_windows: List[float] = []
            end_to_end_windows: List[float] = []

            for rnd in range(num_rounds):
                online_state = _update_round_metrics(
                    consensus,
                    node_ids,
                    ground_truth,
                    online_prob,
                    net_sim,
                    local_cfg,
                )
                _apply_churn(
                    consensus,
                    node_ids,
                    ground_truth,
                    online_prob,
                    stake,
                    hash_power,
                    is_attacker,
                    local_cfg,
                    rng_seed=local_cfg.seed + rnd,
                )

                active_nodes = [node_id for node_id in node_ids if online_state.get(node_id, False)]
                active_node_counts.append(float(len(active_nodes)))
                if not active_nodes:
                    continue

                vrf_output = hashlib.sha256(f"overhead_round_{rnd}_{local_cfg.seed}".encode()).hexdigest()
                probe_messages, probe_bytes = _estimate_probe_overhead_for_round(consensus, strategy, active_nodes)
                score_cpu_ms = _measure_score_construction_cpu_ms(consensus, strategy, active_nodes)

                t0 = time.perf_counter()
                committee_result = _select_committee_strategy_for_overhead(consensus, strategy, active_nodes, vrf_output, local_cfg)
                end_to_end_ms = (time.perf_counter() - t0) * 1000.0

                window_probe_messages += probe_messages
                window_probe_bytes += probe_bytes
                window_score_cpu_ms += score_cpu_ms
                window_optimization_ms += committee_result.solver_time_ms
                window_end_to_end_ms += end_to_end_ms
                current_window_rounds += 1

                if committee_result.primary_leader:
                    _record_simulation_selection_feedback(
                        consensus,
                        selected=committee_result.primary_leader,
                        committee_nodes=committee_result.committee_nodes,
                    )

                if current_window_rounds == window_rounds or rnd == num_rounds - 1:
                    completed_rounds = max(1, current_window_rounds)
                    scale = window_rounds / completed_rounds
                    probe_windows.append(window_probe_messages * scale)
                    byte_windows.append(window_probe_bytes * scale)
                    score_windows.append(window_score_cpu_ms * scale)
                    optimization_windows.append(window_optimization_ms * scale)
                    end_to_end_windows.append(window_end_to_end_ms * scale)

                    window_probe_messages = 0.0
                    window_probe_bytes = 0.0
                    window_score_cpu_ms = 0.0
                    window_optimization_ms = 0.0
                    window_end_to_end_ms = 0.0
                    current_window_rounds = 0

            results.append(
                MeasurementOverheadMetrics(
                    strategy=strategy,
                    num_nodes=num_nodes,
                    num_rounds=num_rounds,
                    window_rounds=window_rounds,
                    num_windows=len(probe_windows),
                    mean_active_nodes=statistics.mean(active_node_counts) if active_node_counts else 0.0,
                    probe_messages_per_window=statistics.mean(probe_windows) if probe_windows else 0.0,
                    probe_bytes_per_window=statistics.mean(byte_windows) if byte_windows else 0.0,
                    score_construction_cpu_ms=statistics.mean(score_windows) if score_windows else 0.0,
                    optimization_latency_ms=statistics.mean(optimization_windows) if optimization_windows else 0.0,
                    end_to_end_selection_ms=statistics.mean(end_to_end_windows) if end_to_end_windows else 0.0,
                )
            )
            print(
                f"  overhead strategy={strategy:26s} nodes={num_nodes:4d} probe_msgs/window={results[-1].probe_messages_per_window:.1f} "
                f"bytes/window={results[-1].probe_bytes_per_window:.1f} score_ms/window={results[-1].score_construction_cpu_ms:.2f} "
                f"solver_ms/window={results[-1].optimization_latency_ms:.2f}"
            )

    return results


def run_committee_baseline_comparison(
    cfg: SimulationConfig,
    preset: str = "literature",
) -> List[StrategyMetrics]:
    """Run a committee-focused comparison using one of the built-in presets."""
    strategies = resolve_strategy_preset(preset, cfg)
    return run_strategy_comparison(cfg, strategies)


def run_strategy_comparison(cfg: SimulationConfig, strategies: Optional[List[str]] = None) -> List[StrategyMetrics]:
    """Run all (or selected) strategies and return their metrics."""
    chosen = strategies or ALL_STRATEGIES
    results: List[StrategyMetrics] = []
    for strat in chosen:
        print(f"\n{'='*60}")
        print(f"  Strategy: {strat}")
        print(f"{'='*60}")
        m = run_simulation(cfg, strat, verbose=False)
        results.append(m)
        print(
            f"  PQI mean={m.pqi_mean:.3f}  attacker_share={m.attacker_share:.3f}  "
            f"gini={m.gini_coefficient:.3f}  solver_ms={m.mean_solver_ms:.1f}"
        )
    return results


# ---------------------------------------------------------------------------
# Ablation runner
# ---------------------------------------------------------------------------

ABLATION_CONFIGS: Dict[str, Tuple[AblationConfig, dict]] = {
    "no_fairness":    (AblationConfig(use_fairness_penalty=False), {}),
    "no_witness":     (AblationConfig(use_witness_quorum=False), {}),
    "argmax_solver":  (AblationConfig(use_qubo_solver=False), {}),
    "no_vrf":         (AblationConfig(use_vrf_tiebreak=False), {}),
    "attacker_0.1":   (AblationConfig(), {"attacker_fraction": 0.1}),
    "attacker_0.2":   (AblationConfig(), {"attacker_fraction": 0.2}),
    "attacker_0.33":  (AblationConfig(), {"attacker_fraction": 0.33}),
    "attacker_0.4":   (AblationConfig(), {"attacker_fraction": 0.4}),
    "witness_W3":     (AblationConfig(witness_quorum_size=3), {}),
    "witness_W5":     (AblationConfig(witness_quorum_size=5), {}),
    "witness_W10":    (AblationConfig(witness_quorum_size=10), {}),
    "noise_10pct":    (AblationConfig(), {"measurement_noise": 0.10}),
    "noise_20pct":    (AblationConfig(), {"measurement_noise": 0.20}),
    "churn_10pct":    (AblationConfig(), {"churn_rate": 0.10}),
    "churn_20pct":    (AblationConfig(), {"churn_rate": 0.20}),
}


COMMITTEE_ABLATION_CONFIGS: Dict[str, CommitteeAblationDefinition] = {
    "full_objective": CommitteeAblationDefinition(
        strategy="committee_quantum",
        ablation_config=AblationConfig(),
        label="Full objective",
    ),
    "lambda_zero": CommitteeAblationDefinition(
        strategy="committee_quantum",
        ablation_config=AblationConfig(use_committee_pairwise_risk=False),
        label="Pairwise risk off",
    ),
    "w_freq_zero": CommitteeAblationDefinition(
        strategy="committee_quantum",
        ablation_config=AblationConfig(use_fairness_penalty=False),
        label="Fairness off",
    ),
    "no_fallback": CommitteeAblationDefinition(
        strategy="committee_quantum",
        ablation_config=AblationConfig(use_committee_fallback=False),
        label="Fallback off",
    ),
    "score_only": CommitteeAblationDefinition(
        strategy="committee_greedy",
        ablation_config=None,
        label="Score-only committee",
    ),
}


def run_ablations(
    base_cfg: SimulationConfig,
    ablation_ids: Optional[List[str]] = None,
) -> Dict[str, StrategyMetrics]:
    """
    Run all (or selected) ablation experiments with strategy='quantum'.

    Each ablation varies only one component vs. the default quantum config.
    Returns a dict mapping ablation_id -> StrategyMetrics.
    """
    chosen = ablation_ids or list(ABLATION_CONFIGS.keys())
    results: Dict[str, StrategyMetrics] = {}

    for abl_id in chosen:
        if abl_id not in ABLATION_CONFIGS:
            print(f"  ⚠  Unknown ablation id: {abl_id!r}, skipping")
            continue
        abl_cfg_obj, overrides = ABLATION_CONFIGS[abl_id]

        # Build modified SimulationConfig
        import dataclasses
        cfg = dataclasses.replace(base_cfg, **overrides)

        print(f"\n{'='*60}")
        print(f"  Ablation: {abl_id}")
        print(f"{'='*60}")
        m = run_simulation(cfg, "quantum", ablation_cfg=abl_cfg_obj, verbose=False)
        m.name = f"quantum/{abl_id}"
        results[abl_id] = m
        print(
            f"  PQI={m.pqi_mean:.3f}  attacker_share={m.attacker_share:.3f}  "
            f"gini={m.gini_coefficient:.3f}  missed={m.missed_slot_rate:.3f}"
        )

    return results


def run_committee_ablations(
    base_cfg: SimulationConfig,
    ablation_ids: Optional[List[str]] = None,
) -> Dict[str, StrategyMetrics]:
    """Run committee-specific objective ablations under the current simulation workload."""
    chosen = ablation_ids or list(COMMITTEE_ABLATION_CONFIGS.keys())
    results: Dict[str, StrategyMetrics] = {}

    for abl_id in chosen:
        if abl_id not in COMMITTEE_ABLATION_CONFIGS:
            print(f"  ⚠  Unknown committee ablation id: {abl_id!r}, skipping")
            continue

        definition = COMMITTEE_ABLATION_CONFIGS[abl_id]

        import dataclasses
        cfg = dataclasses.replace(base_cfg, **definition.cfg_overrides)

        print(f"\n{'='*60}")
        print(f"  Committee ablation: {abl_id}")
        print(f"{'='*60}")
        metrics = run_simulation(
            cfg,
            definition.strategy,
            ablation_cfg=definition.ablation_config,
            verbose=False,
        )
        metrics.name = definition.label or f"{definition.strategy}/{abl_id}"
        results[abl_id] = metrics
        print(
            f"  objective={metrics.committee_objective_mean:.3f}  violations={metrics.committee_constraint_violation_rate:.3f}  "
            f"diversity={metrics.committee_mean_unique_failure_domain_ratio:.3f}  fallback={metrics.committee_fallback_rate:.3f}"
        )

    return results


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def _save_strategy_plots(metrics: List[StrategyMetrics], output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    names = [m.name for m in metrics]
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # 1. PQI
    fig, ax = plt.subplots(figsize=(10, 5))
    x = range(len(names))
    ax.bar([i - 0.2 for i in x], [m.pqi_mean for m in metrics], 0.4, label="PQI mean")
    ax.bar([i + 0.2 for i in x], [m.pqi_p95 for m in metrics], 0.4, label="PQI p95")
    ax.set_xticks(list(x))
    ax.set_xticklabels(names, rotation=15, ha="right")
    ax.set_ylabel("Proposer Quality Index")
    ax.set_title("PQI by Strategy")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"eval_pqi_{timestamp}.png"))
    plt.close(fig)

    # 2. Gini / Nakamoto / attacker share
    fig, ax = plt.subplots(figsize=(12, 5))
    width = 0.25
    xs = list(range(len(names)))
    ax.bar([i - width for i in xs], [m.gini_coefficient for m in metrics], width, label="Gini coeff")
    ax.bar(xs, [m.attacker_share for m in metrics], width, label="Attacker share")
    ax.bar([i + width for i in xs], [m.selection_error_rate for m in metrics], width, label="Selection error rate")
    for m_val, x_pos in zip(metrics, xs):
        ax.text(x_pos - width, m_val.gini_coefficient + 0.01, f"{m_val.gini_coefficient:.2f}", ha="center", fontsize=8)
    ax.set_xticks(xs)
    ax.set_xticklabels(names, rotation=15, ha="right")
    ax.set_ylabel("Rate / Coefficient")
    ax.set_title("Security & Fairness Metrics by Strategy")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"eval_security_{timestamp}.png"))
    plt.close(fig)

    # 3. Solver time
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(names, [m.mean_solver_ms for m in metrics])
    ax.set_ylabel("Mean solver time (ms)")
    ax.set_title("Solver Time by Strategy")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=15, ha="right")
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"eval_solver_time_{timestamp}.png"))
    plt.close(fig)

    # 4. Agreement rate
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(names, [m.agreement_rate for m in metrics])
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Agreement rate")
    ax.set_title("Proposer Agreement Rate by Strategy")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=15, ha="right")
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"eval_agreement_{timestamp}.png"))
    plt.close(fig)

    committee_metrics = [m for m in metrics if m.committee_size > 1]
    if committee_metrics:
        committee_names = [m.name for m in committee_metrics]
        xs = list(range(len(committee_names)))
        width = 0.2
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        ax1.bar([i - width for i in xs], [m.committee_constraint_violation_rate for m in committee_metrics], width, label="Constraint violation rate")
        ax1.bar(xs, [m.committee_mean_unique_failure_domain_ratio for m in committee_metrics], width, label="Unique failure-domain ratio")
        ax1.bar([i + width for i in xs], [m.committee_attacker_seat_share for m in committee_metrics], width, label="Attacker seat share")
        ax1.set_ylabel("Rate")
        ax1.set_title("Committee Security & Diversity Metrics")
        ax1.legend()
        ax1.grid(True, linestyle="--", alpha=0.3)

        ax2.bar([i - width for i in xs], [m.committee_fallback_rate for m in committee_metrics], width, label="Fallback rate")
        ax2.bar(xs, [m.committee_objective_mean for m in committee_metrics], width, label="Objective mean")
        ax2.bar([i + width for i in xs], [m.mean_solver_ms for m in committee_metrics], width, label="Mean solver ms")
        ax2.set_ylabel("Mixed scale")
        ax2.set_title("Committee Objective & Overhead")
        ax2.set_xticks(xs)
        ax2.set_xticklabels(committee_names, rotation=15, ha="right")
        ax2.legend()
        ax2.grid(True, linestyle="--", alpha=0.3)

        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, f"eval_committee_metrics_{timestamp}.png"))
        plt.close(fig)

    print(f"\n  Plots saved to {output_dir}/")


def _save_ablation_heatmap(ablation_results: Dict[str, StrategyMetrics], output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    ablation_ids = list(ablation_results.keys())
    metric_names = ["pqi_mean", "attacker_share", "gini_coefficient",
                    "missed_slot_rate", "selection_error_rate", "agreement_rate"]

    data = []
    for abl_id in ablation_ids:
        m = ablation_results[abl_id]
        row = [
            m.pqi_mean,
            m.attacker_share,
            m.gini_coefficient,
            m.missed_slot_rate,
            m.selection_error_rate,
            m.agreement_rate,
        ]
        data.append(row)

    if not data:
        return

    n_rows = len(ablation_ids)
    n_cols = len(metric_names)
    fig, ax = plt.subplots(figsize=(n_cols * 1.8, n_rows * 0.6 + 1))
    im = ax.imshow(data, aspect="auto", cmap="RdYlGn")
    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(metric_names, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(ablation_ids, fontsize=9)
    ax.set_title("Ablation Heatmap (metric × ablation)")
    plt.colorbar(im, ax=ax)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"ablation_heatmap_{timestamp}.png"))
    plt.close(fig)
    print(f"  Ablation heatmap saved to {output_dir}/")


def save_committee_ablation_results(
    cfg: SimulationConfig,
    committee_ablation_metrics: Dict[str, StrategyMetrics],
    output_dir: str,
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"committee_ablations_{timestamp}.json")
    payload = {
        "config": {
            "num_nodes": cfg.num_nodes,
            "num_rounds": cfg.num_rounds,
            "attacker_fraction": cfg.attacker_fraction,
            "committee_k": cfg.committee_k,
            "metadata_profile": cfg.metadata_profile,
            "seed": cfg.seed,
        },
        "committee_ablations": {k: _metrics_to_dict(v) for k, v in committee_ablation_metrics.items()},
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n  Committee ablation JSON saved to {path}")
    return path


def _save_committee_ablation_plots(
    committee_ablation_metrics: Dict[str, StrategyMetrics],
    output_dir: str,
) -> None:
    if not committee_ablation_metrics:
        return

    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    labels = [committee_ablation_metrics[key].name for key in committee_ablation_metrics.keys()]
    metrics = [committee_ablation_metrics[key] for key in committee_ablation_metrics.keys()]
    xs = list(range(len(labels)))
    width = 0.2

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    ax = axes[0][0]
    ax.bar([i - width for i in xs], [m.committee_constraint_violation_rate for m in metrics], width, label="Violation rate")
    ax.bar(xs, [m.committee_mean_unique_failure_domain_ratio for m in metrics], width, label="Unique failure-domain ratio")
    ax.bar([i + width for i in xs], [m.committee_attacker_seat_share for m in metrics], width, label="Attacker seat share")
    ax.set_title("Committee resilience metrics")
    ax.set_ylabel("Rate")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.3)

    ax = axes[0][1]
    ax.bar([i - width / 2 for i in xs], [m.committee_objective_mean for m in metrics], width, label="Objective mean")
    ax.bar([i + width / 2 for i in xs], [m.committee_raw_objective_mean for m in metrics], width, label="Raw objective mean")
    ax.set_title("Committee objective quality")
    ax.set_ylabel("Objective")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.3)

    ax = axes[1][0]
    ax.bar([i - width for i in xs], [m.committee_fallback_rate for m in metrics], width, label="Fallback rate")
    ax.bar(xs, [m.mean_solver_ms for m in metrics], width, label="Mean solver ms")
    ax.bar([i + width for i in xs], [m.p95_block_time_ms for m in metrics], width, label="P95 block time ms")
    ax.set_title("Fallback and latency overhead")
    ax.set_ylabel("Mixed scale")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.3)

    ax = axes[1][1]
    ax.bar([i - width / 2 for i in xs], [m.attacker_share for m in metrics], width, label="Attacker proposer share")
    ax.bar([i + width / 2 for i in xs], [m.missed_slot_rate for m in metrics], width, label="Missed slot rate")
    ax.set_title("Leader-path impact")
    ax.set_ylabel("Rate")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.3)

    for ax in axes[1]:
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=15, ha="right")
    for ax in axes[0]:
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=15, ha="right")

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"committee_ablations_{timestamp}.png"))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4))
    heatmap_metrics = [
        "committee_objective_mean",
        "committee_constraint_violation_rate",
        "committee_mean_unique_failure_domain_ratio",
        "committee_attacker_seat_share",
        "committee_fallback_rate",
        "mean_solver_ms",
    ]
    heatmap_data = []
    for metric in metrics:
        heatmap_data.append([
            metric.committee_objective_mean,
            metric.committee_constraint_violation_rate,
            metric.committee_mean_unique_failure_domain_ratio,
            metric.committee_attacker_seat_share,
            metric.committee_fallback_rate,
            metric.mean_solver_ms,
        ])
    im = ax.imshow(heatmap_data, aspect="auto", cmap="RdYlGn_r")
    ax.set_xticks(range(len(heatmap_metrics)))
    ax.set_xticklabels(heatmap_metrics, rotation=30, ha="right")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_title("Committee ablation overview")
    plt.colorbar(im, ax=ax)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"committee_ablations_heatmap_{timestamp}.png"))
    plt.close(fig)


def save_measurement_overhead_results(
    overhead_metrics: List[MeasurementOverheadMetrics],
    output_dir: str,
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"measurement_overhead_{timestamp}.json")
    payload = {
        "measurement_overhead": [
            {
                "strategy": metric.strategy,
                "num_nodes": metric.num_nodes,
                "num_rounds": metric.num_rounds,
                "window_rounds": metric.window_rounds,
                "num_windows": metric.num_windows,
                "mean_active_nodes": metric.mean_active_nodes,
                "probe_messages_per_window": metric.probe_messages_per_window,
                "probe_bytes_per_window": metric.probe_bytes_per_window,
                "score_construction_cpu_ms": metric.score_construction_cpu_ms,
                "optimization_latency_ms": metric.optimization_latency_ms,
                "end_to_end_selection_ms": metric.end_to_end_selection_ms,
            }
            for metric in overhead_metrics
        ]
    }
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2)
    print(f"\n  Measurement overhead JSON saved to {path}")
    return path


def _save_measurement_overhead_plots(
    overhead_metrics: List[MeasurementOverheadMetrics],
    output_dir: str,
) -> None:
    if not overhead_metrics:
        return

    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    strategies = sorted(set(metric.strategy for metric in overhead_metrics))
    grouped = {
        strategy: sorted(
            [metric for metric in overhead_metrics if metric.strategy == strategy],
            key=lambda item: item.num_nodes,
        )
        for strategy in strategies
    }

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True)
    for strategy, items in grouped.items():
        xs = [item.num_nodes for item in items]
        axes[0][0].plot(xs, [item.probe_messages_per_window for item in items], marker="o", label=strategy)
        axes[0][1].plot(xs, [item.probe_bytes_per_window for item in items], marker="o", label=strategy)
        axes[1][0].plot(xs, [item.score_construction_cpu_ms for item in items], marker="o", label=strategy)
        axes[1][1].plot(xs, [item.optimization_latency_ms for item in items], marker="o", label=strategy)

    axes[0][0].set_title("Probe messages per window")
    axes[0][1].set_title("Probe bytes per window")
    axes[1][0].set_title("Score construction CPU per window")
    axes[1][1].set_title("Optimization latency per window")
    axes[0][0].set_ylabel("Messages")
    axes[0][1].set_ylabel("Bytes")
    axes[1][0].set_ylabel("Milliseconds")
    axes[1][1].set_ylabel("Milliseconds")
    axes[1][0].set_xlabel("Node count")
    axes[1][1].set_xlabel("Node count")

    for row in axes:
        for ax in row:
            ax.grid(True, linestyle="--", alpha=0.3)
            ax.legend()

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"measurement_overhead_{timestamp}.png"))
    plt.close(fig)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def _metrics_to_dict(m: StrategyMetrics) -> dict:
    return {
        "name": m.name,
        "pqi_mean": m.pqi_mean,
        "pqi_p95": m.pqi_p95,
        "missed_slot_rate": m.missed_slot_rate,
        "p95_block_time_ms": m.p95_block_time_ms,
        "nakamoto_coefficient": m.nakamoto_coefficient,
        "attacker_share": m.attacker_share,
        "selection_error_rate": m.selection_error_rate,
        "gini_coefficient": m.gini_coefficient,
        "selection_entropy": m.selection_entropy,
        "selection_concentration": m.selection_concentration,
        "score_selection_spearman": m.score_selection_spearman,
        "agreement_rate": m.agreement_rate,
        "mean_solver_ms": m.mean_solver_ms,
        "view_change_rate": m.view_change_rate,
        "committee_size": m.committee_size,
        "committee_constraint_violation_rate": m.committee_constraint_violation_rate,
        "committee_mean_unique_failure_domain_ratio": m.committee_mean_unique_failure_domain_ratio,
        "committee_attacker_seat_share": m.committee_attacker_seat_share,
        "committee_fallback_rate": m.committee_fallback_rate,
        "committee_objective_mean": m.committee_objective_mean,
        "committee_raw_objective_mean": m.committee_raw_objective_mean,
        "committee_candidate_count_mean": m.committee_candidate_count_mean,
        "proposer_share_trace": list(m.proposer_share_trace),
    }


def _solver_metrics_to_dict(m: SolverComparisonMetrics) -> dict:
    return {
        "candidate_count": m.candidate_count,
        "committee_k": m.committee_k,
        "n_trials": m.n_trials,
        "exact_objective_mean": m.exact_objective_mean,
        "quantum_objective_mean": m.quantum_objective_mean,
        "greedy_objective_mean": m.greedy_objective_mean,
        "weighted_objective_mean": m.weighted_objective_mean,
        "quantum_optimality_gap_mean": m.quantum_optimality_gap_mean,
        "greedy_optimality_gap_mean": m.greedy_optimality_gap_mean,
        "weighted_optimality_gap_mean": m.weighted_optimality_gap_mean,
        "quantum_disagreement_rate": m.quantum_disagreement_rate,
        "greedy_disagreement_rate": m.greedy_disagreement_rate,
        "weighted_disagreement_rate": m.weighted_disagreement_rate,
        "quantum_solver_ms_mean": m.quantum_solver_ms_mean,
        "exact_solver_ms_mean": m.exact_solver_ms_mean,
        "greedy_solver_ms_mean": m.greedy_solver_ms_mean,
        "weighted_solver_ms_mean": m.weighted_solver_ms_mean,
    }


def save_results(
    cfg: SimulationConfig,
    strategy_metrics: List[StrategyMetrics],
    ablation_metrics: Dict[str, StrategyMetrics],
    output_dir: str,
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"evaluation_overhaul_{timestamp}.json")
    payload = {
        "config": {
            "num_nodes": cfg.num_nodes,
            "num_rounds": cfg.num_rounds,
            "attacker_fraction": cfg.attacker_fraction,
            "network_delay_model": cfg.network_delay_model,
            "churn_rate": cfg.churn_rate,
            "measurement_noise": cfg.measurement_noise,
            "committee_k": cfg.committee_k,
            "primary_leader_policy": cfg.primary_leader_policy,
            "metadata_profile": cfg.metadata_profile,
            "metadata_manifest": cfg.metadata_manifest,
            "seed": cfg.seed,
        },
        "strategy_comparison": [_metrics_to_dict(m) for m in strategy_metrics],
        "ablations": {k: _metrics_to_dict(v) for k, v in ablation_metrics.items()},
        "ortools_available": _ORTOOLS_AVAILABLE,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n  JSON results saved to {path}")
    return path


def save_solver_comparison_results(
    cfg: SimulationConfig,
    solver_metrics: List[SolverComparisonMetrics],
    output_dir: str,
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"solver_comparison_{timestamp}.json")
    payload = {
        "config": {
            "committee_k": cfg.committee_k,
            "metadata_profile": cfg.metadata_profile,
            "attacker_fraction": cfg.attacker_fraction,
            "measurement_noise": cfg.measurement_noise,
            "seed": cfg.seed,
            "exact_oracle_max_candidates": cfg.exact_oracle_max_candidates,
        },
        "solver_comparison": [_solver_metrics_to_dict(m) for m in solver_metrics],
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n  Solver comparison JSON saved to {path}")
    return path


def _save_solver_comparison_plot(
    solver_metrics: List[SolverComparisonMetrics],
    output_dir: str,
) -> None:
    if not solver_metrics:
        return

    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    candidate_counts = [m.candidate_count for m in solver_metrics]

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 10), sharex=True)
    ax1.plot(candidate_counts, [m.quantum_optimality_gap_mean for m in solver_metrics], marker="o", label="SA gap")
    ax1.plot(candidate_counts, [m.greedy_optimality_gap_mean for m in solver_metrics], marker="s", label="Greedy gap")
    ax1.plot(candidate_counts, [m.weighted_optimality_gap_mean for m in solver_metrics], marker="^", label="Weighted gap")
    ax1.set_ylabel("Mean optimality gap")
    ax1.set_title("Solver Quality vs Candidate-Set Size")
    ax1.grid(True, linestyle="--", alpha=0.4)
    ax1.legend()

    ax2.plot(candidate_counts, [m.quantum_disagreement_rate for m in solver_metrics], marker="o", label="SA")
    ax2.plot(candidate_counts, [m.greedy_disagreement_rate for m in solver_metrics], marker="s", label="Greedy")
    ax2.plot(candidate_counts, [m.weighted_disagreement_rate for m in solver_metrics], marker="^", label="Weighted")
    ax2.set_ylabel("Disagreement rate")
    ax2.grid(True, linestyle="--", alpha=0.4)
    ax2.legend()

    ax3.plot(candidate_counts, [m.quantum_solver_ms_mean for m in solver_metrics], marker="o", label="SA")
    ax3.plot(candidate_counts, [m.exact_solver_ms_mean for m in solver_metrics], marker="x", label="Exact oracle")
    ax3.plot(candidate_counts, [m.greedy_solver_ms_mean for m in solver_metrics], marker="s", label="Greedy")
    ax3.plot(candidate_counts, [m.weighted_solver_ms_mean for m in solver_metrics], marker="^", label="Weighted")
    ax3.set_xlabel("Candidate-set size M")
    ax3.set_ylabel("Mean solver time (ms)")
    ax3.grid(True, linestyle="--", alpha=0.4)
    ax3.legend()

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"solver_comparison_{timestamp}.png"))
    plt.close(fig)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluation overhaul: large-scale multi-baseline quantum consensus benchmark",
    )
    parser.add_argument("--nodes", type=int, default=100, help="Number of nodes (default: 100)")
    parser.add_argument("--rounds", type=int, default=1000, help="Number of consensus rounds (default: 1000)")
    parser.add_argument("--attacker-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="reports")
    parser.add_argument("--committee-k", type=int, default=5)
    parser.add_argument(
        "--metadata-profile",
        type=str,
        default="synthetic_static",
        choices=["synthetic_static", "clustered_attackers"],
    )
    parser.add_argument(
        "--primary-leader-policy",
        type=str,
        default="highest_score",
        choices=["highest_score", "vrf_hash"],
    )
    parser.add_argument("--exact-oracle-max-candidates", type=int, default=16)
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=None,
        help="Strategies to evaluate (default: all)",
    )
    parser.add_argument(
        "--strategy-preset",
        type=str,
        default=None,
        choices=["all", "committee-all", "literature", "reduced", "reduced-with-exact"],
        help="Use a built-in strategy preset when --strategies is omitted.",
    )
    parser.add_argument(
        "--ablations",
        nargs="*",
        default=None,
        help="Ablation IDs to run (omit flag = none, empty list = all)",
    )
    parser.add_argument("--network-delay", type=str, default="lognormal",
                        choices=["lognormal", "uniform", "none"])
    parser.add_argument("--churn-rate", type=float, default=0.0)
    parser.add_argument("--measurement-noise", type=float, default=0.0)
    parser.add_argument("--max-candidates", type=int, default=100)
    parser.add_argument("--skip-strategy-comparison", action="store_true")
    parser.add_argument("--solver-study", action="store_true")
    parser.add_argument("--solver-study-candidate-sizes", nargs="*", type=int, default=None)
    parser.add_argument("--solver-study-seed-count", type=int, default=5)
    parser.add_argument("--committee-ablation-study", action="store_true")
    parser.add_argument("--committee-ablation-ids", nargs="*", default=None)
    parser.add_argument("--skip-plots", action="store_true")
    args = parser.parse_args()

    cfg = SimulationConfig(
        num_nodes=args.nodes,
        num_rounds=args.rounds,
        attacker_fraction=args.attacker_fraction,
        seed=args.seed,
        output_dir=args.output_dir,
        network_delay_model=args.network_delay,
        churn_rate=args.churn_rate,
        measurement_noise=args.measurement_noise,
        max_candidate_nodes=args.max_candidates,
        committee_k=args.committee_k,
        primary_leader_policy=args.primary_leader_policy,
        metadata_profile=args.metadata_profile,
        exact_oracle_max_candidates=args.exact_oracle_max_candidates,
        solver_study_candidate_sizes=list(args.solver_study_candidate_sizes or [6, 8, 10, 12, 14, 16]),
        solver_study_seed_count=args.solver_study_seed_count,
    )
    run_layout = create_run_layout(cfg.output_dir, "evaluation_overhaul")
    write_run_metadata(
        run_layout,
        {
            "tool": "evaluation_overhaul",
            "layout": run_layout.to_dict(),
            "config": {
                "num_nodes": cfg.num_nodes,
                "num_rounds": cfg.num_rounds,
                "attacker_fraction": cfg.attacker_fraction,
                "seed": cfg.seed,
                "committee_k": cfg.committee_k,
                "strategy_preset": args.strategy_preset,
                "strategies": args.strategies,
                "solver_study": args.solver_study,
                "committee_ablation_study": args.committee_ablation_study,
            },
        },
    )

    selected_strategies = args.strategies
    if selected_strategies is None and args.strategy_preset is not None:
        selected_strategies = resolve_strategy_preset(args.strategy_preset, cfg)

    print("=" * 70)
    print("  EVALUATION OVERHAUL")
    print(f"  nodes={cfg.num_nodes}  rounds={cfg.num_rounds}  seed={cfg.seed}")
    print(f"  network_delay={cfg.network_delay_model}  churn={cfg.churn_rate}  noise={cfg.measurement_noise}")
    print(f"  committee_k={cfg.committee_k}  metadata_profile={cfg.metadata_profile}  leader_policy={cfg.primary_leader_policy}")
    print(f"  run_output={run_layout.root_dir}")
    print(f"  OR-Tools ILP available: {_ORTOOLS_AVAILABLE}")
    print("=" * 70)

    # Strategy comparison
    strategy_metrics: List[StrategyMetrics] = []
    if not args.skip_strategy_comparison:
        strategy_metrics = run_strategy_comparison(cfg, selected_strategies)

    # Ablations
    ablation_metrics: Dict[str, StrategyMetrics] = {}
    if args.ablations is not None:
        abl_ids = list(ABLATION_CONFIGS.keys()) if len(args.ablations) == 0 else args.ablations
        ablation_metrics = run_ablations(cfg, abl_ids)

    # Save JSON
    if strategy_metrics or ablation_metrics:
        save_results(cfg, strategy_metrics, ablation_metrics, run_layout.data_dir)

    # Plots
    if strategy_metrics and not args.skip_plots:
        _save_strategy_plots(strategy_metrics, run_layout.figures_dir)
        if ablation_metrics:
            _save_ablation_heatmap(ablation_metrics, run_layout.figures_dir)

    if args.solver_study:
        solver_metrics = run_solver_comparison_study(
            cfg,
            candidate_sizes=args.solver_study_candidate_sizes,
            seed_count=args.solver_study_seed_count,
        )
        save_solver_comparison_results(cfg, solver_metrics, run_layout.data_dir)
        if not args.skip_plots:
            _save_solver_comparison_plot(solver_metrics, run_layout.figures_dir)

    if args.committee_ablation_study:
        committee_ablation_metrics = run_committee_ablations(
            cfg,
            ablation_ids=args.committee_ablation_ids,
        )
        save_committee_ablation_results(cfg, committee_ablation_metrics, run_layout.data_dir)
        if not args.skip_plots:
            _save_committee_ablation_plots(committee_ablation_metrics, run_layout.figures_dir)

    if strategy_metrics or ablation_metrics:
        _refresh_live_findings_dashboard(cfg.output_dir)


if __name__ == "__main__":
    main()
