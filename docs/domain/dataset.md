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
- SHA-256 of the exact canonical dataset-content bytes
- provenance

Entity identity remains distinct from content identity. Dataset content uses
canonical UTF-8 JSON with sorted keys and compact separators; independently
allocated Dataset IDs and creation timestamps do not change those bytes.

`dataset-manifest/0.2.0` records the exact content digest together with the
input and transformation provenance. `dataset-manifest/0.1.0` remains an
unchanged supported historical contract but does not bind Dataset content.
Neither version defines storage layout or analytical formulas.
