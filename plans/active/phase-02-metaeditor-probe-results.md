# Phase 02 — Controlled MetaEditor Probe Results

- Status: Executed on 2026-08-09
- Scope: empirical provider observation only
- Explicit exclusion: this is neither Phase 02 runtime implementation nor the Phase 02 execution plan
- Provider coverage: one MetaEditor installation and one Windows/MQL5 data environment

## Purpose and evidence boundary

This record captures P01–P16 from the approved controlled probe plan. All MQL5 fixtures were minimal, strategy-neutral, and created specifically beneath one disposable workspace. No EA Research Lab source or project `.ex5` file was compiled, copied, modified, or overwritten.

`OBSERVATION` identifies directly measured behavior. `INFERENCE` identifies an architectural interpretation that remains subject to provider coverage and contract design. An inference is not provider fact.

## Wave 0 — Environment discovery

### Selected installation

**OBSERVATION**

- Repository-associated terminal data root: `C:\Users\eng_d\AppData\Roaming\MetaQuotes\Terminal\9B101088254A9C260A9790D5079A7B11`.
- That root's `origin.txt` identified `C:\Program Files\Ava Trade MT5 Terminal`.
- The only discovered MetaEditor candidate was `C:\Program Files\Ava Trade MT5 Terminal\MetaEditor64.exe`.
- Executable SHA-256: `50f47217c681e022924e905a2296144a7712dcf07f27bcfc108bf972aa20214c`.
- Executable length: `116419632` bytes.
- File and product version: `5.0.0.6104`.
- Product: `MetaQuotes Language 5 Editor`; company: `MetaQuotes Ltd.`.
- Windows Authenticode status was valid and the signer was `MetaQuotes Ltd.`.
- Relevant roots were the terminal data root above, its `MQL5` directory, and `MQL5\Include`. The installation directory did not contain an `MQL5` tree.
- No MetaEditor or MetaTrader process was running at discovery time.
- No local CLI help file was found. Current official MetaEditor documentation established `/compile:"<full source path>"`, `/log`, and `/include:"<custom MQL5 root>"`; it did not document a separate output-path switch.

**INFERENCE**

- `origin.txt`, executable identity, terminal data root, and compiler version are relevant provider-environment evidence. They must not become core entity identity.
- P07 could not safely test a guessed output-redirection option.

## Execution boundary and common capture

- Disposable workspace (`PROBE_ROOT`): `C:\Users\eng_d\AppData\Local\Temp\EAResearchLab-MetaEditor-Probes-20260809-01`.
- Every fixture, sentinel, generated log, and generated `.ex5` was beneath `PROBE_ROOT`.
- Ordinary invocations used an ordered argv list, `shell=False`, an explicit fixture working directory, and an allowlisted environment containing only `SystemRoot`, `WINDIR`, `PATH`, `TEMP`, `TMP`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `PROGRAMDATA`, `COMSPEC`, `HOMEDRIVE`, and `HOMEPATH` when present.
- MetaEditor stdout and stderr were empty in every started compiler invocation.
- Every generated provider log began with a UTF-16LE BOM (`fffe`) and was decoded as UTF-16LE.
- Before/after inventories were restricted to the relevant fixture tree. No generated file was observed outside `PROBE_ROOT`.
- Except where a probe says otherwise, the exact ordered arguments were `["C:\\Program Files\\Ava Trade MT5 Terminal\\MetaEditor64.exe", "/compile:<absolute fixture .mq5 path>", "/log"]` and the working directory was the fixture's directory.
- The result bundle was reviewed before cleanup. A cleanup attempt resolved and checked the exact `PROBE_ROOT`, confirmed that no MetaEditor/MetaTrader process was active, and was then rejected by the host command policy before deletion. No file was changed by that attempt; the disposable bundle remains outside Git at `PROBE_ROOT`.

## Probe results

### Wave 1 — Basic compilation

