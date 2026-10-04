import hashlib
import io
import ipaddress
import re
import stat
import zipfile
from pathlib import PurePosixPath
from cryptography.fernet import Fernet
from browsergrid.config import settings


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def encrypt(value: str) -> str:
    return Fernet(settings().key()).encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return Fernet(settings().key()).decrypt(value.encode()).decode()


RESERVED = {
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "NODE_OPTIONS",
    "NODE_PATH",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "PATH",
    "HOME",
    "PLAYWRIGHT_BROWSERS_PATH",
}


def validate_env(env: dict):
    if len(env) > 50 or sum(len(str(k)) + len(str(v)) for k, v in env.items()) > 32768:
        raise ValueError("Environment too large")
    for key, value in env.items():
        if (
            not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", key)
            or key in RESERVED
            or key.startswith("BG_")
            or "\0" in value
        ):
            raise ValueError("Invalid or reserved environment variable")


class Redactor:
    def __init__(self, secrets):
        import base64
        import urllib.parse

        self.values = sorted(
            {
                v
                for s in secrets
                if s
                for v in (s, urllib.parse.quote(s, safe=""), base64.b64encode(s.encode()).decode())
            },
            key=len,
            reverse=True,
        )

    def text(self, value: str) -> str:
        for secret in self.values:
            value = value.replace(secret, "[REDACTED]")
        return value

    def data(self, value):
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.data(v) for v in value]
        if isinstance(value, dict):
            return {k: self.data(v) for k, v in value.items()}
        return value


def validate_bundle(data: bytes) -> dict[str, bytes]:
    if len(data) > settings().max_bundle_bytes:
        raise ValueError("Archive too large")
    result = {}
    total = 0
    seen = set()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if len(archive.infolist()) > 500:
            raise ValueError("Too many archive entries")
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in info.filename
                or "\0" in info.filename
                or (mode & 0o170000) == 0o120000
            ):
                raise ValueError("Unsafe archive path or symlink")
            canonical = str(path)
            expected = info.filename.rstrip("/") if info.is_dir() else info.filename
            if not path.parts or canonical != expected or re.match(r"^[A-Za-z]:", canonical):
                raise ValueError("Non-canonical archive path")
            if len(canonical.encode()) > 500 or any(len(p.encode()) > 255 for p in path.parts):
                raise ValueError("Archive path too long")
            if canonical in seen:
                raise ValueError("Duplicate archive entry")
            seen.add(canonical)
            file_type = stat.S_IFMT(mode)
            if file_type not in {0, stat.S_IFREG, stat.S_IFDIR} or (
                file_type == stat.S_IFDIR and not info.is_dir()
            ):
                raise ValueError("Archive special files rejected")
            if info.is_dir():
                continue
            total += info.file_size
            if (
                total > 25 * 1024 * 1024
                or info.file_size > 5 * 1024 * 1024
                or info.file_size > 200 * max(1, info.compress_size)
            ):
                raise ValueError("Archive expansion limit exceeded")
            if info.filename in result or any(p in {"node_modules", ".git"} for p in path.parts):
                raise ValueError("Duplicate or forbidden archive entry")
            result[info.filename] = archive.read(info)
    for name in result:
        if any(str(parent) in result for parent in PurePosixPath(name).parents):
            raise ValueError("Archive file/directory collision")
    if not {"package.json", "package-lock.json"} <= result.keys() or not any(
        p.startswith("tests/") for p in result
    ):
        raise ValueError("Bundle requires package.json, package-lock.json and tests/")
    return result


def is_public_ip(value: str) -> bool:
    return ipaddress.ip_address(value).is_global
