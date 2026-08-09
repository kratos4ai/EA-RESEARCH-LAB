# Run

A Run is one concrete execution of one immutable Test Definition revision with one immutable Artifact under a captured environment/configuration.

A Run owns:

- `run_id`
- test-definition revision reference
- artifact reference
- identified, schema-referenced environment/configuration snapshot
- lifecycle/status
- start/end timestamps
- execution environment
- sealed raw evidence manifest reference and prior manifest revisions where applicable
- derived data references
- analysis references
- reproducibility level and reasons

The Run Manifest may reference a sealed raw evidence manifest by manifest identity, run identity, and an external SHA-256 digest. It does not embed a storage path or mutate the sealed evidence set.

Run status describes execution lifecycle only. Evidence collection, persistence, and analysis have independent lifecycles; for example, a completed Run may have an evidence collection failure without acquiring another Run status.

Run lifecycle status may advance, and raw objects may be appended during active collection. Persisted raw objects and sealed evidence manifests are immutable. Late evidence creates a new linked manifest revision rather than altering historical evidence.
