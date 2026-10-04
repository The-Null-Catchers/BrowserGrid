# Security model and release limitations

This is an early implementation. It has security regression tests, but it has not completed real Docker, network escape, browser sandbox or production penetration validation. Do not treat it as a public hostile-code execution service.

## Threat boundary

Untrusted project code runs only in disposable browser containers. The API never calls a user subprocess. The trusted worker has control-plane credentials and Docker-engine access; compromising that worker can compromise its host. Local Compose colocates services for development; production execution nodes should be separate from the API/database host.

The container boundary reduces exposure; it is not a perfect hostile-code sandbox. A shared kernel remains an attack surface. Stronger adversarial deployments need dedicated VMs/microVMs or a suitably hardened runtime, patched hosts, admission controls and external network enforcement.

## Enforced sandbox configuration

- UID/GID 1000; read-only root filesystem; no host mounts, Docker socket or published ports.
- Drop all capabilities; `no-new-privileges`; version-pinned upstream Playwright seccomp profile.
- 2 CPU, 2 GiB RAM with equal swap limit, 256 PIDs.
- 1 GiB `/work` tmpfs, 128 MiB `/tmp`, 256 MiB shared memory. These mounts also consume the memory allowance.
- Timeout of 10–900 seconds, checked by the worker and scheduler, with an independent Docker watchdog enforcing the sandbox wall deadline.
- Internal Docker bridge without direct internet egress; a separate host firewall guard restricts host and cross-bridge traffic. Proxy and fixture traffic remains available on the sandbox bridge.

The worker monitor attempts independent sandbox removal on cancellation, shutdown, deadline or failed lease confirmation even while the main execution thread is blocked on artifact transport/storage. Docker API and host failures can still prevent removal; this is not a hard real-time guarantee.

The independent watchdog reads deadlines from Docker labels and removes expired sandboxes every two seconds without database access or worker liveness. It has engine access, no network, and no project/storage credentials. The scheduler also fences jobs at their authoritative deadline. Watchdog enforcement depends on the daemon, watchdog process and host clock remaining healthy; it is not a hypervisor guarantee. Real worker-crash and watchdog acceptance is supplied in `infra/scripts/recovery_e2e.py` but has not run in the authoring environment.

The Playwright seccomp profile is copied from the upstream `v1.58.2` Docker utilities. User namespace availability and AppArmor compatibility must be validated on the destination kernel; do not resolve browser launch failures with `--privileged` or unconfined seccomp.

## Network / SSRF

The egress proxy denies loopback, private IPv4, link-local, metadata, multicast, carrier NAT, private IPv6 and mapped IPv4-in-IPv6 destinations. Only HTTP port 80 and HTTPS CONNECT port 443 are allowed. ACLs evaluate the resolved destination. The local fixture exception requires both its fixed IP and hostname on port 8080.

User code can ignore proxy environment variables, but its bridge has no direct external route. An internal Docker network still permits gateway/host communication; it is insufficient by itself. The trusted `network-guard` service joins the host network with only `NET_ADMIN`, no Docker socket, mounts or control-plane credentials. It installs IPv4/IPv6 INPUT drops from the dedicated `bg-sandbox` interface and FORWARD drops from that interface to other interfaces, covering host services and published-port DNAT into other networks. It reasserts these scoped rules every two seconds; worker startup requires a successful guard health check. Rules deliberately persist on process exit to avoid exposing live sandboxes. The guard must be supervised on every execution host; Docker/host-firewall rule ordering changes are a reason to rerun live acceptance, not a security guarantee.

`infra/scripts/network_e2e.py --disposable-stack` starts host and Docker-published canaries, proves both accessible from the engine host before and after a real Chromium run, and verifies the sandbox cannot connect to them. It also checks allowed fixture access and proxy denial of the metadata address. This is a limited acceptance probe, not comprehensive DNS rebinding/IPv6/UDP coverage, and has not run locally. Sandboxes must never join the control-plane network. Test the effective rules on your actual Docker host, including DNS rebinding, IPv6, UDP and host gateway routes, before claiming isolation. Those network escape tests have not run here. Arbitrary custom proxy targets and private production application access are not supported yet.

