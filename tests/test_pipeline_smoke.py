from pathlib import Path
import json

from geograph_lcm.config import LCMAsset, load_pipeline_config
from geograph_lcm.pipeline import run_pipeline


def test_pipeline_scaffold_runs_download_to_match(tmp_path: Path) -> None:
    config = load_pipeline_config(Path("config/default.yaml"))
    config["pipeline"]["output_root"] = str(tmp_path / "outputs")
    config["dataset"]["root"] = str(tmp_path / "outputs" / "dataset")
    lcm_assets = [
        LCMAsset(
            year=2015,
            path=tmp_path / "fake_lcm.tif",
            crs="EPSG:27700",
            resolution_m=25.0,
            nodata=0,
            version="test",
            checksum_sha256="",
        )
    ]
    (tmp_path / "fake_lcm.tif").write_bytes(b"fake")

    manifest = run_pipeline(
        config=config,
        lcm_assets=lcm_assets,
        from_stage="ingest",
        to_stage="georeference",
        command="pytest-smoke",
    )

    assert manifest["from_stage"] == "ingest"
    assert manifest["to_stage"] == "georeference"
    assert "geograph_lcm_version" in manifest["environment"]
    assert (tmp_path / "outputs" / "pipeline_run.json").exists()
    assert (tmp_path / "outputs" / "georeference" / "_SUCCESS.json").exists()


def test_pipeline_force_reruns_completed_stage(tmp_path: Path) -> None:
    config = load_pipeline_config(Path("config/default.yaml"))
    config["pipeline"]["output_root"] = str(tmp_path / "outputs")
    config["dataset"]["root"] = str(tmp_path / "outputs" / "dataset")
    lcm_assets = [
        LCMAsset(
            year=2015,
            path=tmp_path / "fake_lcm.tif",
            crs="EPSG:27700",
            resolution_m=25.0,
            nodata=0,
            version="test",
            checksum_sha256="",
        )
    ]
    (tmp_path / "fake_lcm.tif").write_bytes(b"fake")

    first = run_pipeline(
        config=config,
        lcm_assets=lcm_assets,
        from_stage="ingest",
        to_stage="ingest",
        command="pytest-smoke-first",
    )
    second = run_pipeline(
        config=config,
        lcm_assets=lcm_assets,
        from_stage="ingest",
        to_stage="ingest",
        command="pytest-smoke-second",
    )
    forced = run_pipeline(
        config=config,
        lcm_assets=lcm_assets,
        from_stage="ingest",
        to_stage="ingest",
        command="pytest-smoke-force",
        force=True,
    )

    assert first["stages"][0]["status"] == "completed"
    assert second["stages"][0]["status"] == "skipped_completed"
    assert forced["stages"][0]["status"] == "completed"


def test_from_stage_uses_true_upstream_input_dir(tmp_path: Path) -> None:
    config = load_pipeline_config(Path("config/default.yaml"))
    config["pipeline"]["output_root"] = str(tmp_path / "outputs")
    config["dataset"]["root"] = str(tmp_path / "outputs" / "dataset")
    lcm_assets = [
        LCMAsset(
            year=2015,
            path=tmp_path / "fake_lcm.tif",
            crs="EPSG:27700",
            resolution_m=25.0,
            nodata=0,
            version="test",
            checksum_sha256="",
        )
    ]
    (tmp_path / "fake_lcm.tif").write_bytes(b"fake")

    ingest_dir = tmp_path / "outputs" / "ingest"
    ingest_dir.mkdir(parents=True, exist_ok=True)
    (ingest_dir / "ingested_manifest.jsonl").write_text("", encoding="utf-8")

    run_pipeline(
        config=config,
        lcm_assets=lcm_assets,
        from_stage="curate",
        to_stage="curate",
        command="pytest-smoke-curate-input",
        force=True,
    )

    summary = json.loads(
        (tmp_path / "outputs" / "curate" / "curate_summary.json").read_text(encoding="utf-8")
    )
    assert summary["input_dir"] == str(tmp_path / "outputs" / "ingest")
