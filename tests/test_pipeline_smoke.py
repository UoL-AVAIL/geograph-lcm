from pathlib import Path

from geograph_lcm.config import load_lcm_catalog, load_pipeline_config
from geograph_lcm.pipeline import run_pipeline


def test_pipeline_scaffold_runs_download_to_match(tmp_path: Path) -> None:
    config = load_pipeline_config(Path("config/default.yaml"))
    config["pipeline"]["output_root"] = str(tmp_path / "outputs")
    config["dataset"]["root"] = str(tmp_path / "outputs" / "dataset")
    lcm_assets = load_lcm_catalog(Path("config/lcm_catalog.yaml"))

    manifest = run_pipeline(
        config=config,
        lcm_assets=lcm_assets,
        from_stage="ingest",
        to_stage="match_lcm",
        command="pytest-smoke",
    )

    assert manifest["from_stage"] == "ingest"
    assert manifest["to_stage"] == "match_lcm"
    assert (tmp_path / "outputs" / "pipeline_run.json").exists()
    assert (tmp_path / "outputs" / "match_lcm" / "_SUCCESS.json").exists()
