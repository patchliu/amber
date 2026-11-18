"""SQLite-backed local registry with atomic catalog revision and query cache."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from pathlib import Path

from amber_spec import digest, match_spec, validate_spec
from amber_spec.core import canonical_json

_HEX_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class Registry:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.blobs = root / "blobs"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(root / "registry.sqlite3", check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS manifests (id TEXT PRIMARY KEY, spec TEXT NOT NULL, target TEXT NOT NULL, source_digest TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS catalog (singleton INTEGER PRIMARY KEY CHECK (singleton = 1), revision INTEGER NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS query_cache (key TEXT PRIMARY KEY, revision INTEGER NOT NULL, response TEXT NOT NULL)")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO catalog VALUES (1, 0)")

    @staticmethod
    def _target(value: object) -> dict[str, str]:
        if not isinstance(value, dict) or set(value) != {"backend", "architecture"}:
            raise ValueError("target requires backend and architecture")
        if any(not isinstance(item, str) or not item for item in value.values()):
            raise ValueError("target values must be nonempty strings")
        return value

    def upload(self, spec: object, target: object, source: object) -> dict[str, str]:
        valid_spec = validate_spec(spec, implementation=True)
        valid_target = self._target(target)
        if not isinstance(source, str) or not source or len(source.encode()) > 1_000_000:
            raise ValueError("source must be nonempty UTF-8 text of at most 1 MB")
        data = source.encode()
        blob = "sha256:" + hashlib.sha256(data).hexdigest()
        identity = digest({"spec": valid_spec, "target": valid_target, "source_digest": blob}, "implementation")
        path = self.blobs / blob[7:]
        with self.lock:
            if not path.exists():
                temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
                try:
                    temporary.write_bytes(data)
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
            with self.db:
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO manifests VALUES (?, ?, ?, ?)",
                    (identity, canonical_json(valid_spec).decode(), canonical_json(valid_target).decode(), blob),
                )
                if cursor.rowcount:
                    self.db.execute("UPDATE catalog SET revision = revision + 1 WHERE singleton = 1")
        return {"implementation_digest": identity, "source_digest": blob}

    def search(self, spec: object, target: object) -> dict[str, object]:
        valid_spec = validate_spec(spec)
        valid_target = self._target(target)
        key = digest({"spec": valid_spec, "target": valid_target}, "query")
        with self.lock:
            revision = self.db.execute("SELECT revision FROM catalog WHERE singleton = 1").fetchone()[0]
            row = self.db.execute("SELECT response FROM query_cache WHERE key = ? AND revision = ?", (key, revision)).fetchone()
            if row is not None:
                return {**json.loads(row[0]), "cache": "hit"}
            matches = []
            for identity, raw_spec, raw_target, blob in self.db.execute("SELECT id, spec, target, source_digest FROM manifests ORDER BY id"):
                report = match_spec(valid_spec, json.loads(raw_spec))
                if json.loads(raw_target) != valid_target:
                    report = {"decision": "rejected", "reasons": ["target differs"]}
                matches.append({
                    "implementation_digest": identity,
                    "source_digest": blob,
                    "decision": report["decision"],
                    "reasons": report["reasons"],
                    "evidence": "unverified_source_declaration",
                })
            response: dict[str, object] = {"query_digest": key, "revision": revision, "matches": matches}
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO query_cache VALUES (?, ?, ?)",
                    (key, revision, canonical_json(response).decode()),
                )
            return {**response, "cache": "miss"}

    def download(self, source_digest: str) -> bytes:
        if not _HEX_DIGEST.fullmatch(source_digest):
            raise FileNotFoundError(source_digest)
        with self.lock:
            row = self.db.execute("SELECT 1 FROM manifests WHERE source_digest = ? LIMIT 1", (source_digest,)).fetchone()
            if row is None:
                raise FileNotFoundError(source_digest)
            data = (self.blobs / source_digest[7:]).read_bytes()
        if hashlib.sha256(data).hexdigest() != source_digest[7:]:
            raise OSError("stored source digest mismatch")
        return data
