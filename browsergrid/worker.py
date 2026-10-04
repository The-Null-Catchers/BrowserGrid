import json
import logging
import mimetypes
import os
import queue
import signal
import threading
import time
from datetime import timedelta
from redis import Redis
from sqlalchemy import select
from browsergrid import storage
from browsergrid.api.auth import utc
from browsergrid.config import settings
from browsergrid.db import session_factory
from browsergrid.execution.backend import ExecutionSpec
from browsergrid.execution.logs import bounded_lines
from browsergrid.execution.docker_backend import DockerExecutionBackend
from browsergrid.lifecycle import ACTIVE, TERMINAL, event, transition
from browsergrid.models import Artifact, Bundle, Job, Run, Secret, Worker, now, uid
from browsergrid.results import persist_results
from browsergrid.scheduling import acquire, heartbeat, leased_job
from browsergrid.security import Redactor, decrypt, validate_bundle

log = logging.getLogger("browsergrid.worker")
shutdown = threading.Event()


def state(job_id, token, status, error=None):
    with session_factory()() as db:
        job = leased_job(db, job_id, token)
        run = db.get(Run, job.run_id)
        if run.cancel_requested and status in TERMINAL:
            status, error = "cancelled", None
        transition(db, job, status, error)
        db.commit()


def reap(backend):
    # Remove sandboxes whose DB leases expired, even after a worker process crash.
    for container in backend.client.containers.list(
        all=True, filters={"label": "browsergrid.sandbox=true"}
    ):
        labels = container.labels
        with session_factory()() as db:
            job = db.get(Job, labels.get("browsergrid.job_id"))
            valid = (
                job and job.status in ACTIVE and job.lease_token == labels.get("browsergrid.lease")
            )
        if not valid:
            backend.stop(container)


