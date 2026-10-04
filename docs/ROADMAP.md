# Delivery scope and acceptance gates

The requested product spans ten phases. This source delivery has a verified execution core, **not completion of the full specification**. The real Docker execution gate passed in [CI run 37240077248](https://github.com/The-Null-Catchers/BrowserGrid/actions/runs/37240077248), allowing incremental quality work to begin. Earlier phases still have the broader gaps listed below.

| Phase | Implementation status | Acceptance status |
| --- | --- | --- |
| 1. Foundation | API, sessions, RBAC, workspace/project creation, database migration, Redis, Compose, dashboard | Unit/build checks, clean PostgreSQL migrations and fresh Compose startup passed; dashboard browser E2E pending |
| 2. Execution core | DB queue, leases, concurrency, Docker executor, Chromium runtime, explicit states | Real API/queue/worker/Docker/Playwright path passed for inline and uploaded ZIP; external Git checkout acceptance pending |
| 3. Results | JSON results, retries/flaky classification, private artifacts, failure/log display | Parser/file checks and real result/artifact capture/download passed; richer result UI pending |
| 4. Realtime | SSE replay, timeline, bounded logs, cancellation, lease recovery | State/security tests and live cancellation/worker-loss/watchdog recovery passed; browser UI streaming acceptance pending |
| 5. Browser matrix | Chromium/Firefox/WebKit configuration, viewport matrix | Real three-browser run passed; multi-viewport live acceptance pending |
| 6. Debugging | Video/trace/screenshots; instrumented page console/network JSON | Actual capture/download and expected console/network content passed; full viewers/filters pending |
| 7. Quality | Fixture includes deterministic accessibility/visual/network cases | Axe scans, responsive URL mode and performance metrics not implemented |
| 8. Visual testing | No fabricated baselines or diffs | Baselines, pixel comparison and approvals not implemented |
| 9. Integrations | Scoped API keys, basic API-token CLI, run idempotency | GitHub Apps/webhooks/checks, webhook delivery, schedules not implemented |
| 10. Production hardening | Initial quotas, ZIP/TAR controls, secret encryption, retention, health checks, independent watchdog, upload reservations, CI files, docs | Watchdog, PostgreSQL contention and limited live network probes passed; full observability, image scans, deletion reconciliation and external security validation pending |

Other unfinished requirements include email verification/reset, invitation lifecycle and ownership transfer, persistent project configuration UI, platform-admin area, search and run comparison, dashboard analytics beyond recent-run summaries, embedded media/trace viewer, rich network filtering, in-app notifications and portfolio screenshots from verified runs.

## Next acceptance and delivery work

1. Extend actual execution acceptance to multiple viewports and a pinned public Git repository.
2. Add dashboard browser E2E for account/project creation, live results, failure inspection and cancellation; capture portfolio screenshots from those verified flows.
3. Add axe accessibility scans, responsive URL captures and measured performance data incrementally, with real fixture acceptance for each.
4. Expand live network probes to private control-plane services, IPv6, UDP and DNS rebinding; rerun existing host/DNAT/metadata probes on each deployment host.
5. Implement visual baseline comparison and approval after the quality execution paths are stable.
6. Complete lifecycle deletion, image scanning, observability and the remaining foundation/integration requirements before a production release.

No phase is certified complete while its required integration tests remain unexecuted.