#### P01 — Valid source

**OBSERVATION**

- Timestamp: `2026-08-09T21:15:21Z`; working directory: `PROBE_ROOT\P01`.
- Fixture before invocation: `probe_valid.mq5`, 37 bytes, SHA-256 `58ef26c5f6a0813e3c2f4cdcd99c89f6e8b844209782919defc3209490c7f00b`; no log or `.ex5` existed.
- Process start succeeded as PID `16432`; duration was `1.329428 s`; exit code was `1`.
- Provider log: `probe_valid.log`, 3152 bytes, SHA-256 `e45460149a09eb99a072630a1fbffd91a6c69d7591f989c30e427433b944d06d`; it reported `0 errors, 0 warnings`, `679 msec elapsed`, and `X64 Regular`.
- Candidate: `probe_valid.ex5` beside the source, 5788 bytes, SHA-256 `e9ef84aebd55f5e434cde75b6d279ee78e15515a620457e1dbc7b28a44aa0fcf`.
- No related process remained after completion.

**INFERENCE**

- On this version, process exit code `1` can accompany compiler success. Exit code alone cannot define a successful build.

#### P02 — Compiler error

**OBSERVATION**

- Timestamp: `2026-08-09T21:15:46Z`; working directory: `PROBE_ROOT\P02`.
- Invalid source SHA-256: `96a21a48f35660a01cecd4dd3881f10f3ea1c8fc5726b81477ce6b078550229a`; no log or `.ex5` existed before invocation.
- Process start succeeded as PID `18336`; duration was `0.469923 s`; exit code was `0`.
- Provider log SHA-256: `709625f058f382ebcb393f9c25d5f3de34dfabd0dae6d18a029a98cab34b0f91`; it reported three errors, one warning, and source locations.
- No `.ex5` was present after invocation. No related process remained.

**INFERENCE**

- On this version, process exit code `0` can accompany compiler failure. Future provider logic must interpret bounded provider evidence and validate a fresh candidate; it must not map generic subprocess success directly to build success.

### Wave 2 — Existing and staged output

#### P03 — Failed compile with pre-existing EX5

**OBSERVATION**

- Timestamp: `2026-08-09T21:16:34Z`; working directory: `PROBE_ROOT\P03`.
- The invalid source had SHA-256 `96a21a48f35660a01cecd4dd3881f10f3ea1c8fc5726b81477ce6b078550229a`.
- A 35-byte sentinel at the expected `.ex5` path had SHA-256 `f395170144531a55e2f437b304dbfc4b23c2c25ed8b980d21332ca8ea2bfe0a1` before invocation.
- Process start succeeded as PID `20560`; duration was `0.511767 s`; exit code was `0`.
- Log SHA-256: `4cd735e6df17f821db698ca112de3c89f6ec0fcfb94813c57aa24f7bdfa19621`; it reported three errors and one warning.
- The pre-existing sentinel `.ex5` was deleted; only the source and log remained. No related process remained.

**INFERENCE**

- This observed version removes an expected-name stale candidate on this compiler failure. Artifact acceptance still cannot rely on that behavior being universal or on output existence alone.

#### P06 — Default output location and name

**OBSERVATION**

- Timestamp: `2026-08-09T21:16:53Z`; working directory: `PROBE_ROOT\P06`.
- `probe_location.mq5` had SHA-256 `58ef26c5f6a0813e3c2f4cdcd99c89f6e8b844209782919defc3209490c7f00b`; the tree otherwise contained no output.
- Process start succeeded as PID `15752`; duration was `1.077357 s`; exit code was `1`.
- MetaEditor created `probe_location.ex5` beside the primary source, using the source basename: 5658 bytes, SHA-256 `3a0022d4da26805fda56e2325b3207e28a2b80fd40eba59a16437ec657b7fc7e`.
- Log SHA-256: `c9357374afc62b06dd37f13c1dfcac626446dffd46af8bb520690c28091b87ae`; result was zero errors and warnings. No related process remained.

