# RUNBOOK

Operational guide for running and troubleshooting the `geograph-lcm` pipeline.

## Environment setup

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e ".[dev,geo]"
```

For the interactive map explorer, install viz extras:

```bash
pip install -e ".[dev,viz]"
```

## Core commands

Full run through validation:

```bash
geograph-lcm --from-stage download --to-stage validate --config config/default.yaml --geograph-api-key <YOUR_KEY>
```

Full run with a custom output directory:

```bash
geograph-lcm --from-stage download --to-stage validate --config config/default.yaml --geograph-api-key <YOUR_KEY> --output-dir /path/to/my-run
```

Run a single stage:

```bash
geograph-lcm --from-stage match_lcm --to-stage match_lcm --config config/default.yaml
```

## Saved-search IDs (`query.i`)

Use Geograph saved-search IDs to lock policy-constrained retrieval.

In `config/default.yaml`:

```yaml
downloader:
	query:
		i: "215369747,215369748"
```

You can also provide IDs as a YAML list:

```yaml
downloader:
	query:
		i:
			- "215369747"
			- "215369748"
```

CLI override (comma-separated IDs supported):

```bash
geograph-lcm --from-stage download --to-stage download --config config/default.yaml --geograph-search-id 215369747,215369748
```

## Stage outputs

Default root is `outputs/`. If `--output-dir` is set, replace `outputs/` below with that path.

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

## Label-noise mitigation workflow

To recompute noise metrics for an existing dataset, rerun from `match_lcm` through `validate`:

```bash
geograph-lcm --from-stage match_lcm --to-stage validate --config config/default.yaml --force
```

If using a custom output root:

```bash
geograph-lcm --from-stage match_lcm --to-stage validate --config config/default.yaml --output-dir /path/to/my-run --force
```

### Before/after threshold comparison

1. Save the current validation report:

```bash
cp outputs/validation/report.yaml outputs/validation/report.before.yaml
```

2. Adjust thresholds in `config/default.yaml`:
	- `lcm.noise.min_label_confidence`
	- `validator.label_noise.min_window_agreement`
	- `validator.label_noise.min_label_confidence`

3. Rerun validation path:

```bash
geograph-lcm --from-stage match_lcm --to-stage validate --config config/default.yaml --force
```

4. Compare these fields in `outputs/validation/report.yaml`:
	- `checks.label_noise.below_threshold_count`
	- `metrics.lcm_label_confidence`
	- `metrics.lcm_window_agreement`

### How to interpret new label-noise fields

- `lcm_window_agreement`: fraction of neighborhood pixels that agree with the majority class around the sampled point.
- `lcm_label_confidence`: composite confidence score from neighborhood agreement and georeference confidence.
- `lcm_low_confidence`: boolean flag set when `lcm_label_confidence` is below configured threshold.

Default tuning intent:

- Keep `enforce_thresholds: false` first to observe warning counts.
- Tighten thresholds once per-class sampling looks stable.
- Switch `enforce_thresholds: true` only after warning counts are acceptable for your target dataset size.

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

## Interactive map inspection

Use the Bokeh app to inspect all points on a UK map, colored by `lcm_l3`, with click-to-preview image:

```bash
bokeh serve apps/lcm_map_bokeh.py --show --args --labels outputs/dataset/labels.csv
```

Optional page title:

```bash
bokeh serve apps/lcm_map_bokeh.py --show --args --labels outputs/dataset/labels.csv --title "My LCM Explorer"
```

If `labels.csv` is under a custom output root, point `--labels` at that file directly.
