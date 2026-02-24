from pathlib import Path

from geograph_lcm.config import LCMAsset
from geograph_lcm.lcm_policy import select_lcm_asset


def _assets() -> list[LCMAsset]:
    return [
        LCMAsset(2015, Path("data/lcm/2015.tif"), "EPSG:27700", 25.0, 0, "v", "sha"),
        LCMAsset(2020, Path("data/lcm/2020.tif"), "EPSG:27700", 10.0, 0, "v", "sha"),
        LCMAsset(2024, Path("data/lcm/2024.tif"), "EPSG:27700", 10.0, 0, "v", "sha"),
    ]


def test_selects_exact_capture_year() -> None:
    asset, selection = select_lcm_asset(2020, _assets())
    assert asset.year == 2020
    assert selection.selection_reason == "exact_capture_year"


def test_selects_nearest_year() -> None:
    asset, selection = select_lcm_asset(2023, _assets())
    assert asset.year == 2024
    assert selection.selection_reason == "nearest_available_year"


def test_tie_breaks_to_earlier_year() -> None:
    asset, selection = select_lcm_asset(2022, _assets())
    assert asset.year == 2020
    assert selection.selection_reason == "nearest_available_year"


def test_fallback_without_capture_year_uses_latest_available() -> None:
    asset, selection = select_lcm_asset(None, _assets())
    assert asset.year == 2024
    assert selection.selection_reason == "missing_capture_year_fallback_latest_available"