**INFERENCE**

- Candidate discovery can be scoped to the materialized primary source directory for the observed single-file compile mode, subject to post-build freshness and content checks.

#### P07 — Explicit output redirection/staging

**OBSERVATION**

- Status: blocked without process execution.
- Neither the installed executable context nor the current official CLI documentation exposed a verified output-redirection switch. No speculative switch was invoked.
- No fixture output or provider log was created for P07.

**INFERENCE**

- Direct output redirection is unsupported by the verified interface, not proven impossible. P16 tests the safer alternative of placing the materialized source itself in a build-scoped workspace.

#### P08 — Existing output replacement on success

**OBSERVATION**

- Timestamp: `2026-08-09T21:17:12Z`; working directory: `PROBE_ROOT\P08`.
- Valid source SHA-256: `58ef26c5f6a0813e3c2f4cdcd99c89f6e8b844209782919defc3209490c7f00b`.
- The 35-byte sentinel candidate had SHA-256 `28b549b705a0358bb9063ac639554cdfd378b150e03217023d37d4ab4d91a60c` before invocation.
- Process start succeeded as PID `17928`; duration was `1.195101 s`; exit code was `1`.
- The sentinel was replaced by a 5496-byte `.ex5` with SHA-256 `71ecc3055833ce10bb25e4c0b21ab83ab45e5a6b6fd697c2a90312adc587aa89`.
- Log SHA-256: `2756b52917c7f7a2b453d2d7ef13dbe875a4b9d38423481d7ff39d1bbad9eb7f`; result was zero errors and warnings. No related process remained.

**INFERENCE**

- Successful compilation replaces an expected-name file in this setup. A build-scoped directory avoids risking an unrelated output and makes freshness easier to prove.

### Wave 3 — Windows paths

#### P04 — Path containing spaces

**OBSERVATION**

- Timestamp of the successful attempt: `2026-08-09T21:18:44Z`; working directory: `PROBE_ROOT\P04 path with spaces`.
- Source path: `PROBE_ROOT\P04 path with spaces\probe with spaces.mq5`; source SHA-256: `58ef26c5f6a0813e3c2f4cdcd99c89f6e8b844209782919defc3209490c7f00b`.
- Two ordered-argument attempts—an unquoted `/compile:<path with spaces>` argument and an argument containing literal quote characters—each exited `0` and produced no log or candidate.
- The successful shell-disabled Windows process invocation used this exact command line: `"C:\Program Files\Ava Trade MT5 Terminal\MetaEditor64.exe" /compile:"C:\Users\eng_d\AppData\Local\Temp\EAResearchLab-MetaEditor-Probes-20260809-01\P04 path with spaces\probe with spaces.mq5" /log`.
- The direct process started as PID `19688`, ran for `1.098017 s`, and exited `1`.
- Candidate: 5020 bytes, SHA-256 `e8f181339c78c8bb2955c7157094b929bbfc676257f5a0133575d4619f0a0387`; log SHA-256 `ef6d59a609f16a800fab2a417d978331b415215b136cc2a5e9c0f05ad86d5e96`; zero errors and warnings.
- No related process remained.

**INFERENCE**

- MetaEditor's option parser requires the documented `/compile:"path"` raw Windows command-line grammar for spaces. A future adapter must construct and test that grammar without invoking a shell; generic argv serialization is not sufficient on this provider/version.

#### P05 — Unicode path

**OBSERVATION**

