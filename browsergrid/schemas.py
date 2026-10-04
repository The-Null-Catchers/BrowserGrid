import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Invalid email")
        return value.lower()


class Named(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class Viewport(BaseModel):
    name: str = Field(default="desktop", max_length=40)
    width: int = Field(default=1440, ge=240, le=3840)
    height: int = Field(default=900, ge=240, le=2160)
    device_scale_factor: float = Field(default=1, ge=1, le=3)
    mobile: bool = False
    touch: bool = False
    user_agent: str | None = Field(default=None, max_length=500)


class Source(BaseModel):
    type: Literal["inline", "git", "bundle"] = "inline"
    code: str | None = Field(default=None, max_length=100_000)
    repository: str | None = None
    commit: str | None = None
    bundle_id: str | None = None

    @model_validator(mode="after")
    def validate_source(self):
        if self.type == "inline" and not self.code:
            raise ValueError("Inline source requires code")
        if self.type == "git":
            if not self.repository or not re.fullmatch(
                r"https://github\.com/[\w.-]+/[\w.-]+(?:\.git)?", self.repository
            ):
                raise ValueError("Public HTTPS GitHub repository required")
            if not self.commit or not re.fullmatch(r"[a-fA-F0-9]{40}", self.commit):
                raise ValueError("Exact 40-character commit SHA required")
        if self.type == "bundle" and not self.bundle_id:
            raise ValueError("Bundle ID required")
        return self


class RunConfig(BaseModel):
    source: Source
    browsers: list[Literal["chromium", "firefox", "webkit"]] = Field(
        default=["chromium"], min_length=1, max_length=3
    )
    viewports: list[Viewport] = Field(
        default_factory=lambda: [Viewport()], min_length=1, max_length=4
    )
    timeout_seconds: int = Field(default=900, ge=10, le=900)
    retries: int = Field(default=0, ge=0, le=2)
    command: list[str] = Field(
        default=["/opt/browsergrid/node_modules/.bin/playwright", "test"],
        min_length=1,
        max_length=20,
    )
    working_directory: str = Field(default=".", max_length=200)
    base_url: str | None = Field(default=None, max_length=2000)
    env: dict[str, str] = Field(default_factory=dict)
    video: Literal["off", "on", "retain-on-failure"] = "retain-on-failure"
    trace: Literal["off", "on", "retain-on-failure", "on-first-retry"] = "retain-on-failure"
    screenshot: Literal["off", "on", "only-on-failure"] = "only-on-failure"
    retention_days: Literal[7, 30, 90] = 30

    @field_validator("working_directory")
    @classmethod
    def relative_directory(cls, value):
        from pathlib import PurePosixPath

        if (
            "\\" in value
            or PurePosixPath(value).is_absolute()
            or ".." in PurePosixPath(value).parts
        ):
            raise ValueError("Working directory must be relative")
        return value

    @field_validator("env")
    @classmethod
    def env_valid(cls, value):
        from browsergrid.security import validate_env

        validate_env(value)
        return value

    @model_validator(mode="after")
    def matrix_valid(self):
        if len(set(self.browsers)) != len(self.browsers):
            raise ValueError("Duplicate browsers")
        if "firefox" in self.browsers and any(v.mobile for v in self.viewports):
            raise ValueError(
                "Firefox does not support mobile emulation; use a touch viewport without mobile"
            )
        if len({v.name for v in self.viewports}) != len(self.viewports):
            raise ValueError("Viewport names must be unique")
        return self


class RunCreate(BaseModel):
    project_id: str
    config: RunConfig


class KeyCreate(Named):
    scopes: list[Literal["runs:read", "runs:write", "projects:read", "artifacts:read"]]
    expires_days: int = Field(default=30, ge=1, le=365)


class SecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=4, max_length=8192)


class MemberCreate(BaseModel):
    email: str
    role: Literal["admin", "developer", "viewer"]
