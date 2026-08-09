# Analysis

An Analysis is a versioned computation over a run or dataset.

Minimum metadata:

- analysis ID
- analysis definition
- analysis version
- algorithm/code revision
- analysis parameters
- input dataset(s)
- execution timestamp
- computation environment identity
- output schema version
- result identity
- provenance

Changing an analysis algorithm creates a new analysis version; it must not rewrite historical raw evidence.
