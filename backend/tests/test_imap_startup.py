import json
import subprocess
from pathlib import Path

import pytest

PATCH = Path(__file__).resolve().parents[2] / "n8n/image/patch-imap-startup.cjs"


@pytest.fixture
def patched_module(tmp_path):
    source = tmp_path / "node.js"
    source.write_text("""
const n8n_workflow_1 = {NodeOperationError: class NodeOperationError extends Error {
  constructor(node, message) {super(message)}
}};
exports.start = async function (workflow, node, connection, staticData) {
  const currentSearchCriteria = [];
  currentSearchCriteria.push(['UID', `${staticData.lastMessageUid}:*`]);
  const fetchNewEmails = async () => {};
  const self = {getWorkflow: () => ({id: workflow})};
  await (async function () {
        connection.onArrival(async ({ count }) => await fetchNewEmails(connection, count));
  }).call(self);
  return {last: staticData.lastMessageUid, criteria: currentSearchCriteria};
};
""")
    subprocess.run(["node", str(PATCH), str(source)], check=True)
    return source


def run_start(source, workflow, node, uid_next, previous):
    script = """const m=require(process.argv[1]); const cfg=JSON.parse(process.argv[2]);
const c={client:{mailbox:{uidNext:cfg.uid}}, onArrival:()=>{}, end:async()=>{}};
m.start(cfg.workflow,{id:cfg.node},c,{lastMessageUid:cfg.previous})
 .then(x=>console.log(JSON.stringify(x))).catch(e=>{console.log(e.message);process.exit(1)});"""
    return subprocess.run(
        [
            "node",
            "-e",
            script,
            str(source),
            json.dumps(dict(workflow=workflow, node=node, uid=uid_next, previous=previous)),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_startup_skips_existing_uids_and_handles_empty_mailbox(patched_module):
    for uid_next, expected in [(42, 41), (1, 0)]:
        run = run_start(patched_module, "bec-guard-analysis-webhook", "imap-trigger", uid_next, 5)
        assert run.returncode == 0
        assert json.loads(run.stdout)["last"] == expected
    run = run_start(patched_module, "bec-guard-analysis-webhook", "imap-trigger", 1, 0)
    assert json.loads(run.stdout)["criteria"] == [["UID", "1:*"]]


def test_missing_uid_fails_closed_and_other_workflows_are_untouched(patched_module):
    run = run_start(patched_module, "bec-guard-analysis-webhook", "imap-trigger", None, 5)
    assert run.returncode != 0 and "UIDNEXT unavailable" in run.stdout
    run = run_start(patched_module, "other-workflow", "imap-trigger", 42, 5)
    assert json.loads(run.stdout)["last"] == 5
