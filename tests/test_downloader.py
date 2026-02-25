from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests

from geograph_lcm import downloader


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        json_data: Any = None,
        content: bytes | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._json_data = json_data
        self.content = content or b""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self) -> Any:
        return self._json_data


class FakeSession:
    def __init__(self, scripted_responses: list[Any]) -> None:
        self._responses = scripted_responses
        self.calls: list[dict[str, Any]] = []

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> FakeResponse:
        del headers, timeout
        self.calls.append({"method": method, "url": url, "params": params})
        if not self._responses:
            raise AssertionError("No scripted response left for request")
        next_value = self._responses.pop(0)
        if isinstance(next_value, Exception):
            raise next_value
        return next_value


def test_run_requires_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEOGRAPH_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Missing Geograph API key:"):
        downloader.run(config={}, input_dir=None, output_dir=tmp_path)


def test_downloader_writes_metadata_and_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEOGRAPH_API_KEY", "test-key")

    scripted = [
        FakeResponse(
            headers={"content-type": "application/json"},
            json_data={
                "items": [
                    {
                        "id": "a1",
                        "image_url": "https://images.example/a1.jpg",
                        "license": "CC-BY",
                        "captured_at": "2020-01-01T00:00:00Z",
                        "lat": 52.0,
                        "lon": -1.0,
                    }
                ]
            },
        ),
        FakeResponse(content=b"image-a1"),
        FakeResponse(
            headers={"content-type": "application/json"},
            json_data={
                "items": [
                    {
                        "id": "a2",
                        "image_url": "https://images.example/a2.jpg",
                        "license": "CC-BY-SA",
                        "captured_at": "2021-02-03T00:00:00Z",
                        "lat": 53.0,
                        "lon": -2.0,
                    }
                ]
            },
        ),
        FakeResponse(content=b"image-a2"),
        FakeResponse(headers={"content-type": "application/json"}, json_data={"items": []}),
    ]
    fake_session = FakeSession(scripted)
    monkeypatch.setattr(downloader.requests, "Session", lambda: fake_session)

    config = {
        "geograph": {
            "api_base_url": "https://api.geograph.org.uk",
            "api_key_env_var": "GEOGRAPH_API_KEY",
            "version": "test-agent",
            "max_per_minute": 0,
        },
        "downloader": {
            "endpoint_path": "/syndicator.php",
            "page_size": 1,
            "max_items": 10,
            "timeout_s": 1.0,
            "max_retries": 2,
            "retry_backoff_s": 0.0,
            "auth_key_param": "key",
            "page_param": "page",
            "per_page_param": "perpage",
            "format_param": "format",
            "format_value": "JSON",
            "query": {"i": "12345", "text": "leicestershire"},
            "results_key": "items",
            "require_saved_search_id": True,
            "retrieval_policy": {"capture_year_min": 2015, "capture_year_max": 2024},
            "prefer_details_api_image_url": False,
        },
    }

    summary = downloader.run(config=config, input_dir=None, output_dir=tmp_path / "download")

    assert summary["items_written"] == 2
    assert summary["pages_fetched"] == 3
    assert (tmp_path / "download" / "raw" / "images" / "a1.jpg").exists()
    assert (tmp_path / "download" / "raw" / "images" / "a2.jpg").exists()
    metadata_lines = (
        (tmp_path / "download" / "raw" / "metadata.jsonl")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )
    assert len(metadata_lines) == 2
    first = json.loads(metadata_lines[0])
    assert first["id"] == "a1"
    assert first["provenance"]["source"] == "geograph_api"
    assert first["license"] == "CC-BY"
    assert first["provenance"]["request_params"]["key"] == "***redacted***"
    assert fake_session.calls[0]["params"]["key"] == "test-key"
    assert fake_session.calls[0]["params"]["perpage"] == 1
    assert fake_session.calls[0]["params"]["format"] == "JSON"


