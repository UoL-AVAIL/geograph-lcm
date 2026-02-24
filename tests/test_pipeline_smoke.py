from pathlib import Path

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
    assert (tmp_path / "outputs" / "pipeline_run.json").exists()
    assert (tmp_path / "outputs" / "georeference" / "_SUCCESS.json").exists()
