from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from geograph_lcm import curator, dataset_writer, downloader, georeferencer, ingestor, lcm_matcher, validator
from geograph_lcm.config import LCMAsset
from geograph_lcm.stage_utils import (
    ensure_dir,
    stage_is_complete,
    utc_now_iso,
    write_json,
    write_jsonl_event,
)

StageFn = Callable[[dict[str, Any], Path | None, Path], dict[str, Any]]


@dataclass(frozen=True)
class Stage:
    name: str
    runner: Callable[..., dict[str, Any]]


STAGES: list[Stage] = [
    Stage("download", downloader.run),
    Stage("ingest", ingestor.run),
    Stage("curate", curator.run),
    Stage("georeference", georeferencer.run),
    Stage("match_lcm", lcm_matcher.run),
    Stage("write_dataset", dataset_writer.run),
    Stage("validate", validator.run),
]


def run_pipeline(
    config: dict[str, Any],
    lcm_assets: list[LCMAsset],
    from_stage: str,
    to_stage: str,
    command: str,
) -> dict[str, Any]:
    output_root = Path(config.get("pipeline", {}).get("output_root", "outputs"))
    ensure_dir(output_root)
    logs_path = output_root / "pipeline_events.jsonl"
    print(f"[pipeline] output_root={output_root}")

    selected_stages = _slice_stages(from_stage=from_stage, to_stage=to_stage)
    print("[pipeline] stages=" + ", ".join(stage.name for stage in selected_stages))
    stage_results: list[dict[str, Any]] = []
    started_at = utc_now_iso()

    for idx, stage in enumerate(selected_stages):
        stage_dir = output_root / stage.name
        ensure_dir(stage_dir)
        prev_stage_dir = output_root / selected_stages[idx - 1].name if idx > 0 else None

        if stage_is_complete(stage_dir):
            print(f"[stage:{stage.name}] skipped (already complete)")
            skipped = {
                "stage": stage.name,
                "status": "skipped_completed",
                "timestamp": utc_now_iso(),
                "stage_output_dir": str(stage_dir),
            }
            write_jsonl_event(logs_path, skipped)
            stage_results.append(skipped)
            continue

        start_evt = {"stage": stage.name, "status": "start", "timestamp": utc_now_iso()}
        write_jsonl_event(logs_path, start_evt)
        print(f"[stage:{stage.name}] start")

        if stage.name == "match_lcm":
            result = stage.runner(config, prev_stage_dir, stage_dir, lcm_assets)
        else:
            result = stage.runner(config, prev_stage_dir, stage_dir)

        done_evt = {
            "stage": stage.name,
            "status": "completed",
            "timestamp": utc_now_iso(),
            "stage_output_dir": str(stage_dir),
        }
        write_jsonl_event(logs_path, done_evt)
        stage_results.append({"stage": stage.name, "status": "completed", "result": result})
        print(f"[stage:{stage.name}] completed")

    manifest = {
        "started_at": started_at,
        "completed_at": utc_now_iso(),
        "command": command,
        "from_stage": from_stage,
        "to_stage": to_stage,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "git_commit": _current_git_commit(),
        },
        "stages": stage_results,
    }
    write_json(output_root / "pipeline_run.json", manifest)
    print(f"[pipeline] wrote manifest: {output_root / 'pipeline_run.json'}")
    return manifest


def _slice_stages(from_stage: str, to_stage: str) -> list[Stage]:
    names = [s.name for s in STAGES]
    if from_stage not in names:
        raise ValueError(f"Unknown --from-stage '{from_stage}'. Valid stages: {names}")
    if to_stage not in names:
        raise ValueError(f"Unknown --to-stage '{to_stage}'. Valid stages: {names}")

    start = names.index(from_stage)
    end = names.index(to_stage)
    if start > end:
        raise ValueError("--from-stage must come before or equal to --to-stage")
    return STAGES[start : end + 1]


def _current_git_commit() -> str | None:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        return out
    except Exception:
        return None