## Tenancy and credentials

Every project, run and artifact route authorizes against persisted membership. Worker writes require a nonempty matching lease token and an active job; queued/terminal jobs cannot accept lease writes. Recovery clears the token before stale sessions can continue. PostgreSQL contention/fencing acceptance remains pending. API keys are bound to one workspace and require scopes in addition to the creator's current role. Owners/Admins can manage members and keys; Viewers cannot write. Platform administration has not been implemented and cannot be obtained through a workspace role.

Passwords use Argon2. Opaque browser-session tokens are stored as SHA-256 digests; cookies are HTTP-only, SameSite=Lax, and Secure in HTTPS deployments. Cookie mutations require an allowed Origin. Login rotates the caller's existing session; logout revokes it. Redis write rate limits fail closed. CORS uses explicit configured origins.

Project secrets are encrypted with Fernet, using a persistent key generated on first startup. Secret values are not returned through project APIs. Worker injection never includes database/storage credentials. Reserved execution environment names are rejected.

Worker stdout is treated as untrusted input. Ordinary output has event-count and serialized-byte limits; malformed or repeated control messages cannot bypass those limits. Lifecycle transitions are forward-only and critical control data is normalized. Fixed protocol labels are validated before free-text redaction so a secret coinciding with a state name cannot break execution. Runtime stdout and reports are generated in a code-controlled sandbox and do not attest that a malicious test author honestly tested their application. They never authorize tenant operations or override immutable job/worker/image identities.

Log masking covers literal, URL-encoded and base64 secret values but cannot prevent encoded exfiltration by malicious code. Screenshots, video and trace archives may contain secrets and tokens; restrict artifact readers and retention accordingly. Do not inject credentials into tests from untrusted repositories.

Instrumented console-source and network URLs strip user information, query strings and fragments. Opaque schemes such as data URLs retain only their scheme. Console message text, URL paths and browser failure messages can still contain sensitive data; URL sanitization does not make these artifacts safe for public sharing. Response metadata errors use generic descriptions rather than raw transport exceptions.

## File controls

ZIP upload validation rejects absolute/traversal paths, symlinks, non-canonical names, file/directory collisions, special files, duplicate names, node_modules/.git entries, oversized and high-ratio expansion, and too many members. Bundles require package.json, package-lock.json and test files before queueing. Uploads require a project write role and runs:write API-key scope. A committed pending reservation precedes object writes; the API exposes a usable bundle ID only after storage acknowledgment and a valid completion transaction. Pending bundles cannot create jobs. Cleanup targets only expired pending bundles and preserves ready sources; failed deletes retain metadata for retry. Runtime scratch quotas remain a second defense. Artifact TAR transport and entry counts are bounded; directories and files are both validated. Links/special files/traversal, non-canonical or duplicate names, long paths and file/directory collisions are rejected. Downloads verify ownership and use short-lived signed URLs with attachment disposition. Object keys are generated by the worker.

## Remaining release requirements

Email verification and password reset, platform-admin auditing, live watchdog acceptance, comprehensive live SSRF escape tests, container-image vulnerability scans, upload/proxy ingress body limits, HTTPS deployment verification, lifecycle deletion/orphan reconciliation, distributed contention testing and external security review remain unfinished. Runtime/base images are version-pinned but not validated as free of OS vulnerabilities.

The dashboard currently permits inline Next.js scripts in CSP; nonce-based CSP is a later hardening task. The API's documentation is intended for trusted local/admin access and requires a separately reviewed policy if publicly exposed.

Source/artifact reservations cover ordinary interrupted-upload cleanup, not a complete object-store reconciliation guarantee. Extremely late writes from a frozen uploader after its reservation was cleaned can still require bucket inventory reconciliation. The historical orphan scan and full project/workspace deletion workflow remain release work; do not claim all orphan cases are solved.
