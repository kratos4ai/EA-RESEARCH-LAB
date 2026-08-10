# Phase 02 — Build & Artifact Pipeline Execution Plan

- Status: M6 closure verification; M0-M5 completed; Phase 02 completion pending owner approval and a clean checkpoint
- Scope: Phase 02 only
- Baseline: contract checkpoint `4182552a9852552f24f6e3a0960c478a739ef7cf`
- Runtime baseline: Python `>=3.14,<3.15`

## 1. Objective

Implement the minimum reliable Build and Artifact Pipeline:

```text
declared source/workspace inputs
-> exclusive materialized build workspace
-> Build Input Manifest 0.1.0
-> BuildProvider
-> MetaEditor adapter
-> current-build candidate EX5
-> candidate validation and exact-byte SHA-256
-> accepted immutable Artifact value
-> Build Record 0.2.0
```

The phase must establish which declared source bytes were compiled, which build attempt produced an accepted EX5, and which content identity belongs to that accepted binary. It must not introduce execution, persistence, API, analysis, or presentation capabilities.

## 2. Governing decisions and evidence

Implementation must conform to:

- ADR-0001: the EA remains an opaque System Under Test;
- ADR-0006: MetaEditor is isolated behind `BuildProvider`;
- ADR-0007: source, build, and Artifact provenance remain connected without overstating reproducibility;
- ADR-0008: exact released schema versions are immutable and resolved locally;
- ADR-0009: typed UUIDv7 entity identity remains distinct from SHA-256 content identity;
- ADR-0010: Git cleanliness does not prove build bytes, builds use an exclusive materialized workspace, and candidate existence alone does not establish success;
- `build-input-manifest/0.1.0`, `build-record/0.2.0`, and `artifact-manifest/0.1.0`;
- the controlled MetaEditor P01–P16 observations, with their provider/version limitations.

Provider observations are evidence for the initial adapter, not generic Build semantics. In particular, exit codes `0` and `1`, UTF-16LE logs, Windows command-line grammar, adjacent output, and MetaEditor diagnostics must remain inside the adapter.

## 3. Scope boundaries

### In scope

- a narrow provider-neutral `BuildProvider` application port;
- immutable build request/result values required by the use case;
- exact declared source input materialization;
- an exclusive build workspace with safe cleanup;
- Build Input Manifest creation and validation;
- one MetaEditor adapter for the empirically observed compile mode;
- bounded provider-specific configuration and evidence;
- candidate EX5 attribution, validation, exact-byte hashing, and acceptance;
- Build Record 0.2.0 and Artifact Manifest 0.1.0 finalization;
- deterministic unit tests and controlled MetaEditor integration tests;
- architecture enforcement and directly affected documentation.

### Explicitly out of scope

- Strategy Tester and `ExecutionProvider`;
- trading or Run execution;
- Data Plane persistence, databases, repositories, or durable Artifact storage;
- source archive or snapshot retention infrastructure;
- generic subprocess/process-runner framework;
- generic workflow engine, scheduler, queue, or distributed worker;
- Platform API, transports, CLI, MCP, UI, Semantic Layer, or Analysis Plane;
- MQL dependency parser or include graph;
- universal compiler diagnostic taxonomy;
- deterministic EX5 claims or build reproducibility assessment;
- Phase 03 or later scaffolding.

## 4. Phase 01 foundations to reuse

Phase 02 must reuse rather than duplicate:

| Foundation | Phase 02 use |
|---|---|
| `BuildRecordId`, `ArtifactId`, `EnvironmentConfigurationId` | Build, Artifact, and effective configuration entity identity |
| `new_entity_id()` | ID allocation at the application boundary |
| `Sha256Digest` | Source member, Build Input, executable, log, and Artifact content identity |
| `SourceRevision` | Source-history context, including dirty state |
| `SchemaRef` and `SchemaReferencedPayload` | Build configuration and provider evidence envelopes |
| `RequestContext` | Explicit correlation through the application workflow |
| `ApplicationError` and stable error codes | Safe failures without provider-native leakage |
| `Settings` conventions | Explicit immutable configuration with no import-time side effects |
| operational logging | Bounded lifecycle events without source, EX5, log, or diagnostic payloads |
| contract catalog and validators | Exact schema selection, local resolution, and semantic Build Input validation |

