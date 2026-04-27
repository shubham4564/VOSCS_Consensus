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

from tools.security_experiments import (
    run_attacker_fraction_sweep_experiment,
    run_block_withholding_experiment,
    run_correlated_failure_experiment,
    run_witness_collusion_experiment,
)
from tools.evaluation_overhaul import SimulationConfig, run_simulation
from blockchain.utils.result_layout import create_run_layout


def _figure_output_dir(run_name: str) -> str:
    return create_run_layout("reports", run_name).figures_dir


def test_attacker_fraction_sweep_returns_expected_points():
    results = run_attacker_fraction_sweep_experiment(
        num_nodes=8,
        num_rounds=4,
        attacker_fractions=[0.0, 0.3],
        strategies=["committee_quantum", "committee_greedy"],
        committee_k=3,
        output_dir=_figure_output_dir("test_security_sweep"),
    )

    assert len(results) == 4
    for result in results:
        assert 0.0 <= result.attacker_fraction <= 0.5
        assert 0.0 <= result.attacker_proposer_share <= 1.0
        assert 0.0 <= result.attacker_committee_share <= 1.0
        assert 0.0 <= result.missed_slot_rate <= 1.0
        assert result.estimated_throughput_blocks_per_sec > 0.0
        assert result.throughput_degradation_ratio >= 0.0
        assert result.finality_degradation_ratio >= 0.0

    baseline_results = [result for result in results if result.attacker_fraction == 0.0]
    assert baseline_results
    for result in baseline_results:
        assert result.throughput_degradation_ratio == 0.0
        assert result.finality_degradation_ratio == 0.0


def test_attacker_fraction_sweep_accepts_new_committee_baselines():
    strategies = [
        "committee_uniform",
        "committee_vrf_stake",
        "committee_reputation",
        "committee_composite_greedy",
        "committee_fairness_only",
    ]

    results = run_attacker_fraction_sweep_experiment(
        num_nodes=8,
        num_rounds=3,
        attacker_fractions=[0.2],
        strategies=strategies,
        committee_k=3,
        output_dir=_figure_output_dir("test_security_sweep_new_baselines"),
    )

    assert len(results) == len(strategies)
    for result in results:
        assert result.strategy in strategies
        assert 0.0 <= result.attacker_proposer_share <= 1.0
        assert 0.0 <= result.attacker_committee_share <= 1.0
        assert 0.0 <= result.missed_slot_rate <= 1.0


def test_attacker_fraction_sweep_can_include_exact_when_safe():
    results = run_attacker_fraction_sweep_experiment(
        num_nodes=6,
        num_rounds=2,
        attacker_fractions=[0.2],
        committee_k=3,
        include_exact_when_safe=True,
        output_dir=_figure_output_dir("test_security_sweep_exact"),
    )

    strategies = {result.strategy for result in results}
    assert "committee_exact" in strategies


def test_run_simulation_can_emit_proposer_share_trace():
    cfg = SimulationConfig(
        num_nodes=8,
        num_rounds=5,
        attacker_fraction=0.2,
        committee_k=3,
        seed=17,
        output_dir="reports",
    )

    metrics = run_simulation(cfg, "committee_reputation", verbose=False, trace_interval=2)

    assert metrics.proposer_share_trace
    assert metrics.proposer_share_trace[-1]["round"] == 5
    for point in metrics.proposer_share_trace:
        assert 0.0 <= point["attacker_share"] <= 1.0
        assert 0.0 <= point["gini_coefficient"] <= 1.0
        assert 0.0 <= point["selection_entropy"] <= 1.0
        assert 0.0 <= point["selection_concentration"] <= 1.0
        assert point["round"] >= 1


def test_witness_collusion_experiment_tracks_hypergeometric_bound():
    results = run_witness_collusion_experiment(
        num_nodes=8,
        num_trials=128,
        q_values=[3, 4],
        q_min_values=[1, 2],
        attacker_fraction=0.25,
        output_dir=_figure_output_dir("test_witness_collusion"),
    )

    assert results
    for result in results:
        assert result.q_min <= result.q
        assert 0.0 <= result.measured_capture_rate <= 1.0
        assert 0.0 <= result.hypergeometric_capture_bound <= 1.0
        assert result.absolute_gap >= 0.0


def test_correlated_failure_experiment_reports_resilience_metrics():
    results = run_correlated_failure_experiment(
        num_nodes=8,
        num_rounds=4,
        outage_probabilities=[0.5],
        strategies=["committee_quantum", "committee_greedy"],
        committee_k=3,
        concentrated_top_nodes=4,
        output_dir=_figure_output_dir("test_security_correlated"),
    )

    assert len(results) == 2
    for result in results:
        assert 0.0 <= result.mean_unique_failure_domain_ratio <= 1.0
        assert 0.0 <= result.mean_surviving_seat_ratio <= 1.0
        assert 0.0 <= result.primary_disruption_rate <= 1.0
        assert 0.0 <= result.missed_slot_rate <= 1.0


def test_correlated_failure_experiment_accepts_new_committee_baselines():
    strategies = [
        "committee_uniform",
        "committee_vrf_stake",
        "committee_reputation",
    ]

    results = run_correlated_failure_experiment(
        num_nodes=8,
        num_rounds=4,
        outage_probabilities=[0.5],
        strategies=strategies,
        committee_k=3,
        concentrated_top_nodes=4,
        output_dir=_figure_output_dir("test_security_correlated_new_baselines"),
    )

    assert len(results) == len(strategies)
    for result in results:
        assert result.strategy in strategies
        assert 0.0 <= result.mean_unique_failure_domain_ratio <= 1.0
        assert 0.0 <= result.mean_surviving_seat_ratio <= 1.0
        assert 0.0 <= result.primary_disruption_rate <= 1.0
        assert 0.0 <= result.missed_slot_rate <= 1.0


def test_block_withholding_experiment_reports_fallback_metrics():
    results = run_block_withholding_experiment(
        num_nodes=8,
        num_rounds=4,
        withholding_probabilities=[0.5],
        strategies=["committee_quantum", "committee_greedy"],
        committee_k=3,
        output_dir=_figure_output_dir("test_security_withholding"),
    )

    assert len(results) == 2
    for result in results:
        assert 0.0 <= result.fallback_activation_rate <= 1.0
        assert 0.0 <= result.fallback_success_rate <= 1.0
        assert result.mean_recovery_latency_ms >= 0.0
        assert result.p95_recovery_latency_ms >= 0.0
        assert 0.0 <= result.missed_slot_rate <= 1.0


def test_block_withholding_experiment_accepts_new_committee_baselines():
    strategies = [
        "committee_composite_greedy",
        "committee_fairness_only",
    ]

    results = run_block_withholding_experiment(
        num_nodes=8,
        num_rounds=4,
        withholding_probabilities=[0.5],
        strategies=strategies,
        committee_k=3,
        output_dir=_figure_output_dir("test_security_withholding_new_baselines"),
    )

    assert len(results) == len(strategies)
    for result in results:
        assert result.strategy in strategies
        assert 0.0 <= result.fallback_activation_rate <= 1.0
        assert 0.0 <= result.fallback_success_rate <= 1.0
        assert result.mean_recovery_latency_ms >= 0.0
        assert result.p95_recovery_latency_ms >= 0.0
        assert 0.0 <= result.missed_slot_rate <= 1.0