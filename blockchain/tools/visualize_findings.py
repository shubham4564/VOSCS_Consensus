#!/usr/bin/env python3
"""Create a compact findings bundle from reviewer-facing report artifacts."""

from __future__ import annotations

import argparse
import glob
import html
import json
import os
import statistics
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


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

from blockchain.utils.result_layout import create_run_layout, write_run_metadata


EVALUATION_PATTERN = "evaluation_overhaul_*.json"
SECURITY_PATTERN = "security_experiments_*.json"

STRATEGY_COLORS = {
    "committee_quantum": "#D1495B",
    "committee_vrf_stake": "#2E86AB",
    "committee_reputation": "#4F5D75",
    "committee_composite_greedy": "#3D9970",
    "committee_uniform": "#E0A458",
    "committee_fairness_only": "#7B6D8D",
    "committee_exact": "#1F7A8C",
    "committee_greedy": "#2C3E50",
}


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r") as handle:
        return json.load(handle)


def _write_json(path: str, payload: Mapping[str, Any]) -> str:
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2)
    return path


def _discover_paths(search_root: str, pattern: str) -> List[str]:
    search_pattern = os.path.join(search_root, "**", pattern)
    return sorted(glob.glob(search_pattern, recursive=True))


def _discover_latest_path(search_root: str, pattern: str) -> Optional[str]:
    matches = _discover_paths(search_root, pattern)
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)


def _strategy_color(name: str) -> str:
    if name in STRATEGY_COLORS:
        return STRATEGY_COLORS[name]
    return f"C{abs(hash(name)) % 10}"


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return statistics.fmean(items) if items else 0.0


def _aggregate_series(
    records: Sequence[Mapping[str, Any]],
    x_key: str,
    metric_keys: Sequence[str],
) -> Dict[str, List[Dict[str, float]]]:
    buckets: Dict[str, Dict[float, Dict[str, List[float]]]] = {}
    for record in records:
        strategy = str(record.get("strategy", "unknown"))
        x_value = float(record[x_key])
        strategy_bucket = buckets.setdefault(strategy, {})
        value_bucket = strategy_bucket.setdefault(
            x_value,
            {metric_key: [] for metric_key in metric_keys},
        )
        for metric_key in metric_keys:
            raw_value = record.get(metric_key)
            if isinstance(raw_value, (int, float)):
                value_bucket[metric_key].append(float(raw_value))

    aggregated: Dict[str, List[Dict[str, float]]] = {}
    for strategy, strategy_bucket in buckets.items():
        aggregated[strategy] = []
        for x_value in sorted(strategy_bucket):
            point = {x_key: x_value}
            for metric_key, metric_values in strategy_bucket[x_value].items():
                point[metric_key] = _mean(metric_values)
            aggregated[strategy].append(point)
    return aggregated


