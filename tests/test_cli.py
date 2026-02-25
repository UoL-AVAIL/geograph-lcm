from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from geograph_lcm import cli


def test_parse_args_accepts_output_dir(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "geograph-lcm",
            "--from-stage",
            "download",
            "--to-stage",
            "download",
            "--output-dir",
            "out",
        ],
    )
    args = cli.parse_args()
    assert isinstance(args, argparse.Namespace)
    assert args.output_dir == "out"


def test_parse_args_version_flag_exits(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr("sys.argv", ["geograph-lcm", "--version"])
    try:
        cli.parse_args()
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert out.startswith("geograph-lcm ")


def test_output_dir_override_updates_default_dataset_and_validator() -> None:
    config: dict[str, Any] = {
        "pipeline": {"output_root": "outputs"},
        "dataset": {"root": "outputs/dataset"},
        "validator": {"output_root": "outputs/validation"},
    }
    cli._apply_output_dir_override(config, Path("/tmp/custom-out"))
    assert config["pipeline"]["output_root"] == "/tmp/custom-out"
    assert config["dataset"]["root"] == "/tmp/custom-out/dataset"
    assert config["validator"]["output_root"] == "/tmp/custom-out/validation"


def test_output_dir_override_preserves_explicit_dataset_and_validator_paths() -> None:
    config: dict[str, Any] = {
        "pipeline": {"output_root": "outputs"},
        "dataset": {"root": "/tmp/my-dataset"},
        "validator": {"output_root": "/tmp/my-validation"},
    }
    cli._apply_output_dir_override(config, Path("/tmp/custom-out"))
    assert config["pipeline"]["output_root"] == "/tmp/custom-out"
    assert config["dataset"]["root"] == "/tmp/my-dataset"
    assert config["validator"]["output_root"] == "/tmp/my-validation"


def test_main_passes_output_dir_in_command(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    catalog_path = tmp_path / "catalog.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "pipeline": {"output_root": "outputs"},
                "dataset": {"root": "outputs/dataset"},
                "validator": {"output_root": "outputs/validation"},
                "lcm": {"catalog_path": str(catalog_path)},
            }
        ),
        encoding="utf-8",
    )
    catalog_path.write_text(yaml.safe_dump({"lcm_assets": []}), encoding="utf-8")

    captured: dict[str, Any] = {}

    def _fake_run_pipeline(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(cli, "run_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(
        "sys.argv",
        [
            "geograph-lcm",
            "--from-stage",
            "download",
            "--to-stage",
            "download",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "custom-out"),
        ],
    )

    cli.main()

    assert captured["config"]["pipeline"]["output_root"] == str(tmp_path / "custom-out")
    assert captured["config"]["dataset"]["root"] == str(tmp_path / "custom-out" / "dataset")
    assert captured["config"]["validator"]["output_root"] == str(
        tmp_path / "custom-out" / "validation"
    )
    assert "--output-dir" in captured["command"]
    assert str(tmp_path / "custom-out") in captured["command"]


def test_main_handles_missing_api_key_error(monkeypatch: Any, tmp_path: Path, capsys: Any) -> None:
    config_path = tmp_path / "config.yaml"
    catalog_path = tmp_path / "catalog.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "pipeline": {"output_root": "outputs"},
                "lcm": {"catalog_path": str(catalog_path)},
            }
        ),
        encoding="utf-8",
    )
    catalog_path.write_text(yaml.safe_dump({"lcm_assets": []}), encoding="utf-8")

    def _fake_run_pipeline(**kwargs: Any) -> dict[str, Any]:
        del kwargs
        raise ValueError("Missing Geograph API key: provide --geograph-api-key or env var 'X'")

    monkeypatch.setattr(cli, "run_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(
        "sys.argv",
        [
            "geograph-lcm",
            "--from-stage",
            "download",
            "--to-stage",
            "download",
            "--config",
            str(config_path),
        ],
    )

    try:
        cli.main()
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 2

    err = capsys.readouterr().err
    assert "Missing Geograph API key:" in err


def test_main_reraises_other_value_errors(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    catalog_path = tmp_path / "catalog.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "pipeline": {"output_root": "outputs"},
                "lcm": {"catalog_path": str(catalog_path)},
            }
        ),
        encoding="utf-8",
    )
    catalog_path.write_text(yaml.safe_dump({"lcm_assets": []}), encoding="utf-8")

    def _fake_run_pipeline(**kwargs: Any) -> dict[str, Any]:
        del kwargs
        raise ValueError("some other value error")

    monkeypatch.setattr(cli, "run_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(
        "sys.argv",
        [
            "geograph-lcm",
            "--from-stage",
            "download",
            "--to-stage",
            "download",
            "--config",
            str(config_path),
        ],
    )

    try:
        cli.main()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "some other value error"
