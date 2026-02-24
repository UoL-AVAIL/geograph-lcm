from __future__ import annotations

from pathlib import Path
from typing import Any

from geograph_lcm.stage_utils import ensure_dir, utc_now_iso, write_json, write_stage_success_marker


def run(config: dict[str, Any], input_dir: Path | None, output_dir: Path) -> dict[str, Any]:
    ensure_dir(output_dir)
    dataset_root = Path(config.get("dataset", {}).get("root", "outputs/dataset"))
    ensure_dir(dataset_root / "images")

    summary = {
        "stage": "write_dataset",
        "started_at": utc_now_iso(),
        "input_dir": str(input_dir) if input_dir else None,
        "output_dir": str(output_dir),
        "dataset_root": str(dataset_root),
        "notes": "Scaffold stage: labels.csv and dataset README generation pending.",
    }
    write_json(output_dir / "write_dataset_summary.json", summary)
    write_stage_success_marker(output_dir, summary)
    return summary

