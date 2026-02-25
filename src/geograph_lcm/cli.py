from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys

from geograph_lcm.config import load_lcm_catalog, load_pipeline_config
from geograph_lcm.pipeline import STAGES, run_pipeline


def parse_args() -> argparse.Namespace:
    stage_names = [stage.name for stage in STAGES]
    parser = argparse.ArgumentParser(description="Run geograph-lcm pipeline")
    parser.add_argument(
        "--version",
        action="version",
        version=f"geograph-lcm {_runtime_package_version() or 'unknown'}",
    )
    parser.add_argument(
        "--from-stage",
        choices=stage_names,
        default=stage_names[0],
        help="First stage to execute",
    )
    parser.add_argument(
        "--to-stage",
        choices=stage_names,
        default=stage_names[-1],
        help="Last stage to execute",
    )
    parser.add_argument(
        "--config",
        default="config/default.yaml",
        help="Path to pipeline config YAML",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Pipeline output root directory (overrides pipeline.output_root).",
    )
    parser.add_argument(
        "--geograph-api-key",
        default=None,
        help="Geograph API key (overrides environment variable lookup).",
    )
    parser.add_argument(
        "--geograph-search-id",
        default=None,
        help="Geograph saved search ID injected as downloader.query.i.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run selected stages even if _SUCCESS.json exists.",
    )
    return parser.parse_args()


def _apply_output_dir_override(config: dict[str, object], output_dir: Path) -> None:
    pipeline_cfg = config.setdefault("pipeline", {})
    if not isinstance(pipeline_cfg, dict):
        raise ValueError("pipeline config must be a mapping")
    pipeline_cfg["output_root"] = str(output_dir)

    dataset_cfg = config.setdefault("dataset", {})
    if not isinstance(dataset_cfg, dict):
        raise ValueError("dataset config must be a mapping")
    dataset_root = str(dataset_cfg.get("root", "outputs/dataset"))
    if dataset_root in {"outputs/dataset", "outputs\\dataset"}:
        dataset_cfg["root"] = str(output_dir / "dataset")

    validator_cfg = config.setdefault("validator", {})
    if not isinstance(validator_cfg, dict):
        raise ValueError("validator config must be a mapping")
    validator_root = str(validator_cfg.get("output_root", "outputs/validation"))
    if validator_root in {"outputs/validation", "outputs\\validation"}:
        validator_cfg["output_root"] = str(output_dir / "validation")


def main() -> None:
    args = parse_args()
    print(
        r"""
                                                .__              .__
   ____   ____  ____   ________________  ______ |  |__           |  |   ____   _____
  / ___\_/ __ \/  _ \ / ___\_  __ \__  \ \____ \|  |  \   ______ |  | _/ ___\ /     \
 / /_/  >  ___(  <_> ) /_/  >  | \// __ \|  |_> >   Y  \ /_____/ |  |_\  \___|  Y Y  \
 \___  / \___  >____/\___  /|__|  (____  /   __/|___|  /         |____/\___  >__|_|  /
/_____/      \/     /_____/            \/|__|        \/                    \/      \/
""".strip(
            "\n"
        )
    )
    print(f"[pipeline] from={args.from_stage} to={args.to_stage} config={args.config}")
    config_path = Path(args.config)
    config = load_pipeline_config(config_path)
    if args.output_dir:
        _apply_output_dir_override(config=config, output_dir=Path(args.output_dir))
    if args.geograph_api_key:
        geograph_cfg = config.setdefault("geograph", {})
        geograph_cfg["api_key"] = args.geograph_api_key
    if args.geograph_search_id:
        downloader_cfg = config.setdefault("downloader", {})
        query = downloader_cfg.setdefault("query", {})
        query["i"] = args.geograph_search_id

    catalog_path = Path(config.get("lcm", {}).get("catalog_path", "config/lcm_catalog.yaml"))
    lcm_assets = load_lcm_catalog(catalog_path)

    command = (
        f"geograph-lcm --from-stage {args.from_stage} "
        f"--to-stage {args.to_stage} --config {args.config}"
    )
    if args.output_dir:
        command = f"{command} --output-dir {args.output_dir}"
    if args.force:
        command = f"{command} --force"
    if args.geograph_api_key:
        command = f"{command} --geograph-api-key ***redacted***"
    if args.geograph_search_id:
        command = f"{command} --geograph-search-id {args.geograph_search_id}"

    if args.geograph_api_key:
        print("[pipeline] Geograph API key supplied via CLI")
    if args.geograph_search_id:
        print(f"[pipeline] Geograph search ID supplied: {args.geograph_search_id}")
    if args.output_dir:
        print(f"[pipeline] Output directory override: {args.output_dir}")

    try:
        run_pipeline(
            config=config,
            lcm_assets=lcm_assets,
            from_stage=args.from_stage,
            to_stage=args.to_stage,
            command=command,
            force=args.force,
        )
    except ValueError as exc:
        if _is_missing_geograph_api_key_error(exc):
            print(f"[pipeline] error: {exc}", file=sys.stderr)
            raise SystemExit(2) from None
        raise
    print("[pipeline] run complete")


def _is_missing_geograph_api_key_error(exc: ValueError) -> bool:
    return str(exc).startswith("Missing Geograph API key:")


def _runtime_package_version() -> str | None:
    for package_name in ("geograph-lcm", "geograph_lcm"):
        try:
            return version(package_name)
        except PackageNotFoundError:
            continue
        except Exception:
            return None
    return None
