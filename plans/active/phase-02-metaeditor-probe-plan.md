# Phase 02 — Controlled MetaEditor Probe Plan

- Status: Proposed; not executed
- Scope: empirical provider observation only
- Explicit exclusion: this is not the Phase 02 execution plan

## Objective

Observe the installed MetaEditor build boundary with disposable fixtures so that Phase 02 architecture and contracts are based on evidence rather than assumed CLI, process, include, or output behavior.

The probes never compile project EA/SUT source and never produce or replace a project Artifact.

## Safety boundary

All probe execution must satisfy these rules:

- Create one new, explicitly disposable `PROBE_ROOT` outside the repository and record its resolved absolute path before use.
- Resolve every fixture, log destination, candidate output, and cleanup target beneath `PROBE_ROOT` before writing, moving, or deleting it.
- Invoke processes with an argv sequence and shell execution disabled.
- Do not install software, modify MetaTrader configuration, or modify files outside `PROBE_ROOT`.
- Do not compile, copy, rename, or overwrite project EA/SUT source or project `.ex5` files.
- Do not terminate pre-existing or unrelated MetaEditor/MetaTrader processes.
- Stop before process execution if ownership of the launched process and any process selected for termination cannot be established.
- Treat compiler output and logs as untrusted input; capture bounded bytes and do not execute or interpolate their contents.
- Preserve a probe result bundle until observations are reviewed; cleanup removes only the verified `PROBE_ROOT`.

## Required discovery gate

Before P01, perform a read-only discovery step that records:

- the resolved MetaEditor executable path;
- executable file version and SHA-256 digest;
- any locally verifiable help/version information;
- the exact installed CLI syntax used to compile a source file;
- whether a log or output destination can be supplied explicitly.

If compile syntax cannot be verified without guessing, stop. Do not infer switches from memory or documentation for another installed version.

## Command notation

The matrix uses these argv templates:

- `COMPILE_ARGV(source)`: the exact argv sequence established by the discovery gate for one source file.
- `COMPILE_TO_ARGV(source, output)`: the verified argv sequence for an explicit output location, only if the installed provider supports it.
- `RUN(argv, cwd, env, timeout)`: an ownership-tracked process invocation with shell execution disabled, an explicit working directory, an allowlisted environment, captured process observations, and no automatic termination of processes not proven to belong to the probe.

These are notation for the future probe execution record, not new runtime abstractions or repository code. The concrete argv must be written into the result record before each probe is authorized.

## Probe matrix