No second identity, hashing, context, error, configuration, logging, or schema-validation mechanism may be introduced.

## 5. Minimal package and file layout

No new top-level Python package is planned. The existing package boundaries remain:

```text
src/ea_research_lab/
  domain/
    build.py                  # provider-neutral immutable build/Artifact values
  application/
    build.py                  # BuildProvider port and build use-case orchestration
  infrastructure/
    build_workspace.py       # safe exclusive materialization and cleanup
    metaeditor.py            # MetaEditor-only invocation, parsing, and evidence
    artifact.py              # candidate containment/read/hash acceptance adapter
    config.py                # only consumed Phase 02 settings
    logging.py               # BuildRecordId correlation only
  contracts/
    catalog.py               # exact provider extension registrations if released
    validation.py            # reuse; change only for a demonstrated semantic invariant

schemas/
  metaeditor-build-configuration/
    v0.1.0.schema.json       # original provider configuration contract
    v0.2.0.schema.json       # configuration with logical external-root mappings
  metaeditor-build-evidence/
    v0.1.0.schema.json       # provider-namespaced bounded invocation evidence

tests/
  test_build_domain.py
  test_build_application.py
  test_build_workspace.py
  test_metaeditor.py
  test_artifact_acceptance.py
  test_build_workflow.py
  integration/
    test_metaeditor_build.py
  fixtures/metaeditor/
    valid.mq5
    invalid.mq5
    local_include.mq5
    include/*.mqh
```

The provider extension schemas are limited to the two exact configuration versions and one evidence version listed above. They are justified because existing `SchemaReferencedPayload` values require exact schema identities for real MetaEditor configuration and evidence. They remain pre-stable and provider-namespaced and do not alter any core schema.

Test fixture sources must be minimal, strategy-neutral, and compiled only after copying into a disposable workspace. No `.ex5`, provider log, machine path, or real project EA source enters Git.

## 6. Responsibility and dependency rules

### Domain

`domain/build.py` owns only provider-neutral immutable values such as:

- public `BuildOutcome`: `succeeded` or `failed` only;
- a Build Input reference containing its exact schema reference and SHA-256 identity;
- accepted Artifact content and identity represented without a storage location;
- final provider-neutral build result facts.

It must not import `pathlib`, `subprocess`, contracts, infrastructure, MetaEditor types, or third-party packages. It must not contain Windows paths, exit codes, log encodings, compiler diagnostics, or process states.

### Application

`application/build.py` owns:

- the narrow `BuildProvider` port required by ADR-0006;
- immutable source declaration, provider request, provider result, and use-case result records;
- orchestration policy and transition to public `succeeded`/`failed`;
- ID allocation, request-context propagation, and safe error mapping;
- construction and exact validation of Build Input, Build Record, and Artifact Manifest documents.

Physical `Path` values may exist only as ephemeral operational inputs to materialization/provider ports. They never enter domain identity, serialized core contracts, logs, or returned provenance documents.

The provider result does not define public Build success. It returns bounded observed facts, optional current-workspace candidate location, and schema-referenced provider evidence. The application declares success only after candidate acceptance.

### Infrastructure

`build_workspace.py` owns filesystem isolation and exact-byte materialization. `metaeditor.py` owns all MetaEditor and Windows process behavior. `artifact.py` owns safe reading of a candidate from the exclusive workspace. Infrastructure may depend inward on application/domain types; domain and application must never import an infrastructure implementation.

### Contracts

Existing core schemas remain immutable. Provider-specific extension schemas validate only their own namespaced payloads. They cannot add MetaEditor vocabulary to Build Input Manifest, Build Record, Artifact Manifest, or common definitions.

## 7. End-to-end behavior

The final application workflow must execute this order:

