import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, message } from './api';
import { date, label } from './components';
import { IconBell } from './icons';
import type { Notification } from './types';

const REFRESH_MS = 60_000;

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(0);
  const [items, setItems] = useState<Notification[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);

  const loadCount = useCallback(async () => {
    try {
      const result = await api<{ count: number }>(
        '/notifications/unread-count',
      );
      setCount(result.count);
    } catch {
      // The bell must never break the shell; keep the last known count.
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void loadCount(), 0);
    const timer = window.setInterval(() => void loadCount(), REFRESH_MS);
    const onFocus = () => void loadCount();
    window.addEventListener('focus', onFocus);
    window.addEventListener('bec-live-update', onFocus);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
      window.removeEventListener('focus', onFocus);
      window.removeEventListener('bec-live-update', onFocus);
    };
  }, [loadCount]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const update = () => {
      void loadItems();
    };
    window.addEventListener('bec-live-update', update);
    return () => window.removeEventListener('bec-live-update', update);
  }, [open]);

  async function loadItems() {
    setError('');
    try {
      setItems(await api<Notification[]>('/notifications?limit=10'));
    } catch (error) {
      setItems(null);
      setError(message(error));
    }
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next) void loadItems();
  }

  async function markRead(notification: Notification) {
    setOpen(false);
    if (notification.read_at) return;
    const now = new Date().toISOString();
    setItems(
      (rows) =>
        rows?.map((row) =>
          row.id === notification.id ? { ...row, read_at: now } : row,
        ) ?? null,
    );
    setCount((value) => Math.max(0, value - 1));
    try {
      await api(`/notifications/${notification.id}/read`, { method: 'POST' });
    } catch {
      void loadCount();
      void loadItems();
    }
  }

  async function markAllRead() {
    setBusy(true);
    setError('');
    const now = new Date().toISOString();
    try {
      await api('/notifications/read-all', { method: 'POST' });
      setItems(
        (rows) =>
          rows?.map((row) => ({ ...row, read_at: row.read_at ?? now })) ?? null,
      );
      setCount(0);
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="notifications" ref={wrapper}>
      <button
        className="secondary notification-button"
        aria-expanded={open}
        aria-controls="notification-panel"
        aria-label={count ? `Avisos, ${count} sin leer` : 'Avisos'}
        onClick={toggle}
      >
        <IconBell aria-hidden="true" />
        <span>Avisos</span>
        {count > 0 && (
          <span className="notification-count" aria-hidden="true">
            {count > 99 ? '99+' : count}
          </span>
        )}
      </button>
      {open && (
        <section
          id="notification-panel"
          className="notification-panel"
          aria-label="Avisos"
        >
          <header>
            <h2>Avisos</h2>
            {count > 0 && (
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void markAllRead()}
              >
                Marcar todos leídos
              </button>
            )}
          </header>
          {error ? (
            <p role="alert" className="error">
              {error}
            </p>
          ) : items === null ? (
            <p className="state">Cargando avisos…</p>
          ) : items.length === 0 ? (
            <p className="state empty">No tienes avisos.</p>
          ) : (
            <ul>
              {items.map((notification) => (
                <li
                  key={notification.id}
                  className={
                    notification.read_at ? 'notification read' : 'notification'
                  }
                >
                  <Link
                    to={`/alerts/${notification.alert_id}`}
                    onClick={() => void markRead(notification)}
                  >
                    <strong>{notification.subject || '(Sin asunto)'}</strong>
                    <small>
                      {notification.sender_name || notification.sender_email} ·
                      Riesgo {label(notification.risk_level)} (
                      {notification.risk_score}/100)
                    </small>
                    <small>
                      {notification.read_at ? '' : 'Sin leer · '}
                      {date(notification.created_at)}
                    </small>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
