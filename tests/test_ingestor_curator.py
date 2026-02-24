from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageFilter

from geograph_lcm import curator, ingestor


def test_ingestor_normalizes_download_manifest(tmp_path: Path) -> None:
    download_dir = tmp_path / "download"
    raw_dir = download_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    source = raw_dir / "metadata.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "a1",
                        "image_path": str(tmp_path / "img" / "a1.jpg"),
                        "image_url": "https://example/a1.jpg",
                        "sha256": "sha-a1",
                        "timestamp": "2020-04-05",
                        "lat": "57.46",
                        "lon": "-2.48",
                        "license": "http://creativecommons.org/licenses/by-sa/2.0/",
                        "fetched_at": "2026-01-01T00:00:00Z",
                        "provenance": {"source": "geograph_api"},
                    }
                ),
                "{bad-json",
            ]
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "ingest"
    summary = ingestor.run(config={}, input_dir=download_dir, output_dir=out_dir)
    assert summary["input_records"] == 2
    assert summary["records_written"] == 1
    assert summary["invalid_records"] == 1

    rows = (out_dir / "ingested_manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    record = json.loads(rows[0])
    assert record["capture_year"] == 2020
    assert record["license_normalized"] == "CC-BY-SA"
    assert record["lat"] == 57.46
    assert record["lon"] == -2.48


def test_curator_filters_license_and_dedupes(tmp_path: Path) -> None:
    image_path = tmp_path / "img.jpg"
    _write_checkerboard(image_path, 900, 700)
    ingest_dir = tmp_path / "ingest"
    ingest_dir.mkdir(parents=True, exist_ok=True)
    source = ingest_dir / "ingested_manifest.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "a1",
                        "sha256": "dup-sha",
                        "license_normalized": "CC-BY-SA",
                        "image_path": str(image_path),
                    }
                ),
                json.dumps(
                    {
                        "id": "a2",
                        "sha256": "dup-sha",
                        "license_normalized": "CC-BY-SA",
                        "image_path": str(image_path),
                    }
                ),
                json.dumps(
                    {
                        "id": "b1",
                        "sha256": "other-sha",
                        "license_normalized": "CC-BY",
                        "image_path": str(image_path),
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "curate"
    summary = curator.run(
        config={"curator": {"allowed_licenses": ["CC-BY-SA"]}},
        input_dir=ingest_dir,
        output_dir=out_dir,
    )
    assert summary["input_records"] == 3
    assert summary["records_written"] == 1
    assert summary["skipped_duplicates"] == 1
    assert summary["skipped_license"] == 1

    rows = (out_dir / "curated_manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    record = json.loads(rows[0])
    assert record["id"] == "a1"


def test_curator_filters_small_and_blurry_images(tmp_path: Path) -> None:
    sharp_ok = tmp_path / "sharp.jpg"
    blurry = tmp_path / "blurry.jpg"
    tiny = tmp_path / "tiny.jpg"
    _write_checkerboard(sharp_ok, 900, 700)
    _write_checkerboard(blurry, 900, 700, blur=True)
    _write_checkerboard(tiny, 400, 300)
    sharp_score = float(curator._image_quality(sharp_ok)["blur_score"])  # type: ignore[index]
    blurry_score = float(curator._image_quality(blurry)["blur_score"])  # type: ignore[index]
    threshold = (sharp_score + blurry_score) / 2.0

    ingest_dir = tmp_path / "ingest"
    ingest_dir.mkdir(parents=True, exist_ok=True)
    source = ingest_dir / "ingested_manifest.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "ok",
                        "sha256": "ok-sha",
                        "license_normalized": "CC-BY-SA",
                        "image_path": str(sharp_ok),
                    }
                ),
                json.dumps(
                    {
                        "id": "blur",
                        "sha256": "blur-sha",
                        "license_normalized": "CC-BY-SA",
                        "image_path": str(blurry),
                    }
                ),
                json.dumps(
                    {
                        "id": "small",
                        "sha256": "small-sha",
                        "license_normalized": "CC-BY-SA",
                        "image_path": str(tiny),
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "curate"
    summary = curator.run(
        config={
            "curator": {
                "allowed_licenses": ["CC-BY-SA"],
                "min_width": 800,
                "min_height": 600,
                "blur_threshold": threshold,
            }
        },
        input_dir=ingest_dir,
        output_dir=out_dir,
    )

    assert summary["records_written"] == 1
    assert summary["skipped_blurry"] == 1
    assert summary["skipped_small_image"] == 1
    rows = (out_dir / "curated_manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    record = json.loads(rows[0])
    assert record["id"] == "ok"
    assert record["image_width"] == 900
    assert record["image_height"] == 700
    assert isinstance(record["blur_score"], float)


def _write_checkerboard(path: Path, width: int, height: int, blur: bool = False) -> None:
    img = Image.new("L", (width, height), color=0)
    pixels = img.load()
    block = 16
    for y in range(height):
        for x in range(width):
            pixels[x, y] = 255 if ((x // block + y // block) % 2 == 0) else 0
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=4.0))
    img.convert("RGB").save(path, format="JPEG", quality=95)
