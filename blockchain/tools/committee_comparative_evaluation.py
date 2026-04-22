#!/usr/bin/env python3
"""Committee comparative evaluation runner.

Orchestrates the literature-facing committee baseline studies on top of the
existing evaluation harnesses:

- reduced committee baseline comparison
- literature committee comparison
- small-candidate solver study
- committee security studies

Each stage writes into its own subdirectory and this runner emits a manifest
JSON plus a short Markdown summary for reproducibility.
"""

import csv
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


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

from tools.evaluation_overhaul import (  # noqa: E402
    SimulationConfig,
    _save_solver_comparison_plot,
    _save_strategy_plots,
    resolve_strategy_preset,
    run_committee_baseline_comparison,
    run_solver_comparison_study,
    save_results,
    save_solver_comparison_results,
)
from tools.security_experiments import (  # noqa: E402
    run_attacker_fraction_sweep_experiment,
    run_block_withholding_experiment,
    run_correlated_failure_experiment,
    save_security_results,
)
from blockchain.utils.result_layout import create_run_layout, create_stage_layout  # noqa: E402


STRATEGY_LABELS = {
    "committee_quantum": "This work",
    "committee_vrf_stake": "VRF+Stake",
    "committee_reputation": "Reputation",
    "committee_composite_greedy": "Composite greedy",
    "committee_uniform": "Uniform lottery",
    "committee_fairness_only": "Fairness only",
    "committee_exact": "Exact oracle",
    "committee_greedy": "Score-only committee",
    "committee_weighted": "Weighted committee",
}


@dataclass
class ComparativeEvaluationConfig:
    output_dir: str = "reports"
    seed: int = 42
    attacker_fraction: float = 0.2
    committee_k: int = 5
    metadata_profile: str = "clustered_attackers"
    primary_leader_policy: str = "highest_score"
    network_delay_model: str = "lognormal"
    churn_rate: float = 0.0
    measurement_noise: float = 0.0
    max_candidate_nodes: int = 100
    exact_oracle_max_candidates: int = 16
    include_exact_when_safe: bool = True
    skip_plots: bool = False
    run_reduced: bool = True
    run_literature: bool = True
    run_solver: bool = True
    run_security: bool = True
    reduced_nodes: int = 8
    reduced_rounds: int = 25
    literature_nodes: int = 100
    literature_rounds: int = 250
    security_nodes: int = 40
    security_rounds: int = 200
    solver_candidate_sizes: List[int] = field(default_factory=lambda: [6, 8, 10, 12, 14, 16])
    solver_seed_count: int = 5
    security_attacker_fractions: List[float] = field(default_factory=lambda: [0.1, 0.2, 0.33, 0.4])
    security_outage_probabilities: List[float] = field(default_factory=lambda: [0.1, 0.25, 0.5])
    security_withholding_probabilities: List[float] = field(default_factory=lambda: [0.1, 0.25, 0.5])


def _make_simulation_config(
    cfg: ComparativeEvaluationConfig,
    *,
    num_nodes: int,
    num_rounds: int,
) -> SimulationConfig:
    return SimulationConfig(
        num_nodes=num_nodes,
        num_rounds=num_rounds,
        attacker_fraction=cfg.attacker_fraction,
        seed=cfg.seed,
        output_dir=cfg.output_dir,
        network_delay_model=cfg.network_delay_model,
        churn_rate=cfg.churn_rate,
        measurement_noise=cfg.measurement_noise,
        max_candidate_nodes=cfg.max_candidate_nodes,
        committee_k=cfg.committee_k,
        primary_leader_policy=cfg.primary_leader_policy,
        metadata_profile=cfg.metadata_profile,
        exact_oracle_max_candidates=cfg.exact_oracle_max_candidates,
        solver_study_candidate_sizes=list(cfg.solver_candidate_sizes),
        solver_study_seed_count=cfg.solver_seed_count,
    )


def _write_manifest(metadata_dir: str, manifest: Dict[str, Any]) -> str:
    path = os.path.join(metadata_dir, "comparative_manifest.json")
    with open(path, "w") as handle:
        json.dump(manifest, handle, indent=2)
    return path


def _write_summary(metadata_dir: str, manifest: Dict[str, Any]) -> str:
    path = os.path.join(metadata_dir, "comparative_summary.md")
    lines = [
        "# Committee Comparative Evaluation",
        "",
        f"Run directory: {manifest['run_dir']}",
        f"Created at: {manifest['created_at']}",
        "",
        "## Stages",
    ]

    for stage_name, stage_info in manifest["stages"].items():
        lines.append("")
        lines.append(f"### {stage_name}")
        lines.append(f"Output dir: {stage_info['output_dir']}")
        if "strategies" in stage_info:
            lines.append(f"Strategies: {', '.join(stage_info['strategies'])}")
        if "results_json" in stage_info:
            lines.append(f"JSON: {stage_info['results_json']}")
        if "notes" in stage_info:
            lines.append(f"Notes: {stage_info['notes']}")

    if "exports" in manifest:
        lines.append("")
        lines.append("## Exports")
        lines.append(f"Output dir: {manifest['exports']['output_dir']}")
        for label, export_path in manifest["exports"]["files"].items():
            lines.append(f"- {label}: {export_path}")

    with open(path, "w") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r") as handle:
        return json.load(handle)


