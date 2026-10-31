"""Create isolated mailbox workflows using n8n's public API."""

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID


class N8nUnavailable(Exception):
    """The remote result may be unknown; callers must reconcile before retrying."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class N8nMailboxClient:
    def __init__(self, base_url: str, api_key: str, template_path: Path, backend_url: str):
        parsed = urlparse(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or (
                parsed.scheme == "http" and parsed.hostname not in {"n8n", "localhost", "127.0.0.1"}
            )
            or not api_key
        ):
            raise N8nUnavailable("Invalid n8n configuration")
        self.base_url = f"{parsed.scheme}://{parsed.netloc}/api/v1"
        self.api_key = api_key
        self.template_path = template_path
        self.backend_url = backend_url

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        if not path.startswith("/") or ".." in path or "?" in path or "#" in path:
            raise N8nUnavailable("Invalid n8n request")
        data = json.dumps(body).encode() if body is not None else None
        request = Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"X-N8N-API-KEY": self.api_key, "Content-Type": "application/json"},
        )
        try:
            with build_opener(_NoRedirect()).open(request, timeout=15) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise N8nUnavailable("Invalid n8n response")
                parsed = json.loads(raw) if raw else {}
                if not isinstance(parsed, dict):
                    raise N8nUnavailable("Invalid n8n response")
                return parsed
        except HTTPError, URLError, OSError, ValueError:
            raise N8nUnavailable("n8n request failed") from None

    def workflow(self, mailbox_id: UUID, imap_id: str, automation_id: str) -> dict:
        parsed = urlparse(self.backend_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise N8nUnavailable("Invalid backend URL")
        try:
            workflow = json.loads(self.template_path.read_text())
            identity = mailbox_id.hex
            removed = {"Webhook", "Prepare webhook", "Respond to webhook?", "Respond"}
            nodes = [node for node in workflow["nodes"] if node["name"] not in removed]
            connections = {}
            for name, value in workflow["connections"].items():
                if name in removed:
                    continue
                outputs = [
                    [edge for edge in (output or []) if edge["node"] not in removed]
                    for output in value["main"]
                ]
                if any(outputs):
                    connections[name] = {"main": outputs}
            for node in nodes:
                if node["name"] == "Email Trigger (IMAP)":
                    node["id"] = f"bgm-imap-{identity}"
                    node.pop("disabled", None)
                    node["credentials"] = {
                        "imap": {"id": imap_id, "name": f"BEC Guard IMAP {identity}"}
                    }
                if node["name"] in {"Ingest email", "Analyze email"}:
                    node["credentials"] = {
                        "httpHeaderAuth": {
                            "id": automation_id,
                            "name": f"BEC Guard connector {identity}",
                        }
                    }
                if node["name"] == "Configuration":
                    node["parameters"]["assignments"]["assignments"][0]["value"] = (
                        f"{parsed.scheme}://{parsed.netloc}"
                    )
            return {
                "name": f"BEC Guard — buzón {identity}",
                "nodes": nodes,
                "connections": connections,
                "settings": workflow["settings"],
            }
        except OSError, ValueError, KeyError, TypeError:
            raise N8nUnavailable("Invalid workflow template") from None
