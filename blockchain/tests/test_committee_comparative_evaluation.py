#!/usr/bin/env python3

import json
import os
import sys
import csv


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

from tools.committee_comparative_evaluation import ComparativeEvaluationConfig, run_comparative_evaluation
from tools.evaluation_overhaul import (
    NetworkSimulator,
    SimulationConfig,
    _build_simulation_environment,
    _fairness_only_scores,
    _history_only_scores,
    _record_simulation_selection_feedback,
    _update_round_metrics,
)


def test_run_comparative_evaluation_reduced_only_creates_manifest():
    cfg = ComparativeEvaluationConfig(
        output_dir="reports",
        committee_k=3,
        exact_oracle_max_candidates=6,
        skip_plots=True,
        run_reduced=True,
        run_literature=False,
        run_solver=False,
        run_measurement_overhead=False,
        run_security=False,
        reduced_nodes=6,
        reduced_rounds=2,
    )

    manifest = run_comparative_evaluation(cfg)

    assert os.path.isfile(manifest["manifest_path"])
    assert os.path.isfile(manifest["summary_path"])
    assert os.path.isdir(manifest["exports"]["output_dir"])
    assert os.path.isdir(manifest["layout"]["metadata_dir"])
    assert os.path.isdir(manifest["stages"]["reduced"]["data_dir"])
    assert os.path.isdir(manifest["stages"]["reduced"]["figures_dir"])
    assert set(manifest["stages"].keys()) == {"reduced"}
    assert "committee_exact" in manifest["stages"]["reduced"]["strategies"]
    assert os.path.isfile(manifest["exports"]["files"]["reduced_strategy_summary_csv"])
    assert os.path.isfile(manifest["exports"]["files"]["reduced_paper_strategy_csv"])
    assert os.path.isfile(manifest["exports"]["files"]["reduced_paper_strategy_tex"])
    assert os.path.isfile(manifest["exports"]["files"]["headline_strategy_metrics_csv"])
    assert os.path.isfile(manifest["exports"]["files"]["table_summary_markdown"])
    assert os.path.isfile(manifest["exports"]["files"]["paper_narrative_markdown"])
    assert os.path.isfile(manifest["exports"]["files"]["paper_narrative_tex"])

    with open(manifest["manifest_path"], "r") as handle:
        on_disk_manifest = json.load(handle)

    assert on_disk_manifest["config"]["run_reduced"] is True
    assert set(on_disk_manifest["stages"].keys()) == {"reduced"}
    assert "exports" in on_disk_manifest


def test_simulation_feedback_updates_reputation_and_fairness_state():
    cfg = SimulationConfig(
        num_nodes=6,
        num_rounds=1,
        attacker_fraction=0.0,
        committee_k=3,
        seed=11,
        output_dir="reports",
    )

    consensus, node_ids, ground_truth, stake, hash_power, online_prob, is_attacker = _build_simulation_environment(cfg)
    net_sim = NetworkSimulator(
        model=cfg.network_delay_model,
        mean_ms=cfg.network_delay_mean_ms,
        sigma=cfg.network_delay_sigma,
        seed=cfg.seed,
    )
    online_state = _update_round_metrics(consensus, node_ids, ground_truth, online_prob, net_sim, cfg)
    active_nodes = [node_id for node_id in node_ids if online_state.get(node_id, False)]

    selected = active_nodes[0]
    committee_nodes = active_nodes[: cfg.committee_k]
    _record_simulation_selection_feedback(
        consensus,
        selected=selected,
        committee_nodes=committee_nodes,
    )

    fairness_scores = _fairness_only_scores(consensus, active_nodes)
    history_scores = _history_only_scores(consensus, active_nodes)

    assert len(consensus.selection_history) == 1
    assert consensus.nodes[selected]["proposal_success_count"] == 1
    for node_id in committee_nodes:
        assert consensus.nodes[node_id]["committee_selection_count"] == 1
    assert fairness_scores[selected] < max(fairness_scores[node_id] for node_id in active_nodes if node_id != selected)
    assert history_scores[selected] > min(history_scores[node_id] for node_id in active_nodes if node_id != selected)


def test_run_comparative_evaluation_can_emit_long_horizon_stage():
    cfg = ComparativeEvaluationConfig(
        output_dir="reports",
        skip_plots=True,
        run_reduced=False,
        run_literature=False,
        run_solver=False,
        run_measurement_overhead=False,
        run_security=False,
        run_long_horizon=True,
        security_nodes=8,
        committee_k=7,
        committee_k_values=[4],
        long_horizon_rounds=4,
        long_horizon_trace_interval=2,
        long_horizon_attacker_fractions=[0.2],
        long_horizon_strategies=["committee_reputation"],
    )

    manifest = run_comparative_evaluation(cfg)

    assert "long_horizon" in manifest["stages"]
    assert os.path.isfile(manifest["stages"]["long_horizon"]["results_json"])
    assert os.path.isfile(manifest["exports"]["files"]["long_horizon_summary_csv"])
    assert os.path.isfile(manifest["exports"]["files"]["long_horizon_gini_trace_csv"])

    with open(manifest["exports"]["files"]["long_horizon_gini_trace_csv"], "r", newline="") as handle:
        trace_reader = csv.DictReader(handle)
        trace_fieldnames = trace_reader.fieldnames or []

    assert "selection_entropy" in trace_fieldnames
    assert "selection_concentration" in trace_fieldnames

    with open(manifest["stages"]["long_horizon"]["results_json"], "r") as handle:
        payload = json.load(handle)

    assert len(payload["long_horizon"]) == 1
    row = payload["long_horizon"][0]
    assert row["committee_k"] == 4
    assert row["num_rounds"] == 4
    assert row["proposer_share_trace"]
    assert "selection_entropy" in row
    assert "selection_concentration" in row