1. Validate the provider-neutral build request and effective configuration.
2. Use the request's allocated `BuildRecordId`; do not allocate `ArtifactId` yet.
3. Create a new exclusive workspace beneath an explicitly configured workspace root.
4. Materialize only the declared primary and dependencies using their normalized logical locations and exact bytes.
5. Materialize supported external inputs into provider staging roots when the provider mapping supports it; fail explicitly for an unsupported mapping.
6. Hash the exact materialized bytes, create Build Input Manifest 0.1.0, recompute its aggregate identity, and validate it through the existing contract boundary.
7. Confirm the expected candidate path does not exist.
8. Invoke `BuildProvider` with the exclusive workspace, primary path, staged external-root mappings, and deadline.
9. Capture provider evidence without treating process exit code as Build outcome.
10. Verify materialized input bytes still match the manifest after provider completion.
11. If provider evidence is conclusive and no timeout occurred, validate the single expected candidate within the current workspace.
12. Read candidate bytes once, compute SHA-256, and only then allocate `ArtifactId`.
13. Finalize and validate Artifact Manifest 0.1.0 and succeeded Build Record 0.2.0.
14. On any expected build failure, finalize a failed Build Record without `artifact_id`; retain `build_input` and provider evidence when they were established.
15. Return immutable result values/documents and clean only the verified exclusive workspace.

The accepted Artifact in Phase 02 is immutable `bytes` plus `ArtifactId`, `Sha256Digest`, and its validated manifest. Durable storage is not implied. This keeps Data Plane persistence out of Phase 02 while preserving the exact binary content for the immediate caller.

## 8. Error and outcome policy

Public Build outcome remains exactly:

- `succeeded` after candidate acceptance;
- `failed` otherwise.

Expected provider/compiler failures produce a failed Build Record rather than a provider exception escaping as domain meaning. Application errors remain safe and provider-neutral. Add only codes that are immediately consumed, expected to be no more than:

- `build_input_invalid`;
- `build_provider_failed`;
- `artifact_rejected`.

Timeout, process start failure, undecodable/oversized log, missing summary, nonzero or unusual exit code, missing candidate, and provider diagnostic details remain in provider evidence or internal causes. They do not become new Build outcomes and are not copied automatically into `ApplicationError.details` or operational logs.

Unexpected programming/infrastructure faults retain their exception as the non-serialized `cause`. Cleanup failure is reported and must not trigger broad or unverified deletion.

## 9. Configuration and operational logging

Configuration remains explicit, immutable, and side-effect free. Phase 02 may add only settings consumed by this pipeline:

- MetaEditor executable absolute path;
- terminal/MQL5 root required by the adapter;
- exclusive build workspace parent;
- positive build timeout;
- bounded provider-log/stdout/stderr capture limit;
- stable logical external-root aliases mapped to physical provider roots.

No machine-specific default path is committed. The adapter validates configured paths and records executable version and SHA-256 as provider configuration/evidence. Physical mappings are never part of Build Input Identity.

Operational logging may add `BuildRecordId` as a typed correlation field and emit a small lifecycle vocabulary such as `build.started`, `build.input.materialized`, `build.provider.completed`, `build.artifact.accepted`, and `build.failed`. It must never automatically emit:

- source or EX5 bytes;
- physical paths;
- provider logs or diagnostics;
- build configuration payloads;
- SUT content;
- provider-native exit codes.

`RequestContext` is passed explicitly. No thread-local, context variable, or global request state is introduced.

## 10. Test architecture and quality gates

### Portable authoritative gate

`python tools/check.py` remains runnable without MetaEditor. It must include all domain, application, workspace, parser, candidate-acceptance, fake-provider workflow, schema, and architecture tests. It must not compile a real EA or depend on a local MetaEditor installation.

### Controlled provider acceptance gate

Real MetaEditor tests are a separate required Phase 02 acceptance gate. They run only with explicit provider paths and authorization, use strategy-neutral fixtures copied into a new disposable workspace, and never touch repository EA source or project `.ex5` files.

The integration gate must stop rather than kill an unowned process. It launches with `shell=False`, retains the direct process handle it owns, and never uses name-based broad termination. A timeout rejects all candidates. If detachment, reuse, or an unowned process makes completion ambiguous, the test/build fails closed and reports the limitation.

### Required checks before every milestone checkpoint

