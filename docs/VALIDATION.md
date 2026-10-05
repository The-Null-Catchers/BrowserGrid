# Validation evidence

Authoring date: 2026-10-04. This records executed checks, not expected results.

| Check | Observed result |
| --- | --- |
| Python control-plane/security/scheduler/executor/worker unit suite | 146 passed; 7 PostgreSQL-specific tests skipped in this job and passed in the dedicated PostgreSQL job |
| Ruff lint and formatting | Passed |
| Next.js TypeScript check | Passed |
| Next.js production build | Passed, version 15.5.27 |
| API schema and Compose/workflow configuration syntax | Python/JSON/YAML syntax validated |
| Alembic on a clean SQLite database | Upgrade to head and downgrade to base passed; legacy artifact/source migrations preserve readiness |
| Python dependency audit against pinned lockfile | No known vulnerabilities reported by pip-audit |
| Web/runtime npm production dependency audit | Zero vulnerabilities reported after compatible patch/override updates |
| JavaScript runtime/reporter/SDK/fixture syntax | Passed |
| Node runtime/SDK contracts | 16 passed; includes repository test discovery with a separate Playwright installation, a real SIGTERM child process and bounded console/network capture regressions |
| Actual Playwright CLI/config/reporter → Python parser | Passed locally: mixed outcomes, successful subset and discovery error; no page/browser fixtures |
| Clean PostgreSQL migration / concurrent acquisition | Passed on GitHub Actions: clean upgrade/downgrade/upgrade and all 7 PostgreSQL acceptance tests |
| Docker image builds / Compose startup | Passed on GitHub Actions after replacing unavailable MinIO registry images with a pinned source build |
| Real Chromium/Firefox/WebKit E2E | Passed on GitHub Actions: matrix, uploaded ZIP, results, screenshot/video/trace downloads, console/network JSON, assertion failure and active cancellation with sandbox removal |
| Live worker-crash/watchdog recovery acceptance | Passed: WORKER_LOST fencing, restarted-worker reaping and independent watchdog timeout with the worker stopped |
| Live sandbox/network escape tests | Limited live acceptance passed: fixture allowed; host and published-port DNAT canaries blocked; metadata proxy request denied. Comprehensive DNS rebinding/IPv6/UDP probes remain pending |
| Container OS vulnerability scan | Not executed |
| Dashboard browser/visual/accessibility QA | Not executed; build/type checks do not substitute for these |
| GitHub CI / repository push | Published to The-Null-Catchers/BrowserGrid; all six jobs passed at commit 68529ae058d75aa19e7886023ce941fc18dfaff1 |

Unit executor/worker tests deliberately use doubles to test orchestration and cleanup. They do not establish that a browser launched. `infra/scripts/e2e.py` and the `isolated-browser-e2e` CI job exercise the real path without substituting a mock browser.

The local test environment used Python 3.12.14 and Node 24.19.0. GitHub CI passed control-plane, PostgreSQL, runtime and web checks on the configured Python 3.13 / Node 22 targets. The browser runtime pins Playwright and its image to 1.58.2; actual engine versions are recorded on launch, not invented.

One local warning remains: the installed Starlette TestClient warns that its httpx transport is deprecated. This did not fail the tests. The live execution gate passed; this does not certify completion of the entire product specification.

Dependency audits reflect their current advisory databases and do not guarantee absence of vulnerabilities. The web lockfile uses explicit patched overrides for transitive postcss/sharp dependencies; the production build was rechecked after updating them.

## Execution integrity follow-up

Additional executed regressions cover duplicate worker-ID acquisition, cross-worker lease heartbeat rejection, bounded/consistent Playwright report parsing (including expected failures and flaky retries), and ZIP canonical paths, file collisions and required lockfiles. Malformed reports receive `RESULT_REPORT_INVALID` instead of a passed result.

Eight firewall guard unit cases cover IPv4/IPv6 host and cross-bridge deny rule construction, read-only health checks, failed installation, invalid interface names and restoration ahead of an earlier accept rule. These checks do not establish live packet filtering. The new guard image has not been built here. Previously executed web build and dependency audits were not repeated because web/dependency files did not change in this follow-up.

