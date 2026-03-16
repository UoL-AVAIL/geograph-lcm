from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version as pkg_version
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover - fallback for environments without tqdm installed
    tqdm = None

from geograph_lcm.stage_utils import ensure_dir, utc_now_iso, write_json, write_stage_success_marker

SUPPORTED_SYNDICATOR_QUERY_KEYS = {
    "i",
    "u",
    "q",
    "location",
    "text",
    "distance",
    "perpage",
    "page",
    "format",
    "expand",
    "callback",
}


@dataclass(frozen=True)
class FieldMapping:
    id_field: str
    image_url_field: str
    license_field: str
    timestamp_field: str
    lat_field: str
    lon_field: str


class RateLimiter:
    def __init__(self, max_per_minute: int) -> None:
        self._min_interval = 0.0 if max_per_minute <= 0 else 60.0 / max_per_minute
        self._last_request_monotonic: float | None = None

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        if self._last_request_monotonic is not None:
            elapsed = now - self._last_request_monotonic
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
        self._last_request_monotonic = time.monotonic()


class ProgressLike(Protocol):
    def update(self, n: int) -> None: ...
    def set_postfix(self, ordered_dict: dict[str, Any], refresh: bool = False) -> None: ...
    def close(self) -> None: ...


class _NoopProgress:
    def update(self, n: int) -> None:
        del n

    def set_postfix(self, ordered_dict: dict[str, Any], refresh: bool = False) -> None:
        del ordered_dict, refresh

    def close(self) -> None:
        return None


class _TqdmProgress:
    def __init__(self, tqdm_instance: Any) -> None:
        self._tqdm = tqdm_instance

    def update(self, n: int) -> None:
        self._tqdm.update(n)

    def set_postfix(self, ordered_dict: dict[str, Any], refresh: bool = False) -> None:
        self._tqdm.set_postfix(ordered_dict, refresh=refresh)

    def close(self) -> None:
        self._tqdm.close()


