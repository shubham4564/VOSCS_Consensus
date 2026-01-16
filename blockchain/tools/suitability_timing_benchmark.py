#!/usr/bin/env python3
"""Suitability Score Timing Benchmark
=====================================

This tool benchmarks the time to compute proposer selection based on
suitability scores using:

- A simulated quantum annealer (D-Wave SimulatedAnnealingSampler)
  via the existing QuantumAnnealingConsensus QUBO pipeline.
- A classical greedy selection that directly scans suitability scores
  on a CPU.

It runs the benchmark for a range of node counts and produces:
- A JSON file with raw timing results.
- A PNG plot comparing quantum vs classical selection time.

The script is designed to be flexible and configurable via CLI flags.
"""

import os
import sys
import time
import json
import random
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional


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
class BenchmarkConfig:
    min_nodes: int = 5
    max_nodes: int = 50
    step: int = 5
    trials_per_size: int = 3
    seed: int = 123
    output_dir: str = "reports"
    show: bool = False
    include_quantum: bool = True
    include_classical: bool = True


def _build_synthetic_consensus(num_nodes: int, seed: int) -> Tuple[QuantumAnnealingConsensus, List[str]]:
    """Create a QuantumAnnealingConsensus instance with synthetic node metrics.

    We avoid key generation and probe protocol overhead by directly
    populating the internal nodes structure with reasonable defaults.
    This isolates the cost of suitability scoring and QUBO solving.
    """
    random.seed(seed)

    consensus = QuantumAnnealingConsensus(initialize_genesis=False)

    consensus.nodes = {}
    now = time.time()
    node_ids: List[str] = []

    for i in range(num_nodes):
        node_id = f"node_{i}"
        node_ids.append(node_id)

        # Provide slight variation in metrics so normalization has meaning
        capability = 0.3 + 0.7 * (i / max(1, num_nodes - 1))
        latency = 0.02 + (1.0 - capability) * 0.08  # 20–100ms
        throughput = 10.0 + 90.0 * capability
        success = int(10 * capability)
        failure = int(3 * (1.0 - capability))

        consensus.nodes[node_id] = {
            "public_key": node_id,
            "uptime": 1.0,
            "latency": latency,
            "throughput": throughput,
            "last_seen": now,
            "proposal_success_count": success,
            "proposal_failure_count": failure,
            "performance_history": [],
            "cluster_id": None,
            "trust_score": 0.5,
            "uptime_periods": [(now - 60.0, now)],
            "response_count": 0,
            "measurement_window_start": now,
            "last_registration": now,
        }

    # Clear any performance cache so each benchmark run is consistent
    consensus.node_performance_cache.clear()

    return consensus, node_ids


def _compute_qubo_energy(
    solution: List[int],
    linear: Dict[int, float],
    quadratic: Dict[Tuple[int, int], float],
) -> float:
    """Compute QUBO energy for a binary solution vector.

    E(x) = sum_i Qii x_i + sum_{i<j} Qij x_i x_j
    """
    energy = 0.0
    # Linear terms
    for i, x_i in enumerate(solution):
        if x_i:
            energy += linear.get(i, 0.0)

    # Quadratic terms
    for (i, j), coeff in quadratic.items():
        if solution[i] and solution[j]:
            energy += coeff

    return energy


