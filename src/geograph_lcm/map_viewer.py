from __future__ import annotations

import base64
import csv
import html
import io
import math
from pathlib import Path
from typing import Any

from PIL import Image


def latlon_to_web_mercator(lon: float, lat: float) -> tuple[float, float]:
    # Clamp to the practical Web Mercator latitude limits.
    lat = min(max(lat, -85.05112878), 85.05112878)
    origin_shift = 20037508.34
    x = lon * origin_shift / 180.0
    y = origin_shift * math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / math.pi
    return x, y


def load_map_rows(labels_path: Path) -> list[dict[str, Any]]:
    if not labels_path.exists():
        raise FileNotFoundError(f"labels.csv not found: {labels_path}")

    rows: list[dict[str, Any]] = []
    with labels_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                lat = float(str(row.get("lat", "")).strip())
                lon = float(str(row.get("lon", "")).strip())
            except Exception:
                continue
            x, y = latlon_to_web_mercator(lon=lon, lat=lat)
            rows.append(
                {
                    "id": str(row.get("id", "")),
                    "lcm_l3": str(row.get("lcm_l3", "")).strip() or "UNKNOWN",
                    "timestamp": str(row.get("timestamp", "")),
                    "license": str(row.get("license", "")),
                    "image_path": str(row.get("image_path", "")),
                    "lat": lat,
                    "lon": lon,
                    "x": x,
                    "y": y,
                }
            )
    if not rows:
        raise ValueError(f"No valid rows with coordinates in {labels_path}")
    return rows


def _build_class_color_map(classes: list[str]) -> dict[str, str]:
    # UKCEH LCM raster palette colors (LCM class legend / QGIS style).
    lcm_palette = {
        "broadleaved woodland": "#e10000",
        "coniferous woodland": "#006600",
        "arable and horticulture": "#732600",
        "arable": "#732600",
        "improved grassland": "#00ff00",
        "neutral grassland": "#7fe57f",
        "calcareous grassland": "#70a800",
        "acid grassland": "#998100",
        "fen, marsh and swamp": "#ffff00",
        "heather": "#801a80",
        "heather and shrub": "#801a80",
        "heather grassland": "#e68ca6",
        "bog": "#008073",
        "inland rock": "#d2d2ff",
        "saltwater": "#000080",
        "freshwater": "#0000ff",
        "supralittoral rock": "#ccb300",
        "supralittoral sediment": "#ccb300",
        "littoral rock": "#ffff80",
        "littoral sediment": "#ffff80",
        "saltmarsh": "#8080ff",
        "urban": "#000000",
        "suburban": "#808080",
        "unknown": "#666666",
    }
    color_map: dict[str, str] = {}
    for cls in classes:
        key = cls.strip().lower()
        color_map[cls] = lcm_palette.get(key, "#666666")
    return color_map


def _image_preview_html(image_path: str, max_size: int = 520) -> str:
    path = Path(image_path)
    if not path.exists():
        return "<p><b>Preview:</b> image file not found.</p>"
    try:
        with Image.open(path) as im:
            preview = im.copy()
            preview.thumbnail((max_size, max_size))
            buffer = io.BytesIO()
            preview.save(buffer, format="JPEG", quality=85)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f'<img src="data:image/jpeg;base64,{encoded}" style="max-width:100%;height:auto;border:1px solid #ccc;" />'
    except Exception as exc:
        return f"<p><b>Preview error:</b> {html.escape(str(exc))}</p>"


