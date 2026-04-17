#!/usr/bin/env python3
"""Suitability Score Timing Benchmark
=====================================

Benchmarks proposer-selection timing for:

- Quantum annealer (local simulated annealing over the QUBO).
- Classical greedy (argmax over suitability scores).
- Direct argmax (argmax over VRF-adjusted effective scores).
- ILP (OR-Tools CP-SAT, optional).
- VRF-weighted random (stake * VRF score).

Supports up to 1 000+ nodes. Produces JSON + log-scale PNG.
"""

import hashlib
import hmac
import os
import sys
import time
import json
import random
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

try:
    from ortools.sat.python import cp_model as _cp_model  # type: ignore
    _ORTOOLS_AVAILABLE = True
except ImportError:
    _ORTOOLS_AVAILABLE = False


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

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from blockchain.quantum_consensus.quantum_annealing_consensus import (  # noqa: E402
    QuantumAnnealingConsensus,
)


@dataclass
class BenchmarkConfig:
    min_nodes: int = 5
    max_nodes: int = 100
    step: int = 10
    trials_per_size: int = 3
    seed: int = 123
    output_dir: str = "reports"
    show: bool = False
    include_quantum: bool = True
    include_classical: bool = True
    include_argmax: bool = True
    include_ilp: bool = False
    include_vrf: bool = True


def _build_synthetic_consensus(
    num_nodes: int, seed: int
) -> Tuple[QuantumAnnealingConsensus, List[str], Dict[str, float]]:
    import io
    from contextlib import redirect_stdout
    random.seed(seed)
    with redirect_stdout(io.StringIO()):
        consensus = QuantumAnnealingConsensus(initialize_genesis=False)
    consensus.nodes = {}
    now = time.time()
    node_ids: List[str] = []

    for i in range(num_nodes):
        node_id = f"node_{i}"
        node_ids.append(node_id)
        capability = 0.3 + 0.7 * (i / max(1, num_nodes - 1))
        latency = 0.02 + (1.0 - capability) * 0.08
        throughput = 10.0 + 90.0 * capability
        success = int(10 * capability)
        failure = int(3 * (1.0 - capability))
        with redirect_stdout(io.StringIO()):
            public_key, _ = consensus.ensure_node_keys(node_id)
            consensus.register_node(node_id, public_key)
        # Overwrite synthetic metrics after registration
        consensus.nodes[node_id].update({
            "uptime": 1.0,
            "latency": latency,
            "throughput": throughput,
            "last_seen": now,
            "proposal_success_count": success,
            "proposal_failure_count": failure,
        })

    consensus.node_performance_cache.clear()

    stake: Dict[str, float] = {}
    for i, node_id in enumerate(node_ids):
        cap = 0.3 + 0.7 * (i / max(1, num_nodes - 1))
        stake[node_id] = max(0.1, cap * 10.0)

    return consensus, node_ids, stake


def _compute_qubo_energy(
    solution: List[int],
    linear: Dict[int, float],
    quadratic: Dict[Tuple[int, int], float],
) -> float:
    energy = 0.0
    for i, x_i in enumerate(solution):
        if x_i:
            energy += linear.get(i, 0.0)
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
    if seed is not None:
        random.seed(seed)
    if num_vars <= 0:
        return []
    current = [0] * num_vars
    current[random.randrange(num_vars)] = 1
    current_energy = _compute_qubo_energy(current, linear, quadratic)
    best = current[:]
    best_energy = current_energy
    for step in range(steps):
        frac = step / max(1, steps - 1)
        temperature = t_start + frac * (t_end - t_start)
        if temperature <= 0:
            temperature = 1e-6
        i = random.randrange(num_vars)
        candidate = current[:]
        candidate[i] = 1 - candidate[i]
        candidate_energy = _compute_qubo_energy(candidate, linear, quadratic)
        delta_e = candidate_energy - current_energy
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
    import io
    from contextlib import redirect_stdout
    with redirect_stdout(io.StringIO()):
        linear, quadratic, _ = consensus.formulate_qubo_problem(vrf_output, node_ids)
    num_vars = len(node_ids)
    steps = max(200, 50 * num_vars)
    start = time.time()
    _run_local_simulated_annealing(
        linear=linear, quadratic=quadratic, num_vars=num_vars, steps=steps
    )
    return time.time() - start


def _measure_classical_time(
    consensus: QuantumAnnealingConsensus,
    node_ids: List[str],
) -> float:
    best_score = float("-inf")
    best_node: Optional[str] = None
    start = time.time()
    for node_id in node_ids:
        score = consensus.calculate_suitability_score(node_id)
        if score > best_score:
            best_score = score
            best_node = node_id
    _ = best_node
    return time.time() - start


