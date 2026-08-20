"""Runnable HTTP entry point for issuing legal asset upload intents."""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from legal_asset_uploads import InfraiError, InfraiStorage, LegalAssetUploads, UploadIntentRequest


class MatterIntakeHandler(BaseHTTPRequestHandler):
    workflow: LegalAssetUploads

    def do_POST(self) -> None:
        if self.path != "/upload-intents":
            self._json(404, {"error": "route not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = UploadIntentRequest.from_dict(json.loads(self.rfile.read(length)))
            intent = self.workflow.issue_upload(request)
            self._json(201, asdict(intent))
        except (ValueError, json.JSONDecodeError) as error:
            self._json(400, {"error": str(error)})
        except InfraiError as error:
            status = error.status if 400 <= error.status < 500 else 502
            self._json(status, {"error": error.code, "detail": error.detail})
        except ConnectionError as error:
            self._json(502, {"error": str(error)})

    def _json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    workflow = LegalAssetUploads(InfraiStorage.from_environment())
    workflow.prepare()
    MatterIntakeHandler.workflow = workflow
    server = ThreadingHTTPServer(("127.0.0.1", 8080), MatterIntakeHandler)
    print("Legal asset upload service listening on http://127.0.0.1:8080")
    server.serve_forever()


if __name__ == "__main__":
    main()
