"""Live sandbox escape probes against positive-control canaries on a disposable host."""

import argparse
import http.cookiejar
import http.server
import json
import os
import secrets
import subprocess
import threading
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

    class Canary(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"browsergrid-canary")

        def log_message(self, *_):
            pass

    host = http.server.ThreadingHTTPServer(("0.0.0.0", 0), Canary)
    threading.Thread(target=host.serve_forever, daemon=True).start()
    container = "bg-network-canary-" + secrets.token_hex(8)
    gateway = "172.30.0.1"  # Matches the disposable Compose subnet.

    def positive(port):
        # Proves the canary is reachable from the Docker engine host, including DinD.
        docker(
            "run",
            "--rm",
            "--network",
            "host",
            "browsergrid-control:0.1.0",
            "python",
            "-c",
            f"import urllib.request; assert urllib.request.urlopen('http://{gateway}:{port}', timeout=3).status == 200",
        )

    try:
        host_port = host.server_port
        positive(host_port)
        docker(
            "run",
            "-d",
            "--name",
            container,
            "--network",
            "browsergrid_control",
            "--publish",
            "0.0.0.0::8080",
            "--cap-drop",
            "ALL",
            "--read-only",
            "--user",
            "1000:1000",
            "browsergrid-control:0.1.0",
            "python",
            "-m",
            "http.server",
            "8080",
        )
        published_port = int(
            docker("port", container, "8080/tcp").splitlines()[0].rsplit(":", 1)[1]
        )
        for attempt in range(15):
            try:
                positive(published_port)
                break
            except subprocess.CalledProcessError:
                if attempt == 14:
                    raise
                time.sleep(1)
        request(
            "/auth/register",
            {
                "email": f"network-{secrets.token_hex(8)}@example.test",
                "password": secrets.token_urlsafe(24),
            },
        )
        workspace = request("/workspaces", {"name": "Disposable network acceptance"})
        project = request(f"/workspaces/{workspace['id']}/projects", {"name": "Escape probes"})
        code = """
import {test, expect} from '@playwright/test';
import net from 'node:net';
import http from 'node:http';
const reachable = (host, port) => new Promise(resolve => {
  const socket = net.connect({host, port});
  const finish = value => { socket.destroy(); resolve(value); };
  socket.setTimeout(1500);
  socket.once('connect', () => finish(true));
  socket.once('timeout', () => finish(false));
  socket.once('error', () => finish(false));
});
test('fixture allowed; host and DNAT escape blocked', async ({page}) => {
  await page.goto('http://fixture-app:8080');
  await expect(page.getByRole('heading', {name: 'BrowserGrid Fixture'})).toBeVisible();
  for (const port of PORTS) expect(await reachable('172.30.0.1', port)).toBe(false);
  const status = await new Promise((resolve, reject) => {
    const req = http.get({hostname:'egress', port:3128, path:'http://169.254.169.254/'}, res => {
      res.resume(); resolve(res.statusCode);
    });
    req.setTimeout(5000, () => req.destroy(new Error('proxy timeout')));
    req.on('error', reject);
  });
  expect(status).toBe(403);
});
""".replace("PORTS", json.dumps([host_port, published_port]))
        run = request(
            "/runs",
            {
                "project_id": project["id"],
                "config": {"source": {"type": "inline", "code": code}, "timeout_seconds": 60},
            },
        )
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            detail = request(f"/runs/{run['id']}")
            if detail["status"] in {
                "passed",
                "failed",
                "infrastructure_failed",
                "timed_out",
                "cancelled",
            }:
                assert detail["status"] == "passed", detail
                break
            time.sleep(1)
        else:
            raise AssertionError("Network acceptance execution did not finish")
        positive(host_port)
        positive(published_port)
        print("Live fixture access, host/DNAT escape denial and metadata proxy denial passed.")
    finally:
        subprocess.run(["docker", "rm", "-f", container], timeout=30, check=False)
        host.shutdown()
        host.server_close()


if __name__ == "__main__":
    main()
