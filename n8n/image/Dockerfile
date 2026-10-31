FROM docker.n8n.io/n8nio/n8n:2.44.4
USER root
COPY image/patch-imap-startup.cjs /tmp/patch-imap-startup.cjs
RUN node /tmp/patch-imap-startup.cjs /usr/local/lib/node_modules/n8n/node_modules/n8n-nodes-base/dist/nodes/EmailReadImap/v2/EmailReadImapV2.node.js \
    && rm /tmp/patch-imap-startup.cjs
USER node