def _plot_series_grid(
    title: str,
    output_path: str,
    x_key: str,
    x_label: str,
    series: Mapping[str, Sequence[Mapping[str, float]]],
    metric_specs: Sequence[Mapping[str, str]],
) -> str:
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharex=True)
    flat_axes = list(axes.flatten())

    for axis, metric_spec in zip(flat_axes, metric_specs):
        metric_key = metric_spec["key"]
        for strategy, points in series.items():
            axis.plot(
                [point[x_key] for point in points],
                [point.get(metric_key, 0.0) for point in points],
                marker="o",
                linewidth=2,
                label=strategy,
                color=_strategy_color(strategy),
            )
        axis.set_title(metric_spec["title"])
        axis.set_ylabel(metric_spec["ylabel"])
        axis.grid(True, linestyle="--", alpha=0.35)

    flat_axes[2].set_xlabel(x_label)
    flat_axes[3].set_xlabel(x_label)
    handles, labels = flat_axes[0].get_legend_handles_labels()
    if handles:
        flat_axes[0].legend(loc="best")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def _save_evaluation_summary(
    metrics: Sequence[Mapping[str, Any]],
    output_dir: str,
) -> List[str]:
    if not metrics:
        return []

    paths: List[str] = []
    names = [str(metric["name"]) for metric in metrics]
    xs = list(range(len(names)))
    colors = [_strategy_color(name) for name in names]

    summary_path = os.path.join(output_dir, "findings_strategy_summary.png")
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    width = 0.4
    axes[0][0].bar(
        [index - width / 2 for index in xs],
        [float(metric.get("pqi_mean", 0.0)) for metric in metrics],
        width,
        label="PQI mean",
        color="#4C78A8",
    )
    axes[0][0].bar(
        [index + width / 2 for index in xs],
        [float(metric.get("pqi_p95", 0.0)) for metric in metrics],
        width,
        label="PQI p95",
        color="#F58518",
    )
    axes[0][0].set_title("PQI by Strategy")
    axes[0][0].set_ylabel("Proposer Quality Index")
    axes[0][0].set_xticks(xs)
    axes[0][0].set_xticklabels(names, rotation=15, ha="right")
    axes[0][0].legend()

    axes[0][1].bar(names, [float(metric.get("agreement_rate", 0.0)) for metric in metrics], color=colors)
    axes[0][1].set_ylim(0.0, 1.05)
    axes[0][1].set_title("Agreement Rate by Strategy")
    axes[0][1].set_ylabel("Agreement rate")
    axes[0][1].tick_params(axis="x", rotation=15)

    grouped_width = 0.25
    axes[1][0].bar(
        [index - grouped_width for index in xs],
        [float(metric.get("gini_coefficient", 0.0)) for metric in metrics],
        grouped_width,
        label="Gini coeff",
        color="#4C78A8",
    )
    axes[1][0].bar(
        xs,
        [float(metric.get("attacker_share", 0.0)) for metric in metrics],
        grouped_width,
        label="Attacker share",
        color="#F58518",
    )
    axes[1][0].bar(
        [index + grouped_width for index in xs],
        [float(metric.get("selection_error_rate", 0.0)) for metric in metrics],
        grouped_width,
        label="Selection error rate",
        color="#54A24B",
    )
    axes[1][0].set_title("Security and Fairness Metrics")
    axes[1][0].set_ylabel("Rate / coefficient")
    axes[1][0].set_xticks(xs)
    axes[1][0].set_xticklabels(names, rotation=15, ha="right")
    axes[1][0].legend()

    axes[1][1].bar(names, [float(metric.get("mean_solver_ms", 0.0)) for metric in metrics], color=colors)
    axes[1][1].set_yscale("log")
    axes[1][1].set_title("Solver Time by Strategy")
    axes[1][1].set_ylabel("Mean solver time (ms, log scale)")
    axes[1][1].tick_params(axis="x", rotation=15)

    for row in axes:
        for axis in row:
            axis.grid(True, linestyle="--", alpha=0.3)

    fig.tight_layout()
    fig.savefig(summary_path, dpi=150)
    plt.close(fig)
    paths.append(summary_path)

    committee_metrics = [metric for metric in metrics if int(metric.get("committee_size", 0)) > 1]
    if committee_metrics:
        committee_names = [str(metric["name"]) for metric in committee_metrics]
        committee_xs = list(range(len(committee_names)))
        committee_path = os.path.join(output_dir, "findings_committee_summary.png")
        fig, (axis_top, axis_bottom) = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
        bar_width = 0.2

        axis_top.bar(
            [index - bar_width for index in committee_xs],
            [float(metric.get("committee_constraint_violation_rate", 0.0)) for metric in committee_metrics],
            bar_width,
            label="Constraint violation rate",
        )
        axis_top.bar(
            committee_xs,
            [float(metric.get("committee_mean_unique_failure_domain_ratio", 0.0)) for metric in committee_metrics],
            bar_width,
            label="Unique failure-domain ratio",
        )
        axis_top.bar(
            [index + bar_width for index in committee_xs],
            [float(metric.get("committee_attacker_seat_share", 0.0)) for metric in committee_metrics],
            bar_width,
            label="Attacker seat share",
        )
        axis_top.set_title("Committee Security and Diversity Metrics")
        axis_top.set_ylabel("Rate")
        axis_top.legend()
        axis_top.grid(True, linestyle="--", alpha=0.3)

        axis_bottom.bar(
            [index - bar_width for index in committee_xs],
            [float(metric.get("committee_fallback_rate", 0.0)) for metric in committee_metrics],
            bar_width,
            label="Fallback rate",
        )
        axis_bottom.bar(
            committee_xs,
            [float(metric.get("committee_objective_mean", 0.0)) for metric in committee_metrics],
            bar_width,
            label="Objective mean",
        )
        axis_bottom.bar(
            [index + bar_width for index in committee_xs],
            [float(metric.get("mean_solver_ms", 0.0)) for metric in committee_metrics],
            bar_width,
            label="Mean solver ms",
        )
        axis_bottom.set_title("Committee Objective and Overhead")
        axis_bottom.set_ylabel("Mixed scale")
        axis_bottom.set_xticks(committee_xs)
        axis_bottom.set_xticklabels(committee_names, rotation=15, ha="right")
        axis_bottom.legend()
        axis_bottom.grid(True, linestyle="--", alpha=0.3)

        fig.tight_layout()
        fig.savefig(committee_path, dpi=150)
        plt.close(fig)
        paths.append(committee_path)

    return paths


