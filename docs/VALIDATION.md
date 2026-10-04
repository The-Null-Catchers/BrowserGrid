# Validation evidence

Authoring date: 2026-10-04. This records executed checks, not expected results.

| Check | Observed result |
| --- | --- |
| Python control-plane/security/scheduler/executor/worker unit suite | 59 passed; 1 PostgreSQL-specific test skipped |
| Ruff lint and formatting | Passed |
| Next.js TypeScript check | Passed |
| Next.js production build | Passed, version 15.5.27 |
| API schema and Compose/workflow configuration syntax | Python/JSON/YAML syntax validated |
| Alembic on a clean SQLite database | Upgrade to head and downgrade to base passed; legacy artifact migration preserves readiness |
| Python dependency audit against pinned lockfile | No known vulnerabilities reported by pip-audit |
| Web/runtime npm production dependency audit | Zero vulnerabilities reported after compatible patch/override updates |
| JavaScript runtime/reporter/SDK/fixture syntax | Passed |
| Node runtime contracts | 3 passed; includes real repository test discovery with a separate Playwright installation |
| Clean PostgreSQL migration / concurrent acquisition | Not executed locally; dedicated CI job provided |
| Docker image builds / Compose startup | Not executed: Docker unavailable and effective Linux capabilities are zero |
| Real Chromium/Firefox/WebKit E2E | Not executed: no Docker; attempted Chromium download produced a truncated/non-ZIP response |
| Live worker-crash/watchdog recovery acceptance | Not executed; disposable-stack script and CI step provided |
| Live sandbox/network escape tests | Not executed |
| Container OS vulnerability scan | Not executed |
| Dashboard browser/visual/accessibility QA | Not executed; build/type checks do not substitute for these |
| GitHub CI / repository push | Not executed; no remote repository was supplied or created |

Unit executor/worker tests deliberately use doubles to test orchestration and cleanup. They do not establish that a browser launched. `infra/scripts/e2e.py` and the `isolated-browser-e2e` CI job exercise the real path without substituting a mock browser.

The local test environment used Python 3.12.14 and Node 24.19.0. Docker/CI target Python 3.13 and Node 22. CI must verify those target versions before a release. The browser runtime pins Playwright and its image to 1.58.2; actual engine versions are recorded on launch, not invented.

One local warning remains: the installed Starlette TestClient warns that its httpx transport is deprecated. This did not fail the tests. No required live execution phase is certified complete.

Dependency audits reflect their current advisory databases and do not guarantee absence of vulnerabilities. The web lockfile uses explicit patched overrides for transitive postcss/sharp dependencies; the production build was rechecked after updating them.