## Cancellation and retention follow-up

Eighteen additional executed regressions verify independent sandbox removal during blocked artifact collection/upload, wall timeout, heartbeat outage and worker shutdown; expired preparation cannot create a sandbox. TAR validation now covers directory metadata as well as files, canonical names, duplicate entries, file/directory collisions, path/entry bounds and transport size before parsing.

The scheduler runs artifact retention in a separate session/thread so stalled object storage does not block lease recovery. An object-specific deletion failure leaves its metadata for retry and does not prevent deletion of other expired objects. Both behaviors have executed regression checks.

The real Docker smoke script now waits for the slow job to reach `running` before cancelling it and checks removal of its sandbox. That acceptance script remains unexecuted here. These worker tests use a deliberately stalled transport and backend double; they establish orchestration behavior, not real browser or Docker acceptance. Node/web/dependency checks were not rerun in this follow-up because their source/dependencies were unchanged.

## Runtime exit and output integrity follow-up

The full Python suite now includes runtime-output regressions for count and serialized-byte bounds, repeated state/runtime messages, continued lifecycle/completion processing after truncation, invalid exit codes, non-finite/deep JSON, schema labels unaffected by secret masking, and prevention of a passing run when the command exits nonzero despite a passing report.

Node contract tests launch an actual child process that terminates itself with SIGTERM and verify exit status 143, instead of treating Node's null exit code as zero. This is a real process test, not a browser execution. BrowserGrid records normalized process exit events; the dashboard now subscribes to these and output-truncation events. Next.js type checking and production build were rerun successfully after this frontend change. Browser/dashboard E2E remains pending.

Ordinary worker output is bounded to 10,000 events and 4 MiB of serialized event payloads per job. One truncation event is emitted; subsequent ordinary output is dropped. Forward-only lifecycle states, one runtime identity, one critical runtime error and one completion event remain available beyond that budget. Runtime metadata accepts only bounded browser version and the pinned Playwright version; it cannot overwrite worker/image/source metadata. Dependency advisory audits were not rerun because no dependency files changed.

## Tenant scheduling and PostgreSQL acceptance follow-up

Four additional local SQLite regressions cover oldest-job ordering across tenants, scheduling another tenant when one is at capacity, rejection of a queued job without a lease token, and recovered cancellation without a failure code. Acquisition locks one eligible workspace, rechecks capacity after locking and claims its earliest queued job. A savepoint handles concurrent registration of the same worker ID. Recovery handles one active workspace per transaction and does not lock empty workspaces.

Seven PostgreSQL acceptance tests are now provided: atomic quota under six concurrent workers, skipping a separately locked workspace, acquisition lock scope, duplicate worker-ID registration, stale-session fencing after recovery, global oldest-job order and recovery lock scope. These seven tests were skipped locally because no PostgreSQL service/binaries are available. They must pass in the configured CI job before claiming these lock/race semantics are verified.

PostgreSQL tests create and remove only a uniquely named `bg_test_...` schema per test, instead of dropping application tables. Test connections use statement and lock timeouts to fail contention problems rather than hang indefinitely. The CI database remains disposable. Runtime/web sources were unchanged in this follow-up, so their previously executed five Node contracts and production web build were not repeated.

## Uploaded-source reservation follow-up

Twelve additional local regressions cover a durable source reservation before object writes, successful readiness acknowledgment, lost upload responses with generic 503 errors, denial of pending sources, expiry/removal before completion, ZIP rejection before reservation, Viewer/cross-workspace/read-only API-key upload denial, cross-project source denial, retryable pending cleanup with ready-source preservation, migration compatibility/reversal and worker rejection of unready sources before storage access.

Migration 0003 adds indexed reservation expiry and source readiness. Historical bundles become ready with no expiry; new uploads remain pending for up to one hour until object storage acknowledges success. Cleanup deletes abandoned objects before their pending rows. Successful source objects are retained for reruns; project lifecycle deletion remains unfinished.

