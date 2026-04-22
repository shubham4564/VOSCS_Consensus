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
)
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