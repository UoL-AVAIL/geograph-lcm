from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from geograph_lcm.config import LCMAsset
from geograph_lcm import lcm_matcher


def test_lcm_matcher_preflight_verifies_checksum(tmp_path: Path) -> None:
    raster = tmp_path / "lcm2015gb25m.tif"
    raster.write_bytes(b"fake-raster-bytes")
    checksum = hashlib.sha256(b"fake-raster-bytes").hexdigest()
    asset = LCMAsset(
        year=2015,
        path=raster,
        crs="EPSG:27700",
        resolution_m=25.0,
        nodata=0,
        version="test",
        checksum_sha256=checksum,
    )

    summary = lcm_matcher.run(
        config={"lcm": {"taxonomy_path": "config/lcm2015_taxonomy.yaml"}},
        input_dir=None,
        output_dir=tmp_path / "match",
        lcm_assets=[asset],
    )
    assert summary["checksum_preflight_by_year"]["2015"]["status"] == "verified"
    assert summary["checksum_preflight_by_year"]["2015"]["actual_sha256"] == checksum


def test_lcm_matcher_preflight_raises_on_checksum_mismatch(tmp_path: Path) -> None:
    raster = tmp_path / "lcm2015gb25m.tif"
    raster.write_bytes(b"fake-raster-bytes")
    asset = LCMAsset(
        year=2015,
        path=raster,
        crs="EPSG:27700",
        resolution_m=25.0,
        nodata=0,
        version="test",
        checksum_sha256="deadbeef",
    )

    with pytest.raises(ValueError, match="LCM checksum mismatch"):
        lcm_matcher.run(
            config={"lcm": {"taxonomy_path": "config/lcm2015_taxonomy.yaml"}},
            input_dir=None,
            output_dir=tmp_path / "match",
            lcm_assets=[asset],
        )


def test_lcm_matcher_writes_matched_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raster = tmp_path / "lcm2015gb25m.tif"
    raster.write_bytes(b"fake-raster-bytes")
    checksum = hashlib.sha256(b"fake-raster-bytes").hexdigest()
    asset = LCMAsset(
        year=2015,
        path=raster,
        crs="EPSG:27700",
        resolution_m=25.0,
        nodata=0,
        version="test",
        checksum_sha256=checksum,
    )
    georef_dir = tmp_path / "georeference"
    georef_dir.mkdir(parents=True, exist_ok=True)
    (georef_dir / "georeferenced_manifest.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"id": "1", "lat": 52.0, "lon": -1.0, "capture_year": 2015}),
                json.dumps({"id": "2", "lat": None, "lon": -1.0, "capture_year": 2015}),
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        lcm_matcher,
        "_sample_asset_value",
        lambda asset, lat, lon: {"status": "matched", "value": 7},
    )

    summary = lcm_matcher.run(
        config={"lcm": {"taxonomy_path": "config/lcm2015_taxonomy.yaml"}},
        input_dir=georef_dir,
        output_dir=tmp_path / "match",
        lcm_assets=[asset],
    )
    assert summary["records_written"] == 2
    assert summary["match_status_counts"]["matched"] == 1
    assert summary["match_status_counts"]["missing_coordinates"] == 1
    rows = (tmp_path / "match" / "matched_manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
    parsed = [json.loads(row) for row in rows]
    assert parsed[0]["selected_lcm_year"] == 2015
    assert parsed[0]["lcm_value"] == 7
    assert parsed[0]["lcm_match_status"] == "matched"
    assert parsed[0]["lcm_l3"] == "Acid Grassland"
    assert parsed[0]["lcm_l2"] == "Semi-natural Grassland"
    assert parsed[0]["lcm_l3_code"] == 7
    assert parsed[0]["lcm_l2_code"] == 5


def test_taxonomy_loader_reads_int_keys() -> None:
    taxonomy = lcm_matcher._load_lcm2015_taxonomy(Path("config/lcm2015_taxonomy.yaml"))
    assert taxonomy["l3_labels"][7] == "Acid Grassland"
    assert taxonomy["l2_labels"][5] == "Semi-natural Grassland"
    assert taxonomy["l3_to_l2"][7] == 5
