from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from geograph_lcm.stage_utils import ensure_dir, utc_now_iso, write_json, write_stage_success_marker


def run(config: dict[str, Any], input_dir: Path | None, output_dir: Path) -> dict[str, Any]:
    ensure_dir(output_dir)
    source_manifest = _resolve_source_manifest(input_dir)
    output_manifest = output_dir / "georeferenced_manifest.jsonl"
    georef_cfg = config.get("georeferencer", {})
    max_georef_radius_m = float(georef_cfg.get("max_georef_radius_m", 50.0))

    input_records = 0
    records_written = 0
    invalid_records = 0
    confidence_counts = {"high": 0, "medium": 0, "low": 0, "none": 0}

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

                    georef = _georeference_record(payload, max_georef_radius_m=max_georef_radius_m)
                    payload.update(georef)
                    confidence_counts[payload["georef_confidence"]] += 1
                    out_fh.write(json.dumps(payload, sort_keys=True))
                    out_fh.write("\n")
                    records_written += 1

    summary = {
        "stage": "georeference",
        "started_at": utc_now_iso(),
        "completed_at": utc_now_iso(),
        "input_dir": str(input_dir) if input_dir else None,
        "output_dir": str(output_dir),
        "georeferencer_config": config.get("georeferencer", {}),
        "source_manifest": str(source_manifest) if source_manifest else None,
        "georeferenced_manifest": str(output_manifest),
        "input_records": input_records,
        "records_written": records_written,
        "invalid_records": invalid_records,
        "confidence_counts": confidence_counts,
    }
    write_json(output_dir / "georeference_summary.json", summary)
    write_stage_success_marker(output_dir, summary)
    return summary


def _resolve_source_manifest(input_dir: Path | None) -> Path | None:
    if input_dir is None:
        return None
    return input_dir / "curated_manifest.jsonl"


def _georeference_record(record: dict[str, Any], max_georef_radius_m: float) -> dict[str, Any]:
    lat = _to_float(record.get("lat"))
    lon = _to_float(record.get("lon"))
    if lat is None or lon is None:
        return {
            "georef_confidence": "none",
            "georef_confidence_score": 0.0,
            "georef_radius_m": None,
            "georef_method": "missing_coordinates",
            "georef_reason": "lat_or_lon_missing",
        }

    precision = _coordinate_precision(record)
    radius_m = _radius_from_decimal_places(precision)
    confidence = _confidence_from_radius(radius_m, max_georef_radius_m=max_georef_radius_m)
    score = _confidence_score(
        confidence, radius_m=radius_m, max_georef_radius_m=max_georef_radius_m
    )
    return {
        "georef_confidence": confidence,
        "georef_confidence_score": score,
        "georef_radius_m": radius_m,
        "georef_method": "coordinate_precision_estimate",
        "georef_reason": f"decimal_places={precision}",
    }


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _coordinate_precision(record: dict[str, Any]) -> int:
    raw_item = record.get("raw_item")
    lat_raw = None
    lon_raw = None
    if isinstance(raw_item, dict):
        lat_raw = raw_item.get("lat")
        lon_raw = raw_item.get("long", raw_item.get("lon"))
    if lat_raw is None:
        lat_raw = record.get("lat")
    if lon_raw is None:
        lon_raw = record.get("lon")

    lat_places = _decimal_places(lat_raw)
    lon_places = _decimal_places(lon_raw)
    return min(lat_places, lon_places)


def _decimal_places(value: Any) -> int:
    text = str(value or "").strip()
    if "." not in text:
        return 0
    return max(0, len(text.split(".", 1)[1].rstrip("0")))


def _radius_from_decimal_places(places: int) -> float:
    # Approximate 1 degree latitude as 111,000m.
    return 111000.0 * (10 ** (-places))


def _confidence_from_radius(radius_m: float, max_georef_radius_m: float) -> str:
    if radius_m <= max_georef_radius_m:
        return "high"
    if radius_m <= max_georef_radius_m * 5:
        return "medium"
    return "low"


def _confidence_score(confidence: str, radius_m: float, max_georef_radius_m: float) -> float:
    if confidence == "none":
        return 0.0
    if confidence == "high":
        return max(0.75, min(1.0, 1.0 - (radius_m / max(max_georef_radius_m, 1.0)) * 0.2))
    if confidence == "medium":
        return 0.5
    return 0.2
