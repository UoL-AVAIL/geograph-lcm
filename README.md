# geograph-lcm

Build a labeled dataset of Geograph ground-level images matched to UKCEH Land Cover Map (LCM) labels.

## Tracking

Implementation progress is tracked in `TASKS.md`.
Operational guidance is in `docs/RUNBOOK.md`.

## Current status

This repository includes:

- stage modules and a thin orchestrator (`run_pipeline.py`);
- config files for pipeline settings and multi-year LCM catalog (`2015-2024`);
- LCM year selection policy:
  - exact capture year when available;
  - nearest available year when not available;
  - tie-break to earlier year;
  - fallback to latest available year if capture year is missing;
- JSON run manifest and stage success markers for resume behavior;
- a working Geograph downloader with:
  - `syndicator.php` paging + retry/rate limiting;
  - optional CLI API key (`--geograph-api-key`);
  - optional saved search ID (`--geograph-search-id` or `downloader.query.i`);
  - strict full-res image resolution via details API (no thumb fallback by default);
  - capture-year and license filtering before image download;
  - cache-aware skip of already downloaded items;
  - interrupted/failed run summaries and `tqdm` progress bar support.

## Constraints

- Geograph ingestion must use the official Geograph Image APIs only.
- API credentials can be passed with `--geograph-api-key` or loaded from `GEOGRAPH_API_KEY`.
- LCM files are expected under `data/lcm/<year>/...` and tracked in `config/lcm_catalog.yaml`.
- LCM taxonomy mappings are versioned in `config/lcm_taxonomy.yaml`.
- Downloader uses Geograph `syndicator.php` query semantics. Saved search ID is recommended via `downloader.query.i`.
- Full-resolution download is details-API-first; items without full-res URL are skipped by default.

## Quickstart

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e ".[dev]"
python run_pipeline.py --from-stage download --to-stage download --config config/default.yaml --geograph-api-key <YOUR_KEY>
```

Pipeline outputs are written under `outputs/` including:

- `outputs/pipeline_run.json`
- `outputs/pipeline_events.jsonl`
- `outputs/<stage>/_SUCCESS.json`

## Basic EDA

Generate baseline exploratory charts from `labels.csv`:

```bash
python notebooks/eda_labels.py --labels outputs/dataset/labels.csv --out-dir outputs/validation/eda
```
