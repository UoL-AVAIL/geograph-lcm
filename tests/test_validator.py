from __future__ import annotations

import csv
from pathlib import Path

import yaml

from geograph_lcm import validator


def _write_labels(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_validator_pass_and_samples(tmp_path: Path) -> None:
    labels_path = tmp_path / "dataset" / "labels.csv"
    fieldnames = [
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
    rows = [
        {
            "id": "1",
            "image_path": "outputs/dataset/images/1.jpg",
            "lat": "52.0",
            "lon": "-1.0",
            "lcm_l2": "Semi-natural Grassland",
            "lcm_l3": "Neutral Grassland",
            "timestamp": "2020-01-01",
            "license": "cc",
            "sha256": "sha1",
            "georef_confidence": "high",
        },
        {
            "id": "2",
            "image_path": "outputs/dataset/images/2.jpg",
            "lat": "53.0",
            "lon": "-2.0",
            "lcm_l2": "Mountain, Heath and Bog",
            "lcm_l3": "Heather Grassland",
            "timestamp": "2021-01-01",
            "license": "cc",
            "sha256": "sha2",
            "georef_confidence": "high",
        },
    ]
    _write_labels(labels_path, rows, fieldnames)

    summary = validator.run(
        config={
            "dataset": {"root": str(tmp_path / "dataset")},
            "validator": {"output_root": str(tmp_path / "validation")},
        },
        input_dir=None,
        output_dir=tmp_path / "validate",
    )

    assert summary["status"] == "pass"
    report_path = tmp_path / "validation" / "report.yaml"
    assert report_path.exists()
    report = yaml.safe_load(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    assert (tmp_path / "validation" / "samples" / "random_ids.txt").exists()
    assert (tmp_path / "validation" / "samples" / "by_class_ids.yaml").exists()


def test_validator_fails_when_required_columns_missing(tmp_path: Path) -> None:
    labels_path = tmp_path / "dataset" / "labels.csv"
    # Missing georef_confidence, sha256 and license columns.
    fieldnames = ["id", "image_path", "lat", "lon", "lcm_l2", "lcm_l3", "timestamp"]
    rows = [
        {
            "id": "1",
            "image_path": "outputs/dataset/images/1.jpg",
            "lat": "52.0",
            "lon": "-1.0",
            "lcm_l2": "Semi-natural Grassland",
            "lcm_l3": "Neutral Grassland",
            "timestamp": "2020-01-01",
        }
    ]
    _write_labels(labels_path, rows, fieldnames)

    summary = validator.run(
        config={
            "dataset": {"root": str(tmp_path / "dataset")},
            "validator": {"output_root": str(tmp_path / "validation")},
        },
        input_dir=None,
        output_dir=tmp_path / "validate",
    )
    assert summary["status"] == "fail"
    report = yaml.safe_load((tmp_path / "validation" / "report.yaml").read_text(encoding="utf-8"))
    assert report["status"] == "fail"
    assert report["checks"]["required_columns"]["ok"] is False


def test_validator_fails_license_policy_when_disallowed_present(tmp_path: Path) -> None:
    labels_path = tmp_path / "dataset" / "labels.csv"
    fieldnames = [
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
    rows = [
        {
            "id": "1",
            "image_path": "outputs/dataset/images/1.jpg",
            "lat": "52.0",
            "lon": "-1.0",
            "lcm_l2": "Semi-natural Grassland",
            "lcm_l3": "Neutral Grassland",
            "timestamp": "2020-01-01",
            "license": "https://creativecommons.org/licenses/by-sa/2.0/",
            "sha256": "sha1",
            "georef_confidence": "high",
        },
        {
            "id": "2",
            "image_path": "outputs/dataset/images/2.jpg",
            "lat": "53.0",
            "lon": "-2.0",
            "lcm_l2": "Mountain, Heath and Bog",
            "lcm_l3": "Heather Grassland",
            "timestamp": "2021-01-01",
            "license": "https://creativecommons.org/licenses/by/4.0/",
            "sha256": "sha2",
            "georef_confidence": "high",
        },
    ]
    _write_labels(labels_path, rows, fieldnames)

    summary = validator.run(
        config={
            "dataset": {"root": str(tmp_path / "dataset")},
            "validator": {
                "output_root": str(tmp_path / "validation"),
                "policy": {
                    "licensing": {
                        "enforce_allowed_licenses": True,
                        "allowed_licenses": ["https://creativecommons.org/licenses/by-sa/2.0/"],
                    }
                },
            },
        },
        input_dir=None,
        output_dir=tmp_path / "validate",
    )

    assert summary["status"] == "fail"
    report = yaml.safe_load((tmp_path / "validation" / "report.yaml").read_text(encoding="utf-8"))
    assert report["checks"]["policy"]["licensing"]["enabled"] is True
    assert report["checks"]["policy"]["licensing"]["violating_count"] == 1


def test_validator_fails_ethics_policy_when_required_field_missing(tmp_path: Path) -> None:
    labels_path = tmp_path / "dataset" / "labels.csv"
    fieldnames = [
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
    rows = [
        {
            "id": "1",
            "image_path": "outputs/dataset/images/1.jpg",
            "lat": "52.0",
            "lon": "-1.0",
            "lcm_l2": "Semi-natural Grassland",
            "lcm_l3": "Neutral Grassland",
            "timestamp": "2020-01-01",
            "license": "https://creativecommons.org/licenses/by-sa/2.0/",
            "sha256": "sha1",
            "georef_confidence": "high",
        }
    ]
    _write_labels(labels_path, rows, fieldnames)

    summary = validator.run(
        config={
            "dataset": {"root": str(tmp_path / "dataset")},
            "validator": {
                "output_root": str(tmp_path / "validation"),
                "policy": {
                    "ethics": {
                        "require_review_field": True,
                        "review_field_name": "ethics_review_status",
                        "allowed_values": ["approved", "not_applicable"],
                    }
                },
            },
        },
        input_dir=None,
        output_dir=tmp_path / "validate",
    )

    assert summary["status"] == "fail"
    report = yaml.safe_load((tmp_path / "validation" / "report.yaml").read_text(encoding="utf-8"))
    assert report["checks"]["policy"]["ethics"]["enabled"] is True
    assert report["checks"]["policy"]["ethics"]["missing_required_field"] is True