def run(config: dict[str, Any], input_dir: Path | None, output_dir: Path) -> dict[str, Any]:
    del input_dir
    geograph_cfg = config.get("geograph", {})
    downloader_cfg = config.get("downloader", {})

    api_key_var = str(geograph_cfg.get("api_key_env_var", "GEOGRAPH_API_KEY"))
    api_key = str(geograph_cfg.get("api_key", "")).strip() or os.environ.get(api_key_var)
    if not api_key:
        raise ValueError(
            f"Missing Geograph API key: provide --geograph-api-key or env var '{api_key_var}'"
        )
    api_key_source = "config" if str(geograph_cfg.get("api_key", "")).strip() else "env"

    ensure_dir(output_dir)
    raw_dir = output_dir / "raw"
    images_dir = raw_dir / "images"
    ensure_dir(raw_dir)
    ensure_dir(images_dir)

    endpoint_url = _build_endpoint_url(
        base_url=str(geograph_cfg.get("api_base_url", "https://api.geograph.org.uk")),
        endpoint_path=str(downloader_cfg.get("endpoint_path", "/api/images")),
    )

    timeout_s = float(downloader_cfg.get("timeout_s", 30.0))
    max_retries = int(downloader_cfg.get("max_retries", 3))
    retry_backoff_s = float(downloader_cfg.get("retry_backoff_s", 1.0))
    page_size = int(downloader_cfg.get("page_size", 100))
    max_items = int(downloader_cfg.get("max_items", 1000))
    auth_key_param = str(downloader_cfg.get("auth_key_param", "key"))
    page_param = str(downloader_cfg.get("page_param", "page"))
    per_page_param = str(downloader_cfg.get("per_page_param", "perpage"))
    format_param = str(downloader_cfg.get("format_param", "format"))
    format_value = str(downloader_cfg.get("format_value", "JSON"))
    prefer_details_api_image_url = bool(downloader_cfg.get("prefer_details_api_image_url", True))
    details_api_fallback_to_feed_url = bool(
        downloader_cfg.get("details_api_fallback_to_feed_url", True)
    )
    pre_download_min_width = _to_optional_int(downloader_cfg.get("pre_download_min_width"))
    pre_download_min_height = _to_optional_int(downloader_cfg.get("pre_download_min_height"))
    skip_if_exists = bool(downloader_cfg.get("skip_if_exists", True))
    force_redownload = bool(downloader_cfg.get("force_redownload", False))
    details_api_path_template = str(
        downloader_cfg.get("details_api_path_template", "/api/photo/{photo_id}/{api_key}")
    )
    query = downloader_cfg.get("query", {})
    if query is None:
        query = {}
    if not isinstance(query, dict):
        raise ValueError("downloader.query must be a mapping")
    _validate_syndicator_query_keys(query)
    query = _sanitize_query(query)
    require_saved_search_id = bool(downloader_cfg.get("require_saved_search_id", True))
    show_progress = bool(downloader_cfg.get("show_progress", True))
    _validate_saved_search_id_requirement(query=query, required=require_saved_search_id)
    search_queries = _expand_saved_search_queries(query)
    search_ids = sorted(
        {
            q.get("i", "")
            for q in search_queries
            if isinstance(q.get("i", ""), str) and q.get("i", "")
        }
    )
    print(
        "[download] endpoint="
        f"{endpoint_url} max_items={max_items} page_size={page_size} "
        f"query_keys={sorted(query.keys())} saved_search_count={len(search_queries)}"
    )

    field_mapping = _read_field_mapping(downloader_cfg)
    results_key = str(downloader_cfg.get("results_key", "items"))
    user_agent = _resolve_user_agent(geograph_cfg)
    max_per_minute = int(geograph_cfg.get("max_per_minute", 60))
    headers = {"User-Agent": user_agent}
    rate_limiter = RateLimiter(max_per_minute=max_per_minute)

    metadata_path = raw_dir / "metadata.jsonl"
    existing_records = (
        _load_existing_metadata_by_id(metadata_path)
        if skip_if_exists and not force_redownload
        else {}
    )
    items_written = 0
    pages_fetched = 0
    image_download_errors = 0
    item_errors = 0
    skipped_out_of_year_range = 0
    skipped_disallowed_license = 0
    skipped_already_cached = 0
    skipped_duplicate_item_ids = 0
    skipped_missing_full_res = 0
    skipped_small_dimensions = 0
    details_api_errors = 0
    status = "success"
    error_message: str | None = None
    failure_marker_path = output_dir / "_FAILED.json"
    progress = _make_progress(total=max_items, show_progress=show_progress)
    seen_item_ids: set[str] = set()

    try:
        with (
            requests.Session() as session,
            metadata_path.open("w", encoding="utf-8") as metadata_fh,
        ):
            for search_query in search_queries:
                if items_written >= max_items:
                    break
                page = 1
                while items_written < max_items:
                    params = dict(search_query)
                    params.update(
                        {
                            auth_key_param: api_key,
                            page_param: page,
                            per_page_param: page_size,
                            format_param: format_value,
                        }
                    )

                    response_json = _request_with_retry(
                        session=session,
                        method="GET",
                        url=endpoint_url,
                        headers=headers,
                        params=params,
                        timeout_s=timeout_s,
                        max_retries=max_retries,
                        retry_backoff_s=retry_backoff_s,
                        rate_limiter=rate_limiter,
                    )

                    pages_fetched += 1
                    items = _extract_items(response_json=response_json, results_key=results_key)

                    if not isinstance(items, list):
                        raise ValueError(f"Expected list of items, got {type(items)!r}")

                    if not items:
                        break

                    for item in items:
                        if items_written >= max_items:
                            break
                        if not isinstance(item, dict):
                            item_errors += 1
                            continue
                        item_id = _extract_item_id(item=item, field_mapping=field_mapping)
                        if item_id is None:
                            item_errors += 1
                            continue
                        if item_id in seen_item_ids:
                            skipped_duplicate_item_ids += 1
                            continue
                        if _should_skip_item_for_capture_year(item, field_mapping, downloader_cfg):
                            skipped_out_of_year_range += 1
                            continue
                        if _should_skip_item_for_license(item, field_mapping, downloader_cfg):
                            skipped_disallowed_license += 1
                            continue
                        cached_record = _resolve_cached_record(
                            item=item,
                            field_mapping=field_mapping,
                            existing_records=existing_records,
                        )
                        if cached_record is not None:
                            skipped_already_cached += 1
                            metadata_fh.write(json.dumps(cached_record, sort_keys=True))
                            metadata_fh.write("\n")
                            items_written += 1
                            progress.update(1)
                            seen_item_ids.add(item_id)
                            continue
                        try:
                            record = _download_one_item(
                                item=item,
                                field_mapping=field_mapping,
                                session=session,
                                headers=headers,
                                timeout_s=timeout_s,
                                max_retries=max_retries,
                                retry_backoff_s=retry_backoff_s,
                                rate_limiter=rate_limiter,
                                images_dir=images_dir,
                                endpoint_url=endpoint_url,
                                base_api_url=str(
                                    geograph_cfg.get("api_base_url", "https://api.geograph.org.uk")
                                ),
                                details_api_path_template=details_api_path_template,
                                api_key=api_key,
                                prefer_details_api_image_url=prefer_details_api_image_url,
                                details_api_fallback_to_feed_url=details_api_fallback_to_feed_url,
                                pre_download_min_width=pre_download_min_width,
                                pre_download_min_height=pre_download_min_height,
                                request_params=_redact_request_params(
                                    params=params, redacted_keys={auth_key_param}
                                ),
                            )
                            if record.get("image_url_source") == "feed_fallback":
                                details_api_errors += 1
                            metadata_fh.write(json.dumps(record, sort_keys=True))
                            metadata_fh.write("\n")
                            items_written += 1
                            progress.update(1)
                            seen_item_ids.add(item_id)
                        except ValueError as exc:
                            if str(exc) == "missing_full_res_image_url":
                                skipped_missing_full_res += 1
                            elif str(exc) == "image_dimensions_below_minimum":
                                skipped_small_dimensions += 1
                            else:
                                image_download_errors += 1
                        except Exception:
                            image_download_errors += 1

                    page += 1
                    progress.set_postfix(
                        {
                            "written": items_written,
                            "skip_year": skipped_out_of_year_range,
                            "skip_license": skipped_disallowed_license,
                            "skip_cached": skipped_already_cached,
                            "skip_dupe": skipped_duplicate_item_ids,
                            "skip_fullres": skipped_missing_full_res,
                            "skip_small": skipped_small_dimensions,
                            "errors": image_download_errors,
                        },
                        refresh=False,
                    )
    except KeyboardInterrupt:
        status = "interrupted"
        error_message = "KeyboardInterrupt"
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
    finally:
        progress.close()

    summary = {
        "stage": "download",
        "started_at": utc_now_iso(),
        "completed_at": utc_now_iso(),
        "status": status,
        "source_policy": "geograph_api_only",
        "geograph_api_base_url": geograph_cfg.get("api_base_url"),
        "geograph_api_endpoint_url": endpoint_url,
        "geograph_api_key_env_var": api_key_var,
        "geograph_api_key_present": True,
        "geograph_api_key_source": api_key_source,
        "page_size": page_size,
        "max_items": max_items,
        "saved_search_ids": search_ids,
        "saved_search_count": len(search_queries),
        "pages_fetched": pages_fetched,
        "items_written": items_written,
        "item_errors": item_errors,
        "skipped_out_of_year_range": skipped_out_of_year_range,
        "skipped_disallowed_license": skipped_disallowed_license,
        "skipped_already_cached": skipped_already_cached,
        "skipped_duplicate_item_ids": skipped_duplicate_item_ids,
        "skipped_missing_full_res": skipped_missing_full_res,
        "skipped_small_dimensions": skipped_small_dimensions,
        "image_download_errors": image_download_errors,
        "details_api_errors": details_api_errors,
        "raw_metadata_path": str(metadata_path),
        "raw_images_dir": str(images_dir),
        "retrieval_policy": downloader_cfg.get("retrieval_policy", {}),
        "retrieval_policy_enforcement": _policy_enforcement_summary(
            downloader_cfg.get("retrieval_policy", {})
        ),
        "skip_if_exists": skip_if_exists,
        "force_redownload": force_redownload,
        "error_message": error_message,
    }
    summary = {
        **summary,
        "output_dir": str(output_dir),
    }
    write_json(output_dir / "download_summary.json", summary)
    if status == "success":
        if failure_marker_path.exists():
            failure_marker_path.unlink()
        write_stage_success_marker(output_dir, summary)
    else:
        write_json(failure_marker_path, summary)
        print(f"[download] failed: {error_message}")
        if status == "interrupted":
            raise KeyboardInterrupt
        raise RuntimeError(error_message or "download stage failed")
    print(
        "[download] complete "
        f"pages={pages_fetched} items_written={items_written} "
        f"image_download_errors={image_download_errors}"
    )
    return summary


