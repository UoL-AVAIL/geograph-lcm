from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from geograph_lcm.stage_utils import ensure_dir, utc_now_iso, write_json, write_stage_success_marker


def run(config: dict[str, Any], input_dir: Path | None, output_dir: Path) -> dict[str, Any]:
    geograph_cfg = config.get("geograph", {})
    api_key_var = str(geograph_cfg.get("api_key_env_var", "GEOGRAPH_API_KEY"))
    api_key_present = bool(os.environ.get(api_key_var))

    ensure_dir(output_dir)
    summary = {
        "stage": "download",
        "started_at": utc_now_iso(),
        "geograph_api_base_url": geograph_cfg.get("api_base_url"),
        "geograph_api_key_env_var": api_key_var,
        "geograph_api_key_present": api_key_present,
        "source_policy": "geograph_api_only",
        "input_dir": str(input_dir) if input_dir else None,
        "output_dir": str(output_dir),
        "notes": "Scaffold stage: API integration implementation pending.",
    }
    write_json(output_dir / "download_summary.json", summary)
    write_stage_success_marker(output_dir, summary)
    return summary