- Timestamp of the valid attempt: `2026-08-09T21:20:05.345Z`; working directory: `PROBE_ROOT\P05_café_測試`.
- Source path: `PROBE_ROOT\P05_café_測試\probe_ç_測試.mq5`; source SHA-256: `58ef26c5f6a0813e3c2f4cdcd99c89f6e8b844209782919defc3209490c7f00b`.
- Preliminary inline harness attempts were invalid because the calling pipeline replaced Unicode characters with `?`; their no-output results are harness failures, not MetaEditor evidence.
- The valid attempt used Windows `ProcessStartInfo`, `UseShellExecute=false`, and native Unicode strings with `/compile:"<Unicode absolute path>" /log`.
- Process start succeeded as PID `5232`; duration was `1167.8556 ms`; exit code was `1`.
- Candidate: 5680 bytes, SHA-256 `844bc789d2c273aa33112f2b0dd6eb9c3749aab30345974a614b7450ab8bce74`; log SHA-256 `c126ab0e03af262162a91502da26b1d512e3cd45225021aba208d304a9b9ddcc`.
- The UTF-16LE log preserved the exact Unicode paths and reported zero errors and warnings. No related process remained.

**INFERENCE**

- Native Unicode paths are viable in this environment. Any lossy intermediate command representation would be an adapter defect, not a provider limitation established by this probe.

### Wave 4 — Include resolution

#### P09 — Relative/local include

**OBSERVATION**

- Timestamp: `2026-08-09T21:21:05Z`; working directory: `PROBE_ROOT\P09`.
- Primary source SHA-256: `6b40732020702b6bb6d298f53765ce8a89c4a3dd20aa606f967ee6b3e7a52f3b`; local include SHA-256: `308d02dd33f007c55998554ad0dc739c41f24d28b675728ba51262c83ec5e18c`.
- Process start succeeded as PID `7352`; duration was `1.210637 s`; exit code was `1`.
- The log named the exact local include path. Log SHA-256: `b546ed732200e86b16769aa63a2e9a018c6634dd1e8c48e08f36872a4c6ba73b`.
- Candidate: 6068 bytes, SHA-256 `ace306afa5e23b3f27cc22363b9fe3e6ed62ae67a3f73c6054686377b33fcf48`; no related process remained.

**INFERENCE**

- A local include is part of the exact build input and the observed compiler log can contribute provider evidence for dependency discovery.

#### P10 — Standard MQL5 Include location

**OBSERVATION**

- Timestamp: `2026-08-09T21:21:24Z`; working directory: `PROBE_ROOT\P10`.
- Primary source SHA-256: `1a8ca79b3f69fe9b3bb5767a4df3faf960cdc9d4f74bb90acf1e312973838928`; it referenced `<Arrays\Array.mqh>`.
- No `/include` override was supplied. Process start succeeded as PID `16436`; duration was `1.168993 s`; exit code was `1`.
- The log reported this exact chain in the terminal data root: `Arrays\Array.mqh` → `Object.mqh` → `StdLibErr.mqh`.
- Read-only identities were: `Array.mqh`, 6965 bytes, SHA-256 `2945e251c682a6bfe000e530caf0df19cba544c29f4ae0dcc65850f08eb28b35`; `Object.mqh`, 2036 bytes, SHA-256 `dfad4fdb6d1bf47cf43fcbc2882e52979459f17a776f75f250a7c32d0623ab35`; `StdLibErr.mqh`, 683 bytes, SHA-256 `04bb2c47b1b04dceb052e6dba1f85e0330c53abc602f341e2ea95ea1498ab28b`.
- Candidate: 5304 bytes, SHA-256 `592991024c3b285d4f58aaf556cc5048ee675a684a54e52ca212d0e9b69b474d`; log SHA-256 `601709f966f917555094790599fea9cc11fafff097731a88783bf16d65720fd8`; no related process remained.

**INFERENCE**

- Standard includes are external build inputs resolved implicitly from the associated terminal data environment. Their exact-byte identities and the relevant root/environment context must be explicit in the claimed input set.

#### P11 — Nested/transitive local include

**OBSERVATION**

