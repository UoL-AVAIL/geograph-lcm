from __future__ import annotations

import csv
import json
from pathlib import Path

from geograph_lcm import dataset_writer


def test_dataset_writer_exports_labels_and_images(tmp_path: Path) -> None:
    source_dir = tmp_path / "match_lcm"
    source_dir.mkdir(parents=True, exist_ok=True)
    src_image = tmp_path / "raw" / "1.jpg"
    src_image.parent.mkdir(parents=True, exist_ok=True)
    src_image.write_bytes(b"img-bytes")

    (source_dir / "matched_manifest.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "1",
                        "image_path": str(src_image),
                        "lat": 52.0,
                        "lon": -1.0,
                        "lcm_l2": "Semi-natural Grassland",
                        "lcm_l3": "Neutral Grassland",
                        "timestamp": "2020-01-01",
                        "license_raw": "http://creativecommons.org/licenses/by-sa/2.0/",
                        "sha256": "abc123",
                        "georef_confidence": "high",
                        "lcm_window_agreement": 0.78,
                        "lcm_window_majority_value": 6,
                        "lcm_center_majority_match": True,
                        "lcm_label_confidence": 0.81,
                        "lcm_low_confidence": False,
                        "lcm_match_status": "matched",
                        "selected_lcm_year": 2015,
                    }
                ),
                json.dumps(
                    {
                        "id": "2",
                        "image_path": str(tmp_path / "missing.jpg"),
                        "lcm_match_status": "matched",
                    }
                ),
                json.dumps({"id": "3", "image_path": str(src_image), "lcm_match_status": "nodata"}),
            ]
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "write_dataset"
    dataset_root = tmp_path / "dataset"
    summary = dataset_writer.run(
        config={"dataset": {"root": str(dataset_root)}},
        input_dir=source_dir,
        output_dir=out_dir,
    )

    assert summary["input_records"] == 3
    assert summary["rows_written"] == 1
    assert summary["copied_images"] == 1
    assert summary["skipped_non_matched"] == 1
    assert summary["skipped_missing_image"] == 1
    assert summary["lcm_years_used"] == [2015]

    labels_path = dataset_root / "labels.csv"
    assert labels_path.exists()
    with labels_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["id"] == "1"
    assert rows[0]["lcm_l3"] == "Neutral Grassland"
    assert rows[0]["lcm_window_agreement"] == "0.78"
    assert rows[0]["lcm_label_confidence"] == "0.81"
    assert rows[0]["lcm_low_confidence"] == "False"
    assert Path(rows[0]["image_path"]).exists()

    readme_path = dataset_root / "README.md"
    assert readme_path.exists()
    text = readme_path.read_text(encoding="utf-8")
    assert "rows: 1" in text
    assert "lcm years used: 2015" in text