def execute(backend, worker_id, job_id, token):
    container = None
    stop = threading.Event()
    lost = threading.Event()
    cancelled = threading.Event()
    deadline = time.monotonic() + 900
    redactor = Redactor([])

    def beat():
        next_heartbeat = time.monotonic() + 3
        while not stop.wait(0.5):
            clock = time.monotonic()
            abort = shutdown.is_set() or cancelled.is_set() or lost.is_set() or clock >= deadline
            if not abort and clock >= next_heartbeat:
                try:
                    with session_factory()() as db:
                        if not heartbeat(db, worker_id, job_id, token):
                            cancelled.set()
                            abort = True
                except Exception:
                    # Fail closed: stop jobs whose lease cannot be confirmed.
                    lost.set()
                    abort = True
                next_heartbeat = clock + 3
            if abort:
                # A blocked artifact read/upload must not keep the browser alive.
                # Removing a container is idempotent even if the main thread also exits.
                if container:
                    try:
                        backend.stop(container)
                    except Exception:
                        log.exception(
                            "Sandbox stop failed job_id=%s worker_id=%s", job_id, worker_id
                        )
                        continue
                return

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        with session_factory()() as db:
            job = leased_job(db, job_id, token)
            run = db.get(Run, job.run_id)
            config = {**run.config, "browser": job.browser, "viewport": job.viewport}
            remaining = config["timeout_seconds"] - (now() - utc(job.started_at)).total_seconds()
            deadline = time.monotonic() + max(0, remaining)
            secrets = {
                s.name: decrypt(s.ciphertext)
                for s in db.scalars(select(Secret).where(Secret.project_id == run.project_id))
            }
            environment = {**config.get("env", {}), **secrets}
            redactor = Redactor(list(environment.values()))
            files = {}
            source = config["source"]
            if source["type"] == "bundle":
                bundle = db.get(Bundle, source["bundle_id"])
                files = {
                    f"source/{name}": data
                    for name, data in validate_bundle(storage.get(bundle.key)).items()
                }
            job.runtime = {
                "image": settings().runtime_image,
                "worker": settings().worker_version,
                "playwright": "1.58.2",
                "os": "Ubuntu 24.04 Linux",
                "commit": source.get("commit"),
            }
            db.commit()
        if cancelled.is_set() or shutdown.is_set():
            state(job_id, token, "cancelled")
            return
        if lost.is_set():
            state(job_id, token, "infrastructure_failed", "LEASE_LOST")
            return
        if time.monotonic() >= deadline:
            state(job_id, token, "timed_out", "RUN_TIMEOUT")
            return
        container = backend.create(
            ExecutionSpec(
                job_id,
                token,
                config,
                environment,
                files,
                expires_at=time.time() + max(0, deadline - time.monotonic()),
            )
        )
        lines = queue.Queue(maxsize=1000)

        def read_logs():
            try:
                for line in bounded_lines(container.logs(stream=True, follow=True)):
                    while not stop.is_set():
                        try:
                            lines.put(line, timeout=0.2)
                            break
                        except queue.Full:
                            continue
            except Exception:
                pass

        reader = threading.Thread(target=read_logs, daemon=True)
        reader.start()
        logged = 0
        runtime_exit = None
        setup_error = None
        while True:
            if shutdown.is_set() or cancelled.is_set():
                state(job_id, token, "cancelled")
                return
            if lost.is_set():
                state(job_id, token, "infrastructure_failed", "LEASE_LOST")
                return
            if time.monotonic() > deadline:
                state(job_id, token, "timed_out", "RUN_TIMEOUT")
                return
            try:
                line = lines.get(timeout=0.2)
                control = None
                if line.startswith("@bg:"):
                    try:
                        parsed = json.loads(line[4:])
                        control = parsed.get("kind") if isinstance(parsed, dict) else None
                    except ValueError:
                        pass
                if logged < 10000 or control in {"state", "completed"}:
                    with session_factory()() as db:
                        job = leased_job(db, job_id, token)
                        clean = redactor.text(line)
                        if line.startswith("@bg:"):
                            try:
                                payload = json.loads(line[4:])
                                if payload.get("kind") == "completed":
                                    runtime_exit = int(payload.get("exit_code", 2))
                                elif payload.get("kind") == "state" and payload.get("state") in {
                                    "pulling_source",
                                    "installing_dependencies",
                                    "starting_browser",
                                    "running",
                                }:
                                    transition(db, job, payload["state"])
                                elif payload.get("kind") in {
                                    "test_start",
                                    "test_end",
                                    "runtime",
                                    "error",
                                }:
                                    if payload.get("kind") == "error" and payload.get("code") in {
                                        "REPOSITORY_CLONE_FAILED",
                                        "DEPENDENCY_INSTALL_FAILED",
                                        "BROWSER_LAUNCH_FAILED",
                                        "RUNTIME_SETUP_FAILED",
                                    }:
                                        setup_error = payload["code"]
                                    if payload.get("kind") == "runtime":
                                        job.runtime = {
                                            **job.runtime,
                                            **redactor.data(payload.get("data", {})),
                                        }
                                    event(db, job, payload["kind"], redactor.data(payload))
                                else:
                                    event(db, job, "log", {"message": clean})
                            except (ValueError, TypeError, AttributeError):
                                event(db, job, "log", {"message": clean})
                        else:
                            event(db, job, "log", {"message": clean})
                        db.commit()
                    logged += 1
            except queue.Empty:
                pass
            info = backend.status(container)
            if runtime_exit is not None:
                info = {**info, "ExitCode": runtime_exit}
                break
            if not info["Running"] and lines.empty() and not reader.is_alive():
                break
        with session_factory()() as db:
            job = leased_job(db, job_id, token)
            # Early setup failures do not masquerade as test failures.
            if job.status != "running":
                event(
                    db,
                    job,
                    "error",
                    {
                        "message": "Runtime exited before tests started",
                        "exit_code": info.get("ExitCode"),
                    },
                )
                transition(db, job, "infrastructure_failed", setup_error or "RUNTIME_SETUP_FAILED")
                db.commit()
                return
        state(job_id, token, "uploading_artifacts")
        artifacts = backend.artifacts(container)
        if cancelled.is_set() or shutdown.is_set():
            state(job_id, token, "cancelled")
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("Artifact collection deadline exceeded")
        if lost.is_set():
            raise RuntimeError("Lease confirmation lost")
        report = artifacts.get("report.json")
        if not report:
            state(job_id, token, "infrastructure_failed", "RESULT_REPORT_MISSING")
            return
        with session_factory()() as db:
            job = leased_job(db, job_id, token)
            try:
                tests, errors = persist_results(db, job_id, report, redactor)
            except (ValueError, RecursionError) as exc:
                event(
                    db,
                    job,
                    "error",
                    {"code": "RESULT_REPORT_INVALID", "message": redactor.text(str(exc))},
                )
                transition(db, job, "infrastructure_failed", "RESULT_REPORT_INVALID")
                db.commit()
                return
            if not tests or errors:
                transition(db, job, "infrastructure_failed", "PLAYWRIGHT_CONFIGURATION_ERROR")
                db.commit()
                return
            db.commit()
        for name, data in artifacts.items():
            if time.monotonic() > deadline:
                raise TimeoutError("Artifact upload deadline exceeded")
            if lost.is_set():
                raise RuntimeError("Lease confirmation lost")
            if name.endswith((".json", ".jsonl", ".txt", ".log")):
                data = redactor.text(data.decode(errors="replace")).encode()
            aid = uid()
            mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
            kind = (
                "screenshot"
                if name.endswith(".png")
                else "video"
                if name.endswith(".webm")
                else "trace"
                if name.endswith(".zip")
                else "report"
                if name.endswith(".json")
                else "log"
            )
            with session_factory()() as db:
                job = leased_job(db, job_id, token)
                if db.get(Run, job.run_id).cancel_requested:
                    transition(db, job, "cancelled")
                    db.commit()
                    return
                key = f"artifacts/{job.workspace_id}/{job.run_id}/{job.id}/{aid}"
                # Persist the object reservation BEFORE upload, so worker crashes cannot
                # leave an uploaded object without cleanup metadata.
                db.add(
                    Artifact(
                        id=aid,
                        run_id=job.run_id,
                        job_id=job.id,
                        key=key,
                        name=redactor.text(name)[:500],
                        kind=kind,
                        size=len(data),
                        mime=mime,
                        ready=False,
                        expires_at=now() + timedelta(hours=1),
                    )
                )
                db.commit()
            # Never hold the workspace lock during an object-store network request.
            storage.put(key, data, mime)
            if time.monotonic() > deadline:
                raise TimeoutError("Artifact upload deadline exceeded")
            if lost.is_set():
                raise RuntimeError("Lease confirmation lost")
            with session_factory()() as db:
                job = leased_job(db, job_id, token)
                if db.get(Run, job.run_id).cancel_requested:
                    transition(db, job, "cancelled")
                    db.commit()
                    return
                artifact = db.get(Artifact, aid)
                artifact.ready = True
                artifact.expires_at = now() + timedelta(days=config["retention_days"])
                db.commit()
        with session_factory()() as db:
            job = leased_job(db, job_id, token)
            final = (
                "failed"
                if info.get("ExitCode") != 0
                or any(t["status"] in {"failed", "timed_out"} for t in tests)
                else "passed"
            )
            if db.get(Run, job.run_id).cancel_requested or cancelled.is_set() or shutdown.is_set():
                final = "cancelled"
            if lost.is_set() and final != "cancelled":
                transition(db, job, "infrastructure_failed", "LEASE_LOST")
                db.commit()
                return
            transition(db, job, final, "TEST_FAILED" if final == "failed" else None)
            worker = db.get(Worker, worker_id)
            worker.completed += 1
            worker.job_id = None
            db.commit()
    except TimeoutError:
        try:
            state(job_id, token, "timed_out", "RUN_TIMEOUT")
        except Exception:
            pass
    except Exception:
        log.exception("Execution failed job_id=%s worker_id=%s", job_id, worker_id)
        try:
            if cancelled.is_set() or shutdown.is_set():
                state(job_id, token, "cancelled")
            elif time.monotonic() >= deadline:
                state(job_id, token, "timed_out", "RUN_TIMEOUT")
            elif lost.is_set():
                state(job_id, token, "infrastructure_failed", "LEASE_LOST")
            else:
                state(job_id, token, "infrastructure_failed", "EXECUTION_INFRASTRUCTURE_ERROR")
        except Exception:
            pass  # Scheduler reconciles expired leases after outages.
    finally:
        stop.set()
        thread.join(timeout=4)
        if container:
            backend.stop(container)
        with session_factory()() as db:
            worker = db.get(Worker, worker_id)
            if worker and worker.job_id == job_id:
                worker.job_id = None
                db.commit()


def main():
    logging.basicConfig(level=logging.INFO)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: shutdown.set())
    worker_id = os.environ.get("BG_WORKER_ID") or f"worker-{uid()[:12]}"
    backend = DockerExecutionBackend()
    while not shutdown.is_set():
        try:
            reap(backend)
            with session_factory()() as db:
                claimed = acquire(db, worker_id)
            if claimed:
                execute(backend, worker_id, *claimed)
            else:
                try:
                    Redis.from_url(settings().redis_url, socket_timeout=3).brpop(
                        "bg:wakeup", timeout=2
                    )
                except Exception:
                    shutdown.wait(2)
        except Exception:
            log.exception("Worker loop failed worker_id=%s", worker_id)
            shutdown.wait(3)


if __name__ == "__main__":
    main()