- Timestamp: `2026-08-09T21:21:42Z`; working directory: `PROBE_ROOT\P11`.
- Input identities: primary `24eec2160fadd8cc1aa7a1e3c184cf90c027f69a034b6108113d8c8d426a7396`; `level_a.mqh` `0438298757cc4919a16cfd557fc24f94dd997c57bfb859f02da30bee06ac72d3`; `level_b.mqh` `21c8c6ddbe6722d092c5bc4c252ca7edd8d61a4205168b862bb8750bee00bffe`.
- Process start succeeded as PID `20092`; duration was `1.092491 s`; exit code was `1`.
- The log named the exact primary → A → B chain. Log SHA-256: `c9ef8287d966f1683dac8db375e79ab65b29cdfb1a2b5431a199950775938b01`.
- Candidate: 5546 bytes, SHA-256 `5b657f6071d50db6df88e0e28b98f838ce98de2f23b32c5908406da2bc93d5ab`; no related process remained.

**INFERENCE**

- A deterministic manifest must represent transitive inputs, while discovery remains provider-specific. The probe does not prove that compilation logs enumerate every possible dependency form.

#### P12 — Missing include

**OBSERVATION**

- Timestamp: `2026-08-09T21:21:43Z`; working directory: `PROBE_ROOT\P12`.
- Primary source SHA-256: `1d2e59235ec7c056c29ecf7369e3361aca4abac76db7b7be13a4c77a9c310ee9`; the referenced include was deliberately absent.
- Process start succeeded as PID `19136`; duration was `0.446620 s`; exit code was `0`.
- The log named the exact attempted missing path, reported error `106`, and reported one error and zero warnings. Log SHA-256: `43f170c7bcb37270728a9762bfda90415851fcd7378af2a14852bac95a6b5513`.
- No candidate was created and no related process remained.

**INFERENCE**

- Missing dependency is diagnosable from provider evidence in this case, but the numeric diagnostic remains provider-specific and must not leak into core contracts as universal semantics.

### Wave 5 — Process behavior

#### P13 — Process tree

**OBSERVATION**

- Timestamp: `2026-08-09T21:22:45.534Z`; working directory: `PROBE_ROOT\P13`; no related process existed before launch.
- Fixture source: 37 bytes, SHA-256 `58ef26c5f6a0813e3c2f4cdcd99c89f6e8b844209782919defc3209490c7f00b`; no log or candidate existed before invocation.
- Process start succeeded as PID `20704`; duration was `1175.2243 ms`; exit code was `1`.
- Eleven samples observed only the direct `MetaEditor64.exe` process, whose parent was the probe harness. No child process was observed and none remained after exit.
- Candidate: 4796 bytes, SHA-256 `6c0060a1fab62719675678c3a599e3f3841cbe5378d763596a0b4e1bee7f32e2`; log SHA-256 `9f480881f622bfcbb7a4e7906ddebeb05c3325635eb8263b432c91021070aca7`.

**INFERENCE**

- Waiting for the direct process was a usable completion signal for this short isolated compile. Sampling cannot prove that no child is possible for other inputs or versions.

#### P14 — Timeout and owned termination

**OBSERVATION**

- The initial execution started PID `5060`, timed out, and produced the same ownership, termination, and no-output result described below, but its exact start timestamp was not retained. P14 was repeated solely to close that capture gap.
- Repeat timestamp: `2026-08-09T21:40:49.0907006Z`; working directory: `PROBE_ROOT\P14`; no related process existed before launch.
- Fixture source: 37 bytes, SHA-256 `58ef26c5f6a0813e3c2f4cdcd99c89f6e8b844209782919defc3209490c7f00b`; no log or candidate existed before invocation.
- Exact repeat argv: `["C:\\Program Files\\Ava Trade MT5 Terminal\\MetaEditor64.exe", "/compile:\"C:\\Users\\eng_d\\AppData\\Local\\Temp\\EAResearchLab-MetaEditor-Probes-20260809-01\\P14\\probe_timeout.mq5\"", "/log"]`.
- The direct repeat process started as PID `19164`. A deliberately short `10 ms` deadline expired.
- At the timeout observation, Windows process data matched the launched PID and expected executable and showed no child process. Ownership was classified as `direct_pid_verified_no_children`.
- Only that verified direct PID was terminated. Repeat duration was `212.3953 ms`; observed exit code after termination was `-1`.
- No provider log or candidate existed; only the fixture source remained. No related process was present after a further `1.5 s` observation.

