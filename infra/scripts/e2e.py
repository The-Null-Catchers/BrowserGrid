"""Runs the actual API -> DB queue -> Docker worker -> browser -> S3 path. No mocks."""

import json
import io
import zipfile
from pathlib import Path
import http.cookiejar
import os
import secrets
import struct
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


def upload_bundle(project_id, content):
    boundary = "browsergrid-" + secrets.token_hex(16)
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="suite.zip"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(
        BASE + f"/api/v1/projects/{project_id}/bundles",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Origin": ORIGIN},
    )
    with client.open(req, timeout=30) as response:
        return json.load(response)


def wait(rid):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        run = request(f"/api/v1/runs/{rid}")
        if run["status"] in {"passed", "failed", "infrastructure_failed", "timed_out", "cancelled"}:
            if run["status"] == "infrastructure_failed":
                with client.open(BASE + f"/api/v1/runs/{rid}/events", timeout=20) as response:
                    print("Infrastructure failure timeline:\n" + response.read(256 * 1024).decode())
                print("Individual test results:", request(f"/api/v1/runs/{rid}/tests?limit=100"))
            return run
        time.sleep(1)
    raise AssertionError("Execution never completed")


def verify_browser_logs(run_detail, artifacts):
    observed_console, observed_network = set(), set()
    for artifact in artifacts:
        name = artifact["name"]
        if not name.endswith(("console.json", "network.json")):
            continue
        link = request(f"/api/v1/artifacts/{artifact['id']}/download")
        with urllib.request.urlopen(link["url"], timeout=20) as response:
            data = response.read(8 * 1024 * 1024 + 1)
        assert len(data) <= 8 * 1024 * 1024
        events = json.loads(data)
        assert isinstance(events, list)
        if name.endswith("console.json"):
            assert any(row.get("message") == "browsergrid capture smoke" for row in events), events
            observed_console.add(artifact["job_id"])
        else:
            assert any(
                row.get("url") == "http://fixture-app:8080/api/data"
                and row.get("status") == 200
                and row.get("resource_type") == "fetch"
                for row in events
            ), events
            observed_network.add(artifact["job_id"])
    jobs = {job["id"] for job in run_detail["jobs"]}
    assert observed_console == jobs and observed_network == jobs


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
code = 'import { test, expect } from "@playwright/test"; test("real fixture", async ({page}) => { await page.goto("http://fixture-app:8080"); await expect(page.getByRole("heading",{name:"BrowserGrid Fixture"})).toBeVisible(); await page.evaluate(()=>console.log("browsergrid capture smoke")); await page.getByRole("button",{name:"Load data"}).click(); await expect(page.locator("#data")).toHaveText("Network request complete"); });'
viewports = [
    {"name": "desktop", "width": 1440, "height": 900},
    {"name": "narrow", "width": 390, "height": 844},
]
run = request(
    "/api/v1/runs",
    {
        "project_id": project["id"],
        "config": {
            "source": {"type": "inline", "code": code},
            "browsers": ["chromium", "firefox", "webkit"],
            "viewports": viewports,
            "screenshot": "on",
            "trace": "on",
            "video": "on",
        },
    },
)
result = wait(run["id"])
assert result["status"] == "passed", result
assert len(result["jobs"]) == 6
expected_matrix = {
    (browser, viewport["width"], viewport["height"])
    for browser in ("chromium", "firefox", "webkit")
    for viewport in viewports
}
assert {
    (job["browser"], job["viewport"]["width"], job["viewport"]["height"]) for job in result["jobs"]
} == expected_matrix, result
assert all(j["runtime"].get("browser_version") for j in result["jobs"]), result
artifacts = request(f"/api/v1/runs/{run['id']}/artifacts?limit=100")
assert {"screenshot", "video", "trace"} <= {a["kind"] for a in artifacts}, artifacts
assert len(request(f"/api/v1/runs/{run['id']}/tests")) == 6
verify_browser_logs(result, artifacts)
jobs = {job["id"]: job for job in result["jobs"]}
observed_artifacts = {job_id: set() for job_id in jobs}
for artifact in artifacts:
    link = request(f"/api/v1/artifacts/{artifact['id']}/download")
    with urllib.request.urlopen(link["url"], timeout=20) as response:
        header = response.read(24)
        assert header
        observed_artifacts[artifact["job_id"]].add(artifact["kind"])
        if artifact["kind"] == "screenshot":
            assert header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR", artifact
            viewport = jobs[artifact["job_id"]]["viewport"]
            assert struct.unpack(">II", header[16:24]) == (
                viewport["width"],
                viewport["height"],
            ), artifact
