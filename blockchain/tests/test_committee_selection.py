#!/usr/bin/env python3

import os
import sys


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

from blockchain.quantum_consensus.quantum_annealing_consensus import QuantumAnnealingConsensus
from tools.evaluation_overhaul import (
    SimulationConfig,
    resolve_strategy_preset,
    run_committee_ablations,
    run_committee_baseline_comparison,
    run_simulation,
    run_solver_comparison_study,
)


def test_register_node_stores_committee_metadata():
    consensus = QuantumAnnealingConsensus(initialize_genesis=False, verbose=False)
    public_key, _ = consensus.ensure_node_keys("meta_node")

    consensus.register_node(
        "meta_node",
        public_key,
        metadata={
            "asn": 64512,
            "cloud_provider": "aws",
            "region": "us-west-2",
            "datacenter": "pdx1",
        },
    )

    metadata = consensus.nodes["meta_node"]["committee_metadata"]
    assert metadata["asn"] == 64512
    assert metadata["cloud_provider"] == "aws"
    assert metadata["region"] == "us-west-2"
    assert metadata["datacenter"] == "pdx1"


def test_select_committee_returns_exact_k_and_primary_leader():
    consensus = QuantumAnnealingConsensus(initialize_genesis=False, verbose=False)
    nodes = []
    node_metadata = [
        {"asn": 64512, "cloud_provider": "aws", "region": "us-west-2", "datacenter": "pdx1"},
        {"asn": 64512, "cloud_provider": "aws", "region": "us-west-2", "datacenter": "pdx1"},
        {"asn": 64513, "cloud_provider": "gcp", "region": "eu-central-1", "datacenter": "fra1"},
        {"asn": 64514, "cloud_provider": "azure", "region": "ap-south-1", "datacenter": "bom1"},
    ]

    for index in range(4):
        node_id = f"committee_{index}"
        public_key, _ = consensus.ensure_node_keys(node_id)
        consensus.register_node(node_id, public_key, metadata=node_metadata[index])
        consensus.nodes[node_id]["latency"] = 0.05 + (index * 0.01)
        consensus.nodes[node_id]["throughput"] = 20.0 + index
        consensus.append_committee_observation(
            node_id,
            uptime_sample=1,
            latency_sample=consensus.nodes[node_id]["latency"],
            throughput_sample=consensus.nodes[node_id]["throughput"],
            anchor_id="leader",
        )
        nodes.append(node_id)

    result = consensus.select_committee("seed123", candidate_nodes=nodes, committee_k=2)

    assert len(result.committee_nodes) == 2
    assert result.primary_leader in result.committee_nodes
    assert result.used_fallback in (True, False)


def test_select_committee_exact_matches_or_beats_greedy_objective():
    consensus = QuantumAnnealingConsensus(initialize_genesis=False, verbose=False)
    nodes = []
    node_metadata = [
        {"asn": 64512, "cloud_provider": "aws", "region": "us-west-2", "datacenter": "pdx1"},
        {"asn": 64512, "cloud_provider": "aws", "region": "us-west-2", "datacenter": "pdx1"},
        {"asn": 64513, "cloud_provider": "gcp", "region": "eu-central-1", "datacenter": "fra1"},
        {"asn": 64514, "cloud_provider": "azure", "region": "ap-south-1", "datacenter": "bom1"},
    ]

    for index in range(4):
        node_id = f"exact_committee_{index}"
        public_key, _ = consensus.ensure_node_keys(node_id)
        consensus.register_node(node_id, public_key, metadata=node_metadata[index])
        consensus.nodes[node_id]["latency"] = 0.05 + (index * 0.01)
        consensus.nodes[node_id]["throughput"] = 20.0 + index
        consensus.append_committee_observation(
            node_id,
            uptime_sample=1,
            latency_sample=consensus.nodes[node_id]["latency"],
            throughput_sample=consensus.nodes[node_id]["throughput"],
            anchor_id="leader",
        )
        nodes.append(node_id)

    exact_result = consensus.select_committee_exact(
        "seed123",
        candidate_nodes=nodes,
        committee_k=2,
        max_exact_candidates=6,
    )
    greedy_committee = nodes[:2]
    greedy_breakdown = consensus.evaluate_committee_selection(
        "seed123",
        greedy_committee,
        candidate_nodes=nodes,
        committee_k=2,
    )

    assert len(exact_result.committee_nodes) == 2
    assert exact_result.primary_leader in exact_result.committee_nodes
    assert exact_result.objective_value <= greedy_breakdown["total_objective"]


