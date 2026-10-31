// Construct a receiver from the canonical analysis workflow. Secrets stay in
// n8n credentials; this module only handles opaque credential identifiers.
import { readFileSync } from 'node:fs';

const template = JSON.parse(readFileSync(new URL('./workflows/bec-analysis-webhook.json', import.meta.url), 'utf8'));

export function mailboxWorkflow({ mailboxId, imapCredentialId, automationCredentialId, backendUrl }) {
  const id = mailboxId.replaceAll('-', '').toLowerCase();
  if (!/^[a-f0-9]{32}$/.test(id) || !imapCredentialId || !automationCredentialId) {
    throw new Error('Invalid connector configuration');
  }
  const url = new URL(backendUrl);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
      url.pathname !== '/' || url.search || url.hash) throw new Error('Invalid backend URL');
  const workflow = structuredClone(template);
  workflow.id = `bgm${id}`;
  workflow.name = `BEC Guard — buzón ${id}`;
  workflow.active = false;
  const removed = new Set(['Webhook', 'Prepare webhook', 'Respond to webhook?', 'Respond']);
  workflow.nodes = workflow.nodes.filter(node => !removed.has(node.name));
  for (const name of removed) delete workflow.connections[name];
  for (const [name, connection] of Object.entries(workflow.connections)) {
    connection.main = connection.main.map(output => (output ?? []).filter(edge => !removed.has(edge.node)));
    if (connection.main.every(output => output.length === 0)) delete workflow.connections[name];
  }
  for (const node of workflow.nodes) {
    if (node.name === 'Email Trigger (IMAP)') {
      node.id = `bgm-imap-${id}`;
      delete node.disabled;
      node.credentials = { imap: { id: imapCredentialId, name: `BEC Guard IMAP ${id}` } };
    }
    if (['Ingest email', 'Analyze email'].includes(node.name)) {
      node.credentials = { httpHeaderAuth: { id: automationCredentialId, name: `BEC Guard connector ${id}` } };
    }
    if (node.name === 'Configuration') node.parameters.assignments.assignments[0].value = url.origin;
  }
  return workflow;
}
