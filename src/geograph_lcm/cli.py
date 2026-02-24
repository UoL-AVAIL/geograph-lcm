from __future__ import annotations

import argparse
from pathlib import Path

from geograph_lcm.config import load_lcm_catalog, load_pipeline_config
from geograph_lcm.pipeline import STAGES, run_pipeline


def parse_args() -> argparse.Namespace:
    stage_names = [stage.name for stage in STAGES]
    parser = argparse.ArgumentParser(description="Run geograph-lcm pipeline")
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


def main() -> None:
    args = parse_args()
    print(r"""
                                                .__              .__
   ____   ____  ____   ________________  ______ |  |__           |  |   ____   _____
  / ___\_/ __ \/  _ \ / ___\_  __ \__  \ \____ \|  |  \   ______ |  | _/ ___\ /     \
 / /_/  >  ___(  <_> ) /_/  >  | \// __ \|  |_> >   Y  \ /_____/ |  |_\  \___|  Y Y  \
 \___  / \___  >____/\___  /|__|  (____  /   __/|___|  /         |____/\___  >__|_|  /
/_____/      \/     /_____/            \/|__|        \/                    \/      \/
""".strip("\n"))
    print(f"[pipeline] from={args.from_stage} to={args.to_stage} config={args.config}")
    config_path = Path(args.config)
    config = load_pipeline_config(config_path)
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

    run_pipeline(
        config=config,
        lcm_assets=lcm_assets,
        from_stage=args.from_stage,
        to_stage=args.to_stage,
        command=command,
        force=args.force,
    )
    print("[pipeline] run complete")