def _measure_argmax_time(
    consensus: QuantumAnnealingConsensus,
    node_ids: List[str],
    vrf_output: str,
) -> float:
    import io
    from contextlib import redirect_stdout
    best_score = float("-inf")
    best_node: Optional[str] = None
    start = time.time()
    with redirect_stdout(io.StringIO()):
        for node_id in node_ids:
            score = consensus.calculate_effective_score(node_id, vrf_output)
            if score > best_score:
                best_score = score
                best_node = node_id
    _ = best_node
    return time.time() - start


def _measure_ilp_time(
    consensus: QuantumAnnealingConsensus,
    node_ids: List[str],
    vrf_output: str,
) -> float:
    if not _ORTOOLS_AVAILABLE:
        return _measure_argmax_time(consensus, node_ids, vrf_output)
    scores = {n: consensus.calculate_effective_score(n, vrf_output) for n in node_ids}
    scale = 1_000_000
    int_scores = {n: max(1, int(s * scale + 1e-9)) for n, s in scores.items()}
    start = time.time()
    model = _cp_model.CpModel()
    x = {n: model.NewBoolVar(f"x_{n}") for n in node_ids}
    model.Add(sum(x.values()) == 1)
    model.Maximize(sum(int_scores[n] * x[n] for n in node_ids))
    solver = _cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    solver.Solve(model)
    return time.time() - start


def _measure_vrf_time(
    node_ids: List[str],
    stake: Dict[str, float],
    epoch_seed: str,
) -> float:
    start = time.time()
    weights: List[float] = []
    for n in node_ids:
        vrf_bytes = hmac.new(epoch_seed.encode(), n.encode(), hashlib.sha256).digest()
        vrf_score = int.from_bytes(vrf_bytes[:4], "big") / 0xFFFF_FFFF
        weights.append(max(0.001, stake.get(n, 1.0) * vrf_score))
    total = sum(weights)
    r = random.random() * total
    cumulative = 0.0
    for w in weights:
        cumulative += w
        if r <= cumulative:
            break
    return time.time() - start


def run_benchmark(cfg: BenchmarkConfig) -> Dict[str, List[float]]:
    results: Dict[str, List[float]] = {
        "node_counts": [],
        "quantum_ms": [],
        "classical_ms": [],
        "argmax_ms": [],
        "ilp_ms": [],
        "vrf_ms": [],
    }

    for n in range(cfg.min_nodes, cfg.max_nodes + 1, cfg.step):
        quantum_times: List[float] = []
        classical_times: List[float] = []
        argmax_times: List[float] = []
        ilp_times: List[float] = []
        vrf_times: List[float] = []

        print(f"\n\U0001f50d Benchmarking selection for {n} nodes...")

        for trial in range(cfg.trials_per_size):
            seed = cfg.seed + n * 1000 + trial
            consensus, node_ids, stake = _build_synthetic_consensus(n, seed)
            vrf_output = f"benchmark_{n}_{trial}_{cfg.seed}"
            epoch_seed = f"epoch_{n}_{trial}_{cfg.seed}"

            if cfg.include_quantum:
                try:
                    qt = _measure_quantum_time(consensus, node_ids, vrf_output)
                    quantum_times.append(qt)
                    print(f"   [trial {trial+1}] Quantum (SA): {qt*1000:.2f} ms")
                except Exception as e:
                    print(f"   WARNING Quantum failed n={n} trial={trial+1}: {e}")

            if cfg.include_classical:
                ct = _measure_classical_time(consensus, node_ids)
                classical_times.append(ct)
                print(f"   [trial {trial+1}] Classical (greedy): {ct*1000:.2f} ms")

            if cfg.include_argmax:
                at = _measure_argmax_time(consensus, node_ids, vrf_output)
                argmax_times.append(at)
                print(f"   [trial {trial+1}] Argmax (direct): {at*1000:.2f} ms")

            if cfg.include_ilp:
                if _ORTOOLS_AVAILABLE:
                    it = _measure_ilp_time(consensus, node_ids, vrf_output)
                    ilp_times.append(it)
                    print(f"   [trial {trial+1}] ILP (OR-Tools): {it*1000:.2f} ms")
                else:
                    print(f"   [trial {trial+1}] ILP: OR-Tools not available")

            if cfg.include_vrf:
                vt = _measure_vrf_time(node_ids, stake, epoch_seed)
                vrf_times.append(vt)
                print(f"   [trial {trial+1}] VRF-weighted: {vt*1000:.2f} ms")

        def _mean_ms(ts: List[float]) -> float:
            return (sum(ts) / len(ts) * 1000.0) if ts else 0.0

        results["node_counts"].append(n)
        results["quantum_ms"].append(_mean_ms(quantum_times))
        results["classical_ms"].append(_mean_ms(classical_times))
        results["argmax_ms"].append(_mean_ms(argmax_times))
        results["ilp_ms"].append(_mean_ms(ilp_times))
        results["vrf_ms"].append(_mean_ms(vrf_times))

        q_ms = results["quantum_ms"][-1]
        c_ms = results["classical_ms"][-1]
        a_ms = results["argmax_ms"][-1]
        v_ms = results["vrf_ms"][-1]
        print(
            f"   OK n={n}: quantum={q_ms:.2f}ms "
            f"classical={c_ms:.2f}ms "
            f"argmax={a_ms:.2f}ms "
            f"vrf={v_ms:.2f}ms"
        )

    return results


