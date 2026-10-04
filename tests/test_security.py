import io
import zipfile
import pytest
from browsergrid.security import (
    Redactor,
    decrypt,
    encrypt,
    is_public_ip,
    validate_bundle,
    validate_env,
)


def archive(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, value in files.items():
            z.writestr(name, value)
    return out.getvalue()


@pytest.mark.parametrize(
    "path", ["../escape", "/absolute", "tests/../../etc/passwd", "tests\\escape"]
)
def test_archive_traversal(path):
    with pytest.raises(ValueError):
        validate_bundle(archive({"package.json": "{}", "tests/test.ts": "test()", path: "x"}))


def test_zip_bomb():
    with pytest.raises(ValueError, match="expansion"):
        validate_bundle(archive({"package.json": "{}", "tests/test.ts": "x" * 1_000_000}))


def test_zip_symlink():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        info = zipfile.ZipInfo("tests/link")
        info.external_attr = 0o120777 << 16
        z.writestr(info, "/etc/passwd")
    with pytest.raises(ValueError, match="symlink"):
        validate_bundle(out.getvalue())


def test_bundle():
    assert (
        validate_bundle(archive({"package.json": "{}", "tests/test.ts": "test()"}))["package.json"]
        == b"{}"
    )


@pytest.mark.parametrize(
    "name", ["HTTP_PROXY", "BG_TOKEN", "PATH", "NODE_OPTIONS", "LD_PRELOAD", "HOME"]
)
def test_reserved_env(name):
    with pytest.raises(ValueError):
        validate_env({name: "unsafe"})


def test_secret_storage_and_masking():
    value = "unique-secret-test-7788"
    ciphertext = encrypt(value)
    assert value not in ciphertext
    assert decrypt(ciphertext) == value
    assert value not in Redactor([value]).text(f"Password={value}")
    assert Redactor([value]).data({"message": value}) == {"message": "[REDACTED]"}


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "169.254.169.254", "10.0.0.1", "172.16.0.1", "192.168.0.1", "::1", "fc00::1"],
)
def test_private_ips(ip):
    assert not is_public_ip(ip)
