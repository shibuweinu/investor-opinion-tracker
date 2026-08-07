from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class RepositoryIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical_remote: str
    owner: str
    git_identity: str


class TrustedRepository(RepositoryIdentity):
    authorized_at: datetime


class TrustBackend(Protocol):
    def read(self) -> str | None: ...
    def write(self, value: str) -> None: ...
    def delete(self) -> None: ...


class FileTrustBackend:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> str | None:
        return self.path.read_text() if self.path.exists() else None

    def write(self, value: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(value, encoding="utf-8")
        os.chmod(self.path, 0o600)

    def delete(self) -> None:
        if self.path.exists():
            self.path.unlink()


class KeychainTrustBackend:
    service = "investor-opinion-tracker-config-trust"

    def __init__(self, account: str):
        self.account = account

    def read(self) -> str | None:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", self.service, "-a", self.account, "-w"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def write(self, value: str) -> None:
        subprocess.run(
            ["security", "add-generic-password", "-U", "-s", self.service, "-a", self.account, "-w", value],
            check=True,
            capture_output=True,
        )

    def delete(self) -> None:
        subprocess.run(
            ["security", "delete-generic-password", "-s", self.service, "-a", self.account],
            capture_output=True,
        )


class DeviceTrustStore:
    def __init__(self, backend: TrustBackend):
        self.backend = backend

    def authorize(self, identity: RepositoryIdentity) -> None:
        record = TrustedRepository(**identity.model_dump(), authorized_at=datetime.now(UTC))
        self.backend.write(record.model_dump_json())

    def is_trusted(self, identity: RepositoryIdentity) -> bool:
        raw = self.backend.read()
        if not raw:
            return False
        record = TrustedRepository.model_validate_json(raw)
        return all(
            getattr(record, field) == getattr(identity, field)
            for field in ("canonical_remote", "owner", "git_identity")
        )

    def revoke(self) -> None:
        self.backend.delete()
