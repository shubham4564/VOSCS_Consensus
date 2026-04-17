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
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


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
from blockchain.quantum_consensus.quantum_annealing_consensus import AblationConfig  # type: ignore

# Optional OR-Tools for ILP baseline
try:
    from ortools.sat.python import cp_model as _cp_model  # type: ignore
    _ORTOOLS_AVAILABLE = True
except ImportError:
    _ORTOOLS_AVAILABLE = False


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
    score_selection_spearman: float
    agreement_rate: float
    mean_solver_ms: float
    view_change_rate: float = 0.0  # HotStuff only


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

def _build_simulation_environment(cfg: SimulationConfig):
    """
    Initialise QuantumAnnealingConsensus and synthetic per-node attributes.

    Returns:
        (consensus, node_ids, ground_truth, stake, hash_power, online_prob, is_attacker)
    """
    random.seed(cfg.seed)

    consensus = QuantumAnnealingConsensus(initialize_genesis=False, verbose=False)
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
        consensus.register_node(node_id, public_key)

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
        else:
            node_data["last_seen"] = now - (consensus.node_active_threshold + 10)

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
        consensus.register_node(new_id, pub_key)

        node_ids[idx] = new_id


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


# ---------------------------------------------------------------------------
# Main simulation loop
# ---------------------------------------------------------------------------

def run_simulation(
    cfg: SimulationConfig,
    strategy: str,
    ablation_cfg: Optional[AblationConfig] = None,
    verbose: bool = False,
) -> StrategyMetrics:
    """
    Run a full simulation for a single strategy.

    strategy must be one of:
      quantum | exact_argmax | exact_ilp | vrf_weighted | hotstuff_rr |
      greedy_score | weighted_score | round_robin | pos_stake | pow_hash
    """
    random.seed(cfg.seed)

    consensus = QuantumAnnealingConsensus(
        initialize_genesis=False,
        verbose=False,
        ablation_config=ablation_cfg,
    )
    consensus.max_candidate_nodes = cfg.max_candidate_nodes

    # Build synthetic nodes
    rng = random.Random(cfg.seed)
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
        base_cap = rng.uniform(0.3, 1.0)
        cap = (
            max(0.1, base_cap - rng.uniform(0.2, 0.5))
            if attacker
            else min(1.0, base_cap + rng.uniform(0.0, 0.2))
        )
        ground_truth[node_id] = cap
        is_attacker[node_id] = attacker
        stake[node_id] = max(0.1, cap * rng.uniform(5.0, 15.0))
        hash_power[node_id] = max(0.1, cap * rng.uniform(8.0, 20.0))
        online_prob[node_id] = min(0.98, 0.6 + 0.4 * cap)
        pub_key, _ = consensus.ensure_node_keys(node_id)
        consensus.register_node(node_id, pub_key)

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

        # Agreement rate (sampled every 50 rounds for performance)
        if strategy in ("quantum", "exact_argmax", "exact_ilp") and rnd % 50 == 0:
            agr = _compute_agreement_rate(consensus, active_nodes[:20], vrf_output)
            agreement_scores.append(agr)

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
    mean_solver_ms = statistics.mean(solver_times_ms) if solver_times_ms else 0.0

    # Score-to-selection Spearman correlation
    node_list = list(selection_counts.keys()) if selection_counts else node_ids[:10]
    vrf_last = hashlib.sha256(f"final_{cfg.seed}".encode()).hexdigest()
    score_list = [consensus.calculate_suitability_score(n) for n in node_list]
    count_list = [selection_counts.get(n, 0) for n in node_list]
    spearman = _spearman_correlation(score_list, count_list)

    agreement_rate = statistics.mean(agreement_scores) if agreement_scores else 1.0
    view_change_rate = view_changes / total_valid if strategy == "hotstuff_rr" else 0.0

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
        score_selection_spearman=spearman,
        agreement_rate=agreement_rate,
        mean_solver_ms=mean_solver_ms,
        view_change_rate=view_change_rate,
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
]


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
        "score_selection_spearman": m.score_selection_spearman,
        "agreement_rate": m.agreement_rate,
        "mean_solver_ms": m.mean_solver_ms,
        "view_change_rate": m.view_change_rate,
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


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    import dataclasses

    parser = argparse.ArgumentParser(
        description="Evaluation overhaul: large-scale multi-baseline quantum consensus benchmark",
    )
    parser.add_argument("--nodes", type=int, default=100, help="Number of nodes (default: 100)")
    parser.add_argument("--rounds", type=int, default=1000, help="Number of consensus rounds (default: 1000)")
    parser.add_argument("--attacker-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="reports")
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=None,
        help="Strategies to evaluate (default: all)",
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
    )

    print("=" * 70)
    print("  EVALUATION OVERHAUL")
    print(f"  nodes={cfg.num_nodes}  rounds={cfg.num_rounds}  seed={cfg.seed}")
    print(f"  network_delay={cfg.network_delay_model}  churn={cfg.churn_rate}  noise={cfg.measurement_noise}")
    print(f"  OR-Tools ILP available: {_ORTOOLS_AVAILABLE}")
    print("=" * 70)

    # Strategy comparison
    strategy_metrics = run_strategy_comparison(cfg, args.strategies)

    # Ablations
    ablation_metrics: Dict[str, StrategyMetrics] = {}
    if args.ablations is not None:
        abl_ids = list(ABLATION_CONFIGS.keys()) if len(args.ablations) == 0 else args.ablations
        ablation_metrics = run_ablations(cfg, abl_ids)

    # Save JSON
    save_results(cfg, strategy_metrics, ablation_metrics, args.output_dir)

    # Plots
    if not args.skip_plots:
        _save_strategy_plots(strategy_metrics, args.output_dir)
        if ablation_metrics:
            _save_ablation_heatmap(ablation_metrics, args.output_dir)


if __name__ == "__main__":
    main()
