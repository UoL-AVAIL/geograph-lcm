from __future__ import annotations

from pathlib import Path
from typing import Any

from geograph_lcm.config import LCMAsset
from geograph_lcm.lcm_policy import LCMSelection, select_lcm_asset
from geograph_lcm.stage_utils import ensure_dir, utc_now_iso, write_json, write_stage_success_marker


def run(
    config: dict[str, Any],
    input_dir: Path | None,
    output_dir: Path,
    lcm_assets: list[LCMAsset],
) -> dict[str, Any]:
    ensure_dir(output_dir)

    # Scaffold behavior: demonstrate the policy with an unset capture year.
    asset, selection = select_lcm_asset(capture_year=None, assets=lcm_assets)
    selection_data: dict[str, Any] = _selection_to_dict(selection)
    selection_data["lcm_resolution_m"] = asset.resolution_m
    selection_data["lcm_asset_path"] = str(asset.path)
    selection_data["lcm_asset_crs"] = asset.crs
    selection_data["match_method"] = "native_resolution_pixel_lookup"

    summary = {
        "stage": "match_lcm",
        "started_at": utc_now_iso(),
        "input_dir": str(input_dir) if input_dir else None,
        "output_dir": str(output_dir),
        "selection_example": selection_data,
        "notes": "Scaffold stage: full spatial join implementation pending.",
    }
    write_json(output_dir / "match_lcm_summary.json", summary)
    write_stage_success_marker(output_dir, summary)
    return summary


def _selection_to_dict(selection: LCMSelection) -> dict[str, Any]:
    return {
        "capture_year": selection.capture_year,
        "selected_lcm_year": selection.selected_lcm_year,
        "selection_reason": selection.selection_reason,
    }

