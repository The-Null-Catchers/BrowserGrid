from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ExecutionSpec:
    job_id: str
    lease_token: str
    config: dict
    environment: dict
    files: dict[str, bytes]


class ExecutionBackend(ABC):
    @abstractmethod
    def create(self, spec: ExecutionSpec): ...
    @abstractmethod
    def stop(self, execution): ...
    @abstractmethod
    def status(self, execution): ...
