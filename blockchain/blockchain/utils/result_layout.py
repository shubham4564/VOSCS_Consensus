#!/usr/bin/env python3
"""Shared result directory layout helpers for reviewer-facing runs."""

from __future__ import annotations

import os
import re
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ResultLayout:
    label: str
    start_timestamp: str
    root_dir: str
    data_dir: str
    figures_dir: str
    exports_dir: str
    metadata_dir: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "run"


def _allocate_unique_dir(base_dir: str, folder_name: str) -> str:
    candidate = os.path.join(base_dir, folder_name)
    if not os.path.exists(candidate):
        return candidate

    suffix = 1
    while True:
        candidate = os.path.join(base_dir, f"{folder_name}_{suffix:02d}")
        if not os.path.exists(candidate):
            return candidate
        suffix += 1


def _build_layout(root_dir: str, label: str, start_timestamp: str) -> ResultLayout:
    data_dir = os.path.join(root_dir, "data")
    figures_dir = os.path.join(root_dir, "figures")
    exports_dir = os.path.join(root_dir, "exports")
    metadata_dir = os.path.join(root_dir, "metadata")

    for path in (root_dir, data_dir, figures_dir, exports_dir, metadata_dir):
        os.makedirs(path, exist_ok=True)

    return ResultLayout(
        label=label,
        start_timestamp=start_timestamp,
        root_dir=root_dir,
        data_dir=data_dir,
        figures_dir=figures_dir,
        exports_dir=exports_dir,
        metadata_dir=metadata_dir,
    )


def create_run_layout(
    base_output_dir: str,
    run_name: str,
    *,
    start_timestamp: Optional[str] = None,
) -> ResultLayout:
    os.makedirs(base_output_dir, exist_ok=True)

    timestamp = start_timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{timestamp}_{_slugify(run_name)}"
    root_dir = _allocate_unique_dir(base_output_dir, folder_name)
    return _build_layout(root_dir, run_name, timestamp)


def create_stage_layout(run_layout: ResultLayout, stage_name: str) -> ResultLayout:
    stage_root = os.path.join(run_layout.root_dir, _slugify(stage_name))
    return _build_layout(stage_root, stage_name, run_layout.start_timestamp)


def write_run_metadata(
    layout: ResultLayout,
    payload: Dict[str, Any],
    *,
    filename: str = "run_manifest.json",
) -> str:
    path = os.path.join(layout.metadata_dir, filename)
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2)
    return path