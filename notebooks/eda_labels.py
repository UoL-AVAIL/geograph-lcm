from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPolygon
except Exception as exc:  # pragma: no cover
    raise RuntimeError("matplotlib is required for EDA plotting. Install with pip install matplotlib") from exc

try:
    from PIL import Image
except Exception as exc:  # pragma: no cover
    raise RuntimeError("Pillow is required for image panel EDA. Install with pip install pillow") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate basic EDA plots from dataset labels.csv")
    parser.add_argument("--labels", default="outputs/dataset/labels.csv", help="Path to labels.csv")
    parser.add_argument(
        "--out-dir",
        default="outputs/validation/eda",
        help="Directory to write charts and summary files",
    )
    parser.add_argument(
        "--examples-per-class",
        type=int,
        default=6,
        help="Number of example images to display for each class",
    )
    parser.add_argument(
        "--max-example-classes",
        type=int,
        default=8,
        help="Maximum number of classes to include in the example-image panel",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    labels_path = Path(args.labels)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not labels_path.exists():
        raise FileNotFoundError(f"labels file not found: {labels_path}")

    rows = _read_rows(labels_path)
    if not rows:
        raise RuntimeError("labels.csv contains no rows")

    l3_counts = Counter(row.get("lcm_l3", "") for row in rows if row.get("lcm_l3", ""))
    confidence_counts = Counter(
        row.get("georef_confidence", "") for row in rows if row.get("georef_confidence", "")
    )
    year_counts = Counter(_parse_year(row.get("timestamp", "")) for row in rows)
    year_counts.pop(None, None)

    _bar_chart(
        counts=l3_counts,
        title="LCM L3 Class Distribution",
        xlabel="Class",
        ylabel="Count",
        path=out_dir / "lcm_l3_distribution.png",
        rotate_x=True,
    )
    _bar_chart(
        counts=confidence_counts,
        title="Georeference Confidence Distribution",
        xlabel="Confidence",
        ylabel="Count",
        path=out_dir / "georef_confidence_distribution.png",
        rotate_x=False,
    )
    _bar_chart(
        counts=Counter(dict(sorted(year_counts.items()))),
        title="Capture Year Distribution",
        xlabel="Year",
        ylabel="Count",
        path=out_dir / "capture_year_distribution.png",
        rotate_x=False,
    )
    _spatial_scatter(rows=rows, path=out_dir / "spatial_scatter.png")
    _spatial_scatter_uk_map(rows=rows, path=out_dir / "spatial_scatter_uk_map.png")
    _class_examples_panel(
        rows=rows,
        path=out_dir / "class_examples.png",
        examples_per_class=max(1, args.examples_per_class),
        max_classes=max(1, args.max_example_classes),
    )

    summary = {
        "rows": len(rows),
        "unique_lcm_l3_classes": len(l3_counts),
        "top_lcm_l3": l3_counts.most_common(10),
        "georef_confidence_counts": dict(confidence_counts),
        "capture_year_counts": dict(sorted((k, v) for k, v in year_counts.items() if k is not None)),
        "labels_path": str(labels_path),
        "example_panel": str(out_dir / "class_examples.png"),
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)

    print(f"EDA written to {out_dir}")


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _parse_year(value: str) -> int | None:
    text = (value or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    try:
        return datetime.fromisoformat(text).year
    except Exception:
        return None


def _bar_chart(
    counts: Counter[Any],
    title: str,
    xlabel: str,
    ylabel: str,
    path: Path,
    rotate_x: bool,
) -> None:
    labels = [str(k) for k in counts.keys()]
    values = list(counts.values())
    plt.figure(figsize=(12, 5))
    plt.bar(labels, values)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    if rotate_x:
        plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def _spatial_scatter(rows: list[dict[str, str]], path: Path) -> None:
    points = []
    for row in rows:
        try:
            lat = float(row.get("lat", ""))
            lon = float(row.get("lon", ""))
        except Exception:
            continue
        points.append((lon, lat))
    if not points:
        return
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    plt.figure(figsize=(8, 10))
    plt.scatter(xs, ys, s=8, alpha=0.6)
    plt.title("Spatial Distribution (Lon/Lat)")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def _spatial_scatter_uk_map(rows: list[dict[str, str]], path: Path) -> None:
    points = []
    for row in rows:
        try:
            lat = float(row.get("lat", ""))
            lon = float(row.get("lon", ""))
        except Exception:
            continue
        points.append((lon, lat))
    if not points:
        return

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    fig, ax = plt.subplots(figsize=(8, 10))
    used_accurate_map = _plot_uk_basemap(ax)
    ax.scatter(xs, ys, s=10, alpha=0.7, c="#1f77b4")
    ax.set_xlim(-9.5, 3.5)
    ax.set_ylim(49.5, 59.5)
    ax.set_aspect("equal", adjustable="box")
    map_style = "Accurate low-detail UK map" if used_accurate_map else "Fallback rough UK map"
    ax.set_title(f"Spatial Distribution ({map_style}, Lon/Lat)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close(fig)


def _class_examples_panel(
    rows: list[dict[str, str]],
    path: Path,
    examples_per_class: int,
    max_classes: int,
) -> None:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        cls = row.get("lcm_l3", "").strip()
        if not cls:
            continue
        img_path = _resolve_existing_image_path(row.get("image_path", ""))
        if img_path is None:
            continue
        grouped.setdefault(cls, []).append(row)

    if not grouped:
        return

    ranked_classes = sorted(grouped.keys(), key=lambda c: len(grouped[c]), reverse=True)[:max_classes]
    n_rows = len(ranked_classes)
    n_cols = examples_per_class
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(2.2 * n_cols, 2.2 * n_rows))
    if n_rows == 1:
        axes = [axes]  # type: ignore[assignment]

    for row_idx, cls in enumerate(ranked_classes):
        class_rows = grouped[cls][:examples_per_class]
        ax_row = axes[row_idx]
        if n_cols == 1:
            ax_row = [ax_row]  # type: ignore[assignment]
        for col_idx in range(n_cols):
            ax = ax_row[col_idx]
            ax.axis("off")
            if col_idx >= len(class_rows):
                continue
            item = class_rows[col_idx]
            img_path = _resolve_existing_image_path(item.get("image_path", ""))
            if img_path is None:
                continue
            image = _load_preview_image(img_path)
            if image is None:
                continue
            ax.imshow(image)
            if col_idx == 0:
                ax.set_title(cls, fontsize=9, loc="left")
            else:
                ax.set_title(str(item.get("id", "")), fontsize=8)

    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close(fig)


def _plot_uk_basemap(ax: Any) -> bool:
    try:
        import geopandas as gpd
        import geodatasets
    except Exception:
        _plot_fallback_uk_polygons(ax)
        return False

    try:
        land_path = geodatasets.get_path("naturalearth.land")
        land = gpd.read_file(land_path)
        # Draw a tight UK bounding window for low-detail but accurate coastlines.
        window = land.cx[-11.0:3.0, 49.0:61.0]
        if window.empty:
            _plot_fallback_uk_polygons(ax)
            return False
        window.plot(ax=ax, facecolor="#f2f2f2", edgecolor="#888888", linewidth=0.8)
        return True
    except Exception:
        _plot_fallback_uk_polygons(ax)
        return False


def _plot_fallback_uk_polygons(ax: Any) -> None:
    gb_outline = [
        (-5.8, 50.0),
        (-4.8, 50.1),
        (-3.5, 50.3),
        (-2.0, 50.5),
        (-0.2, 50.7),
        (1.7, 51.0),
        (1.4, 52.0),
        (1.0, 53.2),
        (0.0, 54.5),
        (-1.5, 55.8),
        (-2.5, 56.6),
        (-3.0, 57.1),
        (-4.2, 57.7),
        (-5.0, 58.2),
        (-5.7, 57.7),
        (-6.1, 56.8),
        (-6.2, 55.8),
        (-5.7, 54.8),
        (-5.3, 53.9),
        (-4.9, 53.0),
        (-4.6, 52.2),
        (-5.0, 51.3),
        (-5.5, 50.6),
        (-5.8, 50.0),
    ]
    ni_outline = [
        (-8.2, 54.0),
        (-7.6, 54.2),
        (-6.8, 54.3),
        (-5.9, 54.2),
        (-5.4, 54.6),
        (-5.5, 55.2),
        (-6.0, 55.4),
        (-6.9, 55.3),
        (-7.7, 55.0),
        (-8.2, 54.5),
        (-8.2, 54.0),
    ]
    ax.add_patch(
        MplPolygon(gb_outline, closed=True, facecolor="#f2f2f2", edgecolor="#888888", lw=1.0)
    )
    ax.add_patch(
        MplPolygon(ni_outline, closed=True, facecolor="#f2f2f2", edgecolor="#888888", lw=1.0)
    )


def _resolve_existing_image_path(value: str) -> Path | None:
    text = (value or "").strip()
    if not text:
        return None
    path = Path(text)
    if path.exists():
        return path
    alt = Path.cwd() / text
    if alt.exists():
        return alt
    return None


def _load_preview_image(path: Path) -> Any | None:
    try:
        with Image.open(path) as img:
            image = img.convert("RGB")
            image.thumbnail((300, 300))
            return image
    except Exception:
        return None


if __name__ == "__main__":
    main()
