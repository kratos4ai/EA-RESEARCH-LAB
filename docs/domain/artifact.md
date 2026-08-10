# Artifact

An Artifact is an immutable compiled SUT executable.

Minimum identity:

- `artifact_id`
- logical name
- artifact version
- source revision
- build record reference
- binary SHA-256 content identity
- compiler identity
- build timestamp

Compiler details are carried through a namespaced, schema-referenced opaque payload. Provider-specific compiler fields do not become Artifact vocabulary.

The referenced Build Record owns the build outcome. An Artifact Manifest exists only for a successfully produced immutable artifact; failed attempts remain Build Records without an artifact identity.

Build Record `0.2.0` also owns the content-addressed Build Input Manifest reference. Artifact Manifest `0.1.0` continues to reference the Build Record and does not duplicate Build Input Identity. Reproducibility is assessed separately from these immutable build and artifact facts.

An Artifact must never be silently replaced under the same identity.
