from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

from geograph_lcm.stage_utils import ensure_dir, utc_now_iso, write_json, write_stage_success_marker

LABEL_COLUMNS = [
    "id",
    "image_path",
    "lat",
    "lon",
    "lcm_l2",
    "lcm_l3",
    "timestamp",
    "license",
    "sha256",
    "georef_confidence",
    "lcm_window_agreement",
    "lcm_window_majority_value",
    "lcm_center_majority_match",
    "lcm_label_confidence",
    "lcm_low_confidence",
]


def run(config: dict[str, Any], input_dir: Path | None, output_dir: Path) -> dict[str, Any]:
    ensure_dir(output_dir)
    dataset_root = Path(config.get("dataset", {}).get("root", "outputs/dataset"))
    images_dir = dataset_root / "images"
    ensure_dir(images_dir)
    ensure_dir(dataset_root)
    source_manifest = _resolve_source_manifest(input_dir)
    labels_path = dataset_root / "labels.csv"
    dataset_readme_path = dataset_root / "README.md"

    input_records = 0
    rows_written = 0
    skipped_non_matched = 0
    skipped_missing_image = 0
    invalid_records = 0
    copied_images = 0
    lcm_years_used: set[int] = set()

    with labels_path.open("w", encoding="utf-8", newline="") as labels_fh:
        writer = csv.DictWriter(labels_fh, fieldnames=LABEL_COLUMNS)
        writer.writeheader()
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

                    if str(record.get("lcm_match_status", "")) != "matched":
                        skipped_non_matched += 1
                        continue

                    src_image = _resolve_path(record.get("image_path"))
                    if src_image is None or not src_image.exists():
                        skipped_missing_image += 1
                        continue
                    dst_image = images_dir / _dataset_image_name(record)
                    if not dst_image.exists():
                        shutil.copy2(src_image, dst_image)
                        copied_images += 1

                    selected_year = _to_int(record.get("selected_lcm_year"))
                    if selected_year is not None:
                        lcm_years_used.add(selected_year)

                    row = {
                        "id": str(record.get("id", "")),
                        "image_path": str(dst_image),
                        "lat": _to_string(record.get("lat")),
                        "lon": _to_string(record.get("lon")),
                        "lcm_l2": _to_string(record.get("lcm_l2")),
                        "lcm_l3": _to_string(record.get("lcm_l3")),
                        "timestamp": _to_string(record.get("timestamp")),
                        "license": _to_string(record.get("license_raw", record.get("license"))),
                        "sha256": _to_string(record.get("sha256")),
                        "georef_confidence": _to_string(record.get("georef_confidence")),
                        "lcm_window_agreement": _to_string(record.get("lcm_window_agreement")),
                        "lcm_window_majority_value": _to_string(
                            record.get("lcm_window_majority_value")
                        ),
                        "lcm_center_majority_match": _to_string(
                            record.get("lcm_center_majority_match")
                        ),
                        "lcm_label_confidence": _to_string(record.get("lcm_label_confidence")),
                        "lcm_low_confidence": _to_string(record.get("lcm_low_confidence")),
                    }
                    writer.writerow(row)
                    rows_written += 1

    _write_dataset_readme(
        dataset_readme_path=dataset_readme_path,
        labels_path=labels_path,
        images_dir=images_dir,
        rows_written=rows_written,
        lcm_years_used=sorted(lcm_years_used),
    )

    summary = {
        "stage": "write_dataset",
        "started_at": utc_now_iso(),
        "completed_at": utc_now_iso(),
        "input_dir": str(input_dir) if input_dir else None,
        "output_dir": str(output_dir),
        "dataset_root": str(dataset_root),
        "source_manifest": str(source_manifest) if source_manifest else None,
        "labels_path": str(labels_path),
        "dataset_readme_path": str(dataset_readme_path),
        "input_records": input_records,
        "rows_written": rows_written,
        "copied_images": copied_images,
        "invalid_records": invalid_records,
        "skipped_non_matched": skipped_non_matched,
        "skipped_missing_image": skipped_missing_image,
        "lcm_years_used": sorted(lcm_years_used),
    }
    write_json(output_dir / "write_dataset_summary.json", summary)
    write_stage_success_marker(output_dir, summary)
    return summary


def _resolve_source_manifest(input_dir: Path | None) -> Path | None:
    if input_dir is None:
        return None
    return input_dir / "matched_manifest.jsonl"


def _resolve_path(value: Any) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return Path(text)


def _dataset_image_name(record: dict[str, Any]) -> str:
    item_id = str(record.get("id", "")).strip() or "unknown"
    src = _resolve_path(record.get("image_path"))
    suffix = ".jpg"
    if src is not None and src.suffix:
        suffix = src.suffix.lower()
    return f"{item_id}{suffix}"


def _to_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _write_dataset_readme(
    dataset_readme_path: Path,
    labels_path: Path,
    images_dir: Path,
    rows_written: int,
    lcm_years_used: list[int],
) -> None:
    lines = [
        "# geograph-lcm dataset",
        "",
        f"- rows: {rows_written}",
        f"- labels file: {labels_path}",
        f"- images dir: {images_dir}",
        f"- lcm years used: {', '.join(str(y) for y in lcm_years_used) if lcm_years_used else 'none'}",
        "",
        "Columns in labels.csv:",
        ", ".join(LABEL_COLUMNS),
    ]
    dataset_readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
