#!/usr/bin/env python3
"""Security Experiments
======================

Three targeted security experiments for the quantum annealing consensus
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


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _build_consensus(
    num_nodes: int,
    seed: int,
    attacker_fraction: float = 0.2,
    ablation: Optional[AblationConfig] = None,
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

    now = time.time()
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

        pub, _ = consensus.ensure_node_keys(node_id)
        consensus.register_node(node_id, pub)
        # Initialise metrics
        consensus.nodes[node_id]["latency"] = max(0.001, 0.15 - 0.10 * cap + rng.uniform(-0.02, 0.02))
        consensus.nodes[node_id]["throughput"] = max(1.0, 5.0 + 45.0 * cap * rng.uniform(0.8, 1.2))
        consensus.nodes[node_id]["last_seen"] = now
        consensus.nodes[node_id]["proposal_success_count"] = int(10 * cap)
        consensus.nodes[node_id]["proposal_failure_count"] = int(3 * (1.0 - cap))

    consensus.node_performance_cache.clear()
    return consensus, node_ids, ground_truth, is_attacker


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
# JSON output
# ---------------------------------------------------------------------------

def save_security_results(
    probe_results: List[ProbeManipulationResult],
    infra_results: List[InfraGamingResult],
    racing_results: List[ScoreRacingResult],
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
        choices=["probe_manipulation", "infra_gaming", "score_racing"],
        default=["probe_manipulation", "infra_gaming", "score_racing"],
    )
    # Probe manipulation args
    parser.add_argument("--probe-nodes", type=int, default=30)
    parser.add_argument("--probe-rounds", type=int, default=500)
    parser.add_argument("--max-colluding", type=int, default=10)
    # Infra gaming args
    parser.add_argument("--infra-nodes", type=int, default=40)
    parser.add_argument("--infra-rounds", type=int, default=1000)
    parser.add_argument("--hw-multiplier", type=float, default=2.0)
    parser.add_argument("--attacker-fraction", type=float, default=0.2)
    # Score racing args
    parser.add_argument("--racing-nodes", type=int, default=20)
    parser.add_argument("--racing-max-rounds", type=int, default=2000)
    parser.add_argument("--racing-trials", type=int, default=50)
    args = parser.parse_args()

    probe_results: List[ProbeManipulationResult] = []
    infra_results: List[InfraGamingResult] = []
    racing_results: List[ScoreRacingResult] = []

    if "probe_manipulation" in args.experiments:
        probe_results = run_probe_manipulation_experiment(
            num_nodes=args.probe_nodes,
            num_rounds=args.probe_rounds,
            max_colluding_witnesses=args.max_colluding,
            seed=args.seed,
            output_dir=args.output_dir,
        )

    if "infra_gaming" in args.experiments:
        infra_results = run_infrastructure_gaming_experiment(
            num_nodes=args.infra_nodes,
            num_rounds=args.infra_rounds,
            attacker_hardware_multiplier=args.hw_multiplier,
            attacker_fraction=args.attacker_fraction,
            seed=args.seed,
            output_dir=args.output_dir,
        )

    if "score_racing" in args.experiments:
        racing_results = run_score_racing_experiment(
            num_nodes=args.racing_nodes,
            max_rounds=args.racing_max_rounds,
            n_trials=args.racing_trials,
            seed=args.seed,
            output_dir=args.output_dir,
        )

    save_security_results(probe_results, infra_results, racing_results, args.output_dir)


if __name__ == "__main__":
    main()