def _save_probe_manipulation(records: Sequence[Mapping[str, Any]], output_dir: str) -> List[str]:
    if not records:
        return []

    ordered = sorted(records, key=lambda record: float(record.get("num_colluding_witnesses", 0.0)))
    path = os.path.join(output_dir, "findings_probe_manipulation.png")
    fig, axis_left = plt.subplots(figsize=(10, 5))
    axis_right = axis_left.twinx()

    colluding = [float(record.get("num_colluding_witnesses", 0.0)) for record in ordered]
    axis_left.plot(colluding, [float(record.get("flip_rate", 0.0)) for record in ordered], marker="o", color="#D1495B", label="Flip rate")
    axis_right.plot(colluding, [float(record.get("mean_inflation_ms", 0.0)) for record in ordered], marker="s", color="#2E86AB", label="Mean inflation ms")
    axis_left.set_title("Probe Manipulation Sensitivity")
    axis_left.set_xlabel("Colluding witnesses")
    axis_left.set_ylabel("Flip rate")
    axis_right.set_ylabel("Mean inflation (ms)")
    axis_left.grid(True, linestyle="--", alpha=0.3)

    handles_left, labels_left = axis_left.get_legend_handles_labels()
    handles_right, labels_right = axis_right.get_legend_handles_labels()
    axis_left.legend(handles_left + handles_right, labels_left + labels_right, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return [path]


def _save_infrastructure_gaming(records: Sequence[Mapping[str, Any]], output_dir: str) -> List[str]:
    if not records:
        return []

    ordered = sorted(records, key=lambda record: float(record.get("round", 0.0)))
    path = os.path.join(output_dir, "findings_infrastructure_gaming.png")
    fig, (axis_top, axis_bottom) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    rounds = [float(record.get("round", 0.0)) for record in ordered]
    axis_top.plot(rounds, [float(record.get("attacker_cumulative_share", 0.0)) for record in ordered], marker="o", color="#D1495B")
    axis_top.set_title("Infrastructure Gaming: Attacker Selection Share")
    axis_top.set_ylabel("Cumulative attacker share")
    axis_top.grid(True, linestyle="--", alpha=0.3)

    axis_bottom.plot(rounds, [float(record.get("best_attacker_score", 0.0)) for record in ordered], marker="o", label="Best attacker score", color="#D1495B")
    axis_bottom.plot(rounds, [float(record.get("best_honest_score", 0.0)) for record in ordered], marker="s", label="Best honest score", color="#2E86AB")
    axis_bottom.set_title("Infrastructure Gaming: Score Envelope")
    axis_bottom.set_xlabel("Round")
    axis_bottom.set_ylabel("Score")
    axis_bottom.legend()
    axis_bottom.grid(True, linestyle="--", alpha=0.3)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return [path]


def _save_score_racing(records: Sequence[Mapping[str, Any]], output_dir: str) -> List[str]:
    if not records:
        return []

    ordered = sorted(records, key=lambda record: float(record.get("w_freq", 0.0)))
    path = os.path.join(output_dir, "findings_score_racing.png")
    fig, axis_left = plt.subplots(figsize=(10, 5))
    axis_right = axis_left.twinx()

    weights = [float(record.get("w_freq", 0.0)) for record in ordered]
    axis_left.plot(weights, [float(record.get("rounds_until_rotation_mean", 0.0)) for record in ordered], marker="o", label="Mean rounds until rotation", color="#2E86AB")
    axis_left.plot(weights, [float(record.get("rounds_until_rotation_p95", 0.0)) for record in ordered], marker="s", label="P95 rounds until rotation", color="#4F5D75")
    axis_right.bar(weights, [float(record.get("rotation_count", 0.0)) for record in ordered], width=0.02, alpha=0.25, color="#D1495B", label="Rotation count")
    axis_left.set_title("Score Racing / Fairness Bound")
    axis_left.set_xlabel("w_freq")
    axis_left.set_ylabel("Rounds")
    axis_right.set_ylabel("Rotations")
    axis_left.grid(True, linestyle="--", alpha=0.3)

    handles_left, labels_left = axis_left.get_legend_handles_labels()
    handles_right, labels_right = axis_right.get_legend_handles_labels()
    axis_left.legend(handles_left + handles_right, labels_left + labels_right, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return [path]


def _save_attacker_sweep(records: Sequence[Mapping[str, Any]], output_dir: str) -> List[str]:
    if not records:
        return []

    series = _aggregate_series(
        records,
        "attacker_fraction",
        [
            "attacker_proposer_share",
            "attacker_committee_share",
            "committee_constraint_violation_rate",
            "missed_slot_rate",
            "p95_block_time_ms",
            "mean_solver_ms",
        ],
    )

    paths = [
        _plot_series_grid(
            "Attacker Fraction Outcomes",
            os.path.join(output_dir, "findings_attacker_sweep.png"),
            "attacker_fraction",
            "Attacker fraction",
            series,
            [
                {"key": "attacker_proposer_share", "title": "Attacker proposer share", "ylabel": "Rate"},
                {"key": "attacker_committee_share", "title": "Attacker committee share", "ylabel": "Rate"},
                {"key": "missed_slot_rate", "title": "Missed-slot rate", "ylabel": "Rate"},
                {"key": "p95_block_time_ms", "title": "P95 block time", "ylabel": "Milliseconds"},
            ],
        )
    ]

    robustness_path = os.path.join(output_dir, "findings_attacker_sweep_overhead.png")
    fig, axis = plt.subplots(figsize=(12, 6))
    for strategy, points in series.items():
        fractions = [point["attacker_fraction"] for point in points]
        axis.plot(
            fractions,
            [point.get("committee_constraint_violation_rate", 0.0) for point in points],
            marker="o",
            linewidth=2,
            label=f"{strategy} violation",
            color=_strategy_color(strategy),
        )
        axis.plot(
            fractions,
            [point.get("mean_solver_ms", 0.0) for point in points],
            marker="s",
            linestyle="--",
            linewidth=1.5,
            label=f"{strategy} solver ms",
            color=_strategy_color(strategy),
        )
    axis.set_title("Committee Robustness and Overhead vs Attacker Fraction")
    axis.set_xlabel("Attacker fraction")
    axis.set_ylabel("Rate / milliseconds")
    axis.grid(True, linestyle="--", alpha=0.35)
    axis.legend(loc="best")
    fig.tight_layout()
    fig.savefig(robustness_path, dpi=150)
    plt.close(fig)
    paths.append(robustness_path)
    return paths


def _save_correlated_failure(records: Sequence[Mapping[str, Any]], output_dir: str) -> List[str]:
    if not records:
        return []

    series = _aggregate_series(
        records,
        "outage_probability",
        [
            "mean_unique_failure_domain_ratio",
            "mean_surviving_seat_ratio",
            "primary_disruption_rate",
            "full_committee_failure_rate",
        ],
    )
    path = _plot_series_grid(
        "Correlated Failure Resilience",
        os.path.join(output_dir, "findings_correlated_failure.png"),
        "outage_probability",
        "Outage probability",
        series,
        [
            {"key": "mean_unique_failure_domain_ratio", "title": "Committee diversity", "ylabel": "Ratio"},
            {"key": "mean_surviving_seat_ratio", "title": "Mean surviving seat ratio", "ylabel": "Ratio"},
            {"key": "primary_disruption_rate", "title": "Primary disruption rate", "ylabel": "Rate"},
            {"key": "full_committee_failure_rate", "title": "Full committee failure rate", "ylabel": "Rate"},
        ],
    )
    return [path]


def _save_block_withholding(records: Sequence[Mapping[str, Any]], output_dir: str) -> List[str]:
    if not records:
        return []

    series = _aggregate_series(
        records,
        "withholding_probability",
        [
            "fallback_activation_rate",
            "p95_recovery_latency_ms",
            "attacker_primary_share_initial",
            "attacker_primary_share_final",
            "missed_slot_rate",
        ],
    )
    path = os.path.join(output_dir, "findings_block_withholding.png")
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharex=True)

    for strategy, points in series.items():
        probabilities = [point["withholding_probability"] for point in points]
        color = _strategy_color(strategy)
        axes[0][0].plot(probabilities, [point.get("fallback_activation_rate", 0.0) for point in points], marker="o", label=strategy, color=color)
        axes[0][1].plot(probabilities, [point.get("p95_recovery_latency_ms", 0.0) for point in points], marker="o", label=strategy, color=color)
        axes[1][0].plot(probabilities, [point.get("attacker_primary_share_initial", 0.0) for point in points], marker="o", linestyle="--", label=f"{strategy} initial", color=color)
        axes[1][0].plot(probabilities, [point.get("attacker_primary_share_final", 0.0) for point in points], marker="o", label=f"{strategy} final", color=color)
        axes[1][1].plot(probabilities, [point.get("missed_slot_rate", 0.0) for point in points], marker="o", label=strategy, color=color)

    axes[0][0].set_title("Fallback activation rate")
    axes[0][0].set_ylabel("Rate")
    axes[0][1].set_title("P95 recovery latency")
    axes[0][1].set_ylabel("Milliseconds")
    axes[1][0].set_title("Attacker primary share before vs after penalties")
    axes[1][0].set_ylabel("Rate")
    axes[1][1].set_title("Missed-slot rate")
    axes[1][1].set_ylabel("Rate")
    axes[1][0].set_xlabel("Withholding probability")
    axes[1][1].set_xlabel("Withholding probability")

    for row in axes:
        for axis in row:
            axis.grid(True, linestyle="--", alpha=0.35)
            axis.legend(loc="best")

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return [path]


def _merge_security_payloads(paths: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
    merged = {
        "probe_manipulation": [],
        "infrastructure_gaming": [],
        "score_racing": [],
        "correlated_failure": [],
        "attacker_fraction_sweep": [],
        "block_withholding": [],
    }
    for path in paths:
        payload = _load_json(path)
        for key in merged:
            section = payload.get(key, [])
            if isinstance(section, list):
                merged[key].extend(section)
    return merged


def _select_metric(
    metrics: Sequence[Mapping[str, Any]],
    key: str,
    *,
    reverse: bool,
) -> Optional[Mapping[str, Any]]:
    numeric = [metric for metric in metrics if isinstance(metric.get(key), (int, float))]
    if not numeric:
        return None
    return sorted(numeric, key=lambda metric: float(metric[key]), reverse=reverse)[0]


def _build_strategy_highlights(metrics: Sequence[Mapping[str, Any]]) -> List[str]:
    if not metrics:
        return []

    highlights: List[str] = []
    best_pqi = _select_metric(metrics, "pqi_mean", reverse=True)
    fastest_solver = _select_metric(metrics, "mean_solver_ms", reverse=False)
    lowest_attacker = _select_metric(metrics, "attacker_share", reverse=False)
    lowest_violation = _select_metric(metrics, "committee_constraint_violation_rate", reverse=False)

    if best_pqi:
        highlights.append(f"Best PQI mean: {best_pqi['name']} ({float(best_pqi['pqi_mean']):.3f})")
    if fastest_solver:
        highlights.append(f"Fastest solver: {fastest_solver['name']} ({float(fastest_solver['mean_solver_ms']):.3f} ms)")
    if lowest_attacker:
        highlights.append(f"Lowest attacker proposer share: {lowest_attacker['name']} ({float(lowest_attacker['attacker_share']):.3f})")
    if lowest_violation:
        highlights.append(
            f"Lowest committee violation rate: {lowest_violation['name']} ({float(lowest_violation['committee_constraint_violation_rate']):.3f})"
        )
    return highlights


def _write_summary_markdown(
    output_path: str,
    evaluation_path: Optional[str],
    security_paths: Sequence[str],
    metrics: Sequence[Mapping[str, Any]],
    merged_security: Mapping[str, Sequence[Mapping[str, Any]]],
    figure_paths: Sequence[str],
) -> str:
    lines = ["# Findings Overview", ""]
    if evaluation_path:
        lines.append(f"Evaluation source: `{evaluation_path}`")
    if security_paths:
        lines.append("Security sources:")
        for path in security_paths:
            lines.append(f"- `{path}`")
    lines.append("")

    strategy_highlights = _build_strategy_highlights(metrics)
    if strategy_highlights:
        lines.append("## Strategy Highlights")
        for highlight in strategy_highlights:
            lines.append(f"- {highlight}")
        lines.append("")

    populated_sections = {key: value for key, value in merged_security.items() if value}
    if populated_sections:
        lines.append("## Security Coverage")
        for key, value in populated_sections.items():
            lines.append(f"- `{key}` records: {len(value)}")
        lines.append("")

    if figure_paths:
        lines.append("## Generated Figures")
        for path in figure_paths:
            lines.append(f"- `{path}`")
        lines.append("")

    with open(output_path, "w") as handle:
        handle.write("\n".join(lines))
    return output_path


def _to_forward_slashes(path: str) -> str:
    return path.replace(os.sep, "/")


def _write_latest_manifest(
    output_path: str,
    *,
    output_root: str,
    run_root: str,
    bundle_path: str,
    summary_path: str,
    snapshot_dashboard_path: str,
    figure_paths: Sequence[str],
    evaluation_path: Optional[str],
    security_paths: Sequence[str],
) -> str:
    payload = {
        "generated_at": os.path.basename(run_root).split("_findings_visualization", 1)[0],
        "latest_run_dir": _to_forward_slashes(os.path.relpath(run_root, output_root)),
        "latest_bundle_path": _to_forward_slashes(os.path.relpath(bundle_path, output_root)),
        "latest_summary_path": _to_forward_slashes(os.path.relpath(summary_path, output_root)),
        "latest_snapshot_dashboard_path": _to_forward_slashes(os.path.relpath(snapshot_dashboard_path, output_root)),
        "latest_figures": [_to_forward_slashes(os.path.relpath(path, output_root)) for path in figure_paths],
        "sources": {
            "evaluation_json": evaluation_path,
            "security_json": list(security_paths),
        },
    }
    return _write_json(output_path, payload)


def _write_live_dashboard_html(
    output_path: str,
    *,
    root_prefix: str,
    auto_refresh_ms: int = 15000,
) -> str:
    document = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>Findings Dashboard</title>
    <style>
        :root {{
            --bg: #f4efe8;
            --panel: #fffdf9;
            --ink: #1e2430;
            --muted: #667085;
            --accent: #b4513c;
            --line: #e7d8c9;
            --shadow: 0 16px 40px rgba(72, 52, 34, 0.08);
            --danger: #9f2d2d;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            font-family: Georgia, \"Times New Roman\", serif;
            color: var(--ink);
            background:
                radial-gradient(circle at top right, rgba(180, 81, 60, 0.18), transparent 28%),
                linear-gradient(180deg, #fbf7f1 0%, var(--bg) 100%);
        }}
        .shell {{ max-width: 1280px; margin: 0 auto; padding: 32px 24px 64px; }}
        .hero {{
            background: linear-gradient(135deg, rgba(180, 81, 60, 0.95), rgba(88, 62, 46, 0.95));
            color: #fff;
            border-radius: 24px;
            padding: 32px;
            box-shadow: var(--shadow);
        }}
        .hero h1 {{ margin: 0 0 10px; font-size: 2.4rem; }}
        .hero p {{ margin: 0; font-size: 1.05rem; max-width: 760px; line-height: 1.5; }}
        .badge-row {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 18px; }}
        .badge {{
            background: rgba(255, 255, 255, 0.16);
            border: 1px solid rgba(255, 255, 255, 0.25);
            border-radius: 999px;
            padding: 8px 14px;
            font-size: 0.92rem;
        }}
        .status-bar {{
            margin-top: 16px;
            font-size: 0.92rem;
            opacity: 0.92;
        }}
        .status-bar.error {{ color: #ffe3df; }}
        .grid {{ display: grid; gap: 20px; margin-top: 24px; }}
        .grid.two {{ grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
        .panel {{
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 20px;
            padding: 22px;
            box-shadow: var(--shadow);
        }}
        .panel h2 {{ margin: 0 0 14px; font-size: 1.2rem; }}
        .panel ul {{ margin: 0; padding-left: 20px; line-height: 1.6; }}
        .metric-table {{ width: 100%; border-collapse: collapse; font-size: 0.95rem; }}
        .metric-table th, .metric-table td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; }}
        .metric-table th {{ background: rgba(180, 81, 60, 0.08); }}
        .figure-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; margin-top: 24px; }}
        .figure-card {{
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 20px;
            padding: 18px;
            box-shadow: var(--shadow);
        }}
        .figure-card h3 {{ margin: 0 0 12px; font-size: 1.05rem; }}
        .figure-card img {{ width: 100%; height: auto; border-radius: 14px; border: 1px solid var(--line); background: #fff; }}
        .path {{ margin: 10px 0 0; color: var(--muted); font-size: 0.85rem; word-break: break-all; }}
        .meta-link {{ color: inherit; }}
        @media (max-width: 720px) {{
            .shell {{ padding: 20px 14px 44px; }}
            .hero {{ padding: 24px; }}
            .hero h1 {{ font-size: 1.9rem; }}
        }}
    </style>
</head>
<body>
    <main class=\"shell\">
        <section class=\"hero\">
            <h1>Consensus Findings Dashboard</h1>
            <p>Auto-generated from evaluation-overhaul and security-experiments artifacts. This page follows the newest findings bundle under the current report root and refreshes automatically while it stays open.</p>
            <div class=\"badge-row\">
                <span id=\"strategy-count\" class=\"badge\">Strategies: --</span>
                <span id=\"section-count\" class=\"badge\">Security sections: --</span>
                <span id=\"figure-count\" class=\"badge\">Figures: --</span>
            </div>
            <div id=\"status-bar\" class=\"status-bar\">Loading latest findings…</div>
        </section>

        <section class=\"grid two\">
            <article class=\"panel\">
                <h2>Highlights</h2>
                <ul id=\"highlights-list\"><li>Loading latest findings…</li></ul>
            </article>
            <article class=\"panel\">
                <h2>Artifact Sources</h2>
                <ul id=\"source-list\"><li>Loading latest findings…</li></ul>
            </article>
        </section>

        <section class=\"grid two\">
            <article class=\"panel\">
                <h2>Security Coverage</h2>
                <ul id=\"section-list\"><li>Loading latest findings…</li></ul>
            </article>
            <article class=\"panel\">
                <h2>Strategy Snapshot</h2>
                <table class=\"metric-table\">
                    <thead>
                        <tr>
                            <th>Strategy</th>
                            <th>PQI Mean</th>
                            <th>Agreement</th>
                            <th>Attacker Share</th>
                            <th>Violation</th>
                            <th>Solver ms</th>
                        </tr>
                    </thead>
                    <tbody id=\"strategy-table-body\"><tr><td colspan=\"6\">Loading latest findings…</td></tr></tbody>
                </table>
            </article>
        </section>

        <section id=\"figure-grid\" class=\"figure-grid\"><article class=\"panel\"><h2>Figures</h2><p>Loading latest findings…</p></article></section>
    </main>
    <noscript>This dashboard needs JavaScript enabled to fetch the newest findings bundle.</noscript>
    <script>
        const ROOT_PREFIX = {json.dumps(root_prefix)};
        const AUTO_REFRESH_MS = {auto_refresh_ms};

        function escapeHtml(value) {{
            return String(value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/\"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }}

        function resolvePath(path) {{
            return `${{ROOT_PREFIX}}/${{path}}`;
        }}

        function bustCache(url) {{
            const sep = url.includes('?') ? '&' : '?';
            return `${{url}}${{sep}}_=${{Date.now()}}`;
        }}

        async function fetchJson(path) {{
            const response = await fetch(bustCache(resolvePath(path)));
            if (!response.ok) {{
                throw new Error(`HTTP ${{response.status}} for ${{path}}`);
            }}
            return response.json();
        }}

        function numeric(metric, key) {{
            const value = Number(metric?.[key]);
            return Number.isFinite(value) ? value : 0;
        }}

        function bestMetric(metrics, key, reverse) {{
            const ranked = metrics
                .filter((metric) => Number.isFinite(Number(metric?.[key])))
                .slice()
                .sort((left, right) => reverse ? Number(right[key]) - Number(left[key]) : Number(left[key]) - Number(right[key]));
            return ranked.length ? ranked[0] : null;
        }}

        function buildHighlights(metrics) {{
            const highlights = [];
            const bestPqi = bestMetric(metrics, 'pqi_mean', true);
            const fastestSolver = bestMetric(metrics, 'mean_solver_ms', false);
            const lowestAttacker = bestMetric(metrics, 'attacker_share', false);
            const lowestViolation = bestMetric(metrics, 'committee_constraint_violation_rate', false);
            if (bestPqi) highlights.push(`Best PQI mean: ${{bestPqi.name}} (${{numeric(bestPqi, 'pqi_mean').toFixed(3)}})`);
            if (fastestSolver) highlights.push(`Fastest solver: ${{fastestSolver.name}} (${{numeric(fastestSolver, 'mean_solver_ms').toFixed(3)}} ms)`);
            if (lowestAttacker) highlights.push(`Lowest attacker proposer share: ${{lowestAttacker.name}} (${{numeric(lowestAttacker, 'attacker_share').toFixed(3)}})`);
            if (lowestViolation) highlights.push(`Lowest committee violation rate: ${{lowestViolation.name}} (${{numeric(lowestViolation, 'committee_constraint_violation_rate').toFixed(3)}})`);
            return highlights;
        }}

        function setList(id, items, emptyMessage) {{
            const node = document.getElementById(id);
            if (!items.length) {{
                node.innerHTML = `<li>${{escapeHtml(emptyMessage)}}</li>`;
                return;
            }}
            node.innerHTML = items.join('');
        }}

        function setStatus(message, isError = false) {{
            const node = document.getElementById('status-bar');
            node.textContent = message;
            node.classList.toggle('error', isError);
        }}

        function render(bundle, manifest) {{
            const metrics = Array.isArray(bundle.strategy_comparison) ? bundle.strategy_comparison : [];
            const security = bundle.security && typeof bundle.security === 'object' ? bundle.security : {{}};
            const sections = Object.entries(security).filter(([, value]) => Array.isArray(value) && value.length > 0);
            const figures = Array.isArray(manifest.latest_figures) ? manifest.latest_figures : [];

            document.getElementById('strategy-count').textContent = `Strategies: ${{metrics.length}}`;
            document.getElementById('section-count').textContent = `Security sections: ${{sections.length}}`;
            document.getElementById('figure-count').textContent = `Figures: ${{figures.length}}`;

            setList(
                'highlights-list',
                buildHighlights(metrics).map((item) => `<li>${{escapeHtml(item)}}</li>`),
                'No strategy metrics were available.'
            );

            const sourceItems = [];
            if (bundle.evaluation_source) {{
                sourceItems.push(`<li><strong>Evaluation:</strong> ${{escapeHtml(bundle.evaluation_source)}}</li>`);
            }}
            for (const path of (bundle.security_sources || [])) {{
                sourceItems.push(`<li><strong>Security:</strong> ${{escapeHtml(path)}}</li>`);
            }}
            if (manifest.latest_summary_path) {{
                sourceItems.push(`<li><strong>Latest summary:</strong> <a class=\"meta-link\" href=\"${{escapeHtml(resolvePath(manifest.latest_summary_path))}}\">${{escapeHtml(manifest.latest_summary_path)}}</a></li>`);
            }}
            if (manifest.latest_run_dir) {{
                sourceItems.push(`<li><strong>Latest findings run:</strong> ${{escapeHtml(manifest.latest_run_dir)}}</li>`);
            }}
            setList('source-list', sourceItems, 'No source files recorded.');

            setList(
                'section-list',
                sections.map(([key, value]) => `<li><strong>${{escapeHtml(key)}}</strong>: ${{value.length}} records</li>`),
                'No security experiment sections were populated.'
            );

            const tableBody = document.getElementById('strategy-table-body');
            if (!metrics.length) {{
                tableBody.innerHTML = '<tr><td colspan=\"6\">No strategy metrics were available.</td></tr>';
            }} else {{
                tableBody.innerHTML = metrics.map((metric) => `
                    <tr>
                        <td>${{escapeHtml(metric.name || 'unknown')}}</td>
                        <td>${{numeric(metric, 'pqi_mean').toFixed(3)}}</td>
                        <td>${{numeric(metric, 'agreement_rate').toFixed(3)}}</td>
                        <td>${{numeric(metric, 'attacker_share').toFixed(3)}}</td>
                        <td>${{numeric(metric, 'committee_constraint_violation_rate').toFixed(3)}}</td>
                        <td>${{numeric(metric, 'mean_solver_ms').toFixed(3)}}</td>
                    </tr>
                `).join('');
            }}

            const figureGrid = document.getElementById('figure-grid');
            if (!figures.length) {{
                figureGrid.innerHTML = '<article class=\"panel\"><h2>Figures</h2><p>No figures were generated.</p></article>';
            }} else {{
                figureGrid.innerHTML = figures.map((figurePath) => {{
                    const label = figurePath.split('/').pop().replace(/\\.png$/i, '').replace(/_/g, ' ');
                    const href = resolvePath(figurePath);
                    return `
                        <section class=\"figure-card\">
                            <h3>${{escapeHtml(label.replace(/\\b\\w/g, (char) => char.toUpperCase()))}}</h3>
                            <a href=\"${{escapeHtml(href)}}\"><img src=\"${{escapeHtml(bustCache(href))}}\" alt=\"${{escapeHtml(label)}}\"></a>
                            <p class=\"path\">${{escapeHtml(figurePath)}}</p>
                        </section>
                    `;
                }}).join('');
            }}

            setStatus(`Live view · latest findings generated at ${{manifest.generated_at}} · refresh every ${{AUTO_REFRESH_MS / 1000}}s`);
        }}

        async function loadDashboard() {{
            try {{
                const manifest = await fetchJson('latest_findings_manifest.json');
                const bundle = await fetchJson(manifest.latest_bundle_path);
                render(bundle, manifest);
            }} catch (error) {{
                setStatus(
                    `Could not load latest findings: ${{error.message}}. Serve this dashboard over HTTP rather than opening it as file://.`,
                    true,
                );
            }}
        }}

        loadDashboard();
        window.setInterval(loadDashboard, AUTO_REFRESH_MS);
    </script>
</body>
</html>
"""

    with open(output_path, "w") as handle:
        handle.write(document)
    return output_path


def generate_findings_bundle(
    *,
    search_root: str,
    output_dir: str,
    evaluation_json: Optional[str] = None,
    security_json: Optional[Sequence[str]] = None,
    all_security: bool = False,
) -> Dict[str, Any]:
    evaluation_path = evaluation_json or _discover_latest_path(search_root, EVALUATION_PATTERN)
    if security_json:
        security_paths = list(security_json)
    elif all_security:
        security_paths = _discover_paths(search_root, SECURITY_PATTERN)
    else:
        latest_security = _discover_latest_path(search_root, SECURITY_PATTERN)
        security_paths = [latest_security] if latest_security else []

    if not evaluation_path and not security_paths:
        raise SystemExit("No evaluation_overhaul or security_experiments JSON files were found.")

    run_layout = create_run_layout(output_dir, "findings_visualization")
    figure_paths: List[str] = []
    summary_metrics: List[Mapping[str, Any]] = []
    merged_security: Dict[str, List[Dict[str, Any]]] = {
        "probe_manipulation": [],
        "infrastructure_gaming": [],
        "score_racing": [],
        "correlated_failure": [],
        "attacker_fraction_sweep": [],
        "block_withholding": [],
    }

    if evaluation_path:
        evaluation_payload = _load_json(evaluation_path)
        summary_metrics = list(evaluation_payload.get("strategy_comparison", []))
        figure_paths.extend(_save_evaluation_summary(summary_metrics, run_layout.figures_dir))

    if security_paths:
        merged_security = _merge_security_payloads(security_paths)
        figure_paths.extend(_save_probe_manipulation(merged_security["probe_manipulation"], run_layout.figures_dir))
        figure_paths.extend(_save_infrastructure_gaming(merged_security["infrastructure_gaming"], run_layout.figures_dir))
        figure_paths.extend(_save_score_racing(merged_security["score_racing"], run_layout.figures_dir))
        figure_paths.extend(_save_attacker_sweep(merged_security["attacker_fraction_sweep"], run_layout.figures_dir))
        figure_paths.extend(_save_correlated_failure(merged_security["correlated_failure"], run_layout.figures_dir))
        figure_paths.extend(_save_block_withholding(merged_security["block_withholding"], run_layout.figures_dir))

    findings_data_path = _write_json(
        os.path.join(run_layout.data_dir, "findings_bundle.json"),
        {
            "evaluation_source": evaluation_path,
            "security_sources": security_paths,
            "strategy_comparison": summary_metrics,
            "security": merged_security,
        },
    )
    summary_path = _write_summary_markdown(
        os.path.join(run_layout.exports_dir, "findings_summary.md"),
        evaluation_path,
        security_paths,
        summary_metrics,
        merged_security,
        figure_paths,
    )
    snapshot_dashboard_path = _write_live_dashboard_html(
        os.path.join(run_layout.exports_dir, "findings_dashboard.html"),
        root_prefix="../..",
    )
    latest_manifest_path = _write_latest_manifest(
        os.path.join(output_dir, "latest_findings_manifest.json"),
        output_root=output_dir,
        run_root=run_layout.root_dir,
        bundle_path=findings_data_path,
        summary_path=summary_path,
        snapshot_dashboard_path=snapshot_dashboard_path,
        figure_paths=figure_paths,
        evaluation_path=evaluation_path,
        security_paths=security_paths,
    )
    live_dashboard_path = _write_live_dashboard_html(
        os.path.join(output_dir, "findings_dashboard.html"),
        root_prefix=".",
    )

    write_run_metadata(
        run_layout,
        {
            "tool": "visualize_findings",
            "layout": run_layout.to_dict(),
            "sources": {
                "evaluation_json": evaluation_path,
                "security_json": security_paths,
            },
            "outputs": {
                "data": findings_data_path,
                "summary_markdown": summary_path,
                "dashboard_html": snapshot_dashboard_path,
                "live_dashboard_html": live_dashboard_path,
                "latest_manifest_json": latest_manifest_path,
                "figures": figure_paths,
            },
        },
    )

    return {
        "run_layout": run_layout,
        "evaluation_path": evaluation_path,
        "security_paths": security_paths,
        "figure_paths": figure_paths,
        "findings_data_path": findings_data_path,
        "summary_path": summary_path,
        "snapshot_dashboard_path": snapshot_dashboard_path,
        "live_dashboard_path": live_dashboard_path,
        "latest_manifest_path": latest_manifest_path,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a compact findings bundle from evaluation and security report artifacts.",
    )
    parser.add_argument("--search-root", type=str, default="reports", help="Root directory to search recursively for JSON report artifacts.")
    parser.add_argument("--evaluation-json", type=str, default=None, help="Explicit evaluation_overhaul JSON path.")
    parser.add_argument("--security-json", nargs="*", default=None, help="Explicit security_experiments JSON paths.")
    parser.add_argument("--all-security", action="store_true", help="Merge all matching security JSON files under --search-root.")
    parser.add_argument("--output-dir", type=str, default="reports", help="Base output directory for the generated findings bundle.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = generate_findings_bundle(
        search_root=args.search_root,
        output_dir=args.output_dir,
        evaluation_json=args.evaluation_json,
        security_json=args.security_json,
        all_security=args.all_security,
    )

    print("=" * 70)
    print("  FINDINGS VISUALIZATION")
    print(f"  output={result['run_layout'].root_dir}")
    print(f"  live_dashboard={result['live_dashboard_path']}")
    if result["evaluation_path"]:
        print(f"  evaluation={result['evaluation_path']}")
    if result["security_paths"]:
        print(f"  security={len(result['security_paths'])} source file(s)")
    print("=" * 70)


if __name__ == "__main__":
    main()