def _write_csv(path: str, rows: List[Dict[str, Any]], fieldnames: List[str]) -> str:
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return path


def _markdown_table(headers: List[str], rows: List[List[Any]]) -> List[str]:
    if not rows:
        return ["_No rows._"]

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def _strategy_label(strategy: str) -> str:
    return STRATEGY_LABELS.get(strategy, strategy.replace("_", " ").title())


def _format_numeric(value: Any, decimals: int = 3) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.{decimals}f}"
    return str(value)


def _latex_escape(value: Any) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in str(value))


def _write_latex_table(
    path: str,
    *,
    caption: str,
    label: str,
    headers: List[str],
    rows: List[List[Any]],
) -> str:
    column_spec = "l" + "r" * max(0, len(headers) - 1)
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\small",
        f"\\caption{{{_latex_escape(caption)}}}",
        f"\\label{{{label}}}",
        f"\\begin{{tabular}}{{{column_spec}}}",
        "\\hline",
        " " + " & ".join(_latex_escape(header) for header in headers) + r" \\",
        "\\hline",
    ]
    for row in rows:
        lines.append(" " + " & ".join(_latex_escape(cell) for cell in row) + r" \\")
    lines.extend([
        "\\hline",
        "\\end{tabular}",
        "\\end{table}",
        "",
    ])
    with open(path, "w") as handle:
        handle.write("\n".join(lines))
    return path


def _find_strategy_row(rows: List[Dict[str, Any]], strategy: str, field: str = "name") -> Optional[Dict[str, Any]]:
    for row in rows:
        if row.get(field) == strategy:
            return row
    return None


def _filter_comparator_rows(
    rows: List[Dict[str, Any]],
    *,
    field: str,
    excluded: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    excluded_ids = set(excluded or [])
    return [row for row in rows if row.get(field) not in excluded_ids]


def _format_range(values: List[float], *, percent: bool = False, latex: bool = False) -> str:
    if not values:
        return "n/a"
    factor = 100.0 if percent else 1.0
    decimals = 1 if percent else 3
    suffix = r"\%" if percent and latex else "%" if percent else ""
    minimum = min(values) * factor
    maximum = max(values) * factor
    return f"{minimum:.{decimals}f}--{maximum:.{decimals}f}{suffix}"


def _format_scalar(value: Any, *, percent: bool = False, latex: bool = False) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)):
        if percent:
            suffix = r"\%" if latex else "%"
            return f"{100.0 * value:.1f}{suffix}"
        return f"{value:.3f}"
    return str(value)


