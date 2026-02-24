from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class LCMAsset:
    year: int
    path: Path
    crs: str
    resolution_m: float
    nodata: float | int | None
    version: str
    checksum_sha256: str


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at {path}, got {type(data)!r}")
    return data


def load_pipeline_config(path: Path) -> dict[str, Any]:
    return load_yaml(path)


def load_lcm_catalog(path: Path) -> list[LCMAsset]:
    raw = load_yaml(path)
    assets_raw = raw.get("lcm_assets", [])
    if not isinstance(assets_raw, list):
        raise ValueError("config/lcm_catalog.yaml must define lcm_assets as a list")

    assets: list[LCMAsset] = []
    for item in assets_raw:
        if not isinstance(item, dict):
            raise ValueError("Each lcm asset entry must be a mapping")
        assets.append(
            LCMAsset(
                year=int(item["year"]),
                path=Path(str(item["path"])),
                crs=str(item["crs"]),
                resolution_m=float(item["resolution_m"]),
                nodata=item.get("nodata"),
                version=str(item.get("version", "")),
                checksum_sha256=str(item.get("checksum_sha256", "")),
            )
        )
    return sorted(assets, key=lambda a: a.year)
