import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

TERMINAL = {"passed", "failed", "timed_out", "cancelled", "infrastructure_failed"}


def main():
    parser = argparse.ArgumentParser(description="BrowserGrid CI client")
    parser.add_argument("--url", default=os.environ.get("BROWSERGRID_URL", "http://localhost:8000"))
    parser.add_argument("--token", default=os.environ.get("BROWSERGRID_TOKEN"))
    commands = parser.add_subparsers(dest="command", required=True)
    projects = commands.add_parser("projects")
    projects.add_argument("workspace_id")
    run = commands.add_parser("run")
    run.add_argument("config", help="JSON request containing project_id and config")
    run.add_argument("--idempotency-key")
    run.add_argument("--wait", action="store_true")
    view = commands.add_parser("view")
    view.add_argument("run_id")
    cancel = commands.add_parser("cancel")
    cancel.add_argument("run_id")
    artifacts = commands.add_parser("artifacts")
    artifacts.add_argument("run_id")
    args = parser.parse_args()
    if not args.token:
        parser.error("Set BROWSERGRID_TOKEN to a scoped workspace API key")

    def request(path, body=None):
        headers = {"Authorization": "Bearer " + args.token, "Content-Type": "application/json"}
        if getattr(args, "idempotency_key", None):
            headers["Idempotency-Key"] = args.idempotency_key
        req = urllib.request.Request(
            args.url.rstrip("/") + "/api/v1" + path,
            headers=headers,
            data=json.dumps(body).encode() if body is not None else None,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            print(f"BrowserGrid API returned HTTP {error.code}", file=sys.stderr)
            sys.exit(2)

    if args.command == "projects":
        result = request(f"/workspaces/{args.workspace_id}/projects")
    elif args.command == "run":
        result = request("/runs", json.loads(Path(args.config).read_text()))
        if args.wait:
            rid = result["id"]
            deadline = time.monotonic() + 1800
            while time.monotonic() < deadline:
                result = request(f"/runs/{rid}")
                if result["status"] in TERMINAL:
                    print(json.dumps(result, indent=2))
                    sys.exit(0 if result["status"] == "passed" else 1)
                time.sleep(2)
            sys.exit(2)
    elif args.command == "view":
        result = request(f"/runs/{args.run_id}")
    elif args.command == "cancel":
        result = request(f"/runs/{args.run_id}/cancel", {})
    else:
        result = request(f"/runs/{args.run_id}/artifacts")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