- relevant focused `unittest` modules;
- full `python tools/check.py`;
- `python -m compileall -q src tests tools`;
- `python -m pip check`;
- schema/catalog validation when schemas or serialized documents change;
- `git diff --check`;
- complete diff review for scope and architectural leakage.

M3 through M6 additionally require the controlled MetaEditor integration gate on the explicitly supported installation. Skipped provider tests are not evidence of Phase 02 completion.

## 11. Milestones

### M0 — Phase 02 baseline/checkpoint

- Status: Completed before creation of this plan

#### Objective

Establish an immutable, tested contract baseline for Phase 02 implementation.

#### Inputs

- accepted ADR-0010;
- committed probe evidence;
- approved contract evolution.

#### Files/contracts

- Build Input Manifest 0.1.0;
- Build Record 0.2.0;
- unchanged common 1.0.0, Build Record 0.1.0, and Artifact Manifest 0.1.0;
- contract checkpoint `4182552a9852552f24f6e3a0960c478a739ef7cf`.

#### Tests

- authoritative gate: 86 tests passed before checkpoint;
- schema/catalog validation;
- preserved-contract hash verification;
- staged diff and whitespace review.

#### Acceptance criteria

- contract checkpoint exists on `main`;
- the working tree was clean immediately after the checkpoint;
- no runtime/provider code or dependency entered the checkpoint.

#### Out of scope

- all Phase 02 runtime behavior.

### M1 — Build domain and application boundary

- Status: Completed in checkpoint `f7140ae`

#### Objective

Introduce the minimum provider-neutral Build use-case vocabulary and the `BuildProvider` port without any external provider implementation.

#### Inputs

- ADR-0001, ADR-0006, ADR-0007, ADR-0009, ADR-0010;
- existing identifiers, SHA-256, provenance payload, request context, and errors;
- Build Record 0.2.0 outcome rules.

#### Expected files/modules

- `src/ea_research_lab/domain/build.py`;
- `src/ea_research_lab/application/build.py`;
- exports in the existing package `__init__.py` files only when public use requires them;
- `tests/test_build_domain.py`;
- `tests/test_build_application.py`;
- deliberate architecture-test updates.

#### Contracts/responsibilities

- `BuildOutcome` has only `succeeded` and `failed`;
- the port accepts a materialized-workspace request and returns observed provider facts, optional candidate location, and opaque schema-referenced evidence;
- no provider result can allocate or imply `ArtifactId`;
- application records are frozen and provider-neutral;
- `RequestContext` is explicit.

#### Tests

- frozen/validated build values;
- fake `BuildProvider` satisfies the narrow port;
- provider result cannot become successful Build outcome by itself;
- no MetaEditor, subprocess, Windows, SUT, or storage vocabulary in domain/application modules;
- application error serialization remains safe.

#### Acceptance criteria

- application logic can be tested using a small fake provider;
- domain imports only standard library/domain modules;
- application imports only approved inward modules and the existing contract boundary where exact document validation is required;
- no MetaEditor implementation, filesystem materialization, or Artifact acceptance exists.

#### Out of scope

- exclusive workspace, hashing workflow, provider adapter, candidate handling, record finalization, or provider schemas.

### M2 — Build workspace and Build Input

- Status: Completed in checkpoint `abcb257`

#### Objective

Materialize a declared exact input set into a safe exclusive workspace and produce a validated Build Input Manifest before provider invocation.

#### Inputs

- ADR-0010 snapshot policy;
- Build Input Manifest 0.1.0 and identity v1 implementation;
- P09–P12 and P16 observations;
- M1 request/port values.

#### Expected files/modules

- `src/ea_research_lab/infrastructure/build_workspace.py`;
- narrow additions to `application/build.py` and `infrastructure/config.py`;
- `tests/test_build_workspace.py`;
- strategy-neutral source/include fixtures where unit-generated bytes are insufficient.

#### Contracts/responsibilities

