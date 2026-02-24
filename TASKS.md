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

## Milestone 3: Downloader v1 (Next Slice)

- [ ] Implement Geograph API client (official API only)
- [ ] Load API key from env (`GEOGRAPH_API_KEY`)
- [ ] Add pagination, rate limiting, and retry logic
- [ ] Write raw outputs:
  - [ ] `outputs/download/raw/metadata.jsonl`
  - [ ] `outputs/download/raw/images/<id>.jpg`
  - [ ] `outputs/download/download_summary.json`
- [ ] Record per-item provenance (endpoint, params, timestamp, checksum, license fields)
- [ ] Add fixture-based tests with mocked API responses
- [ ] Validate deterministic stage outputs for resume

## Milestone 4: Ingest and Curation

- [ ] Implement EXIF + metadata normalization
- [ ] Implement quality filtering (size/blur/etc.)
- [ ] Implement license compatibility filtering
- [ ] Implement deduplication
- [ ] Produce curated manifest contract for downstream stages

## Milestone 5: Georeference + LCM Matching

- [ ] Implement georeference confidence and provenance fields
- [ ] Implement LCM spatial matching with per-year raster metadata
- [ ] Record label provenance (`selected_lcm_year`, `lcm_resolution_m`, match method)
- [ ] Add tests with tiny geospatial fixtures

## Milestone 6: Dataset Writer + Validation

- [ ] Write dataset files (`dataset/images`, `dataset/labels.csv`, `dataset/README.md`)
- [ ] Emit `validation/report.yaml`
- [ ] Add schema checks for required label columns
- [ ] Add sampling/report metrics for human review

## Milestone 7: CI and Hardening

- [ ] Add CI pipeline (lint, type-check, tests)
- [ ] Ensure CI runs only tiny fixtures (no raw images)
- [ ] Add runbook for reproducible runs and resume behavior
- [ ] Add policy checks for licensing/ethics constraints

