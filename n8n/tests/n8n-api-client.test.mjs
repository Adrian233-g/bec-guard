import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { n8nApiClient } from '../n8n-api-client.mjs';

test('sends credentials only to the configured n8n API and sanitizes errors', async () => {
  const requests = [];
  const server = http.createServer(async (req, res) => {
    let body = '';
    for await (const chunk of req) body += chunk;
    requests.push({path: req.url, key: req.headers['x-n8n-api-key'], body});
    if (req.url.endsWith('/fail')) {
      res.writeHead(400, {'Content-Type': 'application/json'}).end('{"message":"hidden-password"}');
    } else {
      res.writeHead(200, {'Content-Type': 'application/json'}).end('{"id":"resource1"}');
    }
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  try {
    const request = n8nApiClient({baseUrl: `http://127.0.0.1:${server.address().port}`, apiKey:'api-secret'});
    assert.deepEqual(await request('POST', '/credentials', {password:'hidden-password'}), {id:'resource1'});
    assert.equal(requests[0].path, '/api/v1/credentials');
    assert.equal(requests[0].key, 'api-secret');
    await assert.rejects(request('POST', '/fail', {password:'hidden-password'}), error => {
      assert.equal(error.message, 'n8n API request failed');
      assert.equal(String(error).includes('hidden-password'), false);
      return true;
    });
    await assert.rejects(request('GET', '/../malicious'));
  } finally {
    server.close();
    await once(server, 'close');
  }
});

test('rejects insecure remote hosts and credentials embedded in URL', () => {
  assert.throws(() => n8nApiClient({baseUrl:'http://public.example', apiKey:'x'}));
  assert.throws(() => n8nApiClient({baseUrl:'https://user:pass@example.com', apiKey:'x'}));
});

test('provisions a receiver end to end against a local n8n API simulation', async () => {
  const { createMailboxReceiver } = await import('../mailbox-provisioner.mjs');
  const calls = [];
  const server = http.createServer(async (req, res) => {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    const body = raw ? JSON.parse(raw) : undefined;
    calls.push({path: req.url, body});
    res.setHeader('Content-Type', 'application/json');
    if (req.url.endsWith('/test')) res.end('{"status":"OK","message":"ok"}');
    else if (req.url.endsWith('/workflows')) res.end('{"id":"workflow-generated"}');
    else res.end('{}');
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  try {
    const request = n8nApiClient({baseUrl: `http://127.0.0.1:${server.address().port}`, apiKey:'key'});
    const checkpoints = [];
    const resources = await createMailboxReceiver({request,
      checkpoint: async stage => checkpoints.push(stage),
      mailboxId:'11111111-2222-4333-8444-555555555555', email:'user@gmail.com',
      appPassword:'gmail-secret', connectorToken:'connector-secret', backendUrl:'http://backend:8000',
    });
    assert.equal(resources.workflowId, 'workflow-generated');
    assert.equal(calls.length, 4);
    assert.equal(calls[0].body.type, 'imap');
    assert.ok(calls[1].path.endsWith('/test'));
    assert.equal(calls[2].body.type, 'httpHeaderAuth');
    assert.equal(calls[3].body.name, 'BEC Guard — buzón 11111111222243338444555555555555');
    assert.equal(JSON.stringify(calls[3].body).includes('gmail-secret'), false);
    assert.equal(JSON.stringify(calls[3].body).includes('connector-secret'), false);
    assert.equal(checkpoints.at(-1), 'workflow-created');
  } finally {
    server.close();
    await once(server, 'close');
  }
});