def test_committee_quantum_strategy_exposes_committee_metrics():
    cfg = SimulationConfig(
        num_nodes=12,
        num_rounds=6,
        committee_k=3,
        metadata_profile="clustered_attackers",
    )

    metrics = run_simulation(cfg, "committee_quantum")

    assert metrics.committee_size == 3
    assert 0.0 <= metrics.committee_constraint_violation_rate <= 1.0
    assert 0.0 <= metrics.committee_mean_unique_failure_domain_ratio <= 1.0
    assert 0.0 <= metrics.committee_attacker_seat_share <= 1.0


def test_new_committee_baselines_expose_committee_metrics():
    cfg = SimulationConfig(
        num_nodes=12,
        num_rounds=6,
        committee_k=3,
        metadata_profile="clustered_attackers",
        seed=17,
    )

    strategies = [
        "committee_weighted",
        "committee_uniform",
        "committee_vrf_stake",
        "committee_reputation",
        "committee_composite_greedy",
        "committee_fairness_only",
    ]

    for strategy in strategies:
        metrics = run_simulation(cfg, strategy)

        assert metrics.name == strategy
        assert metrics.committee_size == 3
        assert 0.0 <= metrics.committee_constraint_violation_rate <= 1.0
        assert 0.0 <= metrics.committee_mean_unique_failure_domain_ratio <= 1.0
        assert 0.0 <= metrics.committee_attacker_seat_share <= 1.0
        assert metrics.committee_candidate_count_mean >= 0.0


def test_committee_exact_strategy_exposes_committee_metrics():
    cfg = SimulationConfig(
        num_nodes=6,
        num_rounds=4,
        committee_k=3,
        metadata_profile="clustered_attackers",
        exact_oracle_max_candidates=6,
        seed=23,
    )

    metrics = run_simulation(cfg, "committee_exact")

    assert metrics.name == "committee_exact"
    assert metrics.committee_size == 3
    assert 0.0 <= metrics.committee_constraint_violation_rate <= 1.0
    assert 0.0 <= metrics.committee_mean_unique_failure_domain_ratio <= 1.0
    assert metrics.mean_solver_ms >= 0.0


def test_committee_strategy_preset_includes_exact_only_when_safe():
    small_cfg = SimulationConfig(num_nodes=6, exact_oracle_max_candidates=6)
    large_cfg = SimulationConfig(num_nodes=20, exact_oracle_max_candidates=6)

    assert "committee_exact" in resolve_strategy_preset("reduced-with-exact", small_cfg)
    assert "committee_exact" not in resolve_strategy_preset("reduced-with-exact", large_cfg)


def test_run_committee_baseline_comparison_uses_literature_preset():
    cfg = SimulationConfig(
        num_nodes=8,
        num_rounds=2,
        committee_k=3,
        metadata_profile="clustered_attackers",
        seed=29,
    )

    results = run_committee_baseline_comparison(cfg, preset="literature")
    result_names = {result.name for result in results}

    assert "committee_quantum" in result_names
    assert "committee_vrf_stake" in result_names
    assert "committee_reputation" in result_names
    assert "committee_composite_greedy" in result_names
    assert "committee_uniform" in result_names
    assert "committee_fairness_only" in result_names


def test_committee_uniform_uses_zero_correlation_signal():
    cfg = SimulationConfig(
        num_nodes=8,
        num_rounds=4,
        committee_k=3,
        metadata_profile="clustered_attackers",
        seed=37,
    )

    metrics = run_simulation(cfg, "committee_uniform")

    assert metrics.score_selection_spearman == 0.0


def test_solver_comparison_study_reports_exact_oracle_gaps():
    cfg = SimulationConfig(
        num_nodes=6,
        num_rounds=1,
        committee_k=3,
        exact_oracle_max_candidates=6,
        solver_study_candidate_sizes=[6],
        solver_study_seed_count=2,
    )

    results = run_solver_comparison_study(cfg, candidate_sizes=[6], seed_count=2)

    assert len(results) == 1
    result = results[0]
    assert result.candidate_count == 6
    assert result.committee_k == 3
    assert result.n_trials == 2
    assert result.quantum_optimality_gap_mean >= 0.0
    assert result.greedy_optimality_gap_mean >= 0.0
    assert result.weighted_optimality_gap_mean >= 0.0


def test_committee_ablation_study_reports_expected_variants():
    cfg = SimulationConfig(
        num_nodes=10,
        num_rounds=8,
        committee_k=3,
        metadata_profile="clustered_attackers",
    )

    results = run_committee_ablations(
        cfg,
        ablation_ids=["full_objective", "lambda_zero", "w_freq_zero", "score_only"],
    )

    assert set(results.keys()) == {"full_objective", "lambda_zero", "w_freq_zero", "score_only"}
    for metrics in results.values():
        assert metrics.committee_size == 3
        assert 0.0 <= metrics.committee_constraint_violation_rate <= 1.0
        assert 0.0 <= metrics.committee_mean_unique_failure_domain_ratio <= 1.0
        assert metrics.committee_candidate_count_mean >= 0.0