def _build_paper_narrative(manifest: Dict[str, Any]) -> Dict[str, str]:
    md_lines = [
        "# Paper Narrative Summary",
        "",
        "This auto-generated summary reports observed ranges from the comparative evaluation outputs.",
        "The text is intended as a drafting aid and should still be reviewed for claim scope.",
        "",
    ]
    tex_lines = [
        r"\subsection{Comparative Evaluation Summary}",
        "",
        r"This auto-generated summary reports observed ranges from the comparative evaluation outputs. It is intended as a drafting aid and should still be reviewed for claim scope.",
        "",
    ]

    for stage_name in ("reduced", "literature"):
        stage_info = manifest["stages"].get(stage_name)
        if not stage_info:
            continue
        payload = _load_json(stage_info["results_json"])
        rows = payload.get("strategy_comparison", [])
        this_row = _find_strategy_row(rows, "committee_quantum")
        comparator_rows = _filter_comparator_rows(rows, field="name", excluded=["committee_quantum", "committee_exact"])
        if not this_row or not comparator_rows:
            continue

        violation_range = _format_range([row["committee_constraint_violation_rate"] for row in comparator_rows], percent=True)
        diversity_range = _format_range([row["committee_mean_unique_failure_domain_ratio"] for row in comparator_rows])
        attacker_range = _format_range([row["attacker_share"] for row in comparator_rows], percent=True)

        md_lines.extend([
            f"## {stage_name.title()} Comparison",
            (
                f"This work records PQI mean {_format_scalar(this_row['pqi_mean'])}, attacker share "
                f"{_format_scalar(this_row['attacker_share'], percent=True)}, violation rate "
                f"{_format_scalar(this_row['committee_constraint_violation_rate'], percent=True)}, and diversity ratio "
                f"{_format_scalar(this_row['committee_mean_unique_failure_domain_ratio'])}. "
                f"Across non-oracle baselines, attacker share ranges {attacker_range}, violation rate ranges {violation_range}, "
                f"and diversity ratio ranges {diversity_range}."
            ),
            "",
        ])

        tex_lines.extend([
            f"\\paragraph{{{stage_name.title()} comparison.}} "
            + (
                f"\\emph{{This work}} records PQI mean {_format_scalar(this_row['pqi_mean'], latex=True)}, attacker share "
                f"{_format_scalar(this_row['attacker_share'], percent=True, latex=True)}, violation rate "
                f"{_format_scalar(this_row['committee_constraint_violation_rate'], percent=True, latex=True)}, and diversity ratio "
                f"{_format_scalar(this_row['committee_mean_unique_failure_domain_ratio'], latex=True)}. "
                f"Across non-oracle baselines, attacker share ranges { _format_range([row['attacker_share'] for row in comparator_rows], percent=True, latex=True) }, "
                f"violation rate ranges { _format_range([row['committee_constraint_violation_rate'] for row in comparator_rows], percent=True, latex=True) }, "
                f"and diversity ratio ranges { _format_range([row['committee_mean_unique_failure_domain_ratio'] for row in comparator_rows], latex=True) }."
            ),
            "",
        ])

    solver_stage = manifest["stages"].get("solver")
    if solver_stage:
        payload = _load_json(solver_stage["results_json"])
        rows = payload.get("solver_comparison", [])
        if rows:
            quantum_gap = _format_range([row["quantum_optimality_gap_mean"] for row in rows])
            greedy_gap = _format_range([row["greedy_optimality_gap_mean"] for row in rows])
            weighted_gap = _format_range([row["weighted_optimality_gap_mean"] for row in rows])
            md_lines.extend([
                "## Solver Study",
                (
                    f"Across the solver study candidate sizes, the quantum committee selector has optimality gap {quantum_gap}, "
                    f"compared with greedy gap {greedy_gap} and weighted gap {weighted_gap}."
                ),
                "",
            ])
            tex_lines.extend([
                r"\paragraph{Solver study.} "
                + (
                    f"Across the solver-study candidate sizes, the quantum committee selector has optimality gap "
                    f"{_format_range([row['quantum_optimality_gap_mean'] for row in rows], latex=True)}, compared with greedy gap "
                    f"{_format_range([row['greedy_optimality_gap_mean'] for row in rows], latex=True)} and weighted gap "
                    f"{_format_range([row['weighted_optimality_gap_mean'] for row in rows], latex=True)}."
                ),
                "",
            ])

    security_stage = manifest["stages"].get("security")
    if security_stage:
        payload = _load_json(security_stage["results_json"])
        attacker_rows = payload.get("attacker_fraction_sweep", [])
        correlated_rows = payload.get("correlated_failure", [])
        withholding_rows = payload.get("block_withholding", [])

        this_attacker = [row for row in attacker_rows if row.get("strategy") == "committee_quantum"]
        base_attacker = _filter_comparator_rows(attacker_rows, field="strategy", excluded=["committee_quantum", "committee_exact"])
        if this_attacker and base_attacker:
            md_lines.extend([
                "## Security: Attacker Sweep",
                (
                    f"Across attacker fractions, this work's committee constraint violation ranges "
                    f"{_format_range([row['committee_constraint_violation_rate'] for row in this_attacker], percent=True)} and its missed-slot rate ranges "
                    f"{_format_range([row['missed_slot_rate'] for row in this_attacker], percent=True)}. "
                    f"Across non-oracle baselines, violation rate ranges "
                    f"{_format_range([row['committee_constraint_violation_rate'] for row in base_attacker], percent=True)} and missed-slot rate ranges "
                    f"{_format_range([row['missed_slot_rate'] for row in base_attacker], percent=True)}."
                ),
                "",
            ])
            tex_lines.extend([
                r"\paragraph{Security: attacker sweep.} "
                + (
                    f"Across attacker fractions, \\emph{{This work}} has committee-constraint violation range "
                    f"{_format_range([row['committee_constraint_violation_rate'] for row in this_attacker], percent=True, latex=True)} and missed-slot range "
                    f"{_format_range([row['missed_slot_rate'] for row in this_attacker], percent=True, latex=True)}. "
                    f"Across non-oracle baselines, violation rate ranges "
                    f"{_format_range([row['committee_constraint_violation_rate'] for row in base_attacker], percent=True, latex=True)} and missed-slot rate ranges "
                    f"{_format_range([row['missed_slot_rate'] for row in base_attacker], percent=True, latex=True)}."
                ),
                "",
            ])

        this_corr = [row for row in correlated_rows if row.get("strategy") == "committee_quantum"]
        base_corr = _filter_comparator_rows(correlated_rows, field="strategy", excluded=["committee_quantum", "committee_exact"])
        if this_corr and base_corr:
            md_lines.extend([
                "## Security: Correlated Failure",
                (
                    f"Across outage probabilities, this work's diversity ratio ranges "
                    f"{_format_range([row['mean_unique_failure_domain_ratio'] for row in this_corr])}, its full-committee failure rate ranges "
                    f"{_format_range([row['full_committee_failure_rate'] for row in this_corr], percent=True)}, and its missed-slot rate ranges "
                    f"{_format_range([row['missed_slot_rate'] for row in this_corr], percent=True)}. "
                    f"Across non-oracle baselines, diversity ratio ranges "
                    f"{_format_range([row['mean_unique_failure_domain_ratio'] for row in base_corr])}, full-committee failure rate ranges "
                    f"{_format_range([row['full_committee_failure_rate'] for row in base_corr], percent=True)}, and missed-slot rate ranges "
                    f"{_format_range([row['missed_slot_rate'] for row in base_corr], percent=True)}."
                ),
                "",
            ])
            tex_lines.extend([
                r"\paragraph{Security: correlated failure.} "
                + (
                    f"Across outage probabilities, \\emph{{This work}} has diversity ratio range "
                    f"{_format_range([row['mean_unique_failure_domain_ratio'] for row in this_corr], latex=True)}, full-committee failure range "
                    f"{_format_range([row['full_committee_failure_rate'] for row in this_corr], percent=True, latex=True)}, and missed-slot range "
                    f"{_format_range([row['missed_slot_rate'] for row in this_corr], percent=True, latex=True)}. "
                    f"Across non-oracle baselines, diversity ratio ranges "
                    f"{_format_range([row['mean_unique_failure_domain_ratio'] for row in base_corr], latex=True)}, full-committee failure rate ranges "
                    f"{_format_range([row['full_committee_failure_rate'] for row in base_corr], percent=True, latex=True)}, and missed-slot rate ranges "
                    f"{_format_range([row['missed_slot_rate'] for row in base_corr], percent=True, latex=True)}."
                ),
                "",
            ])

        this_withholding = [row for row in withholding_rows if row.get("strategy") == "committee_quantum"]
        base_withholding = _filter_comparator_rows(withholding_rows, field="strategy", excluded=["committee_quantum", "committee_exact"])
        if this_withholding and base_withholding:
            md_lines.extend([
                "## Security: Block Withholding",
                (
                    f"Across withholding probabilities, this work's fallback activation ranges "
                    f"{_format_range([row['fallback_activation_rate'] for row in this_withholding], percent=True)}, its final attacker proposer share ranges "
                    f"{_format_range([row['final_attacker_proposer_share'] for row in this_withholding], percent=True)}, and its missed-slot rate ranges "
                    f"{_format_range([row['missed_slot_rate'] for row in this_withholding], percent=True)}. "
                    f"Across non-oracle baselines, fallback activation ranges "
                    f"{_format_range([row['fallback_activation_rate'] for row in base_withholding], percent=True)}, final attacker proposer share ranges "
                    f"{_format_range([row['final_attacker_proposer_share'] for row in base_withholding], percent=True)}, and missed-slot rate ranges "
                    f"{_format_range([row['missed_slot_rate'] for row in base_withholding], percent=True)}."
                ),
                "",
            ])
            tex_lines.extend([
                r"\paragraph{Security: block withholding.} "
                + (
                    f"Across withholding probabilities, \\emph{{This work}} has fallback activation range "
                    f"{_format_range([row['fallback_activation_rate'] for row in this_withholding], percent=True, latex=True)}, final attacker proposer share range "
                    f"{_format_range([row['final_attacker_proposer_share'] for row in this_withholding], percent=True, latex=True)}, and missed-slot range "
                    f"{_format_range([row['missed_slot_rate'] for row in this_withholding], percent=True, latex=True)}. "
                    f"Across non-oracle baselines, fallback activation ranges "
                    f"{_format_range([row['fallback_activation_rate'] for row in base_withholding], percent=True, latex=True)}, final attacker proposer share ranges "
                    f"{_format_range([row['final_attacker_proposer_share'] for row in base_withholding], percent=True, latex=True)}, and missed-slot rate ranges "
                    f"{_format_range([row['missed_slot_rate'] for row in base_withholding], percent=True, latex=True)}."
                ),
                "",
            ])

    return {
        "markdown": "\n".join(md_lines) + "\n",
        "latex": "\n".join(tex_lines) + "\n",
    }


