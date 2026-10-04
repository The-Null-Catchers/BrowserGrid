from unittest.mock import MagicMock
import io
import tarfile
import pytest
from browsergrid.execution.backend import ExecutionSpec
from browsergrid.execution.docker_backend import DockerExecutionBackend


def artifact_backend(chunks):
    client = MagicMock()
    client.api.exec_start.return_value = iter(chunks)
    client.api.exec_inspect.return_value = {"Running": False, "ExitCode": 0}
    return DockerExecutionBackend(client)


def test_sandbox_security_contract():
    client = MagicMock()
    client.api.exec_start.return_value._sock.recv.return_value = b""
    client.api.exec_inspect.return_value = {"Running": False, "ExitCode": 0}
    backend = DockerExecutionBackend(client)
    container = backend.create(
        ExecutionSpec("job", "lease", {}, {}, {"source/tests/test.ts": b"test"})
    )
    kwargs = client.containers.create.call_args.kwargs
    assert kwargs["user"] == "1000:1000"
    assert kwargs["read_only"]
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["security_opt"][0] == "no-new-privileges:true"
    assert kwargs["security_opt"][1].startswith("seccomp={")
    assert kwargs["pids_limit"] == 256
    assert kwargs["nano_cpus"] == 2_000_000_000
    assert "volumes" not in kwargs and "mounts" not in kwargs
    assert "ports" not in kwargs
    assert kwargs["network"] == "browsergrid_sandbox"
    assert not any("TOKEN" in key or "SECRET" in key for key in kwargs["environment"])
    assert kwargs["mem_limit"] == kwargs["memswap_limit"] == "2g"
    work_flags = set(kwargs["tmpfs"]["/work"].split(","))
    assert {"rw", "nosuid", "nodev", "exec"} <= work_flags
    container.put_archive.assert_not_called()
    transfer = client.api.exec_create.call_args.kwargs
    assert transfer["user"] == "1000:1000" and transfer["privileged"] is False
    assert "--directory=/work" in transfer["cmd"]
    raw = client.api.exec_start.return_value._sock.sendall.call_args.args[0]
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        entries = archive.getmembers()
        assert entries[-1].name == "ready"
        assert all(item.uid == item.gid == 1000 for item in entries)
        assert archive.extractfile("source/tests/test.ts").read() == b"test"
    backend.stop(container)
    container.remove.assert_called_with(force=True)


def test_browser_chroot_allowed_without_granting_container_capabilities():
    import json
    from pathlib import Path
    import browsergrid.execution.docker_backend as executor

    profile = json.loads(Path(executor.__file__).with_name("seccomp.json").read_text())
    assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
    rules = [rule for rule in profile["syscalls"] if rule["action"] == "SCMP_ACT_ALLOW"]
    assert any("chroot" in rule["names"] and not rule.get("includes") for rule in rules)
    assert not any("mount" in rule["names"] and not rule.get("includes") for rule in rules)


def test_input_failure_removes_container():
    client = MagicMock()
    client.api.exec_start.side_effect = RuntimeError("Docker transfer failed")
    with pytest.raises(RuntimeError):
        DockerExecutionBackend(client).create(ExecutionSpec("job", "lease", {}, {}, {}))
    client.containers.create.return_value.remove.assert_called_with(force=True)


@pytest.mark.parametrize("exit_code,running", [(1, False), (None, False), (0, True)])
def test_input_extraction_failure_removes_container(exit_code, running):
    client = MagicMock()
    client.api.exec_start.return_value._sock.recv.return_value = b""
    client.api.exec_inspect.return_value = {"Running": running, "ExitCode": exit_code}
    with pytest.raises(RuntimeError, match="extraction failed"):
        DockerExecutionBackend(client).create(ExecutionSpec("job", "lease", {}, {}, {}))
    client.api.exec_start.return_value.close.assert_called_once()
    client.containers.create.return_value.remove.assert_called_with(force=True)


