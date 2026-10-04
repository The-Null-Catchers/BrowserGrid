import subprocess
from unittest.mock import Mock

import pytest

from browsergrid.network_guard import apply, rules


def test_rules_cover_host_and_cross_bridge_traffic_for_both_ip_families():
    plan = rules("bg-sandbox")
    assert {(binary, chain) for binary, chain, _ in plan} == {
        (binary, chain) for binary in ("iptables", "ip6tables") for chain in ("INPUT", "FORWARD")
    }
    for _, chain, match in plan:
        assert match[:2] == ["-i", "bg-sandbox"]
        assert match[-2:] == ["-j", "DROP"]
        if chain == "FORWARD":
            assert match[2:5] == ["!", "-o", "bg-sandbox"]


def test_guard_healthcheck_does_not_mutate_firewall(monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=""))
    monkeypatch.setattr(subprocess, "run", run)
    assert not apply("bg-sandbox", check_only=True)
    assert all("-S" in call.args[0] for call in run.call_args_list)


def test_guard_refuses_failed_firewall_installation(monkeypatch):
    run = Mock(
        side_effect=[
            subprocess.CompletedProcess([], 0, stdout=""),
            subprocess.CalledProcessError(1, []),
        ]
    )
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        apply("bg-sandbox")
    assert run.call_args.args[0][-2:] == ["-j", "DROP"]


@pytest.mark.parametrize("bridge", ["", "a" * 16, "eth0;echo", "bridge name"])
def test_invalid_bridge_rejected_before_firewall_call(bridge):
    with pytest.raises(ValueError):
        rules(bridge)


def test_guard_reasserts_before_an_earlier_accept_rule(monkeypatch):
    import shlex

    binary, chain, match = rules("bg-sandbox")[0]
    previous = "-A INPUT -j ACCEPT\n" + shlex.join(["-A", chain, *match]) + "\n"
    run = Mock(
        side_effect=[
            subprocess.CompletedProcess([], 0, stdout=previous),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
            *[subprocess.CompletedProcess([], 0, stdout="") for _ in range(6)],
        ]
    )
    monkeypatch.setattr(subprocess, "run", run)
    assert apply("bg-sandbox")
    assert run.call_args_list[1].args[0] == [
        binary,
        "-w",
        "5",
        "-t",
        "filter",
        "-I",
        chain,
        "1",
        *match,
    ]
    assert run.call_args_list[2].args[0][-3:] == ["-D", "INPUT", "3"]
