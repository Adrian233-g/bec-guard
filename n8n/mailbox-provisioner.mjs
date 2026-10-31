// n8n provisioning primitives. The caller MUST persist the operation and each
// returned resource ID before continuing, and reconcile uncertain network outcomes.
import { randomBytes } from 'node:crypto';
import { mailboxWorkflow } from './mailbox-workflow.mjs';

const credentialId = () => randomBytes(12).toString('base64url');
const safeId = id => typeof id === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(id);

export class ProvisioningError extends Error {
  constructor(stage, resources, uncertain = false) {
    super(`Mailbox provisioning failed at ${stage}`);
    this.name = 'ProvisioningError';
    this.stage = stage;
    this.resources = { ...resources };
    this.uncertain = uncertain;
  }
}

/**
 * request(method, path, body) returns a parsed object. It must reject on any
 * non-2xx response and must never log request bodies or response error bodies.
 * checkpoint(stage, ids) must durably persist resource identifiers before return.
 */
export async function createMailboxReceiver({ request, checkpoint, mailboxId, email, appPassword,
  connectorToken, backendUrl }) {
  const resources = { imapCredentialId: credentialId(), automationCredentialId: credentialId() };
  const id = mailboxId.replaceAll('-', '').toLowerCase();
  // Validate before sending either credential anywhere.
  const draft = mailboxWorkflow({ mailboxId, imapCredentialId: resources.imapCredentialId,
    automationCredentialId: resources.automationCredentialId, backendUrl });
  if (!email || !appPassword || !connectorToken) throw new Error('Invalid connector configuration');
  let stage = 'checkpoint';
  try {
    await checkpoint('allocated', resources);
    stage = 'imap credential';
    await request('POST', '/credentials', { id: resources.imapCredentialId,
      name: `BEC Guard IMAP ${id}`, type: 'imap', data: { user: email, password: appPassword,
        host: 'imap.gmail.com', port: 993, secure: true, allowUnauthorizedCerts: false } });
    await checkpoint('imap-created', resources);
    stage = 'imap verification';
    const verification = await request('POST', `/credentials/${resources.imapCredentialId}/test`);
    if (verification?.status !== 'OK') throw new Error('verification failed');
    await checkpoint('imap-verified', resources);
    stage = 'automation credential';
    await request('POST', '/credentials', { id: resources.automationCredentialId,
      name: `BEC Guard connector ${id}`, type: 'httpHeaderAuth',
      data: { name: 'X-BEC-Automation-Key', value: connectorToken } });
    await checkpoint('automation-created', resources);
    stage = 'workflow';
    // n8n assigns workflow IDs; id, active and pinData are read-only or not accepted.
    const { name, nodes, connections, settings } = draft;
    const created = await request('POST', '/workflows', { name, nodes, connections, settings });
    if (!safeId(created?.id)) throw new Error('invalid workflow id');
    resources.workflowId = created.id;
    await checkpoint('workflow-created', resources);
    // Activation is deliberately separate: backend must first commit the ownership
    // and activation state, otherwise arrivals can race with database persistence.
    return { ...resources };
  } catch {
    // Network errors and failed checkpoints can leave remote resources behind;
    // never claim rollback succeeded or retry until the operation is reconciled.
    throw new ProvisioningError(stage, resources, true);
  }
}

export async function publishMailboxReceiver({ request, workflowId }) {
  if (!safeId(workflowId)) throw new Error('Invalid workflow id');
  try {
    await request('POST', `/workflows/${workflowId}/publish`);
  } catch {
    throw new ProvisioningError('workflow publish', { workflowId }, true);
  }
}

export async function removeMailboxReceiver({ request, resources, checkpoint }) {
  const { workflowId, imapCredentialId, automationCredentialId } = resources;
  if (![workflowId, imapCredentialId, automationCredentialId].every(safeId)) {
    throw new Error('Invalid resource ids');
  }
  let stage = 'unpublish';
  try {
    await request('POST', `/workflows/${workflowId}/unpublish`);
    await checkpoint('workflow-unpublished', resources);
    stage = 'delete workflow';
    await request('DELETE', `/workflows/${workflowId}`);
    await checkpoint('workflow-deleted', resources);
    stage = 'delete imap credential';
    await request('DELETE', `/credentials/${imapCredentialId}`);
    await checkpoint('imap-deleted', resources);
    stage = 'delete automation credential';
    await request('DELETE', `/credentials/${automationCredentialId}`);
    await checkpoint('automation-deleted', resources);
  } catch {
    throw new ProvisioningError(stage, resources, true);
  }
}
