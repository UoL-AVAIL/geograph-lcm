# RUNBOOK

Operational guide for running and troubleshooting the `geograph-lcm` pipeline.

## Environment setup

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e ".[dev,geo]"
```

## Core commands

Full run through validation:

```bash
geograph-lcm --from-stage download --to-stage validate --config config/default.yaml --geograph-api-key <YOUR_KEY>
```

Run a single stage:

```bash
geograph-lcm --from-stage match_lcm --to-stage match_lcm --config config/default.yaml
```

## Stage outputs

- `outputs/download/raw/metadata.jsonl`
- `outputs/ingest/ingested_manifest.jsonl`
- `outputs/curate/curated_manifest.jsonl`
- `outputs/georeference/georeferenced_manifest.jsonl`
- `outputs/match_lcm/matched_manifest.jsonl`
- `outputs/dataset/labels.csv`
- `outputs/validation/report.yaml`

## Resume behavior

Each stage writes `_SUCCESS.json`. If present, the orchestrator skips that stage.

To rerun completed stages, use `--force`:

```bash
geograph-lcm --from-stage match_lcm --to-stage match_lcm --config config/default.yaml --force
```

## Common failures and fixes

Missing Geograph API key:
- Symptom: download stage fails with missing key message.
- Fix: pass `--geograph-api-key` or set `GEOGRAPH_API_KEY`.

LCM checksum mismatch:
- Symptom: `match_lcm` fails preflight.
- Fix: verify file path and hash in `config/lcm_catalog.yaml`.

Raster sampling dependency error:
- Symptom: `Raster sampling requires rasterio`.
- Fix: install geo extras: `pip install -e ".[dev,geo]"`.

No dataset rows written:
- Symptom: `labels.csv` has only header.
- Fix: inspect `outputs/match_lcm/matched_manifest.jsonl` and `lcm_match_status`.

## Data handling guardrails

- Keep `data/` and `outputs/` untracked in git.
- Do not commit raw imagery or large raster files.
- Keep API keys out of config and source control.