def _run_local_simulated_annealing(
    linear: Dict[int, float],
    quadratic: Dict[Tuple[int, int], float],
    num_vars: int,
    steps: int = 1000,
    t_start: float = 10.0,
    t_end: float = 0.1,
    seed: Optional[int] = None,
) -> List[int]:
    """Simple in-process simulated annealing over the QUBO.

    This replaces the external library sampler for benchmarking purposes.
    """
    if seed is not None:
        random.seed(seed)

    if num_vars <= 0:
        return []

    # Start from a random 1-hot solution (select one node)
    current = [0] * num_vars
    current[random.randrange(num_vars)] = 1
    current_energy = _compute_qubo_energy(current, linear, quadratic)

    best = current[:]
    best_energy = current_energy

    for step in range(steps):
        # Linear temperature schedule
        frac = step / max(1, steps - 1)
        temperature = t_start + frac * (t_end - t_start)
        if temperature <= 0:
            temperature = 1e-6

        # Propose flipping a random bit
        i = random.randrange(num_vars)
        candidate = current[:]
        candidate[i] = 1 - candidate[i]

        candidate_energy = _compute_qubo_energy(candidate, linear, quadratic)
        delta_e = candidate_energy - current_energy

        # Metropolis acceptance criterion
        if delta_e <= 0 or random.random() < pow(2.718281828, -delta_e / temperature):
            current = candidate
            current_energy = candidate_energy
            if current_energy < best_energy:
                best = current[:]
                best_energy = current_energy

    return best


def _measure_quantum_time(
    consensus: QuantumAnnealingConsensus,
    node_ids: List[str],
    vrf_output: str,
) -> float:
    """Measure time (seconds) for a local simulated annealer over the QUBO.

    We still use QuantumAnnealingConsensus to build the QUBO, but we
    replace the external sampler with a simple in-file simulated
    annealing loop for benchmarking.
    """
    # Build the QUBO first (not included in timing)
    linear, quadratic, _ = consensus.formulate_qubo_problem(vrf_output, node_ids)

    num_vars = len(node_ids)
    # Scale number of steps with number of variables to keep behavior
    # comparable across different network sizes.
    steps = max(200, 50 * num_vars)

    # Only time the local simulated annealer computation
    start = time.time()
    _ = _run_local_simulated_annealing(
        linear=linear,
        quadratic=quadratic,
        num_vars=num_vars,
        steps=steps,
    )
    end = time.time()
    return end - start


def _measure_classical_time(
    consensus: QuantumAnnealingConsensus,
    node_ids: List[str],
) -> float:
    """Measure time (seconds) for classical greedy suitability selection.

    This simply scans all candidate nodes, computes their suitability
    score on the CPU, and picks the best.
    """
    best_score = float("-inf")
    best_node: Optional[str] = None

    start = time.time()
    for node_id in node_ids:
        score = consensus.calculate_suitability_score(node_id)
        if score > best_score:
            best_score = score
            best_node = node_id
    _ = best_node  # not used, but ensures loop is not optimized away
    end = time.time()
    return end - start


def run_benchmark(cfg: BenchmarkConfig) -> Dict[str, List[float]]:
    """Run the timing benchmark over a range of node counts.

    Returns a dict with keys:
    - "node_counts": list of node counts
    - "quantum_ms": mean quantum time per size in milliseconds
    - "classical_ms": mean classical time per size in milliseconds
    """
    results: Dict[str, List[float]] = {
        "node_counts": [],
        "quantum_ms": [],
        "classical_ms": [],
    }

    for n in range(cfg.min_nodes, cfg.max_nodes + 1, cfg.step):
        quantum_times: List[float] = []
        classical_times: List[float] = []

        print(f"\n🔍 Benchmarking suitability selection for {n} nodes...")

        for trial in range(cfg.trials_per_size):
            seed = cfg.seed + n * 1000 + trial
            consensus, node_ids = _build_synthetic_consensus(n, seed)

            # Deterministic VRF-like string for this trial
            vrf_output = f"benchmark_{n}_{trial}_{cfg.seed}"

            if cfg.include_quantum:
                try:
                    qt = _measure_quantum_time(consensus, node_ids, vrf_output)
                    quantum_times.append(qt)
                    print(f"   [trial {trial+1}] Quantum (simulated annealer): {qt*1000:.2f} ms")
                except Exception as e:
                    print(f"   ⚠️ Quantum benchmark failed for n={n}, trial={trial+1}: {e}")

            if cfg.include_classical:
                ct = _measure_classical_time(consensus, node_ids)
                classical_times.append(ct)
                print(f"   [trial {trial+1}] Classical (greedy suitability): {ct*1000:.2f} ms")

        results["node_counts"].append(n)

        if cfg.include_quantum and quantum_times:
            mean_q = sum(quantum_times) / len(quantum_times)
        else:
            mean_q = 0.0
        if cfg.include_classical and classical_times:
            mean_c = sum(classical_times) / len(classical_times)
        else:
            mean_c = 0.0

        results["quantum_ms"].append(mean_q * 1000.0)
        results["classical_ms"].append(mean_c * 1000.0)

        print(
            f"   ✅ n={n}: quantum={mean_q*1000:.2f} ms, classical={mean_c*1000:.2f} ms"
        )

    return results


