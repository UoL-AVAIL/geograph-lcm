from __future__ import annotations

from dataclasses import dataclass

from geograph_lcm.config import LCMAsset


@dataclass(frozen=True)
class LCMSelection:
    capture_year: int | None
    selected_lcm_year: int
    selection_reason: str


def select_lcm_asset(capture_year: int | None, assets: list[LCMAsset]) -> tuple[LCMAsset, LCMSelection]:
    if not assets:
        raise ValueError("No LCM assets configured")

    by_year = {asset.year: asset for asset in assets}
    years = sorted(by_year.keys())

    if capture_year is None:
        selected_year = years[-1]
        return by_year[selected_year], LCMSelection(
            capture_year=None,
            selected_lcm_year=selected_year,
            selection_reason="missing_capture_year_fallback_latest_available",
        )

    if capture_year in by_year:
        return by_year[capture_year], LCMSelection(
            capture_year=capture_year,
            selected_lcm_year=capture_year,
            selection_reason="exact_capture_year",
        )

    nearest_year = min(years, key=lambda year: (abs(year - capture_year), year))
    return by_year[nearest_year], LCMSelection(
        capture_year=capture_year,
        selected_lcm_year=nearest_year,
        selection_reason="nearest_available_year",
    )