def _build_endpoint_url(base_url: str, endpoint_path: str) -> str:
    base = base_url.rstrip("/")
    path = endpoint_path.strip()
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def _read_field_mapping(downloader_cfg: dict[str, Any]) -> FieldMapping:
    fm = downloader_cfg.get("field_mapping", {})
    if fm is None:
        fm = {}
    if not isinstance(fm, dict):
        raise ValueError("downloader.field_mapping must be a mapping")
    return FieldMapping(
        id_field=str(fm.get("id_field", "id")),
        image_url_field=str(fm.get("image_url_field", "image_url")),
        license_field=str(fm.get("license_field", "license")),
        timestamp_field=str(fm.get("timestamp_field", "captured_at")),
        lat_field=str(fm.get("lat_field", "lat")),
        lon_field=str(fm.get("lon_field", "lon")),
    )


def _extract_items(response_json: Any, results_key: str) -> list[Any]:
    if isinstance(response_json, list):
        return response_json
    if not isinstance(response_json, dict):
        raise ValueError(f"Expected JSON object or array, got {type(response_json)!r}")
    if results_key and results_key in response_json:
        items = response_json.get(results_key)
        return items if isinstance(items, list) else []
    for fallback_key in ("items", "images", "results"):
        fallback_items = response_json.get(fallback_key)
        if isinstance(fallback_items, list):
            return fallback_items
    return []


