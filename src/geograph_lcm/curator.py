from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

from geograph_lcm.stage_utils import ensure_dir, utc_now_iso, write_json, write_stage_success_marker


def run(config: dict[str, Any], input_dir: Path | None, output_dir: Path) -> dict[str, Any]:
    ensure_dir(output_dir)
    source_manifest = _resolve_source_manifest(input_dir)
    output_manifest = output_dir / "curated_manifest.jsonl"
    curator_cfg = config.get("curator", {})
    allowed = _normalized_allowlist(config.get("curator", {}).get("allowed_licenses", []))
    min_width = int(curator_cfg.get("min_width", 0))
    min_height = int(curator_cfg.get("min_height", 0))
    blur_threshold = float(curator_cfg.get("blur_threshold", 0.0))

    input_records = 0
    records_written = 0
    skipped_license = 0
    skipped_duplicates = 0
    skipped_small_image = 0
    skipped_blurry = 0
    invalid_records = 0
    seen_sha: set[str] = set()
    seen_id: set[str] = set()

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

                    license_value = _normalize_license(payload.get("license_normalized"))
                    if allowed and license_value not in allowed:
                        skipped_license += 1
                        continue

                    image_path = _resolve_image_path(payload.get("image_path"))
                    if image_path is None or not image_path.exists():
                        invalid_records += 1
                        continue
                    quality = _image_quality(image_path)
                    if quality is None:
                        invalid_records += 1
                        continue
                    payload["image_width"] = quality["width"]
                    payload["image_height"] = quality["height"]
                    payload["blur_score"] = quality["blur_score"]
                    if quality["width"] < min_width or quality["height"] < min_height:
                        skipped_small_image += 1
                        continue
                    if quality["blur_score"] < blur_threshold:
                        skipped_blurry += 1
                        continue

                    item_id = str(payload.get("id", ""))
                    sha = str(payload.get("sha256", ""))
                    if sha:
                        if sha in seen_sha:
                            skipped_duplicates += 1
                            continue
                        seen_sha.add(sha)
                    elif item_id:
                        if item_id in seen_id:
                            skipped_duplicates += 1
                            continue
                        seen_id.add(item_id)

                    out_fh.write(json.dumps(payload, sort_keys=True))
                    out_fh.write("\n")
                    records_written += 1

    summary = {
        "stage": "curate",
        "started_at": utc_now_iso(),
        "completed_at": utc_now_iso(),
        "input_dir": str(input_dir) if input_dir else None,
        "output_dir": str(output_dir),
        "curator_config": config.get("curator", {}),
        "source_manifest": str(source_manifest) if source_manifest else None,
        "curated_manifest": str(output_manifest),
        "input_records": input_records,
        "records_written": records_written,
        "invalid_records": invalid_records,
        "skipped_license": skipped_license,
        "skipped_duplicates": skipped_duplicates,
        "skipped_small_image": skipped_small_image,
        "skipped_blurry": skipped_blurry,
    }
    write_json(output_dir / "curate_summary.json", summary)
    write_stage_success_marker(output_dir, summary)
    return summary


def _resolve_source_manifest(input_dir: Path | None) -> Path | None:
    if input_dir is None:
        return None
    path = input_dir / "ingested_manifest.jsonl"
    return path


def _normalize_license(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "UNKNOWN"
    if "by-sa" in text:
        return "CC-BY-SA"
    if text in {"cc-by-sa"}:
        return "CC-BY-SA"
    if "by/" in text or text in {"cc-by"}:
        return "CC-BY"
    return text.upper()


def _normalized_allowlist(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {_normalize_license(v) for v in values if _normalize_license(v)}


def _resolve_image_path(value: Any) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return Path(text)


def _image_quality(path: Path) -> dict[str, int | float] | None:
    try:
        with Image.open(path) as img:
            width, height = img.size
            grayscale = img.convert("L")
            # Edge variance is a lightweight blur proxy: low variance often means blurred images.
            edges = grayscale.filter(ImageFilter.FIND_EDGES)
            blur_score = float(ImageStat.Stat(edges).var[0])
    except Exception:
        return None
    return {"width": int(width), "height": int(height), "blur_score": blur_score}
