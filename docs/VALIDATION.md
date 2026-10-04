# Validation evidence

Authoring date: 2026-10-04. This records executed checks, not expected results.

| Check | Observed result |
| --- | --- |
| Python control-plane/security/scheduler/executor/worker unit suite | 123 passed; 1 PostgreSQL-specific test skipped |
| Ruff lint and formatting | Passed |
| Next.js TypeScript check | Passed |
| Next.js production build | Passed, version 15.5.27 |
| API schema and Compose/workflow configuration syntax | Python/JSON/YAML syntax validated |
| Alembic on a clean SQLite database | Upgrade to head and downgrade to base passed; legacy artifact migration preserves readiness |
| Python dependency audit against pinned lockfile | No known vulnerabilities reported by pip-audit |
| Web/runtime npm production dependency audit | Zero vulnerabilities reported after compatible patch/override updates |
| JavaScript runtime/reporter/SDK/fixture syntax | Passed |
| Node runtime contracts | 5 passed; includes real repository test discovery with a separate Playwright installation and a real SIGTERM child-process regression |
| Clean PostgreSQL migration / concurrent acquisition | Not executed locally; dedicated CI job provided |
| Docker image builds / Compose startup | Not executed: Docker unavailable and effective Linux capabilities are zero |
| Real Chromium/Firefox/WebKit E2E | Not executed: no Docker; attempted Chromium download produced a truncated/non-ZIP response |
| Live worker-crash/watchdog recovery acceptance | Not executed; disposable-stack script and CI step provided |
| Live sandbox/network escape tests | Not executed; positive-control host/DNAT/metadata acceptance script and CI step provided |
| Container OS vulnerability scan | Not executed |
| Dashboard browser/visual/accessibility QA | Not executed; build/type checks do not substitute for these |
| GitHub CI / repository push | Not executed; no remote repository was supplied or created |

Unit executor/worker tests deliberately use doubles to test orchestration and cleanup. They do not establish that a browser launched. `infra/scripts/e2e.py` and the `isolated-browser-e2e` CI job exercise the real path without substituting a mock browser.

The local test environment used Python 3.12.14 and Node 24.19.0. Docker/CI target Python 3.13 and Node 22. CI must verify those target versions before a release. The browser runtime pins Playwright and its image to 1.58.2; actual engine versions are recorded on launch, not invented.

One local warning remains: the installed Starlette TestClient warns that its httpx transport is deprecated. This did not fail the tests. No required live execution phase is certified complete.

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
