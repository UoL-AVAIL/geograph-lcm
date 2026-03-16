# TASKS

Progress tracker for `geograph-lcm`.

## Milestone 0: Repository Foundation

- [x] Create project scaffold (`src/`, `tests/`, `config/`, `run_pipeline.py`)
- [x] Add Python packaging/tooling (`pyproject.toml`)
- [x] Add baseline docs (`README.md`, `PIPELINE.md`)
- [x] Add test harness and smoke tests
- [x] Add `.venv` setup and verify tests pass locally

## Milestone 1: Pipeline Skeleton and Contracts

- [x] Define stage modules with `run(config, input_dir, output_dir)` signatures
- [x] Add orchestrator with `--from-stage`, `--to-stage`
- [x] Add stage resume markers (`_SUCCESS.json`)
- [x] Add run manifest (`outputs/pipeline_run.json`)
- [x] Add structured event log (`outputs/pipeline_events.jsonl`)

## Milestone 2: LCM Catalog and Year Selection Policy

- [x] Add `config/lcm_catalog.yaml` with 2015-2024 slots
- [x] Record per-year `resolution_m` metadata
- [x] Implement policy:
  - [x] exact capture year
  - [x] nearest available year fallback
  - [x] tie-break to earlier year
  - [x] no capture year -> latest available year
- [x] Add unit tests for selection policy

## Milestone 3: Downloader v1

- [x] Implement Geograph API client (official API only)
- [x] Load API key from env (`GEOGRAPH_API_KEY`)
- [x] Add pagination, rate limiting, and retry logic
- [x] Write raw outputs:
  - [x] `outputs/download/raw/metadata.jsonl`
  - [x] `outputs/download/raw/images/<id>.jpg`
  - [x] `outputs/download/download_summary.json`
- [x] Record per-item provenance (endpoint, params, timestamp, checksum, license fields)
- [x] Add fixture-based tests with mocked API responses
- [x] Validate deterministic stage outputs for resume
- [x] Add details-API high-resolution image resolution (strict mode)
- [x] Add pre-download year filtering (2015-2024 policy gate)
- [x] Add pre-download license filtering allowlist
- [x] Add cache-aware skip to prevent redundant image downloads
- [x] Add interrupted/failed run summaries and progress bar support

## Milestone 4: Ingest and Curation

- [x] Implement metadata normalization manifest (`ingested_manifest.jsonl`)
- [x] Implement quality filtering (size/blur/etc.)
- [x] Implement license compatibility filtering
- [x] Implement deduplication
- [x] Produce curated manifest contract for downstream stages
- [x] Define and document production Geograph saved-search ID support (`query.i`) for policy-constrained retrieval (single, comma-separated, or YAML list)

## Milestone 5: Georeference + LCM Matching

- [x] Implement georeference confidence and provenance fields
- [x] Implement LCM spatial matching with per-year raster metadata
- [x] Record label provenance (`selected_lcm_year`, `lcm_resolution_m`, match method)
- [x] Add tests with tiny geospatial fixtures

## Milestone 6: Dataset Writer + Validation

- [x] Write dataset files (`dataset/images`, `dataset/labels.csv`, `dataset/README.md`)
- [x] Emit `validation/report.yaml`
- [x] Add schema checks for required label columns
- [x] Add sampling/report metrics for human review

## Milestone 7: CI and Hardening

- [x] Add CI pipeline (lint, type-check, tests)
- [x] Ensure CI runs only tiny fixtures (no raw images)
- [x] Add runbook for reproducible runs and resume behavior
- [x] Add policy checks for licensing/ethics constraints
- [x] Add CLI `--output-dir` override for pipeline outputs

## Milestone 8: Inspection and Visualization

- [x] Add in-depth dataset inspection notebook
- [x] Add interactive Bokeh map explorer for `labels.csv`
- [x] Add map-viewer unit tests
