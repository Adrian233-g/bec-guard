import test from 'node:test';
import assert from 'node:assert/strict';
import { createMailboxReceiver, publishMailboxReceiver, removeMailboxReceiver } from '../mailbox-provisioner.mjs';

const options = {
  mailboxId: '11111111-2222-4333-8444-555555555555', email: 'user@gmail.com',
  appPassword: 'app-password-secret', connectorToken: 'connector-token-secret',
  backendUrl: 'http://backend:8000',
};

function harness(failAt) {
  const calls = [], checkpoints = [];
  return { calls, checkpoints,
    request: async (method, path, body) => {
      calls.push({ method, path, body });
      if (path.includes(failAt ?? '\0')) throw new Error('app-password-secret');
      if (path.endsWith('/test')) return { status: 'OK' };
      if (path === '/workflows') return { id: 'n8n-workflow-1' };
      return {};
    },
    checkpoint: async (stage, ids) => checkpoints.push({ stage, ids: {...ids} }),
  };
}

test('creates tested, isolated credentials and an unpublished workflow', async () => {
  const h = harness();
  const resources = await createMailboxReceiver({ ...options, ...h });
  assert.deepEqual(h.checkpoints.map(x => x.stage), [
    'allocated', 'imap-created', 'imap-verified', 'automation-created', 'workflow-created',
  ]);
  assert.match(resources.imapCredentialId, /^[A-Za-z0-9_-]{16}$/);
  assert.notEqual(resources.imapCredentialId, resources.automationCredentialId);
  const imap = h.calls[0].body;
  assert.deepEqual(imap.data, {user: options.email, password: options.appPassword,
    host: 'imap.gmail.com', port: 993, secure: true, allowUnauthorizedCerts: false});
  const workflow = h.calls.find(x => x.path === '/workflows').body;
  assert.equal(workflow.id, undefined);
  assert.equal(workflow.active, undefined);
  assert.equal(JSON.stringify(workflow).includes(options.appPassword), false);
  assert.equal(JSON.stringify(workflow).includes(options.connectorToken), false);
  assert.equal(h.calls.some(x => x.path.endsWith('/publish')), false);
  await publishMailboxReceiver({request: h.request, workflowId: resources.workflowId});
  assert.equal(h.calls.at(-1).path, '/workflows/n8n-workflow-1/publish');
});

test('failure reports stage and allocated ids without exposing secrets', async () => {
  const h = harness('/test');
  await assert.rejects(createMailboxReceiver({...options, ...h}), error => {
    assert.equal(error.stage, 'imap verification');
    assert.equal(error.uncertain, true);
    assert.equal(JSON.stringify(error).includes(options.appPassword), false);
    assert.equal(error.message.includes(options.appPassword), false);
    assert.ok(error.resources.imapCredentialId);
    return true;
  });
  assert.equal(h.calls.some(x => x.path === '/workflows'), false);
});

test('disconnect unpublishes before deleting workflow and credentials', async () => {
  const h = harness();
  const resources = {workflowId: 'workflow1', imapCredentialId: 'imap1', automationCredentialId: 'auth1'};
  await removeMailboxReceiver({ ...h, resources });
  assert.deepEqual(h.calls.map(x => `${x.method} ${x.path}`), [
    'POST /workflows/workflow1/unpublish', 'DELETE /workflows/workflow1',
    'DELETE /credentials/imap1', 'DELETE /credentials/auth1',
  ]);
  assert.equal(h.checkpoints.at(-1).stage, 'automation-deleted');
});

test('does not continue deletion if unpublish fails', async () => {
  const h = harness('/unpublish');
  await assert.rejects(removeMailboxReceiver({ ...h, resources: {
    workflowId: 'workflow1', imapCredentialId: 'imap1', automationCredentialId: 'auth1',
  }}), {stage: 'unpublish', uncertain: true});
  assert.equal(h.calls.length, 1);
});
