import io
import json
import socket
import tarfile
import time
from pathlib import Path, PurePosixPath
import docker
from browsergrid.config import settings
from browsergrid.execution.backend import ExecutionBackend


class DockerExecutionBackend(ExecutionBackend):
    def __init__(self, client=None):
        self.client = client or docker.from_env(timeout=10)

    def create(self, spec):
        s = settings()
        # Sandbox has NO mounts, engine socket, credentials, host ports or host networking.
        container = self.client.containers.create(
            s.runtime_image,
            command=["node", "/opt/browsergrid/runner.cjs"],
            user="1000:1000",
            detach=True,
            init=True,
            read_only=True,
            cap_drop=["ALL"],
            security_opt=[
                "no-new-privileges:true",
                "seccomp=" + Path(__file__).with_name("seccomp.json").read_text(),
            ],
            mem_limit="2g",
            memswap_limit="2g",
            nano_cpus=2_000_000_000,
            pids_limit=256,
            network=s.sandbox_network,
            tmpfs={
                "/work": "rw,nosuid,nodev,size=1073741824,uid=1000,gid=1000,mode=0700",
                "/tmp": "rw,nosuid,nodev,size=134217728,uid=1000,gid=1000,mode=1777",
            },
            shm_size="256m",
            working_dir="/work",
            environment={
                "HOME": "/work",
                "BG_PROXY": s.egress_proxy,
                "HTTP_PROXY": s.egress_proxy,
                "HTTPS_PROXY": s.egress_proxy,
                "http_proxy": s.egress_proxy,
                "https_proxy": s.egress_proxy,
                "NO_PROXY": "",
                "NODE_PATH": "/opt/browsergrid/node_modules",
                "PLAYWRIGHT_BROWSERS_PATH": "/ms-playwright",
            },
            labels={
                "browsergrid.sandbox": "true",
                "browsergrid.job_id": spec.job_id,
                "browsergrid.lease": spec.lease_token,
                "browsergrid.deadline": str(
                    spec.expires_at
                    or (time.time() + min(900, spec.config.get("timeout_seconds", 900)))
                ),
            },
            log_config=docker.types.LogConfig(
                type="json-file", config={"max-size": "10m", "max-file": "1"}
            ),
        )
        try:
            # tmpfs is mounted only after start. Runner waits for a bounded input file.
            container.start()
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode="w") as archive:
                files = {
                    **spec.files,
                    "input.json": json.dumps(
                        {"config": spec.config, "environment": spec.environment}
                    ).encode(),
                    "ready": b"1",
                }
                directories = sorted(
                    {
                        str(parent)
                        for name in files
                        for parent in PurePosixPath(name).parents
                        if str(parent) != "."
                    },
                    key=lambda value: (value.count("/"), value),
                )
                for directory in directories:
                    if (
                        PurePosixPath(directory).is_absolute()
                        or ".." in PurePosixPath(directory).parts
                    ):
                        raise ValueError("Unsafe execution directory")
                    info = tarfile.TarInfo(directory)
                    info.type = tarfile.DIRTYPE
                    info.uid = info.gid = 1000
                    info.mode = 0o700
                    archive.addfile(info)
                for name, content in files.items():
                    path = PurePosixPath(name)
                    if path.is_absolute() or ".." in path.parts:
                        raise ValueError("Unsafe execution input path")
                    info = tarfile.TarInfo(str(path))
                    info.size = len(content)
                    info.uid = info.gid = 1000
                    info.mode = 0o600
                    archive.addfile(info, io.BytesIO(content))
            self._write_input(container, data.getvalue())
            return container
        except Exception:
            self.stop(container)
            raise

    def _write_input(self, container, data):
        # Docker's archive API rejects a read-only rootfs even for a writable tmpfs.
        # A non-root exec extracts trusted, validated input into the existing tmpfs.
        execution = self.client.api.exec_create(
            container.id,
            cmd=["tar", "--extract", "--no-same-owner", "--file=-", "--directory=/work"],
            user="1000:1000",
            privileged=False,
            stdin=True,
            stdout=True,
            stderr=True,
        )
        connection = self.client.api.exec_start(execution["Id"], socket=True)
        try:
            transport = getattr(connection, "_sock", connection)
            transport.settimeout(30)
            transport.sendall(data)
            transport.shutdown(socket.SHUT_WR)
            # Drain the bounded exec response so the daemon can signal completion.
            received = 0
            while chunk := transport.recv(8192):
                received += len(chunk)
                if received > 65536:
                    raise RuntimeError("Execution input extraction output exceeds limit")
        finally:
            connection.close()
        result = self.client.api.exec_inspect(execution["Id"])
        if result.get("Running") or result.get("ExitCode") != 0:
            raise RuntimeError("Execution input extraction failed")

    def stop(self, container):
        try:
            container.remove(force=True)
        except docker.errors.NotFound:
            pass

    def status(self, container):
        container.reload()
        return container.attrs["State"]

    def artifacts(self, container):
        # Engine archive access does not expose the live container's tmpfs mounts.
        execution = self.client.api.exec_create(
            container.id,
            cmd=["tar", "--create", "--file=-", "--directory=/work", "results"],
            user="1000:1000",
            privileged=False,
            stdout=True,
            stderr=False,
        )
        chunks = self.client.api.exec_start(execution["Id"], stream=True)
        # Bound the TAR transport too, before parsing any untrusted archive metadata.
        limit = settings().max_run_artifacts_bytes
        data = io.BytesIO()
        try:
            for chunk in chunks:
                if data.tell() + len(chunk) > limit:
                    raise ValueError("Artifact transport limit exceeded")
                data.write(chunk)
        finally:
            if hasattr(chunks, "close"):
                chunks.close()
        outcome = self.client.api.exec_inspect(execution["Id"])
        if outcome.get("Running") or outcome.get("ExitCode") != 0:
            raise RuntimeError("Artifact archive extraction failed")
        data.seek(0)
        result = {}
        seen = set()
        with tarfile.open(fileobj=data, mode="r:") as archive:
            for count, item in enumerate(archive, 1):
                if count > 2000:
                    raise ValueError("Too many artifact archive entries")
                path = PurePosixPath(item.name)
                canonical = str(path)
                expected = item.name.rstrip("/") if item.isdir() else item.name
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or not path.parts
                    or path.parts[0] != "results"
                    or "\\" in item.name
                    or "\0" in item.name
                    or canonical != expected
                    or len(canonical.encode()) > 500
                    or any(len(part.encode()) > 255 for part in path.parts)
                ):
                    raise ValueError("Unsafe artifact path")
                if canonical in seen:
                    raise ValueError("Duplicate artifact archive entry")
                seen.add(canonical)
                if item.isdir():
                    continue
                if not item.isfile():
                    raise ValueError("Artifact links and special files rejected")
                if len(path.parts) < 2:
                    raise ValueError("Invalid artifact root file")
                if (
                    item.size < 0
                    or item.size > settings().max_artifact_bytes
                    or len(result) >= 1000
                ):
                    raise ValueError("Artifact limit exceeded")
                content = archive.extractfile(item).read(item.size + 1)
                if len(content) != item.size:
                    raise ValueError("Incomplete artifact")
                result[str(PurePosixPath(*path.parts[1:]))] = content
        for name in result:
            if any(str(parent) in result for parent in PurePosixPath(name).parents):
                raise ValueError("Artifact file/directory collision")
        return result
