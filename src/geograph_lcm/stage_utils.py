from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)


def write_stage_success_marker(stage_output_dir: Path, payload: dict[str, Any]) -> None:
    marker_path = stage_output_dir / "_SUCCESS.json"
    write_json(marker_path, payload)


def stage_is_complete(stage_output_dir: Path) -> bool:
    return (stage_output_dir / "_SUCCESS.json").exists()


def write_jsonl_event(log_path: Path, event: dict[str, Any]) -> None:
    ensure_dir(log_path.parent)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True))
        fh.write("\n")