def test_rejects_unsupported_syndicator_query_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEOGRAPH_API_KEY", "test-key")
    with pytest.raises(ValueError, match="Unsupported syndicator query parameters"):
        downloader.run(
            config={
                "geograph": {"api_base_url": "https://api.geograph.org.uk"},
                "downloader": {
                    "query": {"i": "12345", "county": "leicestershire"},
                    "require_saved_search_id": True,
                    "prefer_details_api_image_url": False,
                },
            },
            input_dir=None,
            output_dir=tmp_path / "download",
        )


def test_requires_saved_search_id_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEOGRAPH_API_KEY", "test-key")
    with pytest.raises(ValueError, match="downloader.query.i"):
        downloader.run(
            config={
                "geograph": {"api_base_url": "https://api.geograph.org.uk"},
                "downloader": {
                    "query": {"text": "leicestershire"},
                    "prefer_details_api_image_url": False,
                },
            },
            input_dir=None,
            output_dir=tmp_path / "download",
        )


def test_downloader_accepts_api_key_from_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GEOGRAPH_API_KEY", raising=False)
    scripted = [FakeResponse(headers={"content-type": "application/json"}, json_data={"items": []})]
    fake_session = FakeSession(scripted)
    monkeypatch.setattr(downloader.requests, "Session", lambda: fake_session)

    summary = downloader.run(
        config={
            "geograph": {"api_base_url": "https://api.geograph.org.uk", "api_key": "cli-key"},
            "downloader": {
                "results_key": "items",
                "query": {"i": "12345"},
                "prefer_details_api_image_url": False,
            },
        },
        input_dir=None,
        output_dir=tmp_path / "download",
    )

    assert summary["geograph_api_key_source"] == "config"
    assert fake_session.calls[0]["params"]["key"] == "cli-key"


def test_request_with_retry_recovers_from_temporary_failure() -> None:
    fake_session = FakeSession(
        [
            requests.ConnectionError("temporary"),
            FakeResponse(headers={"content-type": "application/json"}, json_data={"items": []}),
        ]
    )
    limiter = downloader.RateLimiter(max_per_minute=0)

    response = downloader._request_with_retry(
        session=fake_session,  # type: ignore[arg-type]
        method="GET",
        url="https://api.geograph.org.uk/syndicator.php",
        headers={"User-Agent": "test"},
        params={"page": 1},
        timeout_s=1.0,
        max_retries=2,
        retry_backoff_s=0.0,
        rate_limiter=limiter,
    )
    assert response == {"items": []}


def test_skips_items_outside_capture_year_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEOGRAPH_API_KEY", "test-key")
    scripted = [
        FakeResponse(
            headers={"content-type": "application/json"},
            json_data={
                "items": [
                    {
                        "id": "old-1",
                        "image_url": "https://images.example/old-1.jpg",
                        "license": "CC-BY",
                        "captured_at": "2014-01-01",
                        "lat": 52.0,
                        "lon": -1.0,
                    },
                    {
                        "id": "ok-1",
                        "image_url": "https://images.example/ok-1.jpg",
                        "license": "CC-BY",
                        "captured_at": "2018-01-01",
                        "lat": 52.0,
                        "lon": -1.0,
                    },
                ]
            },
        ),
        FakeResponse(content=b"image-ok-1"),
        FakeResponse(headers={"content-type": "application/json"}, json_data={"items": []}),
    ]
    fake_session = FakeSession(scripted)
    monkeypatch.setattr(downloader.requests, "Session", lambda: fake_session)

    summary = downloader.run(
        config={
            "geograph": {"api_base_url": "https://api.geograph.org.uk", "max_per_minute": 0},
            "downloader": {
                "query": {"i": "12345"},
                "results_key": "items",
                "require_saved_search_id": True,
                "retrieval_policy": {"capture_year_min": 2015, "capture_year_max": 2024},
                "prefer_details_api_image_url": False,
            },
        },
        input_dir=None,
        output_dir=tmp_path / "download",
    )

    assert summary["items_written"] == 1
    assert summary["skipped_out_of_year_range"] == 1
    assert (tmp_path / "download" / "raw" / "images" / "ok-1.jpg").exists()


