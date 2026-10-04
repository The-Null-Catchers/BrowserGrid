"""Destructive recovery acceptance for a disposable Compose stack, never production."""

import argparse
import http.cookiejar
import json
import os
import secrets
import subprocess
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disposable-stack", action="store_true", required=True)
    parser.parse_args()
    base = os.getenv("BROWSERGRID_URL", "http://localhost:8000")
    origin = os.getenv("BROWSERGRID_ORIGIN", "http://localhost:3000")
    client = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )

    def request(path, body=None):
        req = urllib.request.Request(
            base + "/api/v1" + path,
            headers={"Origin": origin, "Content-Type": "application/json"},
            data=json.dumps(body).encode() if body is not None else None,
        )
        with client.open(req, timeout=15) as response:
            return json.load(response)

    def docker(*args):
        return subprocess.check_output(["docker", *args], text=True, timeout=30).strip()

    def wait_for(callback, seconds=90):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            value = callback()
            if value:
                return value
            time.sleep(1)
        raise AssertionError("Recovery acceptance deadline exceeded")

    request(
        "/auth/register",
        {
            "email": f"recovery-{secrets.token_hex(8)}@example.test",
            "password": secrets.token_urlsafe(24),
        },
    )
    workspace = request("/workspaces", {"name": "Disposable recovery acceptance"})
    project = request(f"/workspaces/{workspace['id']}/projects", {"name": "Worker loss"})
    code = 'import {test} from "@playwright/test";test("long execution",async({page})=>{await page.waitForTimeout(60000)});'

    def start(timeout):
        run = request(
            "/runs",
            {
                "project_id": project["id"],
                "config": {"source": {"type": "inline", "code": code}, "timeout_seconds": timeout},
            },
        )
        rid = run["id"]

        def active():
            detail = request(f"/runs/{rid}")
            assert detail["status"] not in {"failed", "infrastructure_failed", "timed_out"}, detail
            return detail if any(j["status"] == "running" for j in detail["jobs"]) else None

        detail = wait_for(active, 30)
        return rid, detail["jobs"][0]["id"]

    def sandbox(job_id):
        return docker(
            "ps",
            "-aq",
            "--filter",
            "label=browsergrid.sandbox=true",
            "--filter",
            f"label=browsergrid.job_id={job_id}",
        )

    try:
        rid, jid = start(120)
        assert sandbox(jid)
        docker("compose", "kill", "-s", "SIGKILL", "worker")
        # Pause restart policy explicitly; Compose stop keeps the test deterministic.
        docker("compose", "stop", "worker")
        failed = wait_for(
            lambda: (
                r if (r := request(f"/runs/{rid}"))["status"] == "infrastructure_failed" else None
            ),
            75,
        )
        assert failed["jobs"][0]["error_code"] == "WORKER_LOST", failed
        docker("compose", "up", "-d", "worker")
        wait_for(lambda: not sandbox(jid), 20)
        rid, jid = start(20)
        assert sandbox(jid)
        docker("compose", "kill", "-s", "SIGKILL", "worker")
        docker("compose", "stop", "worker")
        # This must succeed without restarting any worker.
        wait_for(lambda: not sandbox(jid), 30)
        timed_out = wait_for(
            lambda: r if (r := request(f"/runs/{rid}"))["status"] == "timed_out" else None, 20
        )
        assert timed_out["jobs"][0]["error_code"] == "RUN_TIMEOUT", timed_out
        print("Real worker-loss fencing/reaping and independent watchdog timeout passed.")
    finally:
        docker("compose", "up", "-d", "worker")


if __name__ == "__main__":
    main()
