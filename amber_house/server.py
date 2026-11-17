"""Small local HTTP surface for Spec compilation, upload, search and download."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from pathlib import Path
from urllib.parse import urlsplit

from amber_spec import SpecError, digest, validate_spec
from .store import Registry


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key}")
        result[key] = value
    return result


class LocalHTTPServer(ThreadingHTTPServer):
    def server_bind(self) -> None:
        # HTTPServer normally performs a DNS lookup here, which is unnecessary
        # for a local registry and can stall startup on isolated machines.
        TCPServer.server_bind(self)
        self.server_name = self.server_address[0]
        self.server_port = self.server_address[1]


def make_server(root: Path, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    registry = Registry(root)

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, value: object) -> None:
            data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 1_500_000:
                self._json(413, {"error": "request body must be 1 byte to 1.5 MB"})
                return
            try:
                body = json.loads(self.rfile.read(length), object_pairs_hook=_unique_pairs)
                if not isinstance(body, dict):
                    raise ValueError("request body must be an object")
                path = urlsplit(self.path).path
                if path == "/v1/specs/compile":
                    spec = validate_spec(body.get("spec"))
                    response = {"spec_digest": digest(spec), "spec": spec}
                elif path == "/v1/implementations":
                    response = registry.upload(body.get("spec"), body.get("target"), body.get("source"))
                elif path == "/v1/queries":
                    response = registry.search(body.get("spec"), body.get("target"))
                else:
                    self._json(404, {"error": "unknown endpoint"})
                    return
                self._json(200, response)
            except (ValueError, SpecError, TypeError, KeyError) as exc:
                self._json(422, {"error": str(exc)})

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/health":
                self._json(200, {"status": "ok"})
                return
            if path.startswith("/v1/artifacts/"):
                try:
                    data = registry.download(path.removeprefix("/v1/artifacts/"))
                except FileNotFoundError:
                    self._json(404, {"error": "artifact not found"})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._json(404, {"error": "unknown endpoint"})

    return LocalHTTPServer((host, port), Handler)
