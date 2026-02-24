from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from geograph_lcm.stage_utils import ensure_dir, utc_now_iso, write_json, write_stage_success_marker


def run(config: dict[str, Any], input_dir: Path | None, output_dir: Path) -> dict[str, Any]:
    del config
    ensure_dir(output_dir)
    source_manifest = _resolve_source_manifest(input_dir)
    output_manifest = output_dir / "ingested_manifest.jsonl"

    input_records = 0
    records_written = 0
    invalid_records = 0

    with output_manifest.open("w", encoding="utf-8") as out_fh:
        if source_manifest is not None and source_manifest.exists():
            with source_manifest.open("r", encoding="utf-8") as in_fh:
                for line in in_fh:
                    line = line.strip()
                    if not line:
                        continue
                    input_records += 1
                    try:
                        payload = json.loads(line)
                    except Exception:
                        invalid_records += 1
                        continue
                    if not isinstance(payload, dict):
                        invalid_records += 1
                        continue
                    normalized = _normalize_record(payload)
                    if normalized is None:
                        invalid_records += 1
                        continue
                    out_fh.write(json.dumps(normalized, sort_keys=True))
                    out_fh.write("\n")
                    records_written += 1

    summary = {
        "stage": "ingest",
        "started_at": utc_now_iso(),
        "completed_at": utc_now_iso(),
        "input_dir": str(input_dir) if input_dir else None,
        "output_dir": str(output_dir),
        "source_manifest": str(source_manifest) if source_manifest else None,
        "ingested_manifest": str(output_manifest),
        "input_records": input_records,
        "records_written": records_written,
        "invalid_records": invalid_records,
    }
    write_json(output_dir / "ingest_summary.json", summary)
    write_stage_success_marker(output_dir, summary)
    return summary


def _resolve_source_manifest(input_dir: Path | None) -> Path | None:
    if input_dir is None:
        return None
    raw_path = input_dir / "raw" / "metadata.jsonl"
    if raw_path.exists():
        return raw_path
    direct_path = input_dir / "metadata.jsonl"
    if direct_path.exists():
        return direct_path
    return raw_path


def _normalize_record(record: dict[str, Any]) -> dict[str, Any] | None:
    item_id = record.get("id")
    if item_id is None:
        return None
    timestamp = record.get("timestamp")
    normalized = {
        "id": str(item_id),
        "image_path": record.get("image_path"),
        "image_url": record.get("image_url"),
        "sha256": record.get("sha256"),
        "timestamp": timestamp,
        "capture_year": _extract_capture_year(timestamp),
        "lat": _to_float(record.get("lat")),
        "lon": _to_float(record.get("lon")),
        "license_raw": record.get("license"),
        "license_normalized": _normalize_license(record.get("license")),
        "fetched_at": record.get("fetched_at"),
        "provenance": record.get("provenance", {}),
        "raw_item": record.get("raw_item", {}),
    }
    return normalized


def _extract_capture_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        if value > 100_000:
            try:
                return datetime.fromtimestamp(value, tz=UTC).year
            except Exception:
                return None
        return value
    if isinstance(value, float):
        try:
            return datetime.fromtimestamp(value, tz=UTC).year
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
        if text.isdigit():
            try:
                return datetime.fromtimestamp(float(text), tz=UTC).year
            except Exception:
                return None
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _normalize_license(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "UNKNOWN"
    if "by-sa" in text:
        return "CC-BY-SA"
    if "by/" in text or "cc-by" in text:
        return "CC-BY"
    return text.upper()