- source declarations pair normalized logical locations with ephemeral physical sources;
- materialization reads exact bytes and writes only declared members at normalized destinations;
- destinations are resolved beneath a newly created workspace;
- source links/reparse points are not recreated; input resolution must remain within explicitly declared source roots;
- primary/dependency collisions fail before writing;
- candidate `.ex5` and provider `.log` files are never copied from the source workspace;
- external aliases come from effective configuration, never from absolute path derivation;
- Build Input Manifest is created with the existing identity function and validated locally;
- materialized inputs are rehashed after provider execution before later acceptance.

#### Tests

- primary-only, local, transitive, and external declarations;
- exact-byte BOM/newline/encoding preservation;
- dirty or subsequently mutated development source does not alter the materialized snapshot;
- path traversal, absolute logical path, normalization collision, symlink escape, and destination collision rejection;
- no pre-existing candidate in a new workspace;
- unsupported external-root mapping fails explicitly;
- cleanup targets only the owned workspace and reports locked-file failure safely.

#### Acceptance criteria

- the manifest identity matches the bytes in the exclusive workspace;
- a changed development file after materialization cannot change those bytes;
- Git cleanliness is never consulted as an input-integrity check;
- physical paths appear only in infrastructure/application operational values and provider-specific configuration;
- no provider invocation or ArtifactId allocation exists.

#### Out of scope

- include parsing/discovery, MetaEditor, process management, candidate acceptance, durable snapshot retention, or Artifact persistence.

### M3 — MetaEditor adapter

- Status: Completed in checkpoint `4dd117a`

#### Objective

Implement one evidence-based MetaEditor adapter behind `BuildProvider`, limited to the observed direct compile mode.

#### Inputs

- ADR-0006 and ADR-0010;
- P01–P16 direct observations and unresolved limitations;
- M1 port and M2 exclusive workspace;
- official/empirically verified `/compile`, `/log`, and `/include` behavior.

#### Expected files/modules

- `src/ea_research_lab/infrastructure/metaeditor.py`;
- consumed provider settings in `infrastructure/config.py`;
- `schemas/metaeditor-build-configuration/v0.1.0.schema.json`;
- `schemas/metaeditor-build-evidence/v0.1.0.schema.json`;
- exact catalog/fixture tests for those provider extensions;
- `tests/test_metaeditor.py`;
- `tests/integration/test_metaeditor_build.py` and disposable fixtures.

#### Contracts/responsibilities

- ordered argv invocation with `shell=False` and provider-specific `/compile:"..."` grammar;
- explicit executable, working directory, environment, and deadline;
- direct `Popen` handle is the only process considered owned;
- timeout terminates only the owned direct process and rejects every candidate;
- no name-based or broad MetaEditor/MetaTrader termination;
- stdout/stderr and provider log capture are bounded;
- UTF-16LE BOM/log decoding and result parsing remain private to the adapter;
- exit code is evidence only;
- provider evidence records bounded process/log/result facts and known limitations under its exact namespaced schema;
- observed include paths are mapped back to declared workspace/external members; undeclared observed inputs make the result inconclusive/failed;
- absence, oversize, decoding failure, or ambiguity in provider evidence fails closed.

#### Tests

- argv with ordinary, spaced, and Unicode paths;
- no shell invocation;
- successful and failed recorded log parsing;
- reversed/unusual exit-code behavior does not determine result;
- empty stdout/stderr behavior is not required;
- missing, malformed, wrong-encoding, and oversized logs fail safely;
- timeout rejects candidate and stops only the owned direct process;
- local, transitive, missing, and standard/external include observations;
- executable identity/version/digest capture;
- real valid compile and compiler failure in a disposable workspace.

#### Acceptance criteria

- no MetaEditor/Windows/process/log type appears in domain or serialized core contracts;
- the adapter never claims success from exit code or candidate existence alone;
- real provider tests reproduce the supported observed compile and failure behaviors;
- staged external include mapping is empirically validated for the supported configuration or the combination fails explicitly;
- any detached/reused/child-process ambiguity fails closed without terminating an unowned process;
- provider extension schemas remain pre-stable and do not modify core schema versions.

#### Out of scope

- generic `ProcessRunner`, interactive MetaEditor automation, project-mode builds, universal diagnostic model, dependency-completeness claims, Artifact acceptance, or persistence.