assert all({"screenshot", "video", "trace"} <= kinds for kinds in observed_artifacts.values())
# Real uploaded-source path: validated ZIP -> private storage -> worker/npm ci -> Chromium.
root = Path(__file__).resolve().parents[2]
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
    for filename in ("package.json", "package-lock.json"):
        archive.writestr(filename, (root / "runtimes" / filename).read_bytes())
    archive.writestr(
        "tests/uploaded.spec.ts", code.replace("@playwright/test", "@browsergrid/test")
    )
bundle = upload_bundle(project["id"], buffer.getvalue())
uploaded_run = request(
    "/api/v1/runs",
    {
        "project_id": project["id"],
        "config": {
            "source": {"type": "bundle", "bundle_id": bundle["id"]},
            "screenshot": "on",
            "video": "off",
            "trace": "off",
        },
    },
)
uploaded_result = wait(uploaded_run["id"])
assert uploaded_result["status"] == "passed", uploaded_result
assert len(request(f"/api/v1/runs/{uploaded_run['id']}/tests")) == 1
uploaded_artifacts = request(f"/api/v1/runs/{uploaded_run['id']}/artifacts?limit=100")
verify_browser_logs(uploaded_result, uploaded_artifacts)
shots = [artifact for artifact in uploaded_artifacts if artifact["kind"] == "screenshot"]
assert shots, uploaded_artifacts
link = request(f"/api/v1/artifacts/{shots[0]['id']}/download")
with urllib.request.urlopen(link["url"], timeout=20) as response:
    assert response.read(8) == b"\x89PNG\r\n\x1a\n"

# Public Git is fetched by the non-root sandbox through restricted egress, never by the API.
# CI supplies its exact checkout SHA; local acceptance uses the committed source tree.
git_commit = os.getenv("BG_E2E_COMMIT") or subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=10
).strip()
git_repository = os.getenv("BG_E2E_REPOSITORY", "https://github.com/The-Null-Catchers/BrowserGrid")
git_source = {"type": "git", "repository": git_repository, "commit": git_commit}
git_run = request(
    "/api/v1/runs",
    {
        "project_id": project["id"],
        "config": {
            "source": git_source,
            "working_directory": "fixture-repository",
            "viewports": [{"name": "git-desktop", "width": 1024, "height": 768}],
            "screenshot": "on",
            "video": "off",
            "trace": "off",
        },
    },
)
git_result = wait(git_run["id"])
assert git_result["status"] == "passed", git_result
assert len(git_result["jobs"]) == 1
assert git_result["jobs"][0]["runtime"]["commit"] == git_commit
assert git_result["jobs"][0]["runtime"].get("browser_version"), git_result
assert len(request(f"/api/v1/runs/{git_run['id']}/tests")) == 1
git_artifacts = request(f"/api/v1/runs/{git_run['id']}/artifacts?limit=100")
verify_browser_logs(git_result, git_artifacts)
checkout_verified, git_screenshot_verified = False, False
for artifact in git_artifacts:
    if (
        Path(artifact["name"]).name.startswith("checkout-json-")
        and artifact["name"].endswith(".json")
    ):
        link = request(f"/api/v1/artifacts/{artifact['id']}/download")
        with urllib.request.urlopen(link["url"], timeout=20) as response:
            checkout = json.loads(response.read(4096))
        assert checkout == {"commit": git_commit.lower(), "fixture": "pinned-git-fixture"}
        checkout_verified = True
    elif artifact["kind"] == "screenshot":
        link = request(f"/api/v1/artifacts/{artifact['id']}/download")
        with urllib.request.urlopen(link["url"], timeout=20) as response:
            header = response.read(24)
        assert header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR"
        assert struct.unpack(">II", header[16:24]) == (1024, 768)
        git_screenshot_verified = True
assert checkout_verified and git_screenshot_verified, git_artifacts
# An unavailable immutable commit must be an infrastructure failure, with no test results.
missing_git = request(
    "/api/v1/runs",
    {
        "project_id": project["id"],
        "config": {
            "source": {**git_source, "commit": "0" * 40},
            "working_directory": "fixture-repository",
            "timeout_seconds": 60,
        },
    },
)
missing_result = wait(missing_git["id"])
assert missing_result["status"] == "infrastructure_failed", missing_result
assert missing_result["jobs"][0]["error_code"] == "REPOSITORY_CLONE_FAILED", missing_result
assert request(f"/api/v1/runs/{missing_git['id']}/tests") == []

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
print(
    "Real six-job browser/viewport matrix, PNG dimensions, uploaded bundle, artifacts, "
    "pinned public Git checkout, missing-commit rejection, failure classification and cancellation passed."
)
