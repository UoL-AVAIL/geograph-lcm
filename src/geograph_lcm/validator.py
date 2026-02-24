from __future__ import annotations

from pathlib import Path
from typing import Any

from geograph_lcm.stage_utils import ensure_dir, utc_now_iso, write_json, write_stage_success_marker


def run(config: dict[str, Any], input_dir: Path | None, output_dir: Path) -> dict[str, Any]:
    ensure_dir(output_dir)
    summary = {
        "stage": "validate",
        "started_at": utc_now_iso(),
        "input_dir": str(input_dir) if input_dir else None,
        "output_dir": str(output_dir),
        "notes": "Scaffold stage: automated checks and report.yaml generation pending.",
    }
    write_json(output_dir / "validate_summary.json", summary)
    write_stage_success_marker(output_dir, summary)
    return summary