### M4 — Candidate Artifact acceptance

- Status: Completed in checkpoint `016810b`

#### Objective

Accept an EX5 only when it is attributable to the current exclusive workspace and its exact bytes have been read and hashed.

#### Inputs

- ADR-0009 and ADR-0010;
- P03, P06, P08, and P14 observations;
- Artifact Manifest 0.1.0 and Build Record 0.2.0;
- M2 workspace and M3 provider result.

#### Expected files/modules

- `src/ea_research_lab/infrastructure/artifact.py`;
- additions to `domain/build.py` and `application/build.py`;
- `tests/test_artifact_acceptance.py`;
- Build/Artifact contract fixtures only if existing fixtures cannot express final records.

#### Contracts/responsibilities

- expected candidate path is derived only from the materialized primary in the current workspace;
- the candidate must not exist before invocation;
- after conclusive provider completion, exactly one expected regular non-link EX5 must resolve beneath the workspace;
- missing, extra/ambiguous, escaped, stale, linked, directory, unreadable, or post-timeout candidates are rejected;
- candidate bytes are read once into immutable `bytes` and SHA-256 is calculated from those bytes;
- `ArtifactId` is allocated only after every acceptance check passes;
- succeeded Build Record requires the Build Input reference and accepted ArtifactId;
- failed Build Record never contains ArtifactId;
- Artifact Manifest 0.1.0 is reused unchanged and validated exactly.

#### Tests

- missing and ambiguous candidate;
- pre-existing/stale candidate;
- path escape, symlink/reparse candidate, and wrong extension;
- timeout or failed provider evidence with a candidate present;
- candidate mutation/read behavior and exact-byte digest;
- ArtifactId generator is not called before acceptance and is called once afterward;
- succeeded/failed Build Record 0.2.0 invariants;
- Artifact Manifest remains linked through BuildRecordId and does not duplicate Build Input Identity.

#### Acceptance criteria

- no candidate can become an Artifact through existence, timestamp, or exit code alone;
- accepted immutable bytes hash to the manifest `binary_digest`;
- Artifact and Build Record documents validate through the closed local catalog;
- no filesystem storage key/location enters domain or contract values;
- no durable Artifact repository or Data Plane implementation exists.

#### Out of scope

- end-to-end orchestration, Artifact storage/publication, retention, ExecutionProvider, or run use.

### M5 — End-to-end build workflow

- Status: Completed in checkpoint `208ffe9`

#### Objective

Compose M1–M4 into one application use case with explicit context, safe failures, complete build facts, and controlled cleanup.

#### Inputs

- all prior Phase 02 milestones;
- RequestContext, ID generation, application errors, configuration, logging, and contract validators;
- real provider evidence for valid, failed, timeout, dirty-source, and external-include cases.

#### Expected files/modules

- final orchestration in `src/ea_research_lab/application/build.py`;
- minimal correlation/configuration additions to `infrastructure/logging.py` and `infrastructure/config.py`;
- `tests/test_build_workflow.py`;
- expanded controlled integration tests and disposable fixtures;
- directly affected build/artifact development documentation.

#### Contracts/responsibilities

- one call returns Build Input Manifest, Build Record 0.2.0, optional Artifact Manifest, optional immutable accepted Artifact bytes, and bounded provider evidence;
- BuildRecordId exists for success and failure;
- ArtifactId and Artifact Manifest exist only after acceptance;
- dirty SourceRevision is preserved while exact materialized bytes determine Build Input Identity;
- every returned serialized document is validated against its exact schema;
- cleanup occurs after result materialization and never invalidates returned Artifact bytes;
- provider evidence and physical mappings are not operationally logged.

#### Tests

- fake-provider deterministic success, compiler failure, timeout, malformed evidence, stale/ambiguous candidate, and cleanup failure;
- real MetaEditor valid compile;
- real compiler failure with no ArtifactId;
- real timeout with no accepted candidate;
- development source mutation after snapshot materialization;
- local/transitive includes;
- explicitly declared standard/external include with stable logical alias;
- request/build correlation without global context;
- schema validation of all returned documents;
- no raw source, EX5, log, diagnostic, configuration payload, or physical path in operational logs.

