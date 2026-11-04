import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from './api';
import { IconAlerts, IconMail } from './icons';
import type { EmailSummary, Notification } from './types';

const POLL_MS = 10_000;
const EMAIL_DISPLAY_MS = 8_000;

type LiveNotice =
  | { kind: 'alert'; id: string; item: Notification }
  | { kind: 'email'; id: string; item: EmailSummary };

export function LiveUpdates() {
  const [notices, setNotices] = useState<LiveNotice[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    const seenEmails = new Set<string>();
    const seenAlerts = new Set<string>();
    let initializedEmails = false;
    let initializedAlerts = false;
    let busy = false;
    let timer: number | undefined;

    async function poll() {
      if (busy || controller.signal.aborted) return;
      busy = true;
      try {
        const [emails, alerts] = await Promise.allSettled([
          api<EmailSummary[]>('/emails?limit=100&order=ingested', {
            signal: controller.signal,
          }),
          api<Notification[]>('/notifications?limit=50', {
            signal: controller.signal,
          }),
        ]);
        if (controller.signal.aborted) return;
        const incoming: LiveNotice[] = [];
        if (emails.status === 'fulfilled' && Array.isArray(emails.value)) {
          for (const item of emails.value.slice().reverse()) {
            if (initializedEmails && !seenEmails.has(item.id)) {
              incoming.push({ kind: 'email', id: item.id, item });
            }
            seenEmails.add(item.id);
          }
          initializedEmails = true;
        }
        if (alerts.status === 'fulfilled' && Array.isArray(alerts.value)) {
          for (const item of alerts.value.slice().reverse()) {
            if (initializedAlerts && !seenAlerts.has(item.id)) {
              incoming.push({ kind: 'alert', id: item.id, item });
            }
            seenAlerts.add(item.id);
          }
          initializedAlerts = true;
        }
        if (incoming.length) {
          setNotices((existing) => [...incoming.reverse(), ...existing]);
          window.dispatchEvent(new Event('bec-live-update'));
        }
      } finally {
        busy = false;
        if (!controller.signal.aborted)
          timer = window.setTimeout(() => void poll(), POLL_MS);
      }
    }

    const onFocus = () => {
      window.clearTimeout(timer);
      void poll();
    };
    void poll();
    window.addEventListener('focus', onFocus);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
      window.removeEventListener('focus', onFocus);
    };
  }, []);

  const dismiss = useCallback((kind: LiveNotice['kind'], id: string) => {
    setNotices((existing) =>
      existing.filter((notice) => notice.kind !== kind || notice.id !== id),
    );
  }, []);

  return (
    <aside className="live-notices" aria-label="Novedades">
      {notices.map((notice) => (
        <LiveNoticeCard
          key={`${notice.kind}-${notice.id}`}
          notice={notice}
          onDismiss={dismiss}
        />
      ))}
    </aside>
  );
}

function LiveNoticeCard({
  notice,
  onDismiss,
}: {
  notice: LiveNotice;
  onDismiss: (kind: LiveNotice['kind'], id: string) => void;
}) {
  useEffect(() => {
    if (notice.kind !== 'email') return;
    const timer = window.setTimeout(
      () => onDismiss(notice.kind, notice.id),
      EMAIL_DISPLAY_MS,
    );
    return () => window.clearTimeout(timer);
  }, [notice.kind, notice.id, onDismiss]);
  const isAlert = notice.kind === 'alert';
  const sender = notice.item.sender_name || notice.item.sender_email;
  return (
    <section
      className={`live-notice ${isAlert ? 'live-notice-alert' : 'live-notice-email'}`}
      role={isAlert ? 'alert' : 'status'}
    >
      <div className="live-notice-icon">
        {isAlert ? <IconAlerts /> : <IconMail />}
      </div>
      <div className="live-notice-body">
        <h2>{isAlert ? 'Alerta de posible fraude' : 'Correo nuevo'}</h2>
        <p className="live-notice-subject">
          {notice.item.subject || '(Sin asunto)'}
        </p>
        <p className="live-notice-meta">
          {sender}
          {isAlert && ` · Riesgo ${notice.item.risk_score}/100`}
        </p>
        <Link
          to={
            isAlert ? `/alerts/${notice.item.alert_id}` : `/emails/${notice.id}`
          }
          onClick={() => onDismiss(notice.kind, notice.id)}
        >
          {isAlert ? 'Revisar alerta' : 'Ver correo'}
        </Link>
      </div>
      <button
        className="live-notice-close"
        type="button"
        aria-label={
          isAlert ? 'Cerrar alerta emergente' : 'Cerrar aviso de correo'
        }
        onClick={() => onDismiss(notice.kind, notice.id)}
      >
        <svg
          aria-hidden="true"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          <path d="M18 6 6 18M6 6l12 12" />
        </svg>
      </button>
    </section>
  );
}
