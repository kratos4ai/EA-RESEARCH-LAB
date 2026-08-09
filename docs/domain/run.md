# Run

A Run is one concrete execution of one immutable Test Definition revision with one immutable Artifact under a captured environment/configuration.

A Run owns:

- `run_id`
- test-definition revision reference
- artifact reference
- configuration snapshot/hash
- lifecycle/status
- start/end timestamps
- execution environment
- sealed raw evidence manifest reference and prior manifest revisions where applicable
- derived data references
- analysis references
- reproducibility level and reasons

Run lifecycle status may advance, and raw objects may be appended during active collection. Persisted raw objects and sealed evidence manifests are immutable. Late evidence creates a new linked manifest revision rather than altering historical evidence.
