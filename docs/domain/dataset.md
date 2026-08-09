# Dataset

A Dataset is a versioned collection of data produced from one or more runs.

Datasets may represent normalized, enriched, aggregated, or research-ready data.

Dataset identity must include:

- `dataset_id`
- input sealed evidence manifest(s) and/or dataset(s)
- transformation version
- transformation parameters where applicable
- creation timestamp
- exact dataset-content schema reference
- provenance

The Dataset Manifest records these provenance links directly. It does not define storage layout or analytical formulas.