#### Acceptance criteria

- valid compile produces a linked Build Input Manifest, succeeded Build Record, accepted Artifact bytes/digest, and Artifact Manifest;
- compiler failure and timeout produce failed Build Records without ArtifactId;
- dirty source builds succeed when their exact declared bytes are materialized;
- any observed undeclared dependency or mutated materialized input prevents Artifact acceptance;
- external/standard inputs are logically named and exact-byte hashed without physical paths entering Build Input Identity;
- all disposable workspaces are safely cleaned or cleanup failure is visible;
- no Data Plane, Platform API, execution, or later-phase implementation exists.

#### Out of scope

- persistent commands, API exposure, queues, batching, scheduling, execution, data ingestion, or analysis.

### M6 — Enforcement and Phase 02 closure

- Status: Closure verification complete; pending owner approval and clean checkpoint

#### Objective

Prove the Build and Artifact boundary is reliable, provider-isolated, contract-conformant, and ready to become an input to later ExecutionProvider planning.

#### Inputs

- completed M1–M5 implementation;
- accepted ADRs and architectural principles;
- Phase 02 plan and complete implementation diff;
- portable and controlled-provider test results.

#### Expected files/modules

- deliberate updates to `tests/architecture/test_dependencies.py` and `test_contract_neutrality.py`;
- final `tools/check.py` only if the portable authoritative gate needs explicit new enforcement;
- updates to `docs/architecture/execution-plane.md`, `docs/domain/artifact.md`, `docs/development.md`, and roadmap/plan status only where actual behavior changed;
- no Phase 03 plan or scaffold.

#### Contracts/responsibilities

- domain/application remain provider- and strategy-neutral;
- MetaEditor-specific imports and vocabulary remain confined to its infrastructure module and provider extension schemas;
- exact core schemas remain unchanged;
- no new dependency or top-level runtime package is present;
- provider evidence is namespaced and never redefines public Build outcome;
- reproducibility remains a separate assessment.

#### Tests and checks

- complete portable authoritative gate;
- complete controlled MetaEditor gate on the explicitly supported installation;
- architecture import and vocabulary scans;
- all schema/catalog tests including exact historical version support and no network retrieval;
- `compileall`, `pip check`, `git diff --check`, and complete diff review;
- verification that no `.ex5`, provider log, physical-path fixture, probe workspace, cache, or temporary build directory entered Git.

#### Acceptance criteria

- every Phase 02 objective and M1–M5 criterion is satisfied;
- stale, ambiguous, timed-out, failed, or unowned candidates cannot become Artifacts;
- the full source revision → Build Input → Build Record → Artifact relationship is reconstructable from returned documents;
- provider limitations and incomplete dependency-discovery guarantees remain explicit;
- both gates pass without weakening Phase 01 architecture enforcement;
- documentation describes the supported MetaEditor version/mode without claiming universal behavior;
- Phase 02 can be marked completed only after owner approval and a clean Git checkpoint;
- Phase 03 implementation and planning have not started.

#### Out of scope

- ExecutionProvider and every later roadmap capability.

#### Verified non-blocking limitations

- dependency discovery completeness is not guaranteed;
- interactive or reused MetaEditor behavior remains untested;
- output redirection remains unverified;
- byte-for-byte deterministic EX5 output remains untested;
- provider behavior is validated only against MetaEditor `5.0.0.6104` in the observed direct-compile mode;
- process-tree behavior for larger or project-mode builds remains unverified;
- direct compilation supports only the empirically proven external-root scope;
- persistence and long-term retention of source and Artifact bytes remain deferred.

## 12. Risk register

