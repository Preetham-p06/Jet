"""Blob storage for uploaded documents.

Keys look like `{workspace_id}/{yyyy}/{mm}/{uuid4}{ext}`. They are never built
from user input, and every read checks that the key belongs to the caller's
workspace and resolves inside the storage root. An S3 backend can implement
the same protocol later.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

_SUFFIX_RE = re.compile(r"^\.[a-z0-9]{1,8}$")
_KEY_RE = re.compile(
    r"^(?P<ws>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"/\d{4}/\d{2}/[0-9a-f]{32}(?:\.[a-z0-9]{1,8})?$"
)


class StorageError(Exception):
    """Invalid key, foreign workspace, or path escaping the root."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size: int
    sha256: str


class Storage(Protocol):
    def put(
        self, workspace_id: uuid.UUID, data: bytes, *, suffix: str, content_type: str
    ) -> StoredObject:
        """Store bytes under a fresh key in the workspace's namespace."""
        ...

    def open(self, key: str, *, workspace_id: uuid.UUID) -> bytes:
        """Read an object; raises `StorageError` if it is outside the workspace."""
        ...

    def delete(self, key: str, *, workspace_id: uuid.UUID) -> None:
        """Delete an object if it exists."""
        ...


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalStorage:
    def __init__(self, root: Path) -> None:
        # Created on first write, so importing the app has no filesystem side effects.
        self.root = root.resolve()

    def put(
        self, workspace_id: uuid.UUID, data: bytes, *, suffix: str, content_type: str
    ) -> StoredObject:
        suffix = suffix.lower()
        if suffix and not _SUFFIX_RE.match(suffix):
            raise StorageError(f"invalid suffix {suffix!r}")
        now = datetime.now(UTC)
        key = f"{workspace_id}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{suffix}"
        path = self._resolve(key, workspace_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write atomically so a crash never leaves a half-written document.
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return StoredObject(key=key, size=len(data), sha256=sha256_hex(data))

    def open(self, key: str, *, workspace_id: uuid.UUID) -> bytes:
        path = self._resolve(key, workspace_id)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageError("object not found") from exc

    def delete(self, key: str, *, workspace_id: uuid.UUID) -> None:
        self._resolve(key, workspace_id).unlink(missing_ok=True)

    def _resolve(self, key: str, workspace_id: uuid.UUID) -> Path:
        match = _KEY_RE.match(key)
        if match is None or match.group("ws") != str(workspace_id):
            raise StorageError("invalid storage key")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError("storage key escapes the root")
        return path