def test_run_comparative_evaluation_exports_solver_disagreement_columns():
    cfg = ComparativeEvaluationConfig(
        output_dir="reports",
        skip_plots=True,
        run_reduced=False,
        run_literature=False,
        run_solver=True,
        run_measurement_overhead=False,
        run_security=False,
        run_long_horizon=False,
        committee_k=3,
        exact_oracle_max_candidates=6,
        solver_candidate_sizes=[6],
        solver_seed_count=2,
    )

    manifest = run_comparative_evaluation(cfg)

    solver_csv = manifest["exports"]["files"]["solver_summary_csv"]
    with open(solver_csv, "r", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    assert rows
    assert "quantum_disagreement_rate" in fieldnames
    assert "greedy_disagreement_rate" in fieldnames
    assert "weighted_disagreement_rate" in fieldnames


def test_run_comparative_evaluation_exports_committee_ablation_and_security_degradation_fields():
    cfg = ComparativeEvaluationConfig(
        output_dir="reports",
        skip_plots=True,
        run_reduced=False,
        run_literature=False,
        run_solver=False,
        run_committee_ablation=True,
        run_measurement_overhead=False,
        committee_ablation_nodes=8,
        committee_ablation_rounds=4,
        committee_ablation_ids=["full_objective", "score_only"],
        run_security=True,
        security_nodes=8,
        security_rounds=4,
        security_attacker_fractions=[0.0, 0.49],
        security_correlated_failure_strategies=["committee_quantum", "committee_greedy"],
        security_witness_q_values=[3],
        security_witness_q_min_values=[1, 2],
        security_witness_trials=64,
        security_outage_probabilities=[0.5],
        security_withholding_probabilities=[0.5],
        committee_k=3,
    )

    manifest = run_comparative_evaluation(cfg)

    assert "committee_ablation" in manifest["stages"]
    assert os.path.isfile(manifest["stages"]["committee_ablation"]["results_json"])
    assert os.path.isfile(manifest["exports"]["files"]["committee_ablation_summary_csv"])
    assert os.path.isfile(manifest["exports"]["files"]["committee_ablation_summary_tex"])

    with open(manifest["exports"]["files"]["security_attacker_sweep_csv"], "r", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    assert rows
    assert "estimated_throughput_blocks_per_sec" in fieldnames
    assert "throughput_degradation_ratio" in fieldnames
    assert "finality_degradation_ratio" in fieldnames

    with open(manifest["exports"]["files"]["security_witness_collusion_csv"], "r", newline="") as handle:
        witness_reader = csv.DictReader(handle)
        witness_fieldnames = witness_reader.fieldnames or []
        witness_rows = list(witness_reader)

    assert witness_rows
    assert "hypergeometric_capture_bound" in witness_fieldnames
    assert "absolute_gap" in witness_fieldnames

    with open(manifest["exports"]["files"]["security_correlated_failure_csv"], "r", newline="") as handle:
        correlated_rows = list(csv.DictReader(handle))

    assert {row["strategy"] for row in correlated_rows} == {"committee_mocs", "committee_greedy", "committee_exact"}


def test_run_comparative_evaluation_exports_measurement_overhead_stage():
    cfg = ComparativeEvaluationConfig(
        output_dir="reports",
        skip_plots=True,
        run_reduced=False,
        run_literature=False,
        run_solver=False,
        run_committee_ablation=False,
        run_measurement_overhead=True,
        measurement_overhead_nodes=[8],
        measurement_overhead_rounds=4,
        measurement_overhead_window_rounds=2,
        measurement_overhead_strategies=["committee_quantum", "committee_uniform"],
        run_security=False,
        run_long_horizon=False,
        committee_k=3,
    )

    manifest = run_comparative_evaluation(cfg)

    assert "measurement_overhead" in manifest["stages"]
    assert os.path.isfile(manifest["stages"]["measurement_overhead"]["results_json"])
    assert os.path.isfile(manifest["exports"]["files"]["measurement_overhead_summary_csv"])

    with open(manifest["exports"]["files"]["measurement_overhead_summary_csv"], "r", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    assert rows
    assert "probe_messages_per_window" in fieldnames
    assert "probe_bytes_per_window" in fieldnames
    assert "score_construction_cpu_ms" in fieldnames
    assert "optimization_latency_ms" in fieldnames