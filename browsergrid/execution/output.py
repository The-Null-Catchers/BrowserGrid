"""Bounded, validated runtime output. Sandbox stdout is untrusted input."""

import json
from browsergrid.lifecycle import TRANSITIONS, event, transition

STATES = {"pulling_source", "installing_dependencies", "starting_browser", "running"}
SETUP_ERRORS = {
    "REPOSITORY_CLONE_FAILED",
    "DEPENDENCY_INSTALL_FAILED",
    "BROWSER_LAUNCH_FAILED",
    "RUNTIME_SETUP_FAILED",
}


def error_summary(message, redactor):
    text = redactor.text(message) if isinstance(message, str) else ""
    if len(text) <= 4096:
        return text
    # Browser launch errors include huge argument lists before the useful stderr.
    return text[:1500] + "\n[... message truncated ...]\n" + text[-2500:]


class RuntimeOutput:
    def __init__(self, redactor, *, max_events=10000, max_bytes=4 * 1024 * 1024):
        self.redactor = redactor
        self.max_events, self.max_bytes = max_events, max_bytes
        self.events = self.bytes = 0
        self.state = "preparing"
        self.exit_code = self.setup_error = None
        self.runtime_seen = self.error_seen = self.truncated = False

    def prepare(self, line):
        payload = None
        if line.startswith("@bg:"):
            try:
                candidate = json.loads(line[4:])
                if isinstance(candidate, dict) and isinstance(candidate.get("kind"), str):
                    payload = candidate
            except (ValueError, RecursionError):
                pass
        kind = payload.get("kind") if payload else None
        if kind == "state":
            target = payload.get("state")
            if isinstance(target, str) and target in STATES and target in TRANSITIONS[self.state]:
                return "state", {"state": target}
        elif kind == "completed":
            code = payload.get("exit_code")
            if type(code) is int and 0 <= code <= 255 and self.exit_code is None:
                return "process_exit", {"exit_code": code}
        elif kind == "runtime" and not self.runtime_seen:
            data = payload.get("data")
            if (
                isinstance(data, dict)
                and isinstance(data.get("browser_version"), str)
                and 0 < len(data["browser_version"]) <= 200
                and data.get("playwright") == "1.58.2"
            ):
                return "runtime", {
                    "browser_version": self.redactor.text(data["browser_version"]),
                    "playwright": data["playwright"],
                }
        elif kind == "error" and not self.error_seen:
            code = payload.get("code")
            if isinstance(code, str) and code in SETUP_ERRORS | {"TEST_PROCESS_INTERRUPTED"}:
                message = payload.get("message")
                data = {
                    "code": code,
                    "message": error_summary(message, self.redactor),
                }
                signal = payload.get("signal")
                if isinstance(signal, str):
                    data["signal"] = self.redactor.text(signal)[:40]
                return "error", data
        if self.truncated:
            return None
        if kind in {"test_start", "test_end", "error"}:
            try:
                data = self.redactor.data(payload)
            except RecursionError:
                kind, data = "log", {"message": self.redactor.text(line)}
        else:
            kind, data = "log", {"message": self.redactor.text(line)}
        try:
            size = len(json.dumps(data, allow_nan=False).encode())
        except (ValueError, RecursionError):
            kind, data = "log", {"message": self.redactor.text(line)}
            size = len(json.dumps(data).encode())
        if self.events < self.max_events and self.bytes + size <= self.max_bytes:
            self.events += 1
            self.bytes += size
            return kind, data
        if not self.truncated:
            self.truncated = True
            return "output_truncated", {
                "max_events": self.max_events,
                "max_bytes": self.max_bytes,
                "message": "Further ordinary output omitted; lifecycle events continue",
            }
        return None

    def apply(self, db, job, message):
        kind, data = message
        if kind == "state":
            transition(db, job, data["state"])
            self.state = data["state"]
            return
        if kind == "process_exit":
            self.exit_code = data["exit_code"]
        elif kind == "runtime":
            self.runtime_seen = True
            job.runtime = {**job.runtime, **data}
        elif (
            kind == "error"
            and isinstance(data.get("code"), str)
            and data["code"] in SETUP_ERRORS | {"TEST_PROCESS_INTERRUPTED"}
        ):
            self.error_seen = True
            if data["code"] in SETUP_ERRORS:
                self.setup_error = data["code"]
        event(db, job, kind, data)
