"""Read-only JSON API for a future web dashboard (token-protected)."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_server(store, token, host="127.0.0.1", port=8080):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj, raw=None, ctype="application/json"):
            data = raw if raw is not None else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"ok": True})
            if not token or self.headers.get("Authorization") != "Bearer " + token:
                return self._send(401, {"error": "unauthorized"})
            parts = self.path.strip("/").split("/")
            if parts == ["api", "projects"]:
                return self._send(200, [{"id": p[0], "name": p[1]} for p in store.projects()])
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "builds" and parts[2].isdigit():
                return self._send(200, [{"id": b[0], "status": b[1], "summary": b[2]} for b in store.builds(int(parts[2]))])
            if len(parts) == 4 and parts[:2] == ["api", "builds"] and parts[3] == "logs" and parts[2].isdigit():
                return self._send(200, store.logs(int(parts[2])))
            self._send(404, {"error": "not found"})

    return ThreadingHTTPServer((host, port), H)
