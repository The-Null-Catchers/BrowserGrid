# Delivery scope and acceptance gates

The requested product spans ten phases. This source delivery is the initial foundation and execution implementation, **not completion of the full specification**. Work on quality, visual regression and integrations is gated by a passing real Docker execution path.

| Phase | Implementation status | Acceptance status |
| --- | --- | --- |
| 1. Foundation | API, sessions, RBAC, workspace/project creation, database migration, Redis, Compose, dashboard | Unit tests and web build pass; fresh PostgreSQL/Compose acceptance pending |
| 2. Execution core | DB queue, leases, concurrency, Docker executor, Chromium runtime, explicit states | Blocked in authoring environment; actual Docker browser E2E must pass |
| 3. Results | JSON results, retries/flaky classification, private artifacts, failure/log display | Parsers and file boundary tests pass; actual artifact capture pending |
| 4. Realtime | SSE replay, timeline, bounded logs, cancellation, lease recovery | State/security unit tests pass; live cancellation/recovery acceptance pending |
| 5. Browser matrix | Chromium/Firefox/WebKit configuration, viewport matrix | Three-browser acceptance pending |
| 6. Debugging | Video/trace/screenshots; instrumented page console/network JSON | Runtime implemented; collection unverified; full viewers/filters pending |
| 7. Quality | Fixture includes deterministic accessibility/visual/network cases | Axe scans, responsive URL mode and performance metrics not implemented |
| 8. Visual testing | No fabricated baselines or diffs | Baselines, pixel comparison and approvals not implemented |
| 9. Integrations | Scoped API keys, basic API-token CLI, run idempotency | GitHub Apps/webhooks/checks, webhook delivery, schedules not implemented |
| 10. Production hardening | Initial quotas, ZIP/TAR controls, secret encryption, retention, health checks, CI files, docs | Full observability, watchdogs, deletion reconciliation and external validation pending |

Other unfinished requirements include email verification/reset, invitation lifecycle and ownership transfer, persistent project configuration UI, platform-admin area, search and run comparison, dashboard analytics beyond recent-run summaries, embedded media/trace viewer, rich network filtering, in-app notifications and portfolio screenshots from verified runs.

## Next gate: real execution

1. Run clean PostgreSQL migrations and distributed job acquisition tests.
2. Start the Linux Docker Compose stack from an empty set of volumes.
3. Run `make e2e`: Chromium first, then Firefox/WebKit, assertion failure, screenshot/video/trace download, console/network attachments and cancellation.
4. Kill a worker during an active test, wait for lease recovery, restart a worker and verify container reaping and fenced results.
5. Test proxy denial and direct-network denial of metadata, host gateway, control-plane services, private IPv4/IPv6 and DNS rebinding.
6. Record real screenshots and CI run links only after these checks pass.

No phase is certified complete while its required integration tests remain unexecuted.