def _to_column_data(rows: list[dict[str, Any]], color_map: dict[str, str]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {
        "id": [],
        "lcm_l3": [],
        "timestamp": [],
        "license": [],
        "image_path": [],
        "lat": [],
        "lon": [],
        "x": [],
        "y": [],
        "color": [],
    }
    for row in rows:
        cls = str(row["lcm_l3"])
        out["id"].append(str(row["id"]))
        out["lcm_l3"].append(cls)
        out["timestamp"].append(str(row["timestamp"]))
        out["license"].append(str(row["license"]))
        out["image_path"].append(str(row["image_path"]))
        out["lat"].append(float(row["lat"]))
        out["lon"].append(float(row["lon"]))
        out["x"].append(float(row["x"]))
        out["y"].append(float(row["y"]))
        out["color"].append(color_map[cls])
    return out


def build_bokeh_document(
    doc: Any,
    labels_path: Path,
    title: str = "geograph-lcm map explorer",
) -> None:
    from bokeh.layouts import column, row as bokeh_row
    from bokeh.models import ColumnDataSource, Div, HoverTool, Range1d, Select, WMTSTileSource
    from bokeh.plotting import figure

    rows = load_map_rows(labels_path=labels_path)
    classes = sorted({str(r["lcm_l3"]) for r in rows})
    color_map = _build_class_color_map(classes)

    xs = [float(r["x"]) for r in rows]
    ys = [float(r["y"]) for r in rows]
    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)
    x_pad = (x_max - x_min) * 0.08 if x_max > x_min else 10_000.0
    y_pad = (y_max - y_min) * 0.08 if y_max > y_min else 10_000.0

    rows_by_class: dict[str, list[dict[str, Any]]] = {}
    for rec in rows:
        rows_by_class.setdefault(str(rec["lcm_l3"]), []).append(rec)
    class_sources: dict[str, ColumnDataSource] = {
        cls: ColumnDataSource(_to_column_data(class_rows, color_map))
        for cls, class_rows in rows_by_class.items()
    }

    p = figure(
        x_axis_type="mercator",
        y_axis_type="mercator",
        x_range=Range1d(start=x_min - x_pad, end=x_max + x_pad),
        y_range=Range1d(start=y_min - y_pad, end=y_max + y_pad),
        height=760,
        width=980,
        title=f"{title} ({len(rows):,} points)",
        tools="pan,wheel_zoom,box_zoom,reset,save,tap",
        active_scroll="wheel_zoom",
    )
    p.match_aspect = True
    p.add_tile(WMTSTileSource(url="https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"))
    renderers = []
    renderers_by_class: dict[str, Any] = {}
    for cls in classes:
        renderer = p.scatter(
            x="x",
            y="y",
            source=class_sources[cls],
            marker="circle",
            size=8,
            color=color_map[cls],
            alpha=0.65,
            line_alpha=0.0,
            legend_label=cls,
        )
        renderers.append(renderer)
        renderers_by_class[cls] = renderer
    p.legend.location = "top_left"
    p.legend.click_policy = "hide"

    hover = HoverTool(
        renderers=renderers,
        tooltips=[
            ("id", "@id"),
            ("lcm_l3", "@lcm_l3"),
            ("timestamp", "@timestamp"),
            ("lat", "@lat{0.00000}"),
            ("lon", "@lon{0.00000}"),
        ],
    )
    p.add_tools(hover)

    class_select = Select(
        title="LCM L3 filter",
        value="ALL",
        options=["ALL"] + classes,
        width=460,
    )

    details = Div(
        text=(
            "<div style='overflow-y:auto;line-height:1.35;word-break:break-word;'>"
            "<h3>Selected point</h3>"
            "<p>Tap a point on the map to view metadata and image preview.</p>"
            "</div>"
        ),
        width=460,
        height=600,
    )

    def _set_details(selected_class: str, idx: int) -> None:
        data = class_sources[selected_class].data
        if idx < 0 or idx >= len(data.get("id", [])):
            return
        item_id = html.escape(str(data["id"][idx]))
        cls = html.escape(str(data["lcm_l3"][idx]))
        timestamp = html.escape(str(data["timestamp"][idx]))
        license_value = html.escape(str(data["license"][idx]))
        image_path = str(data["image_path"][idx])
        lat = data["lat"][idx]
        lon = data["lon"][idx]
        preview = _image_preview_html(image_path=image_path)
        details.text = (
            "<div style='overflow-y:auto;line-height:1.35;word-break:break-word;'>"
            "<h3>Selected point</h3>"
            f"<p><b>ID:</b> {item_id}<br/>"
            f"<b>LCM L3:</b> {cls}<br/>"
            f"<b>Timestamp:</b> {timestamp}<br/>"
            f"<b>License:</b> {license_value}<br/>"
            f"<b>Lat/Lon:</b> {lat:.5f}, {lon:.5f}<br/>"
            f"<b>Image path:</b> {html.escape(image_path)}</p>"
            f"{preview}"
            "</div>"
        )

    def _on_selection_change(
        selected_class: str, attr: str, old: list[int], new: list[int]
    ) -> None:
        del attr, old
        if not new:
            return
        _set_details(selected_class, new[0])

    def _on_filter_change(attr: str, old: str, new: str) -> None:
        del attr, old
        if new not in {"ALL", *classes}:
            return
        if new == "ALL":
            for cls in classes:
                class_sources[cls].selected.indices = []
            for cls in classes:
                renderers_by_class[cls].visible = True
            p.title.text = f"{title} ({len(rows):,} points)"
        else:
            for cls in classes:
                class_sources[cls].selected.indices = []
            visible_count = len(rows_by_class.get(new, []))
            for cls in classes:
                renderers_by_class[cls].visible = cls == new
            p.title.text = f"{title} ({visible_count:,} points)"
        details.text = (
            "<div style='overflow-y:auto;line-height:1.35;word-break:break-word;'>"
            "<h3>Selected point</h3>"
            "<p>Tap a point on the map to view metadata and image preview.</p>"
            "</div>"
        )

    controls_info = Div(
        text=(
            "<div style='line-height:1.35;word-break:break-word;'>"
            "<h3>Map controls</h3>"
            f"<p><b>Labels source:</b> {html.escape(str(labels_path))}</p>"
            "<p>Use wheel to zoom, drag to pan, tap a point to inspect.</p>"
            "</div>"
        ),
        width=460,
        height=130,
    )

    for cls in classes:
        class_sources[cls].selected.on_change(
            "indices",
            lambda attr, old, new, cls=cls: _on_selection_change(cls, attr, old, new),
        )
    class_select.on_change("value", _on_filter_change)

    controls = column(
        controls_info,
        class_select,
        width=460,
        height=180,
        sizing_mode="fixed",
    )
    sidebar = column(
        controls,
        details,
        width=460,
        height=760,
        spacing=12,
        sizing_mode="fixed",
    )

    doc.add_root(bokeh_row(p, sidebar))
    doc.title = title