def test_input_transfer_output_is_bounded_and_cleans_up():
    client = MagicMock()
    client.api.exec_start.return_value._sock.recv.return_value = b"x" * 8192
    with pytest.raises(RuntimeError, match="output exceeds limit"):
        DockerExecutionBackend(client).create(ExecutionSpec("job", "lease", {}, {}, {}))
    client.api.exec_start.return_value.close.assert_called_once()
    client.containers.create.return_value.remove.assert_called_with(force=True)


def tar_item(name, content=b"x", type=tarfile.REGTYPE):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as t:
        item = tarfile.TarInfo(name)
        item.type = type
        item.size = len(content)
        t.addfile(item, io.BytesIO(content))
    return out.getvalue()


@pytest.mark.parametrize(
    "name,type",
    [
        ("results/../escape", tarfile.REGTYPE),
        ("results/link", tarfile.SYMTYPE),
        ("/etc/passwd", tarfile.REGTYPE),
    ],
)
def test_artifact_archive_rejects_traversal_and_links(name, type):
    container = MagicMock()
    with pytest.raises(ValueError):
        artifact_backend([tar_item(name, type=type)]).artifacts(container)


def test_artifact_collection():
    container = MagicMock()
    backend = artifact_backend([tar_item("results/report.json", b"{}")])
    assert backend.artifacts(container) == {"report.json": b"{}"}
    container.get_archive.assert_not_called()
    transfer = backend.client.api.exec_create.call_args.kwargs
    assert transfer["user"] == "1000:1000" and transfer["privileged"] is False
    assert transfer["stderr"] is False


def test_fragmented_stdout_stays_bounded():
    from browsergrid.execution.logs import bounded_lines

    chunks = [b'@bg:{"ki', b'nd":"state"}\nhello', b"\n" + b"x" * 100_000]
    lines = list(bounded_lines(chunks, 1000))
    assert lines[0] == '@bg:{"kind":"state"}\n'
    assert lines[1] == "hello\n"
    assert all(len(line.encode()) <= 1000 for line in lines)
    assert sum(len(line) for line in lines[2:]) == 100_000


@pytest.mark.parametrize(
    "name,type",
    [
        ("results//report.json", tarfile.REGTYPE),
        ("results/./report.json", tarfile.REGTYPE),
        ("results", tarfile.REGTYPE),
        ("elsewhere", tarfile.DIRTYPE),
        ("results/../elsewhere", tarfile.DIRTYPE),
        ("results/" + "x" * 256, tarfile.REGTYPE),
    ],
)
def test_artifact_names_and_directory_metadata_are_validated(name, type):
    container = MagicMock()
    with pytest.raises(ValueError):
        artifact_backend([tar_item(name, type=type)]).artifacts(container)


def tar_entries(names):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as archive:
        for name in names:
            info = tarfile.TarInfo(name)
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
    return out.getvalue()


@pytest.mark.parametrize(
    "names",
    [["results/report.json", "results/report.json"], ["results/test", "results/test/image.png"]],
)
def test_artifact_duplicate_and_file_directory_collision_rejected(names):
    container = MagicMock()
    with pytest.raises(ValueError):
        artifact_backend([tar_entries(names)]).artifacts(container)


def test_artifact_transport_limit_before_parsing(monkeypatch):
    import browsergrid.execution.docker_backend as executor
    from types import SimpleNamespace

    monkeypatch.setattr(executor, "settings", lambda: SimpleNamespace(max_run_artifacts_bytes=8))
    container = MagicMock()
    with pytest.raises(ValueError, match="transport limit"):
        artifact_backend([b"12345", b"67890"]).artifacts(container)


def test_artifact_entry_limit_counts_directories():
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as archive:
        for index in range(2001):
            item = tarfile.TarInfo(f"results/directory-{index}")
            item.type = tarfile.DIRTYPE
            archive.addfile(item)
    container = MagicMock()
    with pytest.raises(ValueError, match="Too many"):
        artifact_backend([out.getvalue()]).artifacts(container)


def test_failed_archive_command_cannot_be_parsed_as_success():
    backend = artifact_backend([tar_item("results/report.json", b"{}")])
    backend.client.api.exec_inspect.return_value = {"Running": False, "ExitCode": 2}
    with pytest.raises(RuntimeError, match="extraction failed"):
        backend.artifacts(MagicMock())
