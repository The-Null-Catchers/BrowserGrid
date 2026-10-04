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
    container.get_archive.return_value = ([tar_item(name, type=type)], {})
    with pytest.raises(ValueError):
        DockerExecutionBackend(MagicMock()).artifacts(container)


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
    container.get_archive.return_value = ([tar_entries(names)], {})
    with pytest.raises(ValueError):
        DockerExecutionBackend(MagicMock()).artifacts(container)


def test_artifact_transport_limit_before_parsing(monkeypatch):
    import browsergrid.execution.docker_backend as executor
    from types import SimpleNamespace

    monkeypatch.setattr(executor, "settings", lambda: SimpleNamespace(max_run_artifacts_bytes=8))
    container = MagicMock()
    container.get_archive.return_value = ([b"12345", b"67890"], {})
    with pytest.raises(ValueError, match="transport limit"):
        DockerExecutionBackend(MagicMock()).artifacts(container)


def test_artifact_entry_limit_counts_directories():
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as archive:
        for index in range(2001):
            item = tarfile.TarInfo(f"results/directory-{index}")
            item.type = tarfile.DIRTYPE
            archive.addfile(item)
    container = MagicMock()
    container.get_archive.return_value = ([out.getvalue()], {})
    with pytest.raises(ValueError, match="Too many"):
        DockerExecutionBackend(MagicMock()).artifacts(container)