def _save_results_json(
    cfg: BenchmarkConfig, results: Dict[str, List[float]], output_path: str
) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({"config": cfg.__dict__, "results": results}, f, indent=2)


def _plot_results(
    cfg: BenchmarkConfig, results: Dict[str, List[float]], output_path: str
) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    node_counts = results["node_counts"]
    fig, ax = plt.subplots(figsize=(11, 6))

    if cfg.include_quantum and any(results["quantum_ms"]):
        ax.semilogy(node_counts, [max(1e-3, v) for v in results["quantum_ms"]],
                    marker="o", label="Quantum (simulated annealer)")
    if cfg.include_classical and any(results["classical_ms"]):
        ax.semilogy(node_counts, [max(1e-3, v) for v in results["classical_ms"]],
                    marker="s", label="Classical greedy (suitability)")
    if cfg.include_argmax and any(results["argmax_ms"]):
        ax.semilogy(node_counts, [max(1e-3, v) for v in results["argmax_ms"]],
                    marker="^", linestyle="--", label="Direct argmax (effective score)")
    if cfg.include_ilp and any(results["ilp_ms"]):
        ax.semilogy(node_counts, [max(1e-3, v) for v in results["ilp_ms"]],
                    marker="D", linestyle="-.", label="ILP (OR-Tools CP-SAT)")
    if cfg.include_vrf and any(results["vrf_ms"]):
        ax.semilogy(node_counts, [max(1e-3, v) for v in results["vrf_ms"]],
                    marker="x", linestyle=":", label="VRF-weighted random")

    ax.set_xlabel("Number of nodes")
    ax.set_ylabel("Mean selection time (ms, log scale)")
    ax.set_title("Proposer Selection Timing: All Methods vs Network Size")
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
        description=(
            "Benchmark proposer selection time: simulated quantum annealer, "
            "classical greedy, direct argmax, ILP, and VRF-weighted methods."
        ),
    )
    parser.add_argument("--min-nodes", type=int, default=5)
    parser.add_argument(
        "--max-nodes", type=int, default=100,
        help="Maximum node count (supports 1000+)"
    )
    parser.add_argument("--step", type=int, default=10)
    parser.add_argument("--trials", type=int, default=3, help="Trials per node count")
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--output-dir", type=str, default="reports")
    parser.add_argument("--no-quantum", action="store_true")
    parser.add_argument("--no-classical", action="store_true")
    parser.add_argument("--no-argmax", action="store_true")
    parser.add_argument("--ilp", action="store_true",
                        help="Enable ILP (requires ortools)")
    parser.add_argument("--no-vrf", action="store_true")
    parser.add_argument("--show", action="store_true")
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
        include_argmax=not args.no_argmax,
        include_ilp=args.ilp,
        include_vrf=not args.no_vrf,
    )

    if cfg.min_nodes <= 0 or cfg.max_nodes <= 0 or cfg.step <= 0:
        raise SystemExit("min-nodes, max-nodes, and step must be positive integers")
    if cfg.min_nodes > cfg.max_nodes:
        raise SystemExit("min-nodes must be <= max-nodes")

    print("Running suitability timing benchmark...")
    print(
        f"  Node range: {cfg.min_nodes}..{cfg.max_nodes} step {cfg.step}, "
        f"trials: {cfg.trials_per_size}, seed: {cfg.seed}"
    )
    print(f"  OR-Tools ILP available: {_ORTOOLS_AVAILABLE}")

    results = run_benchmark(cfg)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    prefix = os.path.join(cfg.output_dir, f"suitability_timing_{timestamp}")
    json_path = f"{prefix}_metrics.json"
    png_path = f"{prefix}_timing_comparison.png"

    _save_results_json(cfg, results, json_path)
    _plot_results(cfg, results, png_path)

    print(f"\nMetrics written to: {json_path}")
    print(f"Plot written to: {png_path}")


if __name__ == "__main__":
    main()
