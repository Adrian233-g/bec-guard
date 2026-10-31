// n8n 2.44.4: start this workflow at Gmail's current UIDNEXT on activation.
// Scoped to the legacy BEC Guard trigger and generated mailbox triggers; it fails if the
// upstream implementation changes. No credentials or message content are read.
const fs = require('node:fs');
const path = process.argv[2];
if (!path) throw new Error('Missing IMAP node path');
let source = fs.readFileSync(path, 'utf8');
const replaceOnce = (before, after) => {
  if (source.split(before).length !== 2) throw new Error('Unsupported n8n IMAP implementation');
  source = source.replace(before, after);
};
replaceOnce(
  "currentSearchCriteria.push(['UID', `${staticData.lastMessageUid}:*`]);",
  "currentSearchCriteria.push(['UID', `${Math.max(1, staticData.lastMessageUid)}:*`]);",
);
replaceOnce(
  '        connection.onArrival(async ({ count }) => await fetchNewEmails(connection, count));',
  `        // Snapshot the mailbox after SELECT and before processing queued arrivals.
        // uidNext is supplied by the IMAP server, not by an untrusted message header.
        if ((this.getWorkflow().id === 'bec-guard-analysis-webhook' && node.id === 'imap-trigger') ||
            /^bgm-imap-[a-f0-9]{32}$/.test(node.id)) {
            const uidNext = connection.client?.mailbox?.uidNext;
            if (!Number.isSafeInteger(uidNext) || uidNext < 1) {
                await connection.end();
                throw new n8n_workflow_1.NodeOperationError(node, 'IMAP UIDNEXT unavailable; refusing to process backlog.');
            }
            staticData.lastMessageUid = uidNext - 1;
        }
        connection.onArrival(async ({ count }) => await fetchNewEmails(connection, count));`,
);
fs.writeFileSync(path, source);