def test_prefers_details_api_image_url_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEOGRAPH_API_KEY", "test-key")
    scripted = [
        FakeResponse(
            headers={"content-type": "application/json"},
            json_data={
                "items": [
                    {
                        "guid": "8131806",
                        "thumb": "https://s2.geograph.org.uk/geophotos/08/13/18/8131806_thumb.jpg",
                        "licence": "http://creativecommons.org/licenses/by-sa/2.0/",
                        "imageTaken": "2025-08-22",
                        "lat": "57.460776",
                        "long": "-2.486179",
                    }
                ]
            },
        ),
        FakeResponse(
            headers={"content-type": "application/xml"},
            content=(
                b'<response><img src="https://s0.geograph.org.uk/geophotos/08/13/18/8131806_full.jpg" /></response>'
            ),
        ),
        FakeResponse(content=b"full-image-bytes"),
        FakeResponse(headers={"content-type": "application/json"}, json_data={"items": []}),
    ]
    fake_session = FakeSession(scripted)
    monkeypatch.setattr(downloader.requests, "Session", lambda: fake_session)

    summary = downloader.run(
        config={
            "geograph": {"api_base_url": "https://api.geograph.org.uk", "max_per_minute": 0},
            "downloader": {
                "query": {"i": "12345"},
                "results_key": "items",
                "require_saved_search_id": True,
                "prefer_details_api_image_url": True,
                "details_api_fallback_to_feed_url": False,
                "details_api_path_template": "/api/photo/{photo_id}/{api_key}",
                "field_mapping": {
                    "id_field": "guid",
                    "image_url_field": "thumb",
                    "license_field": "licence",
                    "timestamp_field": "imageTaken",
                    "lat_field": "lat",
                    "lon_field": "long",
                },
            },
        },
        input_dir=None,
        output_dir=tmp_path / "download",
    )

    assert summary["items_written"] == 1
    metadata_lines = (
        (tmp_path / "download" / "raw" / "metadata.jsonl")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )
    first = json.loads(metadata_lines[0])
    assert first["image_url_source"] == "details_api"
    assert first["image_url"].endswith("8131806_full.jpg")


def test_skips_item_when_full_res_missing_and_fallback_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEOGRAPH_API_KEY", "test-key")
    scripted = [
        FakeResponse(
            headers={"content-type": "application/json"},
            json_data={
                "items": [
                    {
                        "guid": "8131806",
                        "thumb": "https://s2.geograph.org.uk/geophotos/08/13/18/8131806_thumb.jpg",
                        "licence": "http://creativecommons.org/licenses/by-sa/2.0/",
                        "imageTaken": "2025-08-22",
                        "lat": "57.460776",
                        "long": "-2.486179",
                    }
                ]
            },
        ),
        FakeResponse(
            headers={"content-type": "application/xml"},
            content=b"<response><foo /></response>",
        ),
        FakeResponse(headers={"content-type": "application/json"}, json_data={"items": []}),
    ]
    fake_session = FakeSession(scripted)
    monkeypatch.setattr(downloader.requests, "Session", lambda: fake_session)

    summary = downloader.run(
        config={
            "geograph": {"api_base_url": "https://api.geograph.org.uk", "max_per_minute": 0},
            "downloader": {
                "query": {"i": "12345"},
                "results_key": "items",
                "require_saved_search_id": True,
                "prefer_details_api_image_url": True,
                "details_api_fallback_to_feed_url": False,
                "details_api_path_template": "/api/photo/{photo_id}/{api_key}",
                "field_mapping": {
                    "id_field": "guid",
                    "image_url_field": "thumb",
                    "license_field": "licence",
                    "timestamp_field": "imageTaken",
                    "lat_field": "lat",
                    "lon_field": "long",
                },
            },
        },
        input_dir=None,
        output_dir=tmp_path / "download",
    )

    assert summary["items_written"] == 0
    assert summary["skipped_missing_full_res"] == 1
    assert not (tmp_path / "download" / "raw" / "images" / "8131806.jpg").exists()


