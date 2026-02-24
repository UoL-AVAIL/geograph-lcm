from __future__ import annotations

import csv
import random
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from geograph_lcm.stage_utils import ensure_dir, utc_now_iso, write_json, write_stage_success_marker

REQUIRED_LABEL_COLUMNS = [
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
]


def run(config: dict[str, Any], input_dir: Path | None, output_dir: Path) -> dict[str, Any]:
    ensure_dir(output_dir)
    validator_cfg = config.get("validator", {})
    validation_root = Path(validator_cfg.get("output_root", "outputs/validation"))
    samples_dir = validation_root / "samples"
    ensure_dir(validation_root)
    ensure_dir(samples_dir)

    dataset_root = Path(config.get("dataset", {}).get("root", "outputs/dataset"))
    labels_path = dataset_root / "labels.csv"
    report_path = validation_root / "report.yaml"
    random_seed = int(validator_cfg.get("random_seed", 42))
    random_sample_size = int(validator_cfg.get("random_sample_size", 50))
    per_class_sample_size = int(validator_cfg.get("per_class_sample_size", 20))
    top_classes_for_sampling = int(validator_cfg.get("top_classes_for_sampling", 5))

    checks: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    warnings: list[str] = []
    errors: list[str] = []
    samples: dict[str, str] = {}

    rows: list[dict[str, str]] = []
    fieldnames: list[str] = []
    if not labels_path.exists():
        errors.append(f"labels.csv not found at {labels_path}")
        status = "fail"
    else:
        with labels_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        missing_cols = [col for col in REQUIRED_LABEL_COLUMNS if col not in fieldnames]
        checks["required_columns"] = {"ok": not missing_cols, "missing": missing_cols}
        if missing_cols:
            errors.append(f"Missing required columns: {missing_cols}")
        if not rows:
            warnings.append("labels.csv has zero rows")

        checks["duplicate_ids"] = _duplicate_check(rows, "id")
        checks["duplicate_sha256"] = _duplicate_check(rows, "sha256")
        if checks["duplicate_ids"]["count"] > 0:
            warnings.append(f"Found duplicate ids: {checks['duplicate_ids']['count']}")
        if checks["duplicate_sha256"]["count"] > 0:
            warnings.append(f"Found duplicate sha256: {checks['duplicate_sha256']['count']}")

        missing_values = _missing_value_counts(rows, REQUIRED_LABEL_COLUMNS)
        checks["missing_values"] = missing_values
        missing_total = sum(missing_values.values())
        if missing_total > 0:
            warnings.append(f"Found missing required values: {missing_total}")

        metrics = _distribution_metrics(rows)

        rng = random.Random(random_seed)
        random_ids = _sample_random_ids(rows, n=random_sample_size, rng=rng)
        random_path = samples_dir / "random_ids.txt"
        random_path.write_text("\n".join(random_ids) + ("\n" if random_ids else ""), encoding="utf-8")
        samples["random_ids"] = str(random_path)

        by_class = _sample_ids_by_class(
            rows,
            class_field="lcm_l3",
            top_n_classes=top_classes_for_sampling,
            per_class_n=per_class_sample_size,
            rng=rng,
        )
        by_class_path = samples_dir / "by_class_ids.yaml"
        with by_class_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(by_class, fh, sort_keys=True)
        samples["by_class_ids"] = str(by_class_path)

        if errors:
            status = "fail"
        elif warnings:
            status = "warn"
        else:
            status = "pass"

    report = {
        "status": status,
        "generated_at": utc_now_iso(),
        "labels_path": str(labels_path),
        "checks": checks,
        "metrics": metrics,
        "warnings": warnings,
        "errors": errors,
        "samples": samples,
    }
    with report_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(report, fh, sort_keys=False)

    summary = {
        "stage": "validate",
        "started_at": utc_now_iso(),
        "completed_at": utc_now_iso(),
        "input_dir": str(input_dir) if input_dir else None,
        "output_dir": str(output_dir),
        "validation_root": str(validation_root),
        "report_path": str(report_path),
        "status": status,
        "warning_count": len(warnings),
        "error_count": len(errors),
    }
    write_json(output_dir / "validate_summary.json", summary)
    write_stage_success_marker(output_dir, summary)
    return summary


def _duplicate_check(rows: list[dict[str, str]], key: str) -> dict[str, Any]:
    values = [row.get(key, "").strip() for row in rows if row.get(key, "").strip()]
    counts = Counter(values)
    duplicates = sorted([value for value, count in counts.items() if count > 1])
    return {"count": len(duplicates), "examples": duplicates[:10]}


def _missing_value_counts(rows: list[dict[str, str]], columns: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for col in columns:
        out[col] = sum(1 for row in rows if not str(row.get(col, "")).strip())
    return out


def _distribution_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    class_counts = Counter(row.get("lcm_l3", "").strip() for row in rows if row.get("lcm_l3", "").strip())
    conf_counts = Counter(
        row.get("georef_confidence", "").strip()
        for row in rows
        if row.get("georef_confidence", "").strip()
    )
    year_counts = Counter(
        _parse_year(row.get("timestamp", "").strip()) for row in rows if row.get("timestamp", "").strip()
    )
    year_counts.pop(None, None)
    return {
        "rows": len(rows),
        "unique_classes_l3": len(class_counts),
        "top_classes_l3": class_counts.most_common(10),
        "georef_confidence_counts": dict(conf_counts),
        "capture_year_counts": dict(sorted((k, v) for k, v in year_counts.items() if k is not None)),
    }


def _sample_random_ids(rows: list[dict[str, str]], n: int, rng: random.Random) -> list[str]:
    ids = [row.get("id", "").strip() for row in rows if row.get("id", "").strip()]
    if not ids:
        return []
    unique_ids = sorted(set(ids))
    sample_n = min(n, len(unique_ids))
    return sorted(rng.sample(unique_ids, sample_n))


def _sample_ids_by_class(
    rows: list[dict[str, str]],
    class_field: str,
    top_n_classes: int,
    per_class_n: int,
    rng: random.Random,
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        cls = row.get(class_field, "").strip()
        item_id = row.get("id", "").strip()
        if not cls or not item_id:
            continue
        grouped.setdefault(cls, []).append(item_id)
    top_classes = sorted(grouped.keys(), key=lambda c: len(grouped[c]), reverse=True)[:top_n_classes]
    out: dict[str, list[str]] = {}
    for cls in top_classes:
        unique_ids = sorted(set(grouped[cls]))
        sample_n = min(per_class_n, len(unique_ids))
        out[cls] = sorted(rng.sample(unique_ids, sample_n))
    return out


def _parse_year(value: str) -> int | None:
    text = value.strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None
