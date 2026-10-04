# Deployment

## Local evaluation

```bash
cp .env.example .env
docker compose up --build -d
python infra/scripts/e2e.py
```

Inspect `docker compose logs api scheduler worker egress` if the E2E fails. Do not bypass seccomp, run sandboxes privileged or disable the network boundary to make the test pass. No production release is currently certified.

Docker Compose assumes Linux x86_64 and the fixed local sandbox subnet `172.30.0.0/24`. If that conflicts with your host networks, change the bridge subnet, fixture address and proxy fixture ACL together. Each sandbox has a unique ID label; no shared unsafe test filesystem is reused.

## Single-server preparation

1. Replace local PostgreSQL and MinIO passwords with generated deployment credentials.
2. Set `BG_ORIGINS` to the exact dashboard HTTPS origin and `BG_SECURE_COOKIES=true`.
3. Route the web service through Caddy using `infra/caddy/Caddyfile`; enable only your expected host.
4. Keep PostgreSQL, Redis, Docker API and MinIO console private. Compose port mappings bind to loopback by default.
5. Serve artifact storage through a separate HTTPS object-storage endpoint; set `BG_S3_PUBLIC_ENDPOINT` to it.
6. Preserve the `state` encryption-key volume. Back it up separately from the database, encrypted and access-controlled. Losing the key makes existing project secrets unreadable.
7. Run migrations through the `init` service and preserve database/object volumes. `docker compose down -v` is destructive and used only by disposable CI.
8. Run the real browser E2E and network/isolation acceptance tests before allowing anyone outside the trusted team.

The trusted worker in local Compose mounts the Docker socket. The API/web do not, and execution containers never receive it. Colocating trusted worker and API is a local evaluation topology; production should separate execution nodes.

## External PostgreSQL and Redis

Set `BG_DATABASE_URL` and `BG_REDIS_URL` in a deployment override. The supplied Compose file explicitly constructs these settings for its local services, so override their entries in API, worker, scheduler and init service environments, not just `.env`. Use TLS/private networking and least-privilege database accounts appropriate to each component.

Run Alembic upgrade before starting the new API. Migration downgrade is a development rollback aid, not a replacement for backups. Clean PostgreSQL migration and row-lock contention checks are release gates; SQLite validation alone is insufficient.

## S3 / R2

Set `BG_S3_ENDPOINT`, `BG_S3_PUBLIC_ENDPOINT`, `BG_S3_ACCESS_KEY`, `BG_S3_SECRET_KEY` and `BG_S3_BUCKET`. Both endpoints must refer to the same bucket; the public endpoint is used to sign browser downloads and may need a provider's canonical hostname. Configure explicit dashboard origins if preview access is added later. Current downloads use attachment disposition and do not require embedded public bucket access.

Create the bucket using a provisioning credential, then give workers narrowly scoped put/get permissions and the retention scheduler delete permissions. The current development stack shares credentials; split them before production. Never place storage credentials in project environment variables.

## Additional worker nodes

- Build/pull `browsergrid-runtime:1.58.2` on each engine; deploy the exact image/tag with a recorded digest.
- Create the node's internal sandbox bridge and a proxy with the same reviewed private-address deny policy.
- Ensure `BG_SANDBOX_NETWORK` and `BG_EGRESS_PROXY` match the node's local network.
- Start one trusted `python -m browsergrid.worker` process per desired simultaneous job; give each a unique `BG_WORKER_ID` when explicitly configured.
- Provide protected access to the encryption key, PostgreSQL, Redis and object storage.
- Respect workspace concurrency; increasing worker count does not bypass it.
- Run reapers/watchdogs independently for recovery when a worker node fails. The supplied `watchdog` service must run once per Docker engine; it uses labels and does not need shared files or control-plane credentials. Supervision across failed hosts remains the operator’s responsibility.

For local scaling, `docker compose up --scale worker=2 -d` uses the same trusted daemon and bridge. Start small; the fixture's two-job concurrency can consume more than 4 GiB of total host memory, in addition to the database/web/storage services.

## Operations

`/health` checks process liveness. `/ready` checks PostgreSQL, Redis and the configured S3 bucket. It does not claim that a browser worker is available. The worker page shows persisted heartbeat health to workspace Owners/Admins.

The scheduler sweeps stale leases every five seconds and expired artifacts every minute. It deletes objects before removing their metadata, retrying storage failures. An independent Docker watchdog checks sandbox deadlines every two seconds. Prometheus/Grafana and OpenTelemetry remain on the release roadmap.

For a **disposable test stack only**, run `python infra/scripts/recovery_e2e.py --disposable-stack` after the main E2E. This intentionally kills/stops the worker and verifies stale-lease recovery, reaping and watchdog-only timeout; it must not be run against an active shared deployment.