def _redact_request_params(params: dict[str, Any], redacted_keys: set[str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in params.items():
        if key in redacted_keys:
            cleaned[key] = "***redacted***"
        else:
            cleaned[key] = str(value)
    return cleaned


def _validate_syndicator_query_keys(query: dict[str, Any]) -> None:
    invalid = sorted(key for key in query if key not in SUPPORTED_SYNDICATOR_QUERY_KEYS)
    if invalid:
        raise ValueError(
            "Unsupported syndicator query parameters: "
            f"{invalid}. Allowed keys: {sorted(SUPPORTED_SYNDICATOR_QUERY_KEYS)}"
        )


def _sanitize_query(query: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in query.items():
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            out[key] = text
            continue
        if isinstance(value, list):
            cleaned = [str(v).strip() for v in value if str(v).strip()]
            if not cleaned:
                continue
            out[key] = cleaned
            continue
        out[key] = value
    return out


def _policy_enforcement_summary(policy: Any) -> dict[str, str]:
    if not isinstance(policy, dict):
        return {"status": "not_configured"}
    return {
        "geographic_scope": "partially_enforced_via_query",
        "capture_year_range": "requires_saved_search_id_or_downstream_filter",
        "ground_level_only": "requires_saved_search_id_or_downstream_filter",
        "sampling_strategy": "requires_downstream_sampler",
        "class_balancing_strategy": "requires_post_lcm_stage",
    }


def _validate_saved_search_id_requirement(query: dict[str, Any], required: bool) -> None:
    if not required:
        return
    if not _extract_saved_search_ids(query):
        raise ValueError(
            "downloader.query.i (Geograph saved-search ID) is required for policy-constrained "
            "retrieval. Set it in config or pass --geograph-search-id."
        )


def _extract_saved_search_ids(query: dict[str, Any]) -> list[str]:
    raw = query.get("i")
    if raw is None:
        return []
    if isinstance(raw, list):
        ids = [str(v).strip() for v in raw if str(v).strip()]
    else:
        text = str(raw).strip()
        if not text:
            return []
        ids = [part.strip() for part in text.split(",") if part.strip()]
    # Preserve order while removing duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for item in ids:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _expand_saved_search_queries(query: dict[str, Any]) -> list[dict[str, Any]]:
    ids = _extract_saved_search_ids(query)
    if not ids:
        return [dict(query)]
    base_query = {k: v for k, v in query.items() if k != "i"}
    expanded = []
    for saved_search_id in ids:
        one = dict(base_query)
        one["i"] = saved_search_id
        expanded.append(one)
    return expanded


def _extract_item_id(item: dict[str, Any], field_mapping: FieldMapping) -> str | None:
    raw = item.get(field_mapping.id_field)
    if raw is None:
        return None
    text = str(raw).strip()
    return text if text else None


def _should_skip_item_for_capture_year(
    item: dict[str, Any], field_mapping: FieldMapping, downloader_cfg: dict[str, Any]
) -> bool:
    policy = downloader_cfg.get("retrieval_policy", {})
    if not isinstance(policy, dict):
        return False
    year_min_raw = policy.get("capture_year_min")
    year_max_raw = policy.get("capture_year_max")
    if year_min_raw is None and year_max_raw is None:
        return False
    capture_year = _extract_capture_year(item.get(field_mapping.timestamp_field))
    if capture_year is None:
        # If no year can be inferred, do not skip at downloader stage.
        return False
    if year_min_raw is not None and capture_year < int(year_min_raw):
        return True
    if year_max_raw is not None and capture_year > int(year_max_raw):
        return True
    return False


def _extract_capture_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        # Heuristic: large ints are usually unix timestamps.
        if value > 100_000:
            try:
                return datetime.fromtimestamp(value, tz=UTC).year
            except Exception:
                return None
        return value
    if isinstance(value, float):
        try:
            return datetime.fromtimestamp(value, tz=UTC).year
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
        if text.isdigit():
            try:
                return datetime.fromtimestamp(float(text), tz=UTC).year
            except Exception:
                return None
    return None


def _load_existing_metadata_by_id(metadata_path: Path) -> dict[str, dict[str, Any]]:
    if not metadata_path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    with metadata_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            item_id = payload.get("id")
            if item_id is None:
                continue
            records[str(item_id)] = payload
    return records


def _resolve_cached_record(
    item: dict[str, Any],
    field_mapping: FieldMapping,
    existing_records: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    item_id = item.get(field_mapping.id_field)
    if item_id is None:
        return None
    cached = existing_records.get(str(item_id))
    if cached is None:
        return None
    image_path = cached.get("image_path")
    if not image_path:
        return None
    if not Path(str(image_path)).exists():
        return None
    return cached


def _should_skip_item_for_license(
    item: dict[str, Any], field_mapping: FieldMapping, downloader_cfg: dict[str, Any]
) -> bool:
    allowed = downloader_cfg.get("allowed_licenses")
    if allowed is None:
        return False
    if not isinstance(allowed, list):
        raise ValueError("downloader.allowed_licenses must be a list when provided")

    normalized_allowed = {_normalize_license(v) for v in allowed if _normalize_license(v)}
    if not normalized_allowed:
        return False

    item_license = _normalize_license(item.get(field_mapping.license_field))
    return item_license not in normalized_allowed


def _normalize_license(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None,
    timeout_s: float,
    max_retries: int,
    retry_backoff_s: float,
    rate_limiter: RateLimiter,
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        rate_limiter.wait()
        try:
            response = session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                timeout=timeout_s,
            )
            if response.status_code >= 500:
                raise requests.HTTPError(f"Server error {response.status_code}", response=response)
            response.raise_for_status()
            ctype = response.headers.get("content-type", "")
            if "application/json" in ctype:
                return response.json()
            return response.content
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt >= max_retries:
                break
            time.sleep(retry_backoff_s * attempt)
    if last_exc is None:
        raise RuntimeError("Unknown request failure")
    raise last_exc


def _download_one_item(
    item: dict[str, Any],
    field_mapping: FieldMapping,
    session: requests.Session,
    headers: dict[str, str],
    timeout_s: float,
    max_retries: int,
    retry_backoff_s: float,
    rate_limiter: RateLimiter,
    images_dir: Path,
    endpoint_url: str,
    base_api_url: str,
    details_api_path_template: str,
    api_key: str,
    prefer_details_api_image_url: bool,
    details_api_fallback_to_feed_url: bool,
    pre_download_min_width: int | None,
    pre_download_min_height: int | None,
    request_params: dict[str, str],
) -> dict[str, Any]:
    item_id = item.get(field_mapping.id_field)
    image_url_raw = item.get(field_mapping.image_url_field)
    if item_id is None or not image_url_raw:
        raise ValueError("Item missing required id or image URL field")

    image_url = str(image_url_raw)
    image_url_source = "feed"
    details_image_width: int | None = None
    details_image_height: int | None = None
    if prefer_details_api_image_url:
        try:
            details_url = _build_endpoint_url(
                base_url=base_api_url,
                endpoint_path=details_api_path_template.format(photo_id=item_id, api_key=api_key),
            )
            details_payload = _request_with_retry(
                session=session,
                method="GET",
                url=details_url,
                headers=headers,
                params=None,
                timeout_s=timeout_s,
                max_retries=max_retries,
                retry_backoff_s=retry_backoff_s,
                rate_limiter=rate_limiter,
            )
            if isinstance(details_payload, (bytes, bytearray)):
                details_img = _extract_details_api_image_info(bytes(details_payload))
                image_url = details_img["src"]
                details_image_width = details_img["width"]
                details_image_height = details_img["height"]
                if _is_below_dimension_threshold(
                    width=details_image_width,
                    height=details_image_height,
                    min_width=pre_download_min_width,
                    min_height=pre_download_min_height,
                ):
                    raise ValueError("image_dimensions_below_minimum")
                image_url_source = "details_api"
            else:
                raise ValueError("Details API response is not XML bytes")
        except ValueError as exc:
            if str(exc) == "image_dimensions_below_minimum":
                raise
            if not details_api_fallback_to_feed_url:
                raise ValueError("missing_full_res_image_url")
            image_url_source = "feed_fallback"
        except Exception:
            if not details_api_fallback_to_feed_url:
                raise ValueError("missing_full_res_image_url")
            image_url_source = "feed_fallback"

    image_bytes = _request_with_retry(
        session=session,
        method="GET",
        url=image_url,
        headers=headers,
        params=None,
        timeout_s=timeout_s,
        max_retries=max_retries,
        retry_backoff_s=retry_backoff_s,
        rate_limiter=rate_limiter,
    )
    if not isinstance(image_bytes, (bytes, bytearray)):
        raise ValueError("Expected binary image payload")

    image_sha256 = hashlib.sha256(image_bytes).hexdigest()
    ext = _extension_from_url(image_url)
    image_path = images_dir / f"{item_id}{ext}"
    with image_path.open("wb") as fh:
        fh.write(image_bytes)

    license_value = item.get(field_mapping.license_field)
    timestamp = item.get(field_mapping.timestamp_field)
    lat = item.get(field_mapping.lat_field)
    lon = item.get(field_mapping.lon_field)

    return {
        "id": str(item_id),
        "image_path": str(image_path),
        "image_url": image_url,
        "image_url_source": image_url_source,
        "details_image_width": details_image_width,
        "details_image_height": details_image_height,
        "sha256": image_sha256,
        "timestamp": timestamp,
        "lat": lat,
        "lon": lon,
        "license": license_value,
        "fetched_at": utc_now_iso(),
        "provenance": {
            "source": "geograph_api",
            "endpoint_url": endpoint_url,
            "request_params": request_params,
            "details_api_preferred": prefer_details_api_image_url,
        },
        "raw_item": item,
    }


def _extension_from_url(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg"


def _make_progress(total: int, show_progress: bool) -> ProgressLike:
    if not show_progress or tqdm is None:
        return _NoopProgress()
    return _TqdmProgress(tqdm(total=total, desc="download", unit="img"))


def _extract_details_api_image_info(xml_bytes: bytes) -> dict[str, int | str | None]:
    root = ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))
    img = root.find(".//img")
    if img is None:
        raise ValueError("No <img> node in details API XML")
    src = img.attrib.get("src")
    if not src:
        raise ValueError("Missing src attribute on <img> in details API XML")
    return {
        "src": src,
        "width": _to_optional_int(img.attrib.get("width")),
        "height": _to_optional_int(img.attrib.get("height")),
    }


def _is_below_dimension_threshold(
    width: int | None,
    height: int | None,
    min_width: int | None,
    min_height: int | None,
) -> bool:
    if min_width is not None and width is not None and width < min_width:
        return True
    if min_height is not None and height is not None and height < min_height:
        return True
    return False


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except Exception:
        return None


def _resolve_user_agent(geograph_cfg: dict[str, Any]) -> str:
    configured_version = str(geograph_cfg.get("version", "")).strip()
    if configured_version:
        return f"geograph-lcm/{configured_version}"

    # Backward compatibility for older config key.
    legacy_user_agent = str(geograph_cfg.get("user_agent", "")).strip()
    if legacy_user_agent:
        return legacy_user_agent

    runtime_version = _runtime_package_version() or "unknown"
    return f"geograph-lcm/{runtime_version}"


def _runtime_package_version() -> str | None:
    for package_name in ("geograph-lcm", "geograph_lcm"):
        try:
            return pkg_version(package_name)
        except PackageNotFoundError:
            continue
        except Exception:
            return None
    return None
