Got it.

# PIPELINE.md

This document defines a straightforward pipeline for the `geograph-lcm` repository. It is written for a single-user or small-team workflow (scripts and modules called from a simple CLI or Makefile). Each step is implemented as a well-tested Python module with a clear public API; orchestration is procedural (one command to run the full pipeline or to resume from a stage).

## Purpose

Produce a labelled dataset of Geograph (https://www.geograph.org.uk/) ground-level images joined to the UKCEH Land Cover Map (LCM). The pipeline emphasises reproducibility, provenance and modularity: simple scripts, functions and a thin orchestrator.

## High-level stages

1. Download — fetch images and provider metadata into a raw cache.
2. Ingest — normalise metadata and extract EXIF (timestamps, GPS).
3. Curate — filter and de-duplicate images by quality and licence.
4. Georeference — ensure reliable lat/lon for each image, record provenance.
5. Match to LCM — spatially join points to LCM pixels/polygons and assign labels.
6. Write dataset — export ready-to-train artefacts (images, labels, manifests).
7. Validate — automated checks, metrics and sampling for human review.
8. Runbook/CI — tests, small-fixture CI, and a reproducible run manifest for each pipeline execution.

Implement each stage as a Python module under with a public `run(...)` function and a simple CLI wrapper.

## Proposed repository layout (single-file focus)

```
geograph-lcm/
├─ src/                    # procedural modules with run(...) functions
│  ├─ downloader.py
│  ├─ ingestor.py
│  ├─ curator.py
│  ├─ georeferencer.py
│  ├─ lcm_matcher.py
│  ├─ dataset_writer.py
│  └─ validator.py
├─ run_pipeline.py            # thin orchestrator: --from-stage, --to-stage
├─ config/default.yaml
├─ tests/                     # unit tests with small fixtures
├─ notebooks/                 # exploratory analysis and examples
├─ data/                      # gitignored: small fixtures allowed
└─ README.md
```

## Implementation guidelines

Use standard libraries and well-supported geospatial packages (requests, rasterio, geopandas, shapely, pyproj). Prefer simple, auditable code over clever heuristics. Each module must:

* accept a `config` object (loaded from `config/default.yaml`) and input/output directory paths;
* write explicit provenance metadata for every output (timestamps, source URLs, checksums, LCM version);
* include unit tests exercising core behaviours with small fixtures;
* log structured JSON lines for pipeline-run auditing.

## Minimal CLI / orchestrator behaviour

`python run_pipeline.py --from-stage download --to-stage write_dataset --config config/default.yaml`

The orchestrator should:

* create a `pipeline_run.json` recording stage start/stop times, git commit, and environment;
* support resume by checking for stage outputs and skipping completed stages;
* allow single-stage invocation for iterative development.

## Key design decisions (rationale)

* Non-agentic: simpler integration with CI, fewer moving parts and predictable execution semantics for reproducible research.
* Provenance-first: every mapping decision must be auditable (why a particular LCM label was assigned).
* Conservative georeferencing: if coordinates are uncertain, record low confidence rather than inventing values.
* Licence-aware curation: surface licence per image and exclude or flag images incompatible with intended model use.

## Example yaml structure

```yaml
downloader:
  id: "geograph-lcm/0.1 (+mailto:your.email@example.com)"
  max_per_minute: 60

curator:
  min_width: 800
  min_height: 600
  blur_threshold: 100.0

georeferencer:
  max_georef_radius_m: 50

lcm:
  path: "/data/lcm/lcm_2020.tif"
  projection: "EPSG:27700"
```

## Outputs

Final dataset layout (examples):

* `dataset/images/<id>.jpg`
* `dataset/labels.csv` — columns: `id,image_path,lat,lon,lcm_l2,lcm_l3,timestamp,license,sha256,georef_confidence`
* `dataset/README.md` — description and LCM version used
* `validation/report.yaml` — automated checks and sampling pointers
* `pipeline_run.json` — exact command, timestamps and provenance for the run

## Ethics and licensing

Record licence metadata per image and fail-fast if a chosen export would violate licence terms. Provide options to blur faces or exclude identifiable people as required by institutional policy.

## Tests and CI

Include unit tests for each module using tiny fixtures (no real images in CI). CI runs linting (black/flake8), mypy and tests. Do not store raw images in the repo or CI artifacts.

## Next steps (practical immediate tasks)

1. scaffold repo and `config/default.yaml`; commit to git.
2. implement `src/downloader.py` with unit tests and a tiny fixture.
3. implement `src/ingestor.py` and `src/curator.py` to produce a curated manifest for 10 sample images.
4. add a minimal `run_pipeline.py` orchestrator and test the end-to-end flow on fixtures.
