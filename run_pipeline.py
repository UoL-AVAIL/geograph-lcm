from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = load_pipeline_config(config_path)

    catalog_path = Path(config.get("lcm", {}).get("catalog_path", "config/lcm_catalog.yaml"))
    lcm_assets = load_lcm_catalog(catalog_path)

    run_pipeline(
        config=config,
        lcm_assets=lcm_assets,
        from_stage=args.from_stage,
        to_stage=args.to_stage,
        command=f"python run_pipeline.py --from-stage {args.from_stage} --to-stage {args.to_stage} --config {args.config}",
    )


if __name__ == "__main__":
    main()
