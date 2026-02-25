from __future__ import annotations

import argparse
from pathlib import Path

from bokeh.io import curdoc

from geograph_lcm.map_viewer import build_bokeh_document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive geograph-lcm map explorer (Bokeh)")
    parser.add_argument(
        "--labels",
        default="outputs/dataset/labels.csv",
        help="Path to dataset labels.csv",
    )
    parser.add_argument(
        "--title",
        default="geograph-lcm map explorer",
        help="Page title",
    )
    return parser.parse_args()


args = parse_args()
build_bokeh_document(
    doc=curdoc(),
    labels_path=Path(args.labels),
    title=args.title,
)