The real Docker smoke script now also uploads a ZIP with the pinned Playwright lockfile, runs it in Chromium through the repository-local CLI and instrumented fixture, checks an individual test result and downloads a PNG screenshot with its signature. This added source path has not been executed locally. SQLite migration upgrades/downgrades and legacy-row compatibility were executed; PostgreSQL migration and real S3/Docker acceptance remain pending CI. No runtime/web dependencies or frontend source changed in this follow-up.

## Console and network capture follow-up

Eleven additional SDK regressions cover delayed response metadata, bounded draining of stalled reads, immutable completed snapshots, failed and still-active requests, concurrent request limits, duplicate terminal events, preserved unrelated listeners, sanitized URLs, console bounds, preserved HTTP status after a size-read error, and writing actual JSON attachments when the test body fails. The full Node suite passed all 16 tests. Capture tests use event/request doubles; they do not establish actual browser capture. Ruff lint/format, JavaScript syntax and diff whitespace checks passed.

The real Docker smoke script now asserts a known console message and a successful fixture fetch in downloaded JSON artifacts for every matrix job and the uploaded-bundle job. This acceptance remains unexecuted. The collector stops its listeners before a two-second metadata drain, marks unfinished records explicitly and bounds console/network records to 1,000 each. No dependencies or frontend source changed; their previous audits/build were not repeated.

## Actual report interoperability follow-up

`infra/scripts/report_contract.py` ran the pinned Playwright CLI against six actual tests, using the same generated-config helper and reporter as the sandbox runtime. BrowserGrid parsed the resulting JSON and correctly classified passed, failed, flaky, skipped, expected-failure and timed-out cases. Assertions also checked retry history, error retention, nine real reporter attempt events and enforcement of the selected project/viewport over original configuration.

A filtered passing run returned process exit code zero and one passing result. A separate test-file discovery exception returned nonzero, no test rows and a global error report. These three CLI executions use no report mocks and were executed locally; they do not launch a browser or exercise Docker, scheduling or storage. The configured runtime CI job now runs the same Python/Node interoperability script. It has not run remotely. Dependencies, frontend and Python business logic are unchanged; previous unit suites/audits/build were not repeated.

## First GitHub validation

