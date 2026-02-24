# geograph-lcm

Build a labeled dataset of Geograph ground-level images matched to UKCEH Land Cover Map (LCM) labels.

## Tracking

Implementation progress is tracked in `TASKS.md`.

## Current status

This repository is scaffolded with:

- stage modules and a thin orchestrator (`run_pipeline.py`);
- config files for pipeline settings and multi-year LCM catalog (`2015-2024`);
- LCM year selection policy:
  - exact capture year when available;
  - nearest available year when not available;
  - tie-break to earlier year;
  - fallback to latest available year if capture year is missing;
- JSON run manifest and stage success markers for resume behavior.

Stage logic is currently stubbed and writes auditable summaries. Full Geograph API calls, EXIF ingest, spatial matching, and dataset export logic are the next implementation steps.

## Constraints

- Geograph ingestion must use the official Geograph Image APIs only.
- API credentials are loaded from environment variable `GEOGRAPH_API_KEY` by default.
- LCM files are expected under `data/lcm/<year>/...` and tracked in `config/lcm_catalog.yaml`.

## Quickstart

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e ".[dev]"
python run_pipeline.py --from-stage download --to-stage validate --config config/default.yaml
```

Pipeline outputs are written under `outputs/` including:

- `outputs/pipeline_run.json`
- `outputs/pipeline_events.jsonl`
- `outputs/<stage>/_SUCCESS.json`
