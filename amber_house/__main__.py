"""Run an AmberHouse local instance."""

import argparse
from pathlib import Path

from .server import make_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an AmberHouse local registry")
    parser.add_argument("--root", type=Path, required=True, help="persistent registry directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = make_server(args.root, args.host, args.port)
    print(f"http://{server.server_address[0]}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
