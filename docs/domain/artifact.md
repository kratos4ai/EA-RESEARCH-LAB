# Artifact

An Artifact is an immutable compiled SUT executable.

Minimum identity:

- `artifact_id`
- logical name
- artifact version
- source revision and content identity
- build record reference
- binary hash
- compiler identity
- build timestamp
- build status

An Artifact must never be silently replaced under the same identity.
