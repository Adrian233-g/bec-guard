import json
import subprocess
from pathlib import Path
from uuid import UUID

import pytest

from app.services.n8n_mailboxes import N8nMailboxClient, N8nUnavailable

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "n8n/workflows/bec-analysis-webhook.json"


def test_python_generator_matches_canonical_javascript_generator():
    mailbox_id = UUID("11111111-2222-4333-8444-555555555555")
    client = N8nMailboxClient("http://n8n:5678", "test-key", TEMPLATE, "http://backend:8000")
    python_workflow = client.workflow(mailbox_id, "imap1", "auth1")
    module = (ROOT / "n8n/mailbox-workflow.mjs").as_uri()
    script = """
      const {mailboxWorkflow} = await import(process.argv[1]);
      const {name,nodes,connections,settings} = mailboxWorkflow({mailboxId:process.argv[2],
        imapCredentialId:'imap1',automationCredentialId:'auth1',backendUrl:'http://backend:8000'});
      process.stdout.write(JSON.stringify({name,nodes,connections,settings}));
    """
    run = subprocess.run(
        ["node", "--input-type=module", "-e", script, module, str(mailbox_id)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert python_workflow == json.loads(run.stdout)
    serialized = json.dumps(python_workflow)
    assert "app-password" not in serialized
    assert "AUTOMATION_API_KEY" not in serialized


@pytest.mark.parametrize(
    "url", ["http://external.example", "https://user:pass@example.com", "http://n8n:5678/path"]
)
def test_client_rejects_insecure_or_credential_bearing_url(url):
    with pytest.raises(N8nUnavailable):
        N8nMailboxClient(url, "key", TEMPLATE, "http://backend:8000")


def test_http_redirect_does_not_forward_n8n_key():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    reached = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            reached.append(self.path)
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/stolen")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = N8nMailboxClient(
            f"http://127.0.0.1:{server.server_port}",
            "private-api-key",
            TEMPLATE,
            "http://backend:8000",
        )
        with pytest.raises(N8nUnavailable) as error:
            client.request("POST", "/credentials", {"password": "private-password"})
        assert "private" not in str(error.value)
        assert reached == ["/api/v1/credentials"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
