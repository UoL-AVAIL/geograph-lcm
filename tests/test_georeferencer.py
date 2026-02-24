from __future__ import annotations

import json
from pathlib import Path

from geograph_lcm import georeferencer


def test_georeferencer_assigns_confidence_levels(tmp_path: Path) -> None:
    curate_dir = tmp_path / "curate"
    curate_dir.mkdir(parents=True, exist_ok=True)
    source = curate_dir / "curated_manifest.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "high-1",
                        "lat": 51.501234,
                        "lon": -0.141234,
                        "raw_item": {"lat": "51.501234", "long": "-0.141234"},
                    }
                ),
                json.dumps(
                    {
                        "id": "medium-1",
                        "lat": 51.501,
                        "lon": -0.141,
                        "raw_item": {"lat": "51.501", "long": "-0.141"},
                    }
                ),
                json.dumps(
                    {
                        "id": "none-1",
                        "lat": None,
                        "lon": -0.141,
                        "raw_item": {"lat": None, "long": "-0.141"},
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "georeference"
    summary = georeferencer.run(
        config={"georeferencer": {"max_georef_radius_m": 50}},
        input_dir=curate_dir,
        output_dir=out_dir,
    )

    assert summary["records_written"] == 3
    assert summary["confidence_counts"]["high"] == 1
    assert summary["confidence_counts"]["medium"] == 1
    assert summary["confidence_counts"]["none"] == 1

    rows = (
        (out_dir / "georeferenced_manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
    )
    parsed = [json.loads(row) for row in rows]
    by_id = {row["id"]: row for row in parsed}
    assert by_id["high-1"]["georef_confidence"] == "high"
    assert by_id["high-1"]["georef_method"] == "coordinate_precision_estimate"
    assert by_id["medium-1"]["georef_confidence"] == "medium"
    assert by_id["none-1"]["georef_confidence"] == "none"


def test_georeferencer_handles_missing_source_manifest(tmp_path: Path) -> None:
    out_dir = tmp_path / "georeference"
    summary = georeferencer.run(
        config={"georeferencer": {"max_georef_radius_m": 50}},
        input_dir=tmp_path / "curate",
        output_dir=out_dir,
    )

    assert summary["input_records"] == 0
    assert summary["records_written"] == 0
    assert (out_dir / "georeferenced_manifest.jsonl").exists()