| ID | Question | Disposable fixture/setup | Command to execute | Observations and files/logs | Safety boundary and cleanup | Architectural decision affected |
|---|---|---|---|---|---|---|
| P01 | Can a minimal valid source compile, and what constitutes observed success? | Minimal strategy-neutral source in `PROBE_ROOT/P01`; no pre-existing output. | `RUN(COMPILE_ARGV(P01_SOURCE), P01_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | Start result, owned PIDs, duration, exit code, stdout/stderr, provider log, all files created, candidate digest. | Abort on ambiguous ownership or writes outside allowed locations; retain capture, then delete only P01 during verified root cleanup. | Evidence required to derive provider-neutral build success. |
| P02 | How does the provider report a compiler error? | Minimal source with one intentional syntax error in `P02`; no output. | `RUN(COMPILE_ARGV(P02_SOURCE), P02_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | Exit behavior, diagnostic channel, encoding, reported location/severity, output presence, provider log. | Treat diagnostics as untrusted; never accept produced output; root-scoped cleanup. | Compiler failure detection and diagnostic parsing boundary. |
| P03 | Can a failed compile leave or appear to produce a stale `.ex5`? | Copy invalid P02 source into `P03`; create sentinel expected-output file with recorded bytes, length, timestamps, and SHA-256. | `RUN(COMPILE_ARGV(P03_SOURCE), P03_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | Whether sentinel remains, changes, disappears, or is replaced; exit and diagnostics; hashes before/after. | Sentinel exists only in P03; never use a real `.ex5`; root-scoped cleanup. | Stale-output rejection and failed-build artifact policy. |
| P04 | Are source and output paths containing spaces handled correctly? | Valid fixture beneath `PROBE_ROOT/P04 path with spaces`. | `RUN(COMPILE_ARGV(P04_SOURCE), P04_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | Literal argv, resolved paths, exit, logs, candidate path/name/hash. | No shell string or manual quoting; stop on any path escape; root-scoped cleanup. | Windows argv/path handling requirements. |
| P05 | Are Unicode source and output paths handled correctly? | Valid fixture beneath a Unicode-named P05 directory. | `RUN(COMPILE_ARGV(P05_SOURCE), P05_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | argv encoding, diagnostic/log encoding, exit, exact created path, candidate readability/hash. | Use filesystem-native Unicode APIs; stop on lossy path conversion or path escape; root-scoped cleanup. | Supported path policy and encoding capture. |
| P06 | What exact output path and filename are chosen by default? | Valid fixture in an otherwise empty `P06` tree. | `RUN(COMPILE_ARGV(P06_SOURCE), P06_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | Recursive before/after inventory under P06, provider log references, candidate name/path, timestamps and digest. | Do not search or mutate outside permitted probe locations; root-scoped cleanup. | Candidate discovery contract. |
| P07 | Can compiler output be directed to a build-scoped staging location? | Valid source in `P07/source` and empty `P07/staging`. | If verified: `RUN(COMPILE_TO_ARGV(P07_SOURCE, P07_OUTPUT), P07_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)`; otherwise record unsupported and do not execute. | Whether the requested location is honored, alternate files created, logs, exit and candidate digest. | Execute only with verified output syntax; stop on output outside allowed probe roots; root-scoped cleanup. | Staging strategy and separation of candidate from accepted Artifact. |
| P08 | How is an existing output treated during a successful compile? | Valid source in P08 plus sentinel expected output with recorded identity. | `RUN(COMPILE_ARGV(P08_SOURCE), P08_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | Replace/delete/in-place behavior, file identity where observable, before/after bytes and digest, temporary files. | Sentinel is disposable and isolated; no project output; root-scoped cleanup. | Atomic acceptance, overwrite protection, and freshness proof. |
| P09 | How is a relative/local include resolved? | Valid primary source and one local include with distinctive harmless constant, both in P09; record both digests. | `RUN(COMPILE_ARGV(P09_SOURCE), P09_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | Success/failure, resolved location if reported, logs, output; repeat only if authorized after changing included bytes and recording a new input set. | Include exists only in P09; no project include paths; root-scoped cleanup. | Build Input Manifest membership and local include materialization. |
| P10 | How is an include from the installed standard MQL5 Include location resolved? | Valid fixture referencing one harmless installed standard include selected during discovery; do not modify the include. | `RUN(COMPILE_ARGV(P10_SOURCE), P10_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | Success/failure, provider log, observable include path/version facts, candidate; hash read-only included file if its exact path is established. | Read standard include only; do not copy back or modify installation/configuration; root-scoped fixture cleanup. | Representation of provider/environment inputs and completeness limits. |
| P11 | Are nested/transitive local includes resolved from a materialized tree? | P11 primary includes A; A includes B; all files disposable with recorded digests. | `RUN(COMPILE_ARGV(P11_SOURCE), P11_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | Success/failure, diagnostics, output, whether all three files are required; recorded manifest candidate. | All source inputs beneath P11; root-scoped cleanup. | Transitive input-set representation without a core dependency parser. |
| P12 | How is a missing include reported, and is any candidate left behind? | P12 source references a deliberately absent file; no pre-existing output. | `RUN(COMPILE_ARGV(P12_SOURCE), P12_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | Exit, diagnostic text/encoding, missing-name representation, log and output presence. | Do not create the missing path outside P12; never accept output; root-scoped cleanup. | Failure evidence and incomplete dependency classification. |
| P13 | Does compilation create child processes, and which process owns completion? | Valid P01-equivalent fixture; capture process snapshot immediately before launch. | `RUN(COMPILE_ARGV(P13_SOURCE), P13_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` with read-only parent/child observation for the owned PID. | Parent/child PIDs, creation times, executable identities, lifetime, exit ordering, lingering owned processes. | Observe only; do not terminate anything in this probe; stop if PID ownership is ambiguous; root-scoped cleanup after owned processes exit. | Smallest process boundary and completion semantics. |
| P14 | What happens when the owned invocation exceeds a deadline? | Valid disposable fixture; use a deliberately short timeout only after P13 establishes ownership. | `RUN(COMPILE_ARGV(P14_SOURCE), P14_DIR, ALLOWLISTED_ENV, SHORT_TIMEOUT)` | Whether timeout occurs, process/child state, termination response if ownership is certain, files/logs left, candidate presence. | Do not force termination without proven ownership; if ownership is uncertain, stop and report the probe blocked; clean only after processes are confirmed stopped. | Timeout, cancellation, orphan prevention, and candidate rejection. |
| P15 | Is MetaEditor detached, reused, or delegated to an existing process? | Valid fixture; record all relevant process identities before invocation without closing existing processes. | `RUN(COMPILE_ARGV(P15_SOURCE), P15_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | Launcher lifetime, reused/detached process evidence, IPC-visible behavior if any, output completion signal, process identities. | If an existing unrelated process appears involved and ownership cannot be isolated, stop; never kill or reconfigure it. | Whether direct subprocess waiting can define provider completion. |
| P16 | Can build execution consume a materialized source snapshot instead of the mutable development tree? | Create source tree A and byte-identical snapshot B under P16; record a candidate manifest for B; mutate A only after B is sealed; compile B. Include local/nested fixtures proven by P09/P11. | `RUN(COMPILE_ARGV(P16_SNAPSHOT_SOURCE), P16_SNAPSHOT_DIR, ALLOWLISTED_ENV, NORMAL_TIMEOUT)` | All paths referenced by logs, output location, success/failure, B digests before/after, evidence of any dependency on A or external roots. | Both trees are disposable; never point to repository source; stop on unexpected access/write outside allowed probe locations; root-scoped cleanup. | ADR-0010 acceptance, materialization feasibility, and claimed input-set boundary. |

## Capture record

Each executed probe must produce a bounded result record containing:

- probe ID and execution timestamp;
- exact argv as an ordered list;
- resolved executable identity;
- resolved workspace paths;
- explicit environment keys supplied, with secrets excluded;
- start/exit/timeout/cancellation observations;
- owned process identities observed;
- bounded stdout/stderr and provider-log copies where safely available;
- before/after file inventory and SHA-256 digests;
- cleanup result;
- conclusion, uncertainty, and any safety stop.

The capture format is a probe artifact, not a released platform contract. Do not add it to the Phase 01 schema catalog.

## Stop conditions

Stop the probe sequence and report before continuing when:

- the executable or CLI syntax cannot be verified;
- MetaEditor requires project source or configuration changes;
- output cannot be confined or safely distinguished from project files;
- process ownership cannot be established;
- a probe would require terminating an unrelated process;
- a path selected for cleanup resolves outside `PROBE_ROOT`;
- provider behavior contradicts an accepted architectural boundary.

## Exit criteria

The probe set is complete when observations are sufficient to decide:

- how MetaEditor process completion and compiler success are distinguished;
- how a fresh candidate `.ex5` is located without trusting timestamps alone;
- whether build-scoped staging or safe quarantine is possible;
- which diagnostics and environment facts are available;
- how local, nested, and standard includes affect the claimed input set;
- whether a materialized snapshot can be compiled safely;
- whether ADR-0010 can be accepted without provider-specific semantics entering the core.

No probe is authorized or executed by this document.