**INFERENCE**

- An owned direct process can be terminated safely in the observed no-child case, but future cancellation must re-establish ownership and account for possible process trees. A timed-out build cannot accept any candidate, even if one appears.

#### P15 — Detached or reused behavior

**OBSERVATION**

- Timestamp: `2026-08-09T21:23:34.1719Z`; working directory: `PROBE_ROOT\P15`; no related process existed before launch.
- Fixture source: 37 bytes, SHA-256 `58ef26c5f6a0813e3c2f4cdcd99c89f6e8b844209782919defc3209490c7f00b`; no log or candidate existed before invocation.
- Process start succeeded as PID `5188`; duration was `1281.301 ms`; exit code was `1`.
- Eight samples observed only the direct, newly launched PID. No pre-existing process, child, detachment, reuse, or lingering related process was observed.
- Candidate: 6188 bytes, SHA-256 `48f0a7fdf66cc3dfe2df434bef2fd177b950d027b27c98622da6d12945d6a5af`; log SHA-256 `a24a0e5f87b2af69201169fa6afd2a3b4949eabe0479da9d24dca60368c6aa50`.

**INFERENCE**

- Direct subprocess waiting is viable when no interactive instance is present. Behavior with an already-running MetaEditor remains unresolved because no unrelated process was started, reused, modified, or terminated for this research.

### Wave 6 — Materialized build input

#### P16 — Compilation from a materialized snapshot

**OBSERVATION**

- Timestamp: `2026-08-09T21:24:41Z`; source tree A was `PROBE_ROOT\P16\source_dev`; byte-identical snapshot B and the compile working directory were `PROBE_ROOT\P16\snapshot`.
- Before sealing B, both trees contained: primary source, 93 bytes, SHA-256 `441ec7691b9a243a1ad235c8c0b5ff79c92eaea7ac5acdeb5af6547d1b4f22c4`; `level_a.mqh`, 77 bytes, SHA-256 `1490f9201d6a63ec338d43a06c07aa06342d9bb7188bc7a7bc658befda151b35`; `level_b.mqh`, 39 bytes, SHA-256 `6f996c171f3c8002041484aa5b769b03879cdd4cbf4ffd676bfeb5670228a55e`.
- After B was sealed, only A's `level_b.mqh` was changed; its new SHA-256 was `04071856da211af2e11f89d00140e2822e4d95e4c99185bbba93465302c104d8`. B retained the original hash.
- Exact arguments selected B's primary source. Process start succeeded as PID `2068`; duration was `1.175846 s`; exit code was `1`.
- The log named only B paths for the primary, local, and transitive inputs. No output appeared in A.
- B's inputs were byte-identical before and after compilation.
- Candidate in B: 6098 bytes, SHA-256 `c2bfde715fafa6be75aaf2e7bf6c3b8cd3d524ddb1a98bf8b56e2059ada3771b`; log SHA-256 `982551eeefce7e8f0cfe8f8adb7313474053a837d7aef59acc7f849fe7bf8d53`; no related process remained.

**INFERENCE**

- MetaEditor can compile this primary/local/transitive input set from a materialized snapshot independently of later mutation in a development tree. This supports build-scoped source materialization as the staging boundary.
- P16 does not eliminate external inputs: P10 separately demonstrates that standard includes can still enter from the terminal data environment.

## Cross-probe observations

### Exit, logs, and candidate acceptance