def test_skips_item_below_pre_download_dimensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEOGRAPH_API_KEY", "test-key")
    scripted = [
        FakeResponse(
            headers={"content-type": "application/json"},
            json_data={
                "items": [
                    {
                        "guid": "8131806",
                        "thumb": "https://s2.geograph.org.uk/geophotos/08/13/18/8131806_thumb.jpg",
                        "licence": "http://creativecommons.org/licenses/by-sa/2.0/",
                        "imageTaken": "2025-08-22",
                        "lat": "57.460776",
                        "long": "-2.486179",
                    }
                ]
            },
        ),
        FakeResponse(
            headers={"content-type": "application/xml"},
            content=(
                b'<response><img src="https://s0.geograph.org.uk/geophotos/08/13/18/8131806_full.jpg" width="640" height="480" /></response>'
            ),
        ),
        FakeResponse(headers={"content-type": "application/json"}, json_data={"items": []}),
    ]
    fake_session = FakeSession(scripted)
    monkeypatch.setattr(downloader.requests, "Session", lambda: fake_session)

    summary = downloader.run(
        config={
            "geograph": {"api_base_url": "https://api.geograph.org.uk", "max_per_minute": 0},
            "downloader": {
                "query": {"i": "12345"},
                "results_key": "items",
                "require_saved_search_id": True,
                "prefer_details_api_image_url": True,
                "details_api_fallback_to_feed_url": False,
                "pre_download_min_width": 800,
                "pre_download_min_height": 600,
                "details_api_path_template": "/api/photo/{photo_id}/{api_key}",
                "field_mapping": {
                    "id_field": "guid",
                    "image_url_field": "thumb",
                    "license_field": "licence",
                    "timestamp_field": "imageTaken",
                    "lat_field": "lat",
                    "lon_field": "long",
                },
            },
        },
        input_dir=None,
        output_dir=tmp_path / "download",
    )

    assert summary["items_written"] == 0
    assert summary["skipped_small_dimensions"] == 1
    assert not (tmp_path / "download" / "raw" / "images").exists() or not list(
        (tmp_path / "download" / "raw" / "images").glob("*")
    )


def test_records_details_dimensions_when_downloaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEOGRAPH_API_KEY", "test-key")
    scripted = [
        FakeResponse(
            headers={"content-type": "application/json"},
            json_data={
                "items": [
                    {
                        "guid": "8131806",
                        "thumb": "https://s2.geograph.org.uk/geophotos/08/13/18/8131806_thumb.jpg",
                        "licence": "http://creativecommons.org/licenses/by-sa/2.0/",
                        "imageTaken": "2025-08-22",
                        "lat": "57.460776",
                        "long": "-2.486179",
                    }
                ]
            },
        ),
        FakeResponse(
            headers={"content-type": "application/xml"},
            content=(
                b'<response><img src="https://s0.geograph.org.uk/geophotos/08/13/18/8131806_full.jpg" width="1024" height="768" /></response>'
            ),
        ),
        FakeResponse(content=b"full-image-bytes"),
        FakeResponse(headers={"content-type": "application/json"}, json_data={"items": []}),
    ]
    fake_session = FakeSession(scripted)
    monkeypatch.setattr(downloader.requests, "Session", lambda: fake_session)

    summary = downloader.run(
        config={
            "geograph": {"api_base_url": "https://api.geograph.org.uk", "max_per_minute": 0},
            "downloader": {
                "query": {"i": "12345"},
                "results_key": "items",
                "require_saved_search_id": True,
                "prefer_details_api_image_url": True,
                "details_api_fallback_to_feed_url": False,
                "pre_download_min_width": 800,
                "pre_download_min_height": 600,
                "details_api_path_template": "/api/photo/{photo_id}/{api_key}",
                "field_mapping": {
                    "id_field": "guid",
                    "image_url_field": "thumb",
                    "license_field": "licence",
                    "timestamp_field": "imageTaken",
                    "lat_field": "lat",
                    "lon_field": "long",
                },
            },
        },
        input_dir=None,
        output_dir=tmp_path / "download",
    )

    assert summary["items_written"] == 1
    assert summary["skipped_small_dimensions"] == 0
    metadata_lines = (
        (tmp_path / "download" / "raw" / "metadata.jsonl")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )
    first = json.loads(metadata_lines[0])
    assert first["details_image_width"] == 1024
    assert first["details_image_height"] == 768


