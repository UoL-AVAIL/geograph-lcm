from __future__ import annotations

import csv
from pathlib import Path

from geograph_lcm.map_viewer import _build_class_color_map, latlon_to_web_mercator, load_map_rows


def test_latlon_to_web_mercator_origin() -> None:
    x, y = latlon_to_web_mercator(lon=0.0, lat=0.0)
    assert abs(x) < 1e-6
    assert abs(y) < 1e-6


def test_load_map_rows_skips_invalid_coordinates(tmp_path: Path) -> None:
    labels_path = tmp_path / "labels.csv"
    with labels_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "id",
                "image_path",
                "lat",
                "lon",
                "lcm_l2",
                "lcm_l3",
                "timestamp",
                "license",
                "sha256",
                "georef_confidence",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "ok-1",
                "image_path": "outputs/dataset/images/ok-1.jpg",
                "lat": "52.0",
                "lon": "-1.0",
                "lcm_l2": "Semi-natural Grassland",
                "lcm_l3": "Neutral Grassland",
                "timestamp": "2020-01-01",
                "license": "cc",
                "sha256": "sha1",
                "georef_confidence": "high",
            }
        )
        writer.writerow(
            {
                "id": "bad-1",
                "image_path": "outputs/dataset/images/bad-1.jpg",
                "lat": "",
                "lon": "",
                "lcm_l2": "Semi-natural Grassland",
                "lcm_l3": "Neutral Grassland",
                "timestamp": "2020-01-01",
                "license": "cc",
                "sha256": "sha2",
                "georef_confidence": "high",
            }
        )

    rows = load_map_rows(labels_path)
    assert len(rows) == 1
    assert rows[0]["id"] == "ok-1"
    assert isinstance(rows[0]["x"], float)
    assert isinstance(rows[0]["y"], float)


def test_class_color_map_uses_lcm_palette() -> None:
    cmap = _build_class_color_map(["Neutral Grassland", "Urban", "UNKNOWN_CLASS"])
    assert cmap["Neutral Grassland"] == "#7fe57f"
    assert cmap["Urban"] == "#000000"
    assert cmap["UNKNOWN_CLASS"] == "#666666"
