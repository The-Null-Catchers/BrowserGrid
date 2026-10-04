"""Trusted host firewall guard; never run inside an execution sandbox."""

import os
import re
import shlex
import subprocess
import sys
import time


def rules(bridge: str) -> list[tuple[str, str, list[str]]]:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,15}", bridge):
        raise ValueError("Invalid sandbox bridge interface")
    # INPUT covers host services; FORWARD covers published-port DNAT to other bridges.
    return [
        (binary, chain, match)
        for binary in ("iptables", "ip6tables")
        for chain, match in (
            (
                "INPUT",
                ["-i", bridge, "-m", "comment", "--comment", "browsergrid-host", "-j", "DROP"],
            ),
            (
                "FORWARD",
                [
                    "-i",
                    bridge,
                    "!",
                    "-o",
                    bridge,
                    "-m",
                    "comment",
                    "--comment",
                    "browsergrid-route",
                    "-j",
                    "DROP",
                ],
            ),
        )
    ]


def apply(bridge: str, *, check_only: bool = False) -> bool:
    healthy = True
    for binary, chain, match in rules(bridge):
        prefix = [binary, "-w", "5", "-t", "filter"]
        result = subprocess.run(prefix + ["-S", chain], capture_output=True, text=True, check=True)
        entries = [
            shlex.split(line)[2:]
            for line in result.stdout.splitlines()
            if line.startswith(f"-A {chain} ")
        ]
        if entries and entries[0] == match:
            continue
        if check_only:
            healthy = False
            continue
        # Reassert at the head if Docker or another service inserts an earlier rule.
        subprocess.run(prefix + ["-I", chain, "1"] + match, check=True)
        # Remove only older identical copies, after installing the new head rule.
        for index in reversed(range(len(entries))):
            if entries[index] == match:
                subprocess.run(prefix + ["-D", chain, str(index + 2)], check=True)
    return healthy


def main() -> None:
    bridge = os.environ.get("BG_SANDBOX_BRIDGE", "bg-sandbox")
    if sys.argv[1:] == ["check"]:
        sys.exit(0 if apply(bridge, check_only=True) else 1)
    if sys.argv[1:]:
        raise SystemExit("Usage: network_guard.py [check]")
    while True:
        apply(bridge)
        time.sleep(2)
    # Rules deliberately survive process exit; live sandboxes still need protection.


if __name__ == "__main__":
    main()
