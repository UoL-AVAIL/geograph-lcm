from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml

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
    source_manifest = _resolve_source_manifest(input_dir)
    output_manifest = output_dir / "matched_manifest.jsonl"
    lcm_cfg = config.get("lcm", {})
    taxonomy_path = Path(lcm_cfg.get("taxonomy_path", "config/lcm_taxonomy.yaml"))
    taxonomy = _load_lcm_taxonomy(taxonomy_path)

    input_records = 0
    records_written = 0
    invalid_records = 0
    status_counts = {
        "matched": 0,
        "missing_coordinates": 0,
        "out_of_bounds": 0,
        "nodata": 0,
        "error": 0,
    }
    preflight_by_year: dict[str, dict[str, Any]] = {}
    preflight_cache: dict[int, dict[str, Any]] = {}

    with output_manifest.open("w", encoding="utf-8") as out_fh:
        if source_manifest is not None and source_manifest.exists():
            with source_manifest.open("r", encoding="utf-8") as in_fh:
                for line in in_fh:
                    line = line.strip()
                    if not line:
                        continue
                    input_records += 1
                    try:
                        record = json.loads(line)
                    except Exception:
                        invalid_records += 1
                        continue
                    if not isinstance(record, dict):
                        invalid_records += 1
                        continue

                    capture_year = _to_int(record.get("capture_year"))
                    asset, selection = select_lcm_asset(
                        capture_year=capture_year, assets=lcm_assets
                    )
                    if asset.year not in preflight_cache:
                        preflight_cache[asset.year] = _validate_asset_checksum(asset)
                    preflight_by_year[str(asset.year)] = preflight_cache[asset.year]

                    matched = _match_record(
                        record=record,
                        asset=asset,
                        selection=selection,
                        taxonomy=taxonomy,
                        lcm_cfg=lcm_cfg,
                    )
                    status = str(matched.get("lcm_match_status", "error"))
                    if status not in status_counts:
                        status = "error"
                    status_counts[status] += 1
                    out_fh.write(json.dumps(matched, sort_keys=True))
                    out_fh.write("\n")
                    records_written += 1

    if not preflight_by_year and lcm_assets:
        default_asset, _ = select_lcm_asset(capture_year=None, assets=lcm_assets)
        preflight_by_year[str(default_asset.year)] = _validate_asset_checksum(default_asset)

    summary = {
        "stage": "match_lcm",
        "started_at": utc_now_iso(),
        "completed_at": utc_now_iso(),
        "input_dir": str(input_dir) if input_dir else None,
        "output_dir": str(output_dir),
        "source_manifest": str(source_manifest) if source_manifest else None,
        "matched_manifest": str(output_manifest),
        "input_records": input_records,
        "records_written": records_written,
        "invalid_records": invalid_records,
        "match_status_counts": status_counts,
        "checksum_preflight_by_year": preflight_by_year,
        "taxonomy_path": str(taxonomy_path),
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


def _resolve_source_manifest(input_dir: Path | None) -> Path | None:
    if input_dir is None:
        return None
    return input_dir / "georeferenced_manifest.jsonl"


def _validate_asset_checksum(asset: LCMAsset) -> dict[str, Any]:
    path = Path(asset.path)
    if not path.exists():
        raise FileNotFoundError(f"Configured LCM asset not found: {path}")

    actual = _sha256_file(path)
    expected = str(asset.checksum_sha256 or "").strip()
    if expected and expected.upper() != "TBD":
        if actual.lower() != expected.lower():
            raise ValueError(
                f"LCM checksum mismatch for {path}: expected {expected}, actual {actual}"
            )
        status = "verified"
    else:
        status = "computed_unverified"

    return {
        "status": status,
        "path": str(path),
        "expected_sha256": expected if expected else None,
        "actual_sha256": actual,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _match_record(
    record: dict[str, Any],
    asset: LCMAsset,
    selection: LCMSelection,
    taxonomy: dict[str, dict[int, Any]],
    lcm_cfg: dict[str, Any],
) -> dict[str, Any]:
    lat = _to_float(record.get("lat"))
    lon = _to_float(record.get("lon"))
    selection_data = _selection_to_dict(selection)

    matched: dict[str, Any] = dict(record)
    matched.update(
        {
            "selected_lcm_year": selection_data["selected_lcm_year"],
            "selection_reason": selection_data["selection_reason"],
            "lcm_asset_path": str(asset.path),
            "lcm_asset_crs": asset.crs,
            "lcm_resolution_m": asset.resolution_m,
            "match_method": "native_resolution_pixel_lookup",
        }
    )

    if lat is None or lon is None:
        matched.update(
            {
                "lcm_value": None,
                "lcm_match_status": "missing_coordinates",
                "lcm_window_size_px": None,
                "lcm_window_valid_count": None,
                "lcm_window_agreement": None,
                "lcm_window_majority_value": None,
                "lcm_center_majority_match": None,
                "lcm_label_confidence": None,
                "lcm_low_confidence": None,
            }
        )
        return matched

    try:
        sample = _sample_asset_value(asset=asset, lat=lat, lon=lon)
    except Exception as exc:
        matched.update(
            {
                "lcm_value": None,
                "lcm_match_status": "error",
                "lcm_error": str(exc),
                "lcm_window_size_px": None,
                "lcm_window_valid_count": None,
                "lcm_window_agreement": None,
                "lcm_window_majority_value": None,
                "lcm_center_majority_match": None,
                "lcm_label_confidence": None,
                "lcm_low_confidence": None,
            }
        )
        return matched

    if sample["status"] == "matched":
        noise_cfg = lcm_cfg.get("noise", {}) if isinstance(lcm_cfg, dict) else {}
        matched.update(
            {
                "lcm_value": sample["value"],
                "lcm_match_status": "matched",
            }
        )
        value = sample["value"]
        if isinstance(value, int):
            labels = _taxonomy_labels_for_code(value, taxonomy=taxonomy)
            matched["lcm_l2"] = labels["l2_label"]
            matched["lcm_l3"] = labels["l3_label"]
            matched["lcm_l2_code"] = labels["l2_code"]
            matched["lcm_l3_code"] = labels["l3_code"]
            quality = _estimate_label_quality(
                asset=asset,
                lat=lat,
                lon=lon,
                center_value=value,
                georef_confidence=record.get("georef_confidence"),
                noise_cfg=noise_cfg,
            )
            min_confidence = _as_float(noise_cfg.get("min_label_confidence", 0.0), default=0.0)
            low_confidence = quality["label_confidence"] < min_confidence
            matched["lcm_window_size_px"] = quality["window_size_px"]
            matched["lcm_window_valid_count"] = quality["window_valid_count"]
            matched["lcm_window_agreement"] = quality["window_agreement"]
            matched["lcm_window_majority_value"] = quality["window_majority_value"]
            matched["lcm_center_majority_match"] = quality["center_majority_match"]
            matched["lcm_label_confidence"] = quality["label_confidence"]
            matched["lcm_low_confidence"] = low_confidence
        else:
            matched["lcm_l2"] = None
            matched["lcm_l3"] = None
            matched["lcm_l2_code"] = None
            matched["lcm_l3_code"] = None
            matched["lcm_window_size_px"] = None
            matched["lcm_window_valid_count"] = None
            matched["lcm_window_agreement"] = None
            matched["lcm_window_majority_value"] = None
            matched["lcm_center_majority_match"] = None
            matched["lcm_label_confidence"] = None
            matched["lcm_low_confidence"] = None
    else:
        matched.update({"lcm_value": None, "lcm_match_status": sample["status"]})
        matched["lcm_l2"] = None
        matched["lcm_l3"] = None
        matched["lcm_l2_code"] = None
        matched["lcm_l3_code"] = None
        matched["lcm_window_size_px"] = None
        matched["lcm_window_valid_count"] = None
        matched["lcm_window_agreement"] = None
        matched["lcm_window_majority_value"] = None
        matched["lcm_center_majority_match"] = None
        matched["lcm_label_confidence"] = None
        matched["lcm_low_confidence"] = None
    return matched


def _estimate_label_quality(
    asset: LCMAsset,
    lat: float,
    lon: float,
    center_value: int,
    georef_confidence: Any,
    noise_cfg: dict[str, Any],
) -> dict[str, Any]:
    window_size = _as_int(noise_cfg.get("neighborhood_window_px", 3), default=3)
    if window_size < 1:
        window_size = 1
    if window_size % 2 == 0:
        window_size += 1

    window = _sample_window_values(asset=asset, lat=lat, lon=lon, window_size_px=window_size)
    values = [v for v in window if v is not None]
    if not values:
        values = [center_value]
    majority_value, agreement = _majority_and_agreement(values)
    center_majority_match = bool(majority_value == center_value)

    georef_score = _georef_confidence_score(georef_confidence)
    score = agreement * 0.7 + georef_score * 0.3
    if not center_majority_match:
        score *= 0.8
    score = min(max(score, 0.0), 1.0)

    return {
        "window_size_px": window_size,
        "window_valid_count": len(values),
        "window_agreement": round(agreement, 4),
        "window_majority_value": majority_value,
        "center_majority_match": center_majority_match,
        "label_confidence": round(score, 4),
    }


def _sample_window_values(
    asset: LCMAsset, lat: float, lon: float, window_size_px: int
) -> list[int | None]:
    if window_size_px <= 1:
        center = _sample_asset_value(asset=asset, lat=lat, lon=lon)
        if center.get("status") != "matched":
            return []
        value = center.get("value")
        return [int(value)] if isinstance(value, int) else []

    try:
        import rasterio
        from rasterio.warp import transform
    except Exception:
        return []

    try:
        with rasterio.open(asset.path) as ds:
            transformed = transform("EPSG:4326", ds.crs, [lon], [lat])
            xs = transformed[0]
            ys = transformed[1]
            x = float(xs[0])
            y = float(ys[0])
            row, col = ds.index(x, y)
            half = window_size_px // 2
            row_start = max(0, row - half)
            row_stop = min(ds.height, row + half + 1)
            col_start = max(0, col - half)
            col_stop = min(ds.width, col + half + 1)
            if row_start >= row_stop or col_start >= col_stop:
                return []

            band = ds.read(1, window=((row_start, row_stop), (col_start, col_stop)))
            nodata = ds.nodata
            values: list[int | None] = []
            for value in band.flatten():
                if nodata is not None and float(value) == float(nodata):
                    continue
                try:
                    parsed = int(value)
                except Exception:
                    continue
                if math.isnan(float(parsed)):
                    continue
                values.append(parsed)
            return values
    except Exception:
        return []


def _majority_and_agreement(values: list[int]) -> tuple[int, float]:
    counts: dict[int, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    majority_value = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    agreement = counts[majority_value] / max(1, len(values))
    return majority_value, agreement


def _georef_confidence_score(value: Any) -> float:
    text = str(value or "").strip().lower()
    if text == "high":
        return 1.0
    if text == "medium":
        return 0.7
    if text == "low":
        return 0.4
    return 0.6


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _sample_asset_value(asset: LCMAsset, lat: float, lon: float) -> dict[str, Any]:
    try:
        import rasterio
        from rasterio.warp import transform
    except Exception as exc:
        raise RuntimeError(
            "Raster sampling requires rasterio. Install optional geo dependencies."
        ) from exc

    with rasterio.open(asset.path) as ds:
        transformed = transform("EPSG:4326", ds.crs, [lon], [lat])
        xs = transformed[0]
        ys = transformed[1]
        x = float(xs[0])
        y = float(ys[0])
        row, col = ds.index(x, y)
        if row < 0 or col < 0 or row >= ds.height or col >= ds.width:
            return {"status": "out_of_bounds", "value": None}
        band = ds.read(1, window=((row, row + 1), (col, col + 1)))
        value = band[0, 0]
        nodata = ds.nodata
        if nodata is not None and float(value) == float(nodata):
            return {"status": "nodata", "value": None}
        try:
            int_value = int(value)
        except Exception:
            int_value = None
        return {"status": "matched", "value": int_value if int_value is not None else float(value)}


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _taxonomy_labels_for_code(code: int, taxonomy: dict[str, dict[int, Any]]) -> dict[str, Any]:
    l3_labels = taxonomy.get("l3_labels", {})
    l2_labels = taxonomy.get("l2_labels", {})
    l3_to_l2 = taxonomy.get("l3_to_l2", {})
    l3_label = str(l3_labels.get(code, f"UNKNOWN_{code}"))
    l2_code = l3_to_l2.get(code)
    l2_label = str(l2_labels.get(l2_code, "UNKNOWN")) if isinstance(l2_code, int) else "UNKNOWN"
    return {
        "l2_code": l2_code,
        "l2_label": l2_label,
        "l3_code": code,
        "l3_label": l3_label,
    }


def _load_lcm_taxonomy(path: Path) -> dict[str, dict[int, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    node = raw.get("lcm_taxonomy", {})
    if not isinstance(node, dict):
        raise ValueError("Invalid taxonomy config: expected top-level lcm_taxonomy mapping")
    l3_codes = _normalize_int_keyed_map(node.get("l3_codes", {}))
    l2_codes = _normalize_int_keyed_map(node.get("l2_aggregate_codes", {}))
    l3_to_l2 = _normalize_int_keyed_map(node.get("l3_to_l2", {}))
    return {"l3_labels": l3_codes, "l2_labels": l2_codes, "l3_to_l2": l3_to_l2}


def _normalize_int_keyed_map(value: Any) -> dict[int, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[int, Any] = {}
    for key, item in value.items():
        try:
            out[int(key)] = item
        except Exception:
            continue
    return out