def _save_results_json(cfg: BenchmarkConfig, results: Dict[str, List[float]], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    payload = {
        "config": cfg.__dict__,
        "results": results,
    }
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)


def _plot_results(cfg: BenchmarkConfig, results: Dict[str, List[float]], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    node_counts = results["node_counts"]
    quantum_ms = results["quantum_ms"]
    classical_ms = results["classical_ms"]

    fig, ax = plt.subplots(figsize=(10, 5))

    if cfg.include_quantum:
        ax.plot(node_counts, quantum_ms, marker="o", label="Quantum (simulated annealer)")
    if cfg.include_classical:
        ax.plot(node_counts, classical_ms, marker="s", label="Classical (greedy suitability)")

    ax.set_xlabel("Number of nodes")
    ax.set_ylabel("Mean selection time (ms)")
    ax.set_title("Suitability-based proposer selection: Quantum vs Classical timing")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()

    plt.tight_layout()
    plt.savefig(output_path)

    if cfg.show:
        plt.show()
    else:
        plt.close(fig)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Benchmark suitability-based proposer selection time: simulated quantum annealer vs classical CPU",
    )
    parser.add_argument("--min-nodes", type=int, default=5, help="Minimum number of nodes")
    parser.add_argument("--max-nodes", type=int, default=50, help="Maximum number of nodes")
    parser.add_argument("--step", type=int, default=5, help="Step size for node count")
    parser.add_argument("--trials", type=int, default=3, help="Trials per node count")
    parser.add_argument("--seed", type=int, default=123, help="Base random seed")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports",
        help="Output directory for JSON and plots (relative to tools/)",
    )
    parser.add_argument(
        "--no-quantum",
        action="store_true",
        help="Disable quantum (simulated annealer) benchmark",
    )
    parser.add_argument(
        "--no-classical",
        action="store_true",
        help="Disable classical greedy benchmark",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display the plot window in addition to saving it",
    )

    args = parser.parse_args()

    cfg = BenchmarkConfig(
        min_nodes=args.min_nodes,
        max_nodes=args.max_nodes,
        step=args.step,
        trials_per_size=args.trials,
        seed=args.seed,
        output_dir=args.output_dir,
        show=args.show,
        include_quantum=not args.no_quantum,
        include_classical=not args.no_classical,
    )

    if cfg.min_nodes <= 0 or cfg.max_nodes <= 0 or cfg.step <= 0:
        raise SystemExit("min-nodes, max-nodes, and step must be positive integers")
    if cfg.min_nodes > cfg.max_nodes:
        raise SystemExit("min-nodes must be <= max-nodes")

    print("🚀 Running suitability timing benchmark...")
    print(
        f"   Node range: {cfg.min_nodes}..{cfg.max_nodes} step {cfg.step}, "
        f"trials: {cfg.trials_per_size}, seed: {cfg.seed}"
    )

    results = run_benchmark(cfg)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    prefix = os.path.join(cfg.output_dir, f"suitability_timing_{timestamp}")

    json_path = f"{prefix}_metrics.json"
    png_path = f"{prefix}_quantum_vs_classical.png"

    _save_results_json(cfg, results, json_path)
    _plot_results(cfg, results, png_path)

    print(f"\n💾 Metrics written to: {json_path}")
    print(f"📈 Plot written to: {png_path}")


if __name__ == "__main__":
    main()
