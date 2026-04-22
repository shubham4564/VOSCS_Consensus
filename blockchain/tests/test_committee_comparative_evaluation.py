#!/usr/bin/env python3

import json
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

from tools.committee_comparative_evaluation import ComparativeEvaluationConfig, run_comparative_evaluation


def test_run_comparative_evaluation_reduced_only_creates_manifest():
    cfg = ComparativeEvaluationConfig(
        output_dir="reports",
        committee_k=3,
        exact_oracle_max_candidates=6,
        skip_plots=True,
        run_reduced=True,
        run_literature=False,
        run_solver=False,
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