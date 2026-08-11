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

The application boundary finalizes the execution lifecycle and seals the
terminal evidence collection outcome in memory. A completed execution may
therefore reference a manifest whose independent collection outcome is
`collection_failed`. Provider verdicts remain observations and never finalize
the Run directly.

Invalid requests fail before admission and create no finalized Run. After a
valid request enters `execute_run`, a provider exception is a terminal attempt:
the application records a safe failure, seals an empty `collection_failed`
manifest when no captured bytes reached the application, and finalizes the Run
as `failed` (`cancelled` for an explicit timeout). It does not manufacture a
provider observation. Evidence already accepted by the application remains in
the sealed manifest if later collection fails.

The external digest in `RawEvidenceManifestRef` identifies the exact
`raw-evidence-manifest/0.1.0` document serialized with JSON `ensure_ascii=False`,
keys sorted lexicographically, separators `(',', ':')`, non-finite numbers
rejected, and the resulting text encoded as UTF-8. The digest is SHA-256 over
those bytes. It is not a digest over a storage representation or location.
