from unittest.mock import MagicMock
import io
import tarfile
import pytest
from browsergrid.execution.backend import ExecutionSpec
from browsergrid.execution.docker_backend import DockerExecutionBackend


def test_sandbox_security_contract():
    client = MagicMock()
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
    backend.stop(container)
    container.remove.assert_called_with(force=True)


def test_input_failure_removes_container():
    client = MagicMock()
    client.containers.create.return_value.put_archive.side_effect = RuntimeError(
        "Docker transfer failed"
    )
    with pytest.raises(RuntimeError):
        DockerExecutionBackend(client).create(ExecutionSpec("job", "lease", {}, {}, {}))
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
    container.get_archive.return_value = ([tar_item(name, type=type)], {})
    with pytest.raises(ValueError):
        DockerExecutionBackend(MagicMock()).artifacts(container)


def test_artifact_collection():
    container = MagicMock()
    container.get_archive.return_value = ([tar_item("results/report.json", b"{}")], {})
    assert DockerExecutionBackend(MagicMock()).artifacts(container) == {"report.json": b"{}"}


def test_fragmented_stdout_stays_bounded():
    from browsergrid.execution.logs import bounded_lines

    chunks = [b'@bg:{"ki', b'nd":"state"}\nhello', b"\n" + b"x" * 100_000]
    lines = list(bounded_lines(chunks, 1000))
    assert lines[0] == '@bg:{"kind":"state"}\n'
    assert lines[1] == "hello\n"
    assert all(len(line.encode()) <= 1000 for line in lines)
    assert sum(len(line) for line in lines[2:]) == 100_000
