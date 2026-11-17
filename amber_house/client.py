"""Thin client with a verified local content-addressed download cache."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from urllib.request import Request, urlopen


class AmberClient:
    def __init__(self, base_url: str, cache_dir: Path) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        data = json.dumps(payload, ensure_ascii=False).encode()
        request = Request(self.base_url + path, data=data, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    def compile(self, spec: dict[str, object]) -> dict[str, object]:
        return self._post("/v1/specs/compile", {"spec": spec})

    def upload(self, spec: dict[str, object], target: dict[str, str], source: str) -> dict[str, object]:
        return self._post("/v1/implementations", {"spec": spec, "target": target, "source": source})

    def search(self, spec: dict[str, object], target: dict[str, str]) -> dict[str, object]:
        return self._post("/v1/queries", {"spec": spec, "target": target})

    def download(self, source_digest: str) -> tuple[Path, bool]:
        if re.fullmatch(r"sha256:[0-9a-f]{64}", source_digest) is None:
            raise ValueError("invalid source digest")
        expected = source_digest[7:]
        path = self.cache_dir / expected
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            return path, True
        with urlopen(self.base_url + "/v1/artifacts/" + source_digest, timeout=10) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise OSError("downloaded source digest mismatch")
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return path, False