def _export_tabular_summaries(exports_dir: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(exports_dir, exist_ok=True)

    export_files: Dict[str, str] = {}
    markdown_lines = [
        "# Comparative Tables",
        "",
        f"Run directory: {manifest['run_dir']}",
        "",
    ]

    headline_rows: List[Dict[str, Any]] = []
    strategy_fieldnames = [
        "stage",
        "name",
        "pqi_mean",
        "pqi_p95",
        "attacker_share",
        "missed_slot_rate",
        "p95_block_time_ms",
        "committee_constraint_violation_rate",
        "committee_mean_unique_failure_domain_ratio",
        "committee_attacker_seat_share",
        "committee_fallback_rate",
        "committee_objective_mean",
        "mean_solver_ms",
        "score_selection_spearman",
    ]

    for stage_name in ("reduced", "literature"):
        stage_info = manifest["stages"].get(stage_name)
        if not stage_info:
            continue
        stage_payload = _load_json(stage_info["results_json"])
        rows = stage_payload.get("strategy_comparison", [])
        if not rows:
            continue

        csv_rows = []
        for row in rows:
            csv_row = {"stage": stage_name, **row}
            csv_rows.append(csv_row)
            headline_rows.append({field: csv_row.get(field, "") for field in strategy_fieldnames})

        csv_path = os.path.join(exports_dir, f"{stage_name}_strategy_summary.csv")
        _write_csv(csv_path, csv_rows, strategy_fieldnames)
        export_files[f"{stage_name}_strategy_summary_csv"] = csv_path

        paper_rows = [
            {
                "strategy": _strategy_label(row["name"]),
                "pqi_mean": row["pqi_mean"],
                "attacker_share": row["attacker_share"],
                "missed_slot_rate": row["missed_slot_rate"],
                "p95_block_time_ms": row["p95_block_time_ms"],
                "violation_rate": row["committee_constraint_violation_rate"],
                "diversity_ratio": row["committee_mean_unique_failure_domain_ratio"],
                "attacker_seat_share": row["committee_attacker_seat_share"],
                "solver_ms": row["mean_solver_ms"],
            }
            for row in rows
        ]
        paper_fields = [
            "strategy",
            "pqi_mean",
            "attacker_share",
            "missed_slot_rate",
            "p95_block_time_ms",
            "violation_rate",
            "diversity_ratio",
            "attacker_seat_share",
            "solver_ms",
        ]
        paper_csv_path = os.path.join(exports_dir, f"{stage_name}_paper_strategy_table.csv")
        _write_csv(paper_csv_path, paper_rows, paper_fields)
        export_files[f"{stage_name}_paper_strategy_csv"] = paper_csv_path

        paper_tex_path = os.path.join(exports_dir, f"{stage_name}_paper_strategy_table.tex")
        _write_latex_table(
            paper_tex_path,
            caption=f"{stage_name.title()} committee baseline comparison.",
            label=f"tab:{stage_name}_committee_baselines",
            headers=[
                "Strategy",
                "PQI mean",
                "Attacker share",
                "Missed slot",
                "P95 ms",
                "Violation",
                "Diversity",
                "Seat share",
                "Solver ms",
            ],
            rows=[
                [
                    row["strategy"],
                    _format_numeric(row["pqi_mean"]),
                    _format_numeric(row["attacker_share"]),
                    _format_numeric(row["missed_slot_rate"]),
                    _format_numeric(row["p95_block_time_ms"]),
                    _format_numeric(row["violation_rate"]),
                    _format_numeric(row["diversity_ratio"]),
                    _format_numeric(row["attacker_seat_share"]),
                    _format_numeric(row["solver_ms"]),
                ]
                for row in paper_rows
            ],
        )
        export_files[f"{stage_name}_paper_strategy_tex"] = paper_tex_path

        markdown_lines.append(f"## {stage_name.title()} Strategy Summary")
        markdown_lines.extend(
            _markdown_table(
                [
                    "strategy",
                    "pqi_mean",
                    "attacker_share",
                    "missed_slot_rate",
                    "violation_rate",
                    "diversity_ratio",
                    "solver_ms",
                ],
                [
                    [
                        row["name"],
                        f"{row['pqi_mean']:.3f}",
                        f"{row['attacker_share']:.3f}",
                        f"{row['missed_slot_rate']:.3f}",
                        f"{row['committee_constraint_violation_rate']:.3f}",
                        f"{row['committee_mean_unique_failure_domain_ratio']:.3f}",
                        f"{row['mean_solver_ms']:.3f}",
                    ]
                    for row in rows
                ],
            )
        )
        markdown_lines.append("")

    if headline_rows:
        headline_csv = os.path.join(exports_dir, "headline_strategy_metrics.csv")
        _write_csv(headline_csv, headline_rows, strategy_fieldnames)
        export_files["headline_strategy_metrics_csv"] = headline_csv

    solver_stage = manifest["stages"].get("solver")
    if solver_stage:
        solver_payload = _load_json(solver_stage["results_json"])
        solver_rows = solver_payload.get("solver_comparison", [])
        if solver_rows:
            solver_fields = [
                "candidate_count",
                "committee_k",
                "n_trials",
                "exact_objective_mean",
                "quantum_objective_mean",
                "greedy_objective_mean",
                "weighted_objective_mean",
                "quantum_optimality_gap_mean",
                "greedy_optimality_gap_mean",
                "weighted_optimality_gap_mean",
                "quantum_solver_ms_mean",
                "exact_solver_ms_mean",
                "greedy_solver_ms_mean",
                "weighted_solver_ms_mean",
            ]
            solver_csv = os.path.join(exports_dir, "solver_summary.csv")
            _write_csv(solver_csv, solver_rows, solver_fields)
            export_files["solver_summary_csv"] = solver_csv

            solver_tex = os.path.join(exports_dir, "solver_summary.tex")
            _write_latex_table(
                solver_tex,
                caption="Small-candidate solver comparison against the exact committee oracle.",
                label="tab:solver_summary",
                headers=[
                    "Candidates",
                    "Exact obj",
                    "Quantum gap",
                    "Greedy gap",
                    "Weighted gap",
                    "Quantum ms",
                    "Exact ms",
                ],
                rows=[
                    [
                        row["candidate_count"],
                        _format_numeric(row["exact_objective_mean"]),
                        _format_numeric(row["quantum_optimality_gap_mean"]),
                        _format_numeric(row["greedy_optimality_gap_mean"]),
                        _format_numeric(row["weighted_optimality_gap_mean"]),
                        _format_numeric(row["quantum_solver_ms_mean"]),
                        _format_numeric(row["exact_solver_ms_mean"]),
                    ]
                    for row in solver_rows
                ],
            )
            export_files["solver_summary_tex"] = solver_tex

            markdown_lines.append("## Solver Summary")
            markdown_lines.extend(
                _markdown_table(
                    [
                        "candidate_count",
                        "exact_obj",
                        "quantum_gap",
                        "greedy_gap",
                        "weighted_gap",
                    ],
                    [
                        [
                            row["candidate_count"],
                            f"{row['exact_objective_mean']:.3f}",
                            f"{row['quantum_optimality_gap_mean']:.3f}",
                            f"{row['greedy_optimality_gap_mean']:.3f}",
                            f"{row['weighted_optimality_gap_mean']:.3f}",
                        ]
                        for row in solver_rows
                    ],
                )
            )
            markdown_lines.append("")

    security_stage = manifest["stages"].get("security")
    if security_stage:
        security_payload = _load_json(security_stage["results_json"])
        security_exports = {
            "security_attacker_sweep_csv": (
                "attacker_fraction_sweep",
                [
                    "strategy",
                    "attacker_fraction",
                    "attacker_proposer_share",
                    "attacker_committee_share",
                    "committee_constraint_violation_rate",
                    "missed_slot_rate",
                    "p95_block_time_ms",
                    "mean_solver_ms",
                    "n_rounds",
                ],
                "security_attacker_sweep.csv",
            ),
            "security_correlated_failure_csv": (
                "correlated_failure",
                [
                    "strategy",
                    "outage_probability",
                    "mean_unique_failure_domain_ratio",
                    "mean_surviving_seat_ratio",
                    "primary_disruption_rate",
                    "recovery_success_rate",
                    "full_committee_failure_rate",
                    "missed_slot_rate",
                    "n_rounds",
                ],
                "security_correlated_failure.csv",
            ),
            "security_block_withholding_csv": (
                "block_withholding",
                [
                    "strategy",
                    "withholding_probability",
                    "fallback_activation_rate",
                    "fallback_success_rate",
                    "mean_recovery_latency_ms",
                    "p95_recovery_latency_ms",
                    "attacker_primary_share_initial",
                    "attacker_primary_share_final",
                    "final_attacker_proposer_share",
                    "missed_slot_rate",
                    "n_rounds",
                ],
                "security_block_withholding.csv",
            ),
        }

        markdown_lines.append("## Security Tables")
        for export_label, (payload_key, fieldnames, filename) in security_exports.items():
            rows = security_payload.get(payload_key, [])
            if not rows:
                continue
            csv_path = os.path.join(exports_dir, filename)
            _write_csv(csv_path, rows, fieldnames)
            export_files[export_label] = csv_path
            markdown_lines.append(f"- {payload_key}: {csv_path} ({len(rows)} rows)")

            tex_path = os.path.join(exports_dir, filename.replace(".csv", ".tex"))
            latex_headers = [field.replace("_", " ") for field in fieldnames]
            latex_rows = []
            for row in rows:
                latex_row = []
                for field in fieldnames:
                    value = row.get(field, "")
                    if field == "strategy":
                        latex_row.append(_strategy_label(str(value)))
                    elif isinstance(value, (int, float)):
                        latex_row.append(_format_numeric(value))
                    else:
                        latex_row.append(value)
                latex_rows.append(latex_row)
            _write_latex_table(
                tex_path,
                caption=f"{payload_key.replace('_', ' ').title()} comparison.",
                label=f"tab:{payload_key}",
                headers=latex_headers,
                rows=latex_rows,
            )
            export_files[export_label.replace("_csv", "_tex")] = tex_path
        markdown_lines.append("")

    table_summary_path = os.path.join(exports_dir, "table_summary.md")
    with open(table_summary_path, "w") as handle:
        handle.write("\n".join(markdown_lines) + "\n")
    export_files["table_summary_markdown"] = table_summary_path

    narrative = _build_paper_narrative(manifest)
    narrative_md_path = os.path.join(exports_dir, "paper_narrative_summary.md")
    with open(narrative_md_path, "w") as handle:
        handle.write(narrative["markdown"])
    export_files["paper_narrative_markdown"] = narrative_md_path

    narrative_tex_path = os.path.join(exports_dir, "paper_narrative_insert.tex")
    with open(narrative_tex_path, "w") as handle:
        handle.write(narrative["latex"])
    export_files["paper_narrative_tex"] = narrative_tex_path

    return {
        "output_dir": exports_dir,
        "files": export_files,
    }


def run_comparative_evaluation(cfg: ComparativeEvaluationConfig) -> Dict[str, Any]:
    run_layout = create_run_layout(cfg.output_dir, "committee_comparative_evaluation")
    run_dir = run_layout.root_dir

    manifest: Dict[str, Any] = {
        "created_at": run_layout.start_timestamp,
        "run_dir": run_dir,
        "layout": run_layout.to_dict(),
        "config": asdict(cfg),
        "stages": {},
    }

    if cfg.run_reduced:
        stage_layout = create_stage_layout(run_layout, "reduced")
        reduced_cfg = _make_simulation_config(cfg, num_nodes=cfg.reduced_nodes, num_rounds=cfg.reduced_rounds)
        preset = "reduced-with-exact" if cfg.include_exact_when_safe else "reduced"
        reduced_metrics = run_committee_baseline_comparison(reduced_cfg, preset=preset)
        reduced_json = save_results(reduced_cfg, reduced_metrics, {}, stage_layout.data_dir)
        if not cfg.skip_plots:
            _save_strategy_plots(reduced_metrics, stage_layout.figures_dir)
        manifest["stages"]["reduced"] = {
            "output_dir": stage_layout.root_dir,
            "data_dir": stage_layout.data_dir,
            "figures_dir": stage_layout.figures_dir,
            "preset": preset,
            "strategies": [metric.name for metric in reduced_metrics],
            "results_json": reduced_json,
        }

    if cfg.run_literature:
        stage_layout = create_stage_layout(run_layout, "literature")
        literature_cfg = _make_simulation_config(cfg, num_nodes=cfg.literature_nodes, num_rounds=cfg.literature_rounds)
        literature_metrics = run_committee_baseline_comparison(literature_cfg, preset="literature")
        literature_json = save_results(literature_cfg, literature_metrics, {}, stage_layout.data_dir)
        if not cfg.skip_plots:
            _save_strategy_plots(literature_metrics, stage_layout.figures_dir)
        manifest["stages"]["literature"] = {
            "output_dir": stage_layout.root_dir,
            "data_dir": stage_layout.data_dir,
            "figures_dir": stage_layout.figures_dir,
            "preset": "literature",
            "strategies": [metric.name for metric in literature_metrics],
            "results_json": literature_json,
        }

    if cfg.run_solver:
        stage_layout = create_stage_layout(run_layout, "solver")
        solver_cfg = _make_simulation_config(
            cfg,
            num_nodes=max(cfg.solver_candidate_sizes) if cfg.solver_candidate_sizes else cfg.exact_oracle_max_candidates,
            num_rounds=1,
        )
        solver_metrics = run_solver_comparison_study(
            solver_cfg,
            candidate_sizes=cfg.solver_candidate_sizes,
            seed_count=cfg.solver_seed_count,
        )
        solver_json = save_solver_comparison_results(solver_cfg, solver_metrics, stage_layout.data_dir)
        if not cfg.skip_plots:
            _save_solver_comparison_plot(solver_metrics, stage_layout.figures_dir)
        manifest["stages"]["solver"] = {
            "output_dir": stage_layout.root_dir,
            "data_dir": stage_layout.data_dir,
            "figures_dir": stage_layout.figures_dir,
            "candidate_sizes": list(cfg.solver_candidate_sizes),
            "results_json": solver_json,
        }

    if cfg.run_security:
        stage_layout = create_stage_layout(run_layout, "security")
        attacker_sweep_results = run_attacker_fraction_sweep_experiment(
            num_nodes=cfg.security_nodes,
            num_rounds=cfg.security_rounds,
            attacker_fractions=cfg.security_attacker_fractions,
            committee_k=cfg.committee_k,
            include_exact_when_safe=cfg.include_exact_when_safe,
            seed=cfg.seed,
            output_dir=stage_layout.figures_dir,
        )
        correlated_failure_results = run_correlated_failure_experiment(
            num_nodes=cfg.security_nodes,
            num_rounds=cfg.security_rounds,
            outage_probabilities=cfg.security_outage_probabilities,
            committee_k=cfg.committee_k,
            attacker_fraction=cfg.attacker_fraction,
            include_exact_when_safe=cfg.include_exact_when_safe,
            seed=cfg.seed,
            output_dir=stage_layout.figures_dir,
        )
        block_withholding_results = run_block_withholding_experiment(
            num_nodes=cfg.security_nodes,
            num_rounds=cfg.security_rounds,
            withholding_probabilities=cfg.security_withholding_probabilities,
            committee_k=cfg.committee_k,
            attacker_fraction=cfg.attacker_fraction,
            include_exact_when_safe=cfg.include_exact_when_safe,
            seed=cfg.seed,
            output_dir=stage_layout.figures_dir,
        )
        security_json = save_security_results(
            [],
            [],
            [],
            correlated_failure_results,
            attacker_sweep_results,
            block_withholding_results,
            stage_layout.data_dir,
        )
        security_strategies = sorted({result.strategy for result in attacker_sweep_results})
        manifest["stages"]["security"] = {
            "output_dir": stage_layout.root_dir,
            "data_dir": stage_layout.data_dir,
            "figures_dir": stage_layout.figures_dir,
            "strategies": security_strategies,
            "results_json": security_json,
            "notes": "Attacker sweep, correlated failure, and block withholding studies",
        }

    manifest["exports"] = _export_tabular_summaries(run_layout.exports_dir, manifest)

    manifest_path = _write_manifest(run_layout.metadata_dir, manifest)
    summary_path = _write_summary(run_layout.metadata_dir, manifest)
    manifest["manifest_path"] = manifest_path
    manifest["summary_path"] = summary_path
    return manifest


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the committee comparative evaluation stack with reproducible outputs.",
    )
    parser.add_argument("--output-dir", type=str, default="reports")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--attacker-fraction", type=float, default=0.2)
    parser.add_argument("--committee-k", type=int, default=5)
    parser.add_argument("--metadata-profile", type=str, default="clustered_attackers")
    parser.add_argument("--primary-leader-policy", type=str, default="highest_score")
    parser.add_argument("--exact-oracle-max-candidates", type=int, default=16)
    parser.add_argument("--max-candidate-nodes", type=int, default=100)
    parser.add_argument("--network-delay", type=str, default="lognormal")
    parser.add_argument("--churn-rate", type=float, default=0.0)
    parser.add_argument("--measurement-noise", type=float, default=0.0)
    parser.add_argument("--reduced-nodes", type=int, default=8)
    parser.add_argument("--reduced-rounds", type=int, default=25)
    parser.add_argument("--literature-nodes", type=int, default=100)
    parser.add_argument("--literature-rounds", type=int, default=250)
    parser.add_argument("--security-nodes", type=int, default=40)
    parser.add_argument("--security-rounds", type=int, default=200)
    parser.add_argument("--solver-candidate-sizes", nargs="*", type=int, default=None)
    parser.add_argument("--solver-seed-count", type=int, default=5)
    parser.add_argument("--security-attacker-fractions", nargs="*", type=float, default=None)
    parser.add_argument("--security-outage-probabilities", nargs="*", type=float, default=None)
    parser.add_argument("--security-withholding-probabilities", nargs="*", type=float, default=None)
    parser.add_argument("--skip-reduced", action="store_true")
    parser.add_argument("--skip-literature", action="store_true")
    parser.add_argument("--skip-solver", action="store_true")
    parser.add_argument("--skip-security", action="store_true")
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--no-exact-when-safe", action="store_true")
    args = parser.parse_args()

    cfg = ComparativeEvaluationConfig(
        output_dir=args.output_dir,
        seed=args.seed,
        attacker_fraction=args.attacker_fraction,
        committee_k=args.committee_k,
        metadata_profile=args.metadata_profile,
        primary_leader_policy=args.primary_leader_policy,
        network_delay_model=args.network_delay,
        churn_rate=args.churn_rate,
        measurement_noise=args.measurement_noise,
        max_candidate_nodes=args.max_candidate_nodes,
        exact_oracle_max_candidates=args.exact_oracle_max_candidates,
        include_exact_when_safe=not args.no_exact_when_safe,
        skip_plots=args.skip_plots,
        run_reduced=not args.skip_reduced,
        run_literature=not args.skip_literature,
        run_solver=not args.skip_solver,
        run_security=not args.skip_security,
        reduced_nodes=args.reduced_nodes,
        reduced_rounds=args.reduced_rounds,
        literature_nodes=args.literature_nodes,
        literature_rounds=args.literature_rounds,
        security_nodes=args.security_nodes,
        security_rounds=args.security_rounds,
        solver_candidate_sizes=list(args.solver_candidate_sizes or [6, 8, 10, 12, 14, 16]),
        solver_seed_count=args.solver_seed_count,
        security_attacker_fractions=list(args.security_attacker_fractions or [0.1, 0.2, 0.33, 0.4]),
        security_outage_probabilities=list(args.security_outage_probabilities or [0.1, 0.25, 0.5]),
        security_withholding_probabilities=list(args.security_withholding_probabilities or [0.1, 0.25, 0.5]),
    )

    print("=" * 72)
    print("  COMMITTEE COMPARATIVE EVALUATION")
    print(f"  reduced={cfg.run_reduced} literature={cfg.run_literature} solver={cfg.run_solver} security={cfg.run_security}")
    print(f"  committee_k={cfg.committee_k} metadata_profile={cfg.metadata_profile} include_exact={cfg.include_exact_when_safe}")
    print("=" * 72)

    manifest = run_comparative_evaluation(cfg)
    print(f"\nManifest: {manifest['manifest_path']}")
    print(f"Summary: {manifest['summary_path']}")


if __name__ == "__main__":
    main()