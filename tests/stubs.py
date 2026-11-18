"""Stand-ins for the registry and the app, so promote and push run without a deploy.

`Registry` is a directory the stub `skopeo` and `docker` in tests/fixtures/stubs
read and write. `Health` is a local HTTP server that answers like an app whose
version follows a tag, the way Podman auto-update makes it follow `:prod`.
"""

import hashlib
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from workflow import ROOT

STUBS = ROOT / "tests" / "fixtures" / "stubs"


def digest(name):
    return "sha256:" + hashlib.sha256(name.encode()).hexdigest()


class Registry:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        (self.dir / "tags").mkdir()
        (self.dir / "kinds").mkdir()

    def close(self):
        self._tmp.cleanup()

    def add(self, name, kind="image", tags=()):
        """An image the registry holds, and the tags pointing at it. Returns its digest."""
        d = digest(name)
        (self.dir / "kinds" / d).write_text(kind)
        for t in tags:
            self.tag(t, d)
        return d

    def tag(self, name, d):
        (self.dir / "tags" / name).write_text(d + "\n")

    def tag_of(self, name):
        f = self.dir / "tags" / name
        return f.read_text().strip() if f.exists() else None

    def calls(self):
        f = self.dir / "calls.log"
        return f.read_text().splitlines() if f.exists() else []

    def env(self):
        return {"PATH": f"{STUBS}:/usr/local/bin:/usr/bin:/bin", "STUB": str(self.dir)}


class Health:
    """GET answers `behave(version_of_prod, poll_number)` as (status, body).

    `tag_of` returns the digest `:prod` points at now; `versions` maps a digest to the version that image reports."""

    def __init__(self, tag_of, versions, behave):
        self.polls = 0
        self.headers_seen = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.polls += 1
                outer.headers_seen.append(dict(self.headers))
                version = versions.get(tag_of())
                status, body = behave(version, outer.polls)
                self.send_response(status)
                self.end_headers()
                self.wfile.write(body.encode())

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/healthz"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
