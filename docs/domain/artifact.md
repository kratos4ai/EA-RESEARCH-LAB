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

An Artifact must never be silently replaced under the same identity.