The source was published after explicit approval to the public repository, preserving the nine incremental changes as commits with references to their original local IDs. The final uploaded Git tree matched the local source tree exactly. The [first CI run](https://github.com/The-Null-Catchers/BrowserGrid/actions/runs/37238102249) passed control-plane, PostgreSQL, runtime contracts, web build/audit and dependency/secret checks. PostgreSQL clean migrations and all seven contention tests ran successfully. Previous notes about absent remote execution describe the earlier authoring stage.

Isolated browser acceptance initially stopped before builds because the pinned MinIO image could not be pulled from Docker Hub; a Quay attempt also returned an authorization error. The local storage service now builds official MinIO security-release source at an exact commit with a non-root runtime. The [source-build CI run](https://github.com/The-Null-Catchers/BrowserGrid/actions/runs/37238282547) built the images and started the stack, then failed at sandbox input transfer: Docker's archive API rejected the read-only rootfs despite the writable tmpfs.

Input now streams through a non-root, unprivileged tar exec into `/work`, preserving the read-only rootfs, bounded tmpfs, capabilities and network policy. Local executor checks verify transfer metadata, readiness ordering, exit failures, bounded exec output and sandbox cleanup. These use Docker API doubles; the later acceptance below verifies the actual Docker path.

## Passing Docker execution acceptance

[CI run 37240077248](https://github.com/The-Null-Catchers/BrowserGrid/actions/runs/37240077248) passed all six jobs at commit `68529ae058d75aa19e7886023ce941fc18dfaff1`. This supersedes the earlier pending browser, PostgreSQL, network and recovery notes above; those sections preserve the earlier authoring history.

The clean Compose build/startup and real API → durable queue → worker → disposable container → Playwright → S3/DB path passed. The matrix launched Chromium, Firefox and WebKit against the deterministic fixture, produced individual passing results, and downloaded nonempty screenshots, videos and traces. Console and network JSON contained the expected console message and successful fixture fetch for each browser. A separately uploaded ZIP installed its pinned dependencies, ran the repository-local CLI, returned a passing individual result and produced a PNG with the expected signature and log attachments. An intentional assertion failed as a test failure; an active run cancelled and its sandbox was removed.

The live network script proved both host and published-port canaries reachable from the engine host before and after execution, then verified they were unreachable from the Chromium sandbox. Fixture access succeeded and the proxy denied a metadata request. This verifies those routes on the CI host, not exhaustive SSRF, DNS rebinding, IPv6 or UDP protection.

The recovery script killed and stopped the trusted worker during an active execution. The scheduler returned `infrastructure_failed` with `WORKER_LOST`; restarting the worker reaped the orphaned sandbox. A second execution reached its wall deadline and the independent watchdog removed its sandbox while the worker remained stopped; the scheduler recorded `timed_out` with `RUN_TIMEOUT`.

Actual CI exposed and drove fixes for unavailable MinIO registry images, archive transport on a read-only rootfs with tmpfs, browser child-namespace `chroot` filtering and Docker's default noexec workspace mount. Artifact collection now uses bounded non-root tar exec output; `/work` explicitly permits execution while remaining `nosuid,nodev`. All capabilities remain dropped, rootfs read-only and seccomp enabled. No browser result was substituted to pass acceptance.

Git repository checkout against an external repository, multi-viewport browser acceptance, the dashboard's own browser E2E, rich media viewers and comprehensive production security/observability remain separate work. The CI artifact `execution-evidence` retains Compose logs under GitHub's artifact retention policy.

## Six-job matrix and Git source follow-up

[CI run 37240669670](https://github.com/The-Null-Catchers/BrowserGrid/actions/runs/37240669670) passed all six jobs at commit `7b379a170982c603da3257356b44f3de56942795`. The real browser test now runs Chromium, Firefox and WebKit at both 1440×900 and 390×844, checks all six individual results, verifies downloaded PNG IHDR dimensions and requires screenshot/video/trace plus console/network evidence for every job. This supersedes the earlier multi-viewport pending note.

A committed `fixture-repository/` now exercises public HTTPS Git fetching at the exact CI checkout SHA, a nested working directory, pinned dependency installation, the repository-local CLI and user configuration with enforced viewport settings. The test reads actual `git rev-parse HEAD` inside the sandbox and attaches its observed SHA; the acceptance script checks that downloaded attachment and a 1024×768 PNG. A second run requests a nonexistent all-zero commit and requires `REPOSITORY_CLONE_FAILED` with no test rows. Local syntax checks, all 16 Node contracts and actual Playwright discovery of this fixture passed. The new Git browser path still requires CI execution; these local checks do not establish checkout, browser or network success.

## Passing pinned Git source acceptance — 2026-10-05

[CI run 37341003027](https://github.com/The-Null-Catchers/BrowserGrid/actions/runs/37341003027) passed at code commit `8bb5816d232e398ad80a1e5dacd693dee28299f7`: control-plane, PostgreSQL, runtime contracts, web, dependency/security and isolated execution. The Docker test fetched this public repository at that immutable SHA through the sandbox egress proxy, installed the nested fixture lockfile with scripts disabled, and ran actual Chromium through the repository-local CLI. User configuration loaded, the enforced 1024×768 viewport won, and the downloaded checkout JSON matched actual `git rev-parse HEAD`. The screenshot dimensions and expected console/network data were verified. A nonexistent commit became `infrastructure_failed` / `REPOSITORY_CLONE_FAILED` with no test rows.

The initial attempt exposed that a Playwright body attachment is embedded in its JSON report rather than guaranteed to exist as a downloadable object. The fixture now writes its checkout evidence to disk and attaches that path; a separate actual Playwright CLI execution verified the resulting attachment filename. This follow-up also passed the six-job browser/viewport matrix, uploaded ZIP execution, intentional failure/cancellation, existing limited network probes and worker-loss/watchdog recovery. Local executor/security tests passed (51), Node contracts passed (16), lint/formatting passed and the actual CLI/reporter/parser contract passed. This supersedes the preceding pending Git source note; dashboard browser E2E remains the next acceptance gate.
