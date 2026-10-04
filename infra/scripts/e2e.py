"""Runs the actual API -> DB queue -> Docker worker -> browser -> S3 path. No mocks."""

import json
import http.cookiejar
import os
import secrets
import subprocess
import time
import urllib.request

BASE = os.getenv("BROWSERGRID_URL", "http://localhost:8000")
ORIGIN = os.getenv("BROWSERGRID_ORIGIN", "http://localhost:3000")
cookies = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))


def request(path, data=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json", "Origin": ORIGIN},
    )
    with client.open(req, timeout=30) as response:
        return json.load(response)


def wait(rid):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        run = request(f"/api/v1/runs/{rid}")
        if run["status"] in {"passed", "failed", "infrastructure_failed", "timed_out", "cancelled"}:
            return run
        time.sleep(1)
    raise AssertionError("Execution never completed")


for _ in range(120):
    try:
        request("/ready")
        break
    except Exception:
        time.sleep(1)
else:
    raise AssertionError("Control plane not ready")
request(
    "/api/v1/auth/register",
    {"email": f"e2e-{secrets.token_hex(8)}@example.test", "password": secrets.token_urlsafe(24)},
)
workspace = request("/api/v1/workspaces", {"name": "Real execution smoke"})
project = request(f"/api/v1/workspaces/{workspace['id']}/projects", {"name": "Fixture"})
code = 'import { test, expect } from "@playwright/test"; test("real fixture", async ({page}) => { await page.goto("http://fixture-app:8080"); await expect(page.getByRole("heading",{name:"BrowserGrid Fixture"})).toBeVisible(); });'
run = request(
    "/api/v1/runs",
    {
        "project_id": project["id"],
        "config": {
            "source": {"type": "inline", "code": code},
            "browsers": ["chromium", "firefox", "webkit"],
            "screenshot": "on",
            "trace": "on",
            "video": "on",
        },
    },
)
result = wait(run["id"])
assert result["status"] == "passed", result
assert len(result["jobs"]) == 3
assert all(j["runtime"].get("browser_version") for j in result["jobs"]), result
artifacts = request(f"/api/v1/runs/{run['id']}/artifacts?limit=100")
assert {"screenshot", "video", "trace"} <= {a["kind"] for a in artifacts}, artifacts
assert len(request(f"/api/v1/runs/{run['id']}/tests")) == 3
for artifact in artifacts:
    link = request(f"/api/v1/artifacts/{artifact['id']}/download")
    with urllib.request.urlopen(link["url"], timeout=20) as response:
        assert response.read(1)
failed = request(
    "/api/v1/runs",
    {
        "project_id": project["id"],
        "config": {
            "source": {
                "type": "inline",
                "code": code.replace(".toBeVisible()", '.toHaveText("INTENTIONAL MISMATCH")'),
            },
            "timeout_seconds": 30,
        },
    },
)
assert wait(failed["id"])["status"] == "failed"
slow = request(
    "/api/v1/runs",
    {
        "project_id": project["id"],
        "config": {
            "source": {
                "type": "inline",
                "code": 'import {test} from "@playwright/test";test("wait",async({page})=>{await page.waitForTimeout(60000);});',
            }
        },
    },
)
# Exercise cancellation of a launched browser, not only a queued job.
for _ in range(60):
    active = request(f"/api/v1/runs/{slow['id']}")
    assert active["status"] not in {"failed", "infrastructure_failed", "timed_out", "passed"}, (
        active
    )
    if any(job["status"] == "running" for job in active["jobs"]):
        break
    time.sleep(0.5)
else:
    raise AssertionError("Slow execution never reached running")
request(f"/api/v1/runs/{slow['id']}/cancel", {})
assert wait(slow["id"])["status"] == "cancelled"
for _ in range(20):
    remaining = subprocess.check_output(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=browsergrid.sandbox=true",
            "--filter",
            f"label=browsergrid.job_id={active['jobs'][0]['id']}",
        ],
        text=True,
        timeout=15,
    ).strip()
    if not remaining:
        break
    time.sleep(0.5)
else:
    raise AssertionError("Cancelled execution left its sandbox behind")
print("Real browser matrix, artifacts, failure classification and cancellation passed.")
