# Test Definition

A Test Definition declares what should be executed.

Runs reference an immutable Test Definition revision. Editing a definition creates a new revision rather than changing the meaning of an existing run.

It contains:

- immutable definition and revision identities;
- an artifact reference;
- a schema-referenced opaque execution configuration;
- separately schema-referenced opaque SUT inputs.

Symbols, timeframes, date ranges, tester settings, provider options, and EA inputs may appear inside the appropriate external contract. They are not core Test Definition fields and are not interpreted by the platform core.

A Test Definition is not a strategy definition.