**OBSERVATION**

- Every successful compile exited `1`; every ordinary compiler failure exited `0`.
- MetaEditor emitted no stdout or stderr. Diagnostics and final compiler result were in adjacent UTF-16LE `.log` files when `/log` was supplied.
- Successful compilation produced or replaced the expected adjacent `.ex5`; ordinary failed compilation produced no candidate and removed the P03 expected-name sentinel.

**INFERENCE**

- Future accepted-build logic needs a conjunction of provider-log outcome, a newly observed expected-path candidate, candidate content identity, and absence of timeout/cancellation. Exit code remains evidence but is not a provider-neutral success predicate.
- Build-scoped materialization reduces stale-artifact risk. It does not remove the need to reject candidates after timeout, ambiguous completion, or failed provider evidence.

### Include and Build Input Identity implications

**OBSERVATION**

- The provider log exposed exact paths for tested local, nested, standard, and missing includes.
- The provider resolved standard includes from the terminal data root without an explicit `/include` override.
- P16 compiled a sealed local snapshot and did not read its later-mutated sibling development tree according to paths reported in the log.

**INFERENCE**

- ADR-0010 can retain its provider-neutral Build Input Manifest direction: exact-byte identities must cover the primary source, local/transitive inputs, and observed provider/environment inputs.
- `SourceRevision` and Git cleanliness are not authoritative byte evidence.
- Provider compilation evidence can inform dependency discovery, but the completeness of compiler-log enumeration is not established for conditional, macro-selected, generated, resource, library, or project-mode inputs.
- Digest identity and durable byte retention remain separate concerns.

## Decisions now supported by evidence

- A build may operate on a content-identified materialized snapshot instead of the mutable development working tree.
- Dirty-source builds need not be categorically rejected when the claimed exact input is materialized and identified.
- External standard includes must be explicit members of the claimed input boundary or explicit reproducibility limitations.
- MetaEditor-specific dependency discovery, Windows command-line construction, log decoding, outcome classification, and candidate discovery belong behind the provider adapter boundary.
- Core identifiers remain opaque entity identities; a Build Input Manifest digest remains SHA-256 content identity.
- ADR-0010 can now decide its provider-neutral policy, while retaining explicit limits on dependency-discovery completeness. Its status is not changed by this record.

## Contract evidence, without contract changes

The observations support later consideration of:

- a pre-stable Build Input Manifest contract with deterministic serialization and exact-byte identities;
- a new exact Build Record version referencing the manifest content identity and provider/compiler environment evidence;
- namespaced provider evidence for diagnostics, raw result text, executable identity, and process outcome;
- explicit timeout/cancellation/failure-stage evidence separate from core build outcome.

No schema was added or changed during probe execution. Whether Artifact Manifest needs a direct build-input reference, rather than receiving it through Build Record provenance, remains a design question.

## Unresolved uncertainties

- Explicit output redirection was not tested because no verified switch was available.
- Only MetaEditor `5.0.0.6104`, one installation, and one terminal data environment were observed.
- Behavior with an already-running interactive MetaEditor was not observed.
- The polling probes cannot prove that no child process can ever appear for longer, project-mode, or other builds.
- P14 exercised termination before compilation produced output; partial-output behavior on a later timeout remains unknown and must still be treated as unsafe.
- Compiler-log dependency enumeration completeness is unproven beyond the tested include forms.
- Deterministic repeatability of `.ex5` bytes from repeated identical builds was not tested by this matrix.
- The relationship among terminal installation updates, standard include updates, and retained reproducibility evidence remains a future retention concern.
- Exact Windows command-line serialization for spaces and Unicode requires implementation-level tests when a provider adapter is authorized.

## Scope confirmation

The probes introduced no production package code, provider adapter, process runner, persistence, schema, runtime component, or Phase 02 execution plan. ADR-0010 remains Proposed pending explicit architectural review of these results.
