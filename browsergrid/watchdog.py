"""Host-side sandbox wall-clock enforcement; no DB/storage credentials required."""

import logging
import math
import signal
import threading
import time
from browsergrid.execution.docker_backend import DockerExecutionBackend

log = logging.getLogger("browsergrid.watchdog")


def expired(labels, clock):
    try:
        deadline = float(labels["browsergrid.deadline"])
    except (KeyError, TypeError, ValueError):
        return True
    # Invalid / infinite deadlines never disable host-side cleanup.
    return not math.isfinite(deadline) or clock >= deadline


def sweep(backend, clock=None):
    clock = time.time() if clock is None else clock
    removed = 0
    for container in backend.client.containers.list(
        all=True, filters={"label": "browsergrid.sandbox=true"}
    ):
        if expired(container.labels, clock):
            backend.stop(container)
            removed += 1
            log.info("Expired sandbox removed container_id=%s", container.id)
    return removed


def main():
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    backend = DockerExecutionBackend()
    while not stop.is_set():
        try:
            sweep(backend)
        except Exception:
            log.exception("Sandbox watchdog sweep failed")
        stop.wait(2)


if __name__ == "__main__":
    main()
