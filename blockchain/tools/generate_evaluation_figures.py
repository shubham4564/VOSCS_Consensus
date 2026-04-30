#!/usr/bin/env python3
"""Generate publication-style figures for the ACM CCS 2026 submission.

Styling targets the ``acmart`` document class in ``sigconf`` mode (the
configuration ACM CCS uses).  Geometry constants are derived from the acmart
LaTeX sources so figure widths match the column / text widths exactly, font
choices follow the acmart serif stack (Libertinus / Linux Libertine), and
rcParams are calibrated against the 9 pt body / 8 pt caption used by the
template.  Outputs are emitted as Type-42 PDFs (ACM does not accept Type-3
fonts in camera-ready submissions) plus PNG previews.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import matplotlib
from matplotlib import font_manager

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_ROOTS = [
    PROJECT_ROOT / "reports" / "ccs_eval_old",
    PROJECT_ROOT / "reports" / "ccs_eval",
    PROJECT_ROOT / "reports" / "old",
]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "figure"
FIGURE_EXTENSIONS = (".svg", ".png")  # PDF for camera-ready, SVG for editable vector, PNG for previews.

# --- ACM acmart sigconf geometry --------------------------------------------------
# Derived from acmart.cls:
#   \columnwidth = 241.14749 pt -> 3.343 in
#   \textwidth   = 506.295   pt -> 7.024 in
# Body text is 9 pt with 10.5 pt leading; captions are 8 pt.  We size figure
# text against the 9 pt body so it stays legible after \includegraphics scaling.
ACM_SINGLE_COLUMN_WIDTH = 3.343
ACM_DOUBLE_COLUMN_WIDTH = 7.024
ACM_PANEL_HEIGHT = 2.40
ACM_WIDE_PANEL_HEIGHT = 2.80
ACM_GRID_HEIGHT = 4.90

# acmart's default serif is Linux Libertine; the modernized Libertinus fork is
# the recommended substitute on systems without the original.  TeX Gyre Termes
# and Nimbus Roman are Times-compatible fallbacks shipped with TeX Live, and
# STIX / DejaVu are last-resort fallbacks always present with matplotlib.
ACM_SERIF_CANDIDATES = [
    "Libertinus Serif",
    "Linux Libertine O",
    "Linux Libertine",
    "TeX Gyre Termes",
    "Nimbus Roman",
    "STIX Two Text",
    "STIXGeneral",
    "DejaVu Serif",
]

STRATEGY_LABELS = {
    "committee_quantum": "VOSCS (Ours)",
    "committee_mocs": "VOSCS (Ours)",
    "committee_greedy": "Greedy",
    "committee_weighted": "Weighted sampling",
    "committee_vrf_stake": "VRF/stake",
    "committee_reputation": "Reputation",
    "committee_composite_greedy": "Composite greedy",
    "committee_uniform": "Uniform",
    "committee_fairness_only": "Fairness only",
    "committee_exact": "Exact enumeration",
}

STRATEGY_ORDER = [
    "committee_quantum",
    "committee_mocs",
    "committee_greedy",
    "committee_weighted",
    "committee_vrf_stake",
    "committee_reputation",
    "committee_composite_greedy",
    "committee_uniform",
    "committee_fairness_only",
    "committee_exact",
]

# Wong colour-blind-safe palette: prints legibly in greyscale, which matters for
# ACM CCS reviewers who routinely print the PDF.
COLOR_MAP = {
    "committee_quantum": "#111111",
    "committee_mocs": "#111111",
    "committee_greedy": "#0072B2",
    "committee_weighted": "#E69F00",
    "committee_vrf_stake": "#009E73",
    "committee_reputation": "#56B4E9",
    "committee_composite_greedy": "#CC79A7",
    "committee_uniform": "#7F7F7F",
    "committee_fairness_only": "#D55E00",
    "committee_exact": "#4D4D4D",
}

MARKER_MAP = {
    "committee_quantum": "o",
    "committee_mocs": "o",
    "committee_greedy": "o",
    "committee_weighted": "o",
    "committee_vrf_stake": "s",
    "committee_reputation": "^",
    "committee_composite_greedy": "D",
    "committee_uniform": "P",
    "committee_fairness_only": "X",
    "committee_exact": "x",
}

LINESTYLE_MAP = {
    "committee_quantum": "-",
    "committee_mocs": "-",
    "committee_greedy": "--",
    "committee_weighted": "-.",
    "committee_vrf_stake": ":",
    "committee_reputation": (0, (5, 1.2)),
    "committee_composite_greedy": (0, (3, 1.2, 1, 1.2)),
    "committee_uniform": (0, (2, 1.4)),
    "committee_fairness_only": (0, (1, 1.0)),
    "committee_exact": "--",
}


@dataclass
class ManifestRecord:
    path: Path
    payload: dict[str, Any]


@dataclass
class GeneratedFigure:
    section: str
    path: Path
    sources: list[Path]


def available_serif_fonts() -> list[str]:
    installed = {font.name for font in font_manager.fontManager.ttflist}
    selected = [name for name in ACM_SERIF_CANDIDATES if name in installed]
    return selected or ["DejaVu Serif"]


def configure_plot_style() -> str:
    """Apply the ACM CCS 2026 (acmart sigconf) figure style to matplotlib.

    Sizes follow the convention used in recent CCS/USENIX Security camera-ready
    figures: in-axes text 1-2 pt below the 9 pt body, tick labels another
    notch smaller, legends smaller still.  This keeps figures legible without
    overpowering the surrounding caption when scaled to ``\\columnwidth`` or
    ``\\textwidth``.
    """
    serif_fonts = available_serif_fonts()
    plt.style.use("default")
    plt.rcParams.update(
        {
            # --- Typography ---------------------------------------------------
            # acmart's serif stack; STIX gives Times-compatible math glyphs that
            # blend with Libertinus / Linux Libertine without recompiling fonts.
            "font.family": "serif",
            "font.serif": serif_fonts,
            "mathtext.fontset": "stix",
            "mathtext.default": "regular",
            "axes.formatter.use_mathtext": True,

            # --- Font embedding -----------------------------------------------
            # ACM's PDF preflight rejects Type-3 fonts; 42 = TrueType embedding.
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",

            # --- Render / export ----------------------------------------------
            "figure.dpi": 150,
            "savefig.dpi": 600,            # ACM print: >=600 dpi for raster fallbacks.
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.02,
            "savefig.transparent": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",

            # --- Sizes (matched to acmart's 9 pt body / 8 pt caption) --------
            "font.size": 12.0,
            "axes.titlesize": 10.0,
            "axes.titleweight": "semibold",
            "axes.titlepad": 4.5,
            "axes.labelsize": 9.0,
            "axes.labelpad": 3.0,
            "legend.fontsize": 8.5,
            "legend.title_fontsize": 9.0,
            "xtick.labelsize": 8.0,
            "ytick.labelsize": 8.0,
            "figure.titlesize": 10.0,
            "figure.titleweight": "semibold",

            # --- Axes ---------------------------------------------------------
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#2b2b2b",
            "axes.linewidth": 0.6,
            "axes.unicode_minus": False,
            "axes.axisbelow": True,

            # --- Grid (subtle, behind data) -----------------------------------
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linestyle": "--",
            "grid.linewidth": 0.4,
            "grid.color": "#b5b5b5",

            # --- Ticks --------------------------------------------------------
            "xtick.direction": "out",
            "ytick.direction": "out",
            "xtick.major.width": 0.55,
            "ytick.major.width": 0.55,
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "xtick.minor.width": 0.4,
            "ytick.minor.width": 0.4,
            "xtick.minor.size": 1.6,
            "ytick.minor.size": 1.6,
            "xtick.major.pad": 2.5,
            "ytick.major.pad": 2.5,

            # --- Lines / markers (a touch thicker for print legibility) -------
            "lines.linewidth": 1.25,
            "lines.markersize": 4.2,
            "lines.markeredgewidth": 0.85,
            "patch.linewidth": 0.55,

            # --- Legend -------------------------------------------------------
            "legend.frameon": False,
            "legend.borderaxespad": 0.3,
            "legend.handlelength": 2.0,
            "legend.handletextpad": 0.5,
            "legend.columnspacing": 1.0,
            "legend.labelspacing": 0.3,
        }
    )
    return serif_fonts[0]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def reports_suffix(path_text: str) -> Optional[str]:
    normalized = path_text.replace("\\", "/")
    if normalized.startswith("reports/"):
        return normalized[len("reports/") :]
    marker = "/reports/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return None


def resolve_report_path(path_text: str, manifest_path: Optional[Path] = None) -> Optional[Path]:
    candidates: list[Path] = []
    raw_path = Path(path_text)

    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append(PROJECT_ROOT / raw_path)
        if manifest_path is not None:
            candidates.append(manifest_path.parent / raw_path)

    suffix = reports_suffix(path_text)
    if suffix:
        candidates.append(PROJECT_ROOT / "reports" / suffix)
        if suffix.startswith("ccs_eval/"):
            candidates.append(PROJECT_ROOT / "reports" / suffix.replace("ccs_eval/", "ccs_eval_old/", 1))
        if suffix.startswith("ccs_eval_old/"):
            candidates.append(PROJECT_ROOT / "reports" / suffix.replace("ccs_eval_old/", "ccs_eval/", 1))
        if manifest_path is not None and "/reports/old/" in str(manifest_path) and not suffix.startswith("old/"):
            candidates.append(PROJECT_ROOT / "reports" / "old" / suffix)

    if manifest_path is not None and "ccs_eval_old" in str(manifest_path):
        remapped: list[Path] = []
        for candidate in candidates:
            candidate_text = str(candidate)
            if "/reports/ccs_eval/" in candidate_text:
                remapped.append(Path(candidate_text.replace("/reports/ccs_eval/", "/reports/ccs_eval_old/")))
        candidates.extend(remapped)

    if manifest_path is not None and "/reports/old/" in str(manifest_path):
        remapped_old: list[Path] = []
        for candidate in candidates:
            candidate_text = str(candidate)
            if "/reports/old/" not in candidate_text and "/reports/" in candidate_text:
                remapped_old.append(Path(candidate_text.replace("/reports/", "/reports/old/", 1)))
        candidates.extend(remapped_old)

    seen: set[Path] = set()
    for candidate in candidates:
        normalized = candidate.resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.exists():
            return candidate
    return None


def parse_timestamp(path: Path) -> str:
    matches = re.findall(r"\d{8}_\d{6}", str(path))
    return matches[-1] if matches else "00000000_000000"


def extract_seed(path: Path) -> Optional[int]:
    for part in path.parts:
        match = re.fullmatch(r"seed_(\d+)", part)
        if match:
            return int(match.group(1))
        match = re.fullmatch(r"paper_run_seed_(\d+)", part)
        if match:
            return int(match.group(1))
    return None


def canonical_strategy_key(name: str) -> str:
    if name == "committee_mocs":
        return "committee_quantum"
    return name


def strategy_label(name: str) -> str:
    return STRATEGY_LABELS.get(name, STRATEGY_LABELS.get(canonical_strategy_key(name), name))


def strategy_color(name: str) -> str:
    key = canonical_strategy_key(name)
    return COLOR_MAP.get(name, COLOR_MAP.get(key, "#333333"))


def strategy_marker(name: str) -> str:
    key = canonical_strategy_key(name)
    return MARKER_MAP.get(name, MARKER_MAP.get(key, "o"))


def strategy_linestyle(name: str) -> str | tuple[int, tuple[float, ...]]:
    key = canonical_strategy_key(name)
    return LINESTYLE_MAP.get(name, LINESTYLE_MAP.get(key, "-"))


def strategy_sort_key(name: str) -> tuple[int, str]:
    key = canonical_strategy_key(name)
    try:
        return (STRATEGY_ORDER.index(key), key)
    except ValueError:
        return (len(STRATEGY_ORDER), key)


def discover_solver_study_files(report_roots: Iterable[Path]) -> list[Path]:
    grouped: dict[int, list[Path]] = defaultdict(list)
    for root in report_roots:
        if not root.exists():
            continue
        for path in root.rglob("solver_comparison_*.json"):
            if "solver_study" not in path.parts:
                continue
            seed = extract_seed(path)
            if seed is None:
                continue
            grouped[seed].append(path)

    selected: list[Path] = []
    for seed, paths in grouped.items():
        selected.append(max(paths, key=parse_timestamp))
    return sorted(selected, key=lambda path: extract_seed(path) or -1)


def discover_comparative_manifests(report_roots: Iterable[Path]) -> list[ManifestRecord]:
    records: list[ManifestRecord] = []
    seen: set[Path] = set()
    for root in report_roots:
        if not root.exists():
            continue
        for path in root.rglob("comparative_manifest.json"):
            normalized = path.resolve(strict=False)
            if normalized in seen:
                continue
            seen.add(normalized)
            try:
                records.append(ManifestRecord(path=path, payload=load_json(path)))
            except json.JSONDecodeError:
                continue
    return records


def load_stage_payload(record: ManifestRecord, stage_name: str) -> tuple[Optional[dict[str, Any]], Optional[Path]]:
    stage = record.payload.get("stages", {}).get(stage_name)
    if not stage:
        return None, None
    results_json = stage.get("results_json")
    if not results_json:
        return None, None
    resolved = resolve_report_path(str(results_json), record.path)
    if resolved is None:
        return None, None
    return load_json(resolved), resolved


def mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return float(values[0]), 0.0
    return statistics.fmean(values), statistics.stdev(values)


def save_figure(fig: plt.Figure, path: Path, tight_rect: Optional[tuple[float, float, float, float]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(pad=0.35, rect=tight_rect)
    for extension in FIGURE_EXTENSIONS:
        export_path = path.with_suffix(extension)
        fig.savefig(export_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def select_canonical_comparison(
    records: list[ManifestRecord],
    preferred_nodes: int,
    preferred_rounds: int,
    preferred_seed: int,
) -> Optional[ManifestRecord]:
    candidates: list[ManifestRecord] = []
    for record in records:
        stages = record.payload.get("stages", {})
        if not all(name in stages for name in ("literature", "measurement_overhead", "committee_ablation", "security")):
            continue
        candidates.append(record)

    if not candidates:
        return None

    def score(record: ManifestRecord) -> tuple[int, int, int, int, int, str]:
        cfg = record.payload.get("config", {})
        nodes = int(cfg.get("literature_nodes", 0) or 0)
        rounds = int(cfg.get("literature_rounds", 0) or 0)
        seed = int(cfg.get("seed", -1) or -1)
        path_text = str(record.path)
        return (
            1 if "/comparison/" in path_text else 0,
            1 if nodes == preferred_nodes else 0,
            1 if rounds == preferred_rounds else 0,
            1 if seed == preferred_seed else 0,
            nodes * 100000 + rounds,
            parse_timestamp(record.path),
        )

    return max(candidates, key=score)


def select_long_horizon_record(records: list[ManifestRecord]) -> tuple[Optional[ManifestRecord], Optional[dict[str, Any]], Optional[Path]]:
    best_record: Optional[ManifestRecord] = None
    best_payload: Optional[dict[str, Any]] = None
    best_path: Optional[Path] = None
    best_score: tuple[int, int, str] | None = None

    for record in records:
        payload, data_path = load_stage_payload(record, "long_horizon")
        if payload is None or data_path is None:
            continue
        rows = payload.get("long_horizon", [])
        if not rows:
            continue
        score = (
            max(int(row.get("num_rounds", 0) or 0) for row in rows),
            len(rows),
            parse_timestamp(record.path),
        )
        if best_score is None or score > best_score:
            best_record = record
            best_payload = payload
            best_path = data_path
            best_score = score
    return best_record, best_payload, best_path


def aggregate_solver_metrics(paths: list[Path]) -> tuple[dict[int, dict[str, tuple[float, float]]], list[Path]]:
    per_seed: dict[int, dict[int, dict[str, float]]] = {}
    sources: list[Path] = []

    for path in paths:
        payload = load_json(path)
        seed = int(payload.get("config", {}).get("seed", extract_seed(path) or -1))
        rows = payload.get("solver_comparison", [])
        if not rows:
            continue
        per_seed[seed] = {
            int(row["candidate_count"]): {
                "quantum_gap": float(row["quantum_optimality_gap_mean"]),
                "greedy_gap": float(row["greedy_optimality_gap_mean"]),
                "weighted_gap": float(row["weighted_optimality_gap_mean"]),
                "quantum_ms": float(row["quantum_solver_ms_mean"]),
                "greedy_ms": float(row["greedy_solver_ms_mean"]),
                "weighted_ms": float(row["weighted_solver_ms_mean"]),
                "exact_ms": float(row["exact_solver_ms_mean"]),
            }
            for row in rows
        }
        sources.append(path)

    aggregated: dict[int, dict[str, tuple[float, float]]] = {}
    candidate_counts = sorted({candidate for rows in per_seed.values() for candidate in rows})
    for candidate in candidate_counts:
        metric_values: dict[str, list[float]] = defaultdict(list)
        for rows in per_seed.values():
            if candidate not in rows:
                continue
            for metric_name, value in rows[candidate].items():
                metric_values[metric_name].append(value)
        aggregated[candidate] = {metric_name: mean_std(values) for metric_name, values in metric_values.items()}

    return aggregated, sources


def plot_solver_figures(aggregated: dict[int, dict[str, tuple[float, float]]], output_dir: Path) -> list[GeneratedFigure]:
    generated: list[GeneratedFigure] = []
    if not aggregated:
        return generated

    candidate_counts = sorted(aggregated)

    fig, ax = plt.subplots(figsize=(ACM_DOUBLE_COLUMN_WIDTH, ACM_PANEL_HEIGHT))
    for metric_name, label, color in (
        ("quantum_gap", "Simulated annealing", "#111111"),
        ("greedy_gap", "Greedy", COLOR_MAP["committee_greedy"]),
        ("weighted_gap", "Weighted sampling", COLOR_MAP["committee_weighted"]),
    ):
        means = [aggregated[count][metric_name][0] for count in candidate_counts]
        stds = [aggregated[count][metric_name][1] for count in candidate_counts]
        ax.errorbar(
            candidate_counts,
            means,
            yerr=stds,
            marker="o",
            markerfacecolor="white",
            markeredgewidth=0.9,
            capsize=2.2,
            linewidth=1.3,
            linestyle="-",
            label=label,
            color=color,
        )
    ax.set_title("Solver optimality gap against exact enumeration")
    ax.set_xlabel("Candidate count")
    ax.set_ylabel("Mean optimality gap")
    ax.legend(loc="upper left", ncol=3)
    path = output_dir / "solver" / "solver_optimality_gap.png"
    save_figure(fig, path)
    generated.append(GeneratedFigure(section="solver_optimality_gap", path=path, sources=[]))

    fig, ax = plt.subplots(figsize=(ACM_DOUBLE_COLUMN_WIDTH, ACM_PANEL_HEIGHT))
    for metric_name, label, color in (
        ("greedy_ms", "Greedy", COLOR_MAP["committee_greedy"]),
        ("weighted_ms", "Weighted sampling", COLOR_MAP["committee_weighted"]),
        ("exact_ms", "Exact enumeration", "#009E73"),
        ("quantum_ms", "Simulated annealing", "#111111"),
    ):
        means = [aggregated[count][metric_name][0] for count in candidate_counts]
        stds = [aggregated[count][metric_name][1] for count in candidate_counts]
        ax.errorbar(
            candidate_counts,
            means,
            yerr=stds,
            marker="o",
            markerfacecolor="white",
            markeredgewidth=0.9,
            capsize=2.2,
            linewidth=1.3,
            linestyle="-",
            label=label,
            color=color,
        )
    ax.set_yscale("log")
    ax.set_title("Solver runtime scaling")
    ax.set_xlabel("Candidate count")
    ax.set_ylabel("Solver time (ms)")
    ax.legend(loc="upper left", ncol=2)
    path = output_dir / "solver" / "solver_runtime_scaling.png"
    save_figure(fig, path)
    generated.append(GeneratedFigure(section="solver_runtime_scaling", path=path, sources=[]))

    return generated


def literature_rows_from_manifest(record: ManifestRecord) -> tuple[list[dict[str, Any]], Optional[Path]]:
    payload, source = load_stage_payload(record, "literature")
    if payload is None:
        return [], None
    rows = payload.get("strategy_comparison", [])
    return rows, source


def plot_literature_diversity_scatter(record: ManifestRecord, output_dir: Path) -> Optional[GeneratedFigure]:
    rows, source = literature_rows_from_manifest(record)
    if not rows or source is None:
        return None

    # Square-leaning aspect (~1.4:1) so the dense top-left cluster has room
    # to breathe instead of being smeared across a 7-inch-wide strip.
    fig, ax = plt.subplots(figsize=(5.0, 3.6))

    # Subtle tint marking the preferred region (low concentration, high
    # diversity) plus a small directional cue.  Tinting reads faster than the
    # old prose annotation and stays out of the data layer.
    ax.add_patch(
        plt.Rectangle(
            (-0.02, 0.95), 0.32, 0.075,
            facecolor="#2a7a2a", alpha=0.07, edgecolor="none", zorder=0,
        )
    )
    ax.text(
        0.14, 0.963, "preferred region",
        fontsize=8, color="#2a7a2a", style="italic", alpha=0.9, zorder=1,
    )
    ax.annotate(
        "better",
        xy=(0.04, 0.955), xycoords="axes fraction",
        xytext=(0.22, 0.82), textcoords="axes fraction",
        fontsize=8.0, color="#2a7a2a", style="italic",
        arrowprops=dict(arrowstyle="-|>", color="#2a7a2a", lw=0.9, alpha=0.75,
                        connectionstyle="arc3,rad=-0.15"),
        ha="center", va="center", zorder=2,
    )

    sorted_rows = sorted(rows, key=lambda item: strategy_sort_key(str(item["name"])))

    # Markers: hollow with coloured edge for baselines, filled with a black
    # rim for the proposed VOSCS / QUBO method so it reads as the focal point.
    for row in sorted_rows:
        x_value = float(row.get("selection_concentration", 0.0))
        y_value = float(row.get("committee_mean_unique_failure_domain_ratio", 0.0))
        pqi = float(row.get("pqi_mean", 0.0))
        size = 42 + 88 * max(0.0, min(pqi, 1.0))
        name = str(row["name"])
        is_proposed = canonical_strategy_key(name) == "committee_quantum"

        if is_proposed:
            ax.scatter(
                x_value, y_value, s=size * 1.18,
                facecolor=strategy_color(name), edgecolor="black",
                linewidth=1.3, marker="o",
                alpha=0.96, zorder=4,
            )
        else:
            ax.scatter(
                x_value, y_value, s=size,
                facecolor=strategy_color(name), edgecolor=strategy_color(name),
                linewidth=1.05, marker="o",
                alpha=0.85, zorder=3,
            )

    # Label placement with rough collision avoidance.  Keeps inline labels
    # (helpful for reviewers reading the print copy) without the visual mess
    # of overlapping text in the dense top-left cluster.
    occupied: list[tuple[float, float]] = []
    for row in sorted_rows:
        x_value = float(row.get("selection_concentration", 0.0))
        y_value = float(row.get("committee_mean_unique_failure_domain_ratio", 0.0))
        name = str(row["name"])
        is_proposed = canonical_strategy_key(name) == "committee_quantum"

        if x_value > 0.62:
            dx, ha = -0.018, "right"
        else:
            dx, ha = 0.018, "left"
        if y_value > 0.99:
            dy, va = -0.011, "top"
        else:
            dy, va = 0.009, "bottom"

        # Per-strategy overrides for legibility
        if canonical_strategy_key(name) == "committee_uniform":
            dy, va = -0.011, "top"

        for ox, oy in occupied:
            if abs(ox - (x_value + dx)) < 0.06 and abs(oy - (y_value + dy)) < 0.014:
                dy = -dy if dy > 0 else -dy + 0.020
                va = "bottom" if dy > 0 else "top"
                break
        occupied.append((x_value + dx, y_value + dy))

        ax.text(
            x_value + dx, y_value + dy, strategy_label(name),
            fontsize=8.0, ha=ha, va=va,
            fontweight="semibold" if is_proposed else "normal",
            color="#111111" if is_proposed else "#262626",
            zorder=5,
        )

    # Inline note explaining the size encoding.  Cheaper than a second legend.
    ax.text(
        0.985, 0.025, r"Marker size $\propto$ mean PQI",
        transform=ax.transAxes, fontsize=8, ha="right", va="bottom",
        color="#555555", style="italic",
    )

    ax.set_xlim(-0.02, 1.05)
    ax.set_ylim(0.75, 1.025)
    ax.set_title("Committee strategies: failure-domain diversity vs. selection concentration")
    ax.set_xlabel("Selection concentration (lower is better)", fontsize=10)
    ax.set_ylabel("Failure-domain diversity ratio (higher is better)", fontsize=10)

    path = output_dir / "baselines" / "literature_diversity_vs_concentration.png"
    save_figure(fig, path)
    return GeneratedFigure(section="literature_diversity_vs_concentration", path=path, sources=[source])


def plot_measurement_overhead(record: ManifestRecord, output_dir: Path) -> Optional[GeneratedFigure]:
    payload, source = load_stage_payload(record, "measurement_overhead")
    if payload is None or source is None:
        return None

    rows = payload.get("measurement_overhead", [])
    if not rows:
        return None

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["strategy"])].append(row)

    # Slightly taller than the original 2.80 in to absorb a top legend strip
    # at body-sized font without crashing into the axis title.
    fig, ax = plt.subplots(figsize=(ACM_DOUBLE_COLUMN_WIDTH, ACM_WIDE_PANEL_HEIGHT + 0.40))
    for strategy_name in sorted(grouped, key=strategy_sort_key):
        items = sorted(grouped[strategy_name], key=lambda item: int(item["num_nodes"]))
        xs = [int(item["num_nodes"]) for item in items]
        ys = [float(item["optimization_latency_ms"]) for item in items]
        ax.plot(
            xs,
            ys,
            marker=strategy_marker(strategy_name),
            linestyle=strategy_linestyle(strategy_name),
            markerfacecolor="white",
            markeredgewidth=0.9,
            linewidth=1.3,
            label=strategy_label(strategy_name),
            color=strategy_color(strategy_name),
        )
    ax.set_yscale("log")
    ax.set_xlabel("Number of nodes", fontsize=13)
    ax.set_ylabel("Optimization latency (ms)", fontsize=13)
    ax.tick_params(axis="both", labelsize=12)
    # Anchor the legend just inside the figure top so its anchor coordinate
    # and the tight_rect reservation share the same frame -- this is what
    # used to make the legend appear to "float" awkwardly above the axes.
    ax.legend(loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.16), columnspacing=0.9, handletextpad=0.5, fontsize=11)

    path = output_dir / "baselines" / "measurement_overhead_latency.png"
    save_figure(fig, path, tight_rect=(0.0, 0.0, 1.0, 0.83))
    return GeneratedFigure(section="measurement_overhead_latency", path=path, sources=[source])


def plot_committee_ablation(record: ManifestRecord, output_dir: Path) -> Optional[GeneratedFigure]:
    payload, source = load_stage_payload(record, "committee_ablation")
    if payload is None or source is None:
        return None

    rows = payload.get("committee_ablations", {})
    if not rows:
        return None

    order = ["full_objective", "lambda_zero", "w_freq_zero", "no_fallback", "score_only"]
    labels = []
    diversity = []
    concentration = []
    for key in order:
        row = rows.get(key)
        if not row:
            continue
        labels.append(str(row.get("name", key)))
        diversity.append(float(row.get("committee_mean_unique_failure_domain_ratio", 0.0)))
        concentration.append(float(row.get("selection_concentration", 0.0)))

    if not labels:
        return None

    xs = list(range(len(labels)))
    fig, axes = plt.subplots(1, 2, figsize=(ACM_DOUBLE_COLUMN_WIDTH, ACM_PANEL_HEIGHT), sharex=True)
    axes[0].bar(xs, diversity, color="#0072B2", edgecolor="#1f1f1f", linewidth=0.6, width=0.7)
    axes[0].set_title("Failure-domain diversity")
    axes[0].set_ylabel("Mean unique failure-domain ratio")
    axes[0].set_xticks(xs)
    axes[0].set_xticklabels(labels, rotation=20, ha="right")

    axes[1].bar(xs, concentration, color="#D55E00", edgecolor="#1f1f1f", linewidth=0.6, width=0.7)
    axes[1].set_title("Leader concentration")
    axes[1].set_ylabel("Selection concentration")
    axes[1].set_xticks(xs)
    axes[1].set_xticklabels(labels, rotation=20, ha="right")

    fig.suptitle("Committee diversity and concentration under ablations")
    path = output_dir / "ablation" / "committee_ablation_diversity_concentration.png"
    save_figure(fig, path)
    return GeneratedFigure(section="committee_ablation", path=path, sources=[source])


def aggregate_strategy_scaling(records: list[ManifestRecord]) -> tuple[dict[int, dict[str, dict[int, dict[str, float]]]], list[Path]]:
    aggregated: dict[int, dict[str, dict[int, list[dict[str, Any]]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    sources: list[Path] = []

    for record in records:
        if "/comparison/" not in str(record.path):
            continue
        payload, source = load_stage_payload(record, "literature")
        if payload is None or source is None:
            continue
        cfg = record.payload.get("config", {})
        num_nodes = int(cfg.get("literature_nodes", 0) or 0)
        num_rounds = int(cfg.get("literature_rounds", 0) or 0)
        if num_nodes <= 0 or num_rounds <= 0:
            continue
        for row in payload.get("strategy_comparison", []):
            strategy_name = canonical_strategy_key(str(row.get("name", "")))
            if strategy_name not in STRATEGY_ORDER:
                continue
            aggregated[num_rounds][strategy_name][num_nodes].append(row)
        sources.append(source)

    collapsed: dict[int, dict[str, dict[int, dict[str, float]]]] = defaultdict(dict)
    for num_rounds, strategy_map in aggregated.items():
        collapsed[num_rounds] = {}
        for strategy_name, node_map in strategy_map.items():
            collapsed[num_rounds][strategy_name] = {}
            for num_nodes, rows in node_map.items():
                collapsed[num_rounds][strategy_name][num_nodes] = {
                    "pqi_mean": statistics.fmean(float(row.get("pqi_mean", 0.0)) for row in rows),
                    "selection_concentration": statistics.fmean(float(row.get("selection_concentration", 0.0)) for row in rows),
                    "committee_mean_unique_failure_domain_ratio": statistics.fmean(
                        float(row.get("committee_mean_unique_failure_domain_ratio", 0.0)) for row in rows
                    ),
                    "mean_solver_ms": statistics.fmean(float(row.get("mean_solver_ms", 0.0)) for row in rows),
                }
    return collapsed, sorted(set(sources))


def plot_strategy_scaling(records: list[ManifestRecord], output_dir: Path) -> list[GeneratedFigure]:
    aggregated, sources = aggregate_strategy_scaling(records)
    generated: list[GeneratedFigure] = []
    if not aggregated:
        return generated

    metrics = [
        ("pqi_mean", "PQI mean", False),
        ("committee_mean_unique_failure_domain_ratio", "Failure-domain diversity", False),
        ("selection_concentration", "Selection concentration", False),
        ("mean_solver_ms", "Mean solver time (ms)", True),
    ]

    for num_rounds in sorted(aggregated):
        fig, axes = plt.subplots(
            2, 2,
            figsize=(ACM_DOUBLE_COLUMN_WIDTH, ACM_GRID_HEIGHT),
            sharex=True,
            gridspec_kw={"hspace": 0.34, "wspace": 0.28},
        )
        for axis, (metric_name, title, log_scale) in zip(axes.flat, metrics):
            for strategy_name in sorted(aggregated[num_rounds], key=strategy_sort_key):
                node_map = aggregated[num_rounds][strategy_name]
                xs = sorted(node_map)
                ys = [node_map[num_nodes][metric_name] for num_nodes in xs]
                axis.plot(
                    xs,
                    ys,
                    marker=strategy_marker(strategy_name),
                    linestyle=strategy_linestyle(strategy_name),
                    markerfacecolor="white",
                    markeredgewidth=0.8,
                    linewidth=1.25,
                    label=strategy_label(strategy_name),
                    color=strategy_color(strategy_name),
                )
            if log_scale:
                axis.set_yscale("log")
            axis.set_title(title)
            axis.set_xlabel("Number of nodes")
        axes[0][0].set_ylabel("Higher is better")
        axes[0][1].set_ylabel("Higher is better")
        axes[1][0].set_ylabel("Lower is better")
        axes[1][1].set_ylabel("Milliseconds")

        handles, labels = axes[0][0].get_legend_handles_labels()
        # 5-column legend collapses ~9 strategies into 2 compact rows that sit
        # immediately under the suptitle, so the gap between caption and grid
        # is the legend itself rather than empty whitespace.
        fig.legend(
            handles, labels,
            loc="upper center",
            ncol=5,
            bbox_to_anchor=(0.5, 0.965),
            columnspacing=1.1,
            handletextpad=0.45,
            frameon=False,
            fontsize=7.0,
        )
        fig.suptitle(
            f"Strategy scaling across network sizes (rounds={num_rounds})",
            y=0.998,
            fontsize=8.6,
        )

        path = output_dir / "scaling" / f"strategy_scaling_rounds_{num_rounds}.png"
        save_figure(fig, path, tight_rect=(0.0, 0.0, 1.0, 0.91))
        generated.append(GeneratedFigure(section=f"strategy_scaling_rounds_{num_rounds}", path=path, sources=sources))

    return generated


def plot_attacker_sweep(record: ManifestRecord, output_dir: Path) -> Optional[GeneratedFigure]:
    payload, source = load_stage_payload(record, "security")
    if payload is None or source is None:
        return None
    rows = payload.get("attacker_fraction_sweep", [])
    if not rows:
        return None

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["strategy"])].append(row)

    # Modest height bump (+0.40 in) so the body-sized top legend has room
    # without forcing the chart area into a cramped strip.
    fig, axes = plt.subplots(1, 2, figsize=(ACM_DOUBLE_COLUMN_WIDTH, ACM_PANEL_HEIGHT + 0.40), sharex=True)
    for strategy_name in sorted(grouped, key=strategy_sort_key):
        items = sorted(grouped[strategy_name], key=lambda item: float(item["attacker_fraction"]))
        xs = [float(item["attacker_fraction"]) for item in items]
        _is_proposed = canonical_strategy_key(strategy_name) == "committee_quantum"
        _lw = 2.2 if _is_proposed else 1.25
        _zorder = 4 if _is_proposed else 2
        axes[0].plot(xs, [float(item["attacker_proposer_share"]) for item in items], marker=strategy_marker(strategy_name), linestyle=strategy_linestyle(strategy_name), markerfacecolor="white", markeredgewidth=0.8, linewidth=_lw, zorder=_zorder, label=strategy_label(strategy_name), color=strategy_color(strategy_name))
        axes[1].plot(xs, [float(item["throughput_degradation_ratio"]) for item in items], marker=strategy_marker(strategy_name), linestyle=strategy_linestyle(strategy_name), markerfacecolor="white", markeredgewidth=0.8, linewidth=_lw, zorder=_zorder, label=strategy_label(strategy_name), color=strategy_color(strategy_name))
    axes[0].plot([0.0, 0.5], [0.0, 0.5], linestyle=":", color="#444444", linewidth=1.0, label="Ideal y=x")
    axes[0].set_title("Attacker capture under attacker-fraction sweep")
    axes[0].set_ylabel("Attacker proposer share")
    axes[1].set_title("Throughput degradation")
    axes[1].set_ylabel("Degradation ratio")
    for axis in axes:
        axis.set_xlabel("Attacker fraction")
    handles, labels = axes[0].get_legend_handles_labels()
    # Legend top edge anchored at y=1.0 (figure top) and tight_rect reserves
    # the matching 20% strip -- one coordinate frame, no floating gap.
    fig.legend(handles, labels, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.0), columnspacing=0.9, handletextpad=0.5)

    path = output_dir / "security" / "security_attacker_sweep.png"
    save_figure(fig, path, tight_rect=(0.0, 0.0, 1.0, 0.80))
    return GeneratedFigure(section="security_attacker_sweep", path=path, sources=[source])


def plot_correlated_failure(record: ManifestRecord, output_dir: Path) -> Optional[GeneratedFigure]:
    payload, source = load_stage_payload(record, "security")
    if payload is None or source is None:
        return None
    rows = payload.get("correlated_failure", [])
    if not rows:
        return None

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["strategy"])].append(row)

    fig, axes = plt.subplots(1, 2, figsize=(ACM_DOUBLE_COLUMN_WIDTH, ACM_PANEL_HEIGHT + 0.40), sharex=True)
    for strategy_name in sorted(grouped, key=strategy_sort_key):
        items = sorted(grouped[strategy_name], key=lambda item: float(item["outage_probability"]))
        xs = [float(item["outage_probability"]) for item in items]
        axes[0].plot(xs, [float(item["mean_unique_failure_domain_ratio"]) for item in items], marker=strategy_marker(strategy_name), linestyle=strategy_linestyle(strategy_name), markerfacecolor="white", markeredgewidth=0.8, label=strategy_label(strategy_name), color=strategy_color(strategy_name))
        axes[1].plot(xs, [float(item["recovery_success_rate"]) for item in items], marker=strategy_marker(strategy_name), linestyle=strategy_linestyle(strategy_name), markerfacecolor="white", markeredgewidth=0.8, label=strategy_label(strategy_name), color=strategy_color(strategy_name))
    axes[0].set_title("Correlated failure: diversity retention")
    axes[0].set_ylabel("Mean unique failure-domain ratio")
    axes[1].set_title("Correlated failure: recovery success")
    axes[1].set_ylabel("Recovery success rate")
    for axis in axes:
        axis.set_xlabel("Outage probability")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.0), columnspacing=0.9, handletextpad=0.5)

    path = output_dir / "security" / "security_correlated_failure.png"
    save_figure(fig, path, tight_rect=(0.0, 0.0, 1.0, 0.80))
    return GeneratedFigure(section="security_correlated_failure", path=path, sources=[source])


def plot_witness_collusion(record: ManifestRecord, output_dir: Path) -> Optional[GeneratedFigure]:
    payload, source = load_stage_payload(record, "security")
    if payload is None or source is None:
        return None
    rows = payload.get("witness_collusion", [])
    if not rows:
        return None

    labels = [f"q={int(row['q'])}, q_min={int(row['q_min'])}" for row in rows]
    xs = list(range(len(rows)))
    width = 0.36

    fig, ax = plt.subplots(figsize=(ACM_DOUBLE_COLUMN_WIDTH, ACM_PANEL_HEIGHT))
    ax.bar(
        [x - width / 2 for x in xs],
        [float(row["measured_capture_rate"]) for row in rows],
        width=width, label="Measured capture rate",
        color="#0072B2", edgecolor="#1f1f1f", linewidth=0.6,
    )
    ax.bar(
        [x + width / 2 for x in xs],
        [float(row["hypergeometric_capture_bound"]) for row in rows],
        width=width, label="Hypergeometric bound",
        color="#E69F00", edgecolor="#1f1f1f", linewidth=0.6,
        hatch="//", alpha=0.95,
    )
    ax.set_title("Witness-collusion validation")
    ax.set_ylabel("Capture rate")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.legend()

    path = output_dir / "security" / "security_witness_collusion.png"
    save_figure(fig, path)
    return GeneratedFigure(section="security_witness_collusion", path=path, sources=[source])


def plot_block_withholding(record: ManifestRecord, output_dir: Path) -> Optional[GeneratedFigure]:
    payload, source = load_stage_payload(record, "security")
    if payload is None or source is None:
        return None
    rows = payload.get("block_withholding", [])
    if not rows:
        return None

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["strategy"])].append(row)

    fig, axes = plt.subplots(1, 2, figsize=(ACM_DOUBLE_COLUMN_WIDTH, ACM_PANEL_HEIGHT + 0.40), sharex=True)
    for strategy_name in sorted(grouped, key=strategy_sort_key):
        items = sorted(grouped[strategy_name], key=lambda item: float(item["withholding_probability"]))
        xs = [float(item["withholding_probability"]) for item in items]
        axes[0].plot(xs, [float(item["fallback_activation_rate"]) for item in items], marker=strategy_marker(strategy_name), linestyle=strategy_linestyle(strategy_name), markerfacecolor="white", markeredgewidth=0.8, label=strategy_label(strategy_name), color=strategy_color(strategy_name))
        axes[1].plot(xs, [float(item["mean_recovery_latency_ms"]) for item in items], marker=strategy_marker(strategy_name), linestyle=strategy_linestyle(strategy_name), markerfacecolor="white", markeredgewidth=0.8, label=strategy_label(strategy_name), color=strategy_color(strategy_name))
    axes[0].set_title("Block withholding: fallback activation")
    axes[0].set_ylabel("Fallback activation rate")
    axes[1].set_title("Block withholding: recovery latency")
    axes[1].set_ylabel("Mean recovery latency (ms)")
    for axis in axes:
        axis.set_xlabel("Withholding probability")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.0), columnspacing=0.9, handletextpad=0.5)

    path = output_dir / "security" / "security_block_withholding.png"
    save_figure(fig, path, tight_rect=(0.0, 0.0, 1.0, 0.80))
    return GeneratedFigure(section="security_block_withholding", path=path, sources=[source])


def plot_long_horizon(payload: dict[str, Any], source: Path, output_dir: Path, preferred_k: int) -> Optional[GeneratedFigure]:
    rows = payload.get("long_horizon", [])
    if not rows:
        return None

    available_k = sorted({int(row.get("committee_k", 0) or 0) for row in rows})
    if not available_k:
        return None
    target_k = preferred_k if preferred_k in available_k else available_k[len(available_k) // 2]
    filtered = [row for row in rows if int(row.get("committee_k", 0) or 0) == target_k]
    if not filtered:
        return None

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in filtered:
        grouped[str(row["strategy"])].append(row)

    fig, axes = plt.subplots(1, 2, figsize=(ACM_DOUBLE_COLUMN_WIDTH, ACM_PANEL_HEIGHT + 0.40), sharex=True)
    for strategy_name in sorted(grouped, key=strategy_sort_key):
        items = sorted(grouped[strategy_name], key=lambda item: float(item["attacker_fraction"]))
        xs = [float(item["attacker_fraction"]) for item in items]
        axes[0].plot(xs, [float(item.get("selection_concentration", 0.0)) for item in items], marker=strategy_marker(strategy_name), linestyle=strategy_linestyle(strategy_name), markerfacecolor="white", markeredgewidth=0.8, label=strategy_label(strategy_name), color=strategy_color(strategy_name))
        axes[1].plot(xs, [float(item.get("gini_coefficient", 0.0)) for item in items], marker=strategy_marker(strategy_name), linestyle=strategy_linestyle(strategy_name), markerfacecolor="white", markeredgewidth=0.8, label=strategy_label(strategy_name), color=strategy_color(strategy_name))
    axes[0].set_title(f"Long-horizon concentration (k={target_k})")
    axes[0].set_ylabel("Selection concentration")
    axes[1].set_title(f"Long-horizon fairness (k={target_k})")
    axes[1].set_ylabel("Gini coefficient")
    for axis in axes:
        axis.set_xlabel("Attacker fraction")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.0), columnspacing=0.9, handletextpad=0.5)

    path = output_dir / "long_horizon" / f"long_horizon_fairness_k{target_k}.png"
    save_figure(fig, path, tight_rect=(0.0, 0.0, 1.0, 0.80))
    return GeneratedFigure(section="long_horizon_fairness", path=path, sources=[source])


def write_figure_manifest(output_dir: Path, generated: list[GeneratedFigure], report_roots: list[Path], font_family: str) -> Path:
    payload = {
        "paper_profile": "acm_ccs_2026",
        "template": "acmart sigconf",
        "geometry": {
            "single_column_width_in": ACM_SINGLE_COLUMN_WIDTH,
            "double_column_width_in": ACM_DOUBLE_COLUMN_WIDTH,
            "panel_height_in": ACM_PANEL_HEIGHT,
            "wide_panel_height_in": ACM_WIDE_PANEL_HEIGHT,
            "grid_height_in": ACM_GRID_HEIGHT,
        },
        "font_family": font_family,
        "font_fallbacks": available_serif_fonts(),
        "export_formats": list(FIGURE_EXTENSIONS),
        "output_dir": str(output_dir),
        "report_roots": [str(root) for root in report_roots],
        "figures": [
            {
                "section": figure.section,
                "path": str(figure.path),
                "sources": [str(source) for source in figure.sources],
            }
            for figure in generated
        ],
    }
    manifest_path = output_dir / "figure_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return manifest_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ACM CCS 2026 figures from archived evaluation results.")
    parser.add_argument(
        "--report-roots",
        nargs="*",
        default=[str(path) for path in DEFAULT_REPORT_ROOTS],
        help="Report roots to scan for manifests and raw JSON artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where figures and the figure manifest will be written.",
    )
    parser.add_argument("--canonical-nodes", type=int, default=100, help="Preferred node count for canonical comparison plots.")
    parser.add_argument("--canonical-rounds", type=int, default=1000, help="Preferred round count for canonical comparison plots.")
    parser.add_argument("--canonical-seed", type=int, default=42, help="Preferred seed for canonical comparison plots.")
    parser.add_argument("--long-horizon-k", type=int, default=7, help="Preferred committee size for long-horizon fairness plots.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    font_family = configure_plot_style()

    report_roots = [Path(entry).resolve() for entry in args.report_roots]
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    generated: list[GeneratedFigure] = []

    solver_files = discover_solver_study_files(report_roots)
    if solver_files:
        solver_aggregated, solver_sources = aggregate_solver_metrics(solver_files)
        solver_figures = plot_solver_figures(solver_aggregated, output_dir)
        for figure in solver_figures:
            figure.sources.extend(solver_sources)
        generated.extend(solver_figures)

    manifest_records = discover_comparative_manifests(report_roots)
    canonical_record = select_canonical_comparison(
        manifest_records,
        preferred_nodes=args.canonical_nodes,
        preferred_rounds=args.canonical_rounds,
        preferred_seed=args.canonical_seed,
    )

    if canonical_record is not None:
        figure = plot_literature_diversity_scatter(canonical_record, output_dir)
        if figure is not None:
            generated.append(figure)

        figure = plot_measurement_overhead(canonical_record, output_dir)
        if figure is not None:
            generated.append(figure)

        figure = plot_committee_ablation(canonical_record, output_dir)
        if figure is not None:
            generated.append(figure)

        for plotter in (plot_attacker_sweep, plot_correlated_failure, plot_witness_collusion, plot_block_withholding):
            figure = plotter(canonical_record, output_dir)
            if figure is not None:
                generated.append(figure)

    generated.extend(plot_strategy_scaling(manifest_records, output_dir))

    long_record, long_payload, long_source = select_long_horizon_record(manifest_records)
    if long_payload is not None and long_source is not None:
        figure = plot_long_horizon(long_payload, long_source, output_dir, preferred_k=args.long_horizon_k)
        if figure is not None:
            generated.append(figure)

    manifest_path = write_figure_manifest(output_dir, generated, report_roots, font_family)

    print(f"Generated {len(generated)} figure(s) under {output_dir}")
    print(f"Font family: {font_family}")
    for figure in generated:
        print(f"- {figure.section}: {figure.path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()