def test_skips_item_with_disallowed_license(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEOGRAPH_API_KEY", "test-key")
    scripted = [
        FakeResponse(
            headers={"content-type": "application/json"},
            json_data={
                "items": [
                    {
                        "guid": "8131806",
                        "thumb": "https://s2.geograph.org.uk/geophotos/08/13/18/8131806_thumb.jpg",
                        "licence": "http://creativecommons.org/licenses/by-sa/2.0/",
                        "imageTaken": "2025-08-22",
                        "lat": "57.460776",
                        "long": "-2.486179",
                    }
                ]
            },
        ),
        FakeResponse(headers={"content-type": "application/json"}, json_data={"items": []}),
    ]
    fake_session = FakeSession(scripted)
    monkeypatch.setattr(downloader.requests, "Session", lambda: fake_session)

    summary = downloader.run(
        config={
            "geograph": {"api_base_url": "https://api.geograph.org.uk", "max_per_minute": 0},
            "downloader": {
                "query": {"i": "12345"},
                "results_key": "items",
                "require_saved_search_id": True,
                "prefer_details_api_image_url": True,
                "details_api_fallback_to_feed_url": False,
                "allowed_licenses": ["http://creativecommons.org/licenses/by/2.0/"],
                "field_mapping": {
                    "id_field": "guid",
                    "image_url_field": "thumb",
                    "license_field": "licence",
                    "timestamp_field": "imageTaken",
                    "lat_field": "lat",
                    "lon_field": "long",
                },
            },
        },
        input_dir=None,
        output_dir=tmp_path / "download",
    )

    assert summary["items_written"] == 0
    assert summary["skipped_disallowed_license"] == 1


def test_skips_redownload_when_item_is_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEOGRAPH_API_KEY", "test-key")

    first_run_scripted = [
        FakeResponse(
            headers={"content-type": "application/json"},
            json_data={
                "items": [
                    {
                        "id": "cache-1",
                        "image_url": "https://images.example/cache-1.jpg",
                        "license": "http://creativecommons.org/licenses/by-sa/2.0/",
                        "captured_at": "2020-01-01T00:00:00Z",
                        "lat": 52.0,
                        "lon": -1.0,
                    }
                ]
            },
        ),
        FakeResponse(content=b"image-cache-1"),
        FakeResponse(headers={"content-type": "application/json"}, json_data={"items": []}),
    ]
    first_session = FakeSession(first_run_scripted)
    monkeypatch.setattr(downloader.requests, "Session", lambda: first_session)

    config = {
        "geograph": {"api_base_url": "https://api.geograph.org.uk", "max_per_minute": 0},
        "downloader": {
            "query": {"i": "12345"},
            "results_key": "items",
            "require_saved_search_id": True,
            "prefer_details_api_image_url": False,
            "skip_if_exists": True,
            "force_redownload": False,
            "allowed_licenses": ["http://creativecommons.org/licenses/by-sa/2.0/"],
        },
    }

    first_summary = downloader.run(config=config, input_dir=None, output_dir=tmp_path / "download")
    assert first_summary["items_written"] == 1
    assert first_summary["skipped_already_cached"] == 0

    second_run_scripted = [
        FakeResponse(
            headers={"content-type": "application/json"},
            json_data={
                "items": [
                    {
                        "id": "cache-1",
                        "image_url": "https://images.example/cache-1.jpg",
                        "license": "http://creativecommons.org/licenses/by-sa/2.0/",
                        "captured_at": "2020-01-01T00:00:00Z",
                        "lat": 52.0,
                        "lon": -1.0,
                    }
                ]
            },
        ),
        FakeResponse(headers={"content-type": "application/json"}, json_data={"items": []}),
    ]
    second_session = FakeSession(second_run_scripted)
    monkeypatch.setattr(downloader.requests, "Session", lambda: second_session)

    second_summary = downloader.run(config=config, input_dir=None, output_dir=tmp_path / "download")
    assert second_summary["items_written"] == 1
    assert second_summary["skipped_already_cached"] == 1