| Risk | Required treatment |
|---|---|
| Stale EX5 | New exclusive workspace, candidate absent before invocation, expected-path and ambiguity checks; never trust timestamp or existence alone. |
| Mutable source during build | Materialize exact declared bytes before invocation and rehash the isolated inputs afterward. The development tree is never compiled directly. |
| Dirty working tree | Preserve `SourceRevision.is_dirty`; do not reject it or use Git cleanliness as byte evidence. |
| Standard/external includes | Stable logical aliases from configuration, materialized/staged when supported, exact-byte hashing, provider-log mapping, and explicit failure for unsupported mappings. |
| Provider log parsing | Strict bounded read, UTF-16LE/BOM handling, exact adapter-private grammar, fixtures for malformed/oversized logs, and fail-closed ambiguity. |
| Unusual exit codes | Capture as provider evidence only; require provider verdict plus accepted candidate for public success. |
| Timeout and process ownership | Retain the directly launched process handle, terminate only that process, reject every candidate, never kill by process name, and fail closed on child/detach/reuse ambiguity. |
| Physical versus logical paths | Physical paths remain ephemeral/provider-specific; only normalized logical locations enter Build Input Identity. |
| Incomplete dependency discovery | Compare every observed provider path with the declared set, reject known undeclared inputs, and preserve the unproven completeness limitation in provider evidence/reproducibility work. |
| Candidate hashing before acceptance | Read exact candidate bytes and compute SHA-256 before allocating ArtifactId or finalizing a succeeded record. |
| Provider/version drift | Verify executable path, product/file version, and SHA-256; unsupported observations fail visibly instead of inheriting the probe assumptions. |
| EX5 nondeterminism | Do not infer deterministic compiler output; record each accepted binary digest independently. |
| Windows cleanup/file locks | Cleanup only the resolved owned workspace after process completion; report failure and never broaden deletion. |
| No durable Artifact storage | Return immutable bytes and provenance documents; do not claim retention. Add persistence only through a later approved Data Plane decision. |

## 13. Dependencies

No new dependency is planned.

The Python 3.14 standard library provides the immediately required functionality: `pathlib`, `tempfile`, `shutil`, `hashlib`, `subprocess`, `datetime`, `json`, `codecs`, `re`, and `unittest`. Existing `jsonschema[format]` and the current contract catalog provide schema validation. A generic process library, filesystem abstraction, validation model library, DI container, or test framework would add ownership without solving a demonstrated gap.

If implementation evidence proves that safe process-tree ownership cannot be achieved for the supported MetaEditor mode using the directly owned `Popen` process, stop M3 and request an explicit dependency/architecture decision. Do not silently add `psutil` or a generic process layer.

The existing non-blocking Foundation follow-ups remain unchanged:

- wheel/distribution packaging of external schemas has not been validated;
- `referencing` is directly used while transitively installed and remains subject to later dependency/distribution review.

## 14. Objective Phase 02 completion criteria

Phase 02 is complete only when all are true:

1. The contract baseline checkpoint remains immutable and readable.
2. BuildProvider is narrow, provider-neutral, and independently testable.
3. The mutable development workspace is never the provider compile target.
4. Build Input Manifest identifies the exact declared materialized input bytes before invocation.
5. MetaEditor behavior is confined to one adapter and provider extension schemas.
6. Timeout, exit code, logs, paths, and diagnostics never become public Build outcomes or core domain semantics.
7. A candidate is accepted only from the current exclusive workspace after conclusive provider completion and exact-byte hashing.
8. ArtifactId is allocated only after acceptance.
9. Succeeded Build Record 0.2.0 references Build Input and Artifact; failed records never reference Artifact.
10. Artifact Manifest 0.1.0 remains unchanged and linked through BuildRecordId.
11. Dirty source builds are supported through materialized exact-byte identity.
12. Known external inputs are declared and logically mapped; completeness is not overstated.
13. Provider integration tests prove valid, failed, timeout, dirty-snapshot, and external-include paths on the supported installation.
14. Portable and provider acceptance gates pass.
15. No dependency, Data Plane persistence, ExecutionProvider, Platform API, or later-phase scaffold was introduced.
16. Documentation and architecture enforcement match the actual implementation.
17. The owner approves a clean Phase 02 closure checkpoint.

## 15. Approval and execution boundary

M0-M5 are implemented and checkpointed. M6 contains enforcement and documentation closure only. Phase 02 may be marked completed after the owner approves M6 and creates a clean closure checkpoint. Phase 03 planning and implementation remain unauthorized.
