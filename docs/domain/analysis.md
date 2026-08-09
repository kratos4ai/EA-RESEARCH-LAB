# Analysis

An Analysis is a versioned computation over one or more datasets.

Minimum metadata for an Analysis Result:

- result identity
- analysis definition identity
- analysis version
- analysis parameters
- input dataset(s)
- execution timestamp
- computation environment identity
- exact result-content schema reference
- provenance

The analysis definition/version identifies the computation, including its algorithm or code revision according to that definition's own versioning policy. Parameters and result content remain schema-referenced; the core result contract does not define formulas or metric catalogs.

Changing an analysis algorithm creates a new analysis version; it must not rewrite historical raw evidence.
