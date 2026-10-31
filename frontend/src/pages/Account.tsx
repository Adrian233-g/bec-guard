import { useState } from 'react';
import type { FormEvent } from 'react';
import { api, ApiError, message } from '../api';
import { Badge, LoadingState, PageHeader } from '../components';
import type { Mailbox } from '../types';
import { useResource } from '../useResource';

export function Account() {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const [mailboxBusy, setMailboxBusy] = useState(false);
  const [mailboxNotice, setMailboxNotice] = useState('');
  const [mailboxError, setMailboxError] = useState('');

  const mailboxResource = useResource<Mailbox[]>('/mailboxes');
  const mailbox = mailboxResource.data?.[0];

  async function submitPassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    if (data.get('new') !== data.get('confirm')) {
      setError('Las contraseñas nuevas no coinciden.');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await api('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({
          current_password: data.get('current'),
          new_password: data.get('new'),
        }),
      });
      form.reset();
      setNotice('Contraseña actualizada.');
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 400
          ? 'Comprueba tu contraseña actual y elige una nueva diferente de al menos 12 caracteres.'
          : message(e),
      );
    } finally {
      setBusy(false);
    }
  }

  async function submitMailbox(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const email = String(data.get('email_address') || '').trim();
    if (!email) return;

    setMailboxBusy(true);
    setMailboxError('');
    setMailboxNotice('');
    try {
      await api<Mailbox>('/mailboxes', {
        method: 'POST',
        body: JSON.stringify({ email_address: email, provider: 'gmail' }),
      });
      form.reset();
      setMailboxNotice('Buzón registrado y conectado.');
      mailboxResource.reload();
    } catch (e) {
      setMailboxError(
        e instanceof ApiError && e.status === 409
          ? 'La dirección ya está registrada o ya posees un buzón activo.'
          : message(e),
      );
    } finally {
      setMailboxBusy(false);
    }
  }

  async function toggleMailboxStatus() {
    if (!mailbox) return;
    setMailboxBusy(true);
    setMailboxError('');
    setMailboxNotice('');
    const nextStatus = mailbox.status === 'ACTIVE' ? 'DISCONNECTED' : 'ACTIVE';
    try {
      await api<Mailbox>(`/mailboxes/${mailbox.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: nextStatus }),
      });
      setMailboxNotice(
        nextStatus === 'ACTIVE' ? 'Buzón activado.' : 'Buzón desconectado.',
      );
      mailboxResource.reload();
    } catch (e) {
      setMailboxError(message(e));
    } finally {
      setMailboxBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Mi cuenta"
        description="Gestiona tu buzón personal y tus credenciales de acceso."
      />
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      <section className="panel" aria-labelledby="mailbox-heading">
        <h2 id="mailbox-heading">Buzón personal</h2>
        <p className="muted">
          Conecta la dirección de correo corporativa o personal que será
          protegida por BEC Guard.
        </p>

        {mailboxNotice && (
          <p role="status" className="notice">
            {mailboxNotice}
          </p>
        )}
        {mailboxError && (
          <p role="alert" className="error">
            {mailboxError}
          </p>
        )}

        {mailboxResource.loading ? (
          <LoadingState />
        ) : mailbox ? (
          <div className="mailbox-card">
            <dl className="facts">
              <div>
                <dt>Dirección de correo</dt>
                <dd>
                  <strong>{mailbox.email_address}</strong>
                </dd>
              </div>
              <div>
                <dt>Proveedor</dt>
                <dd>{mailbox.provider.toUpperCase()}</dd>
              </div>
              <div>
                <dt>Estado de conexión</dt>
                <dd>
                  <Badge value={mailbox.status} />
                </dd>
              </div>
            </dl>
            <div style={{ marginTop: '1rem' }}>
              <button
                type="button"
                className="secondary"
                disabled={mailboxBusy}
                onClick={() => void toggleMailboxStatus()}
              >
                {mailbox.status === 'ACTIVE'
                  ? 'Desconectar buzón'
                  : 'Reactivar buzón'}
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={(e) => void submitMailbox(e)}>
            <label htmlFor="mailbox-email">
              Dirección de correo electrónico
            </label>
            <input
              id="mailbox-email"
              name="email_address"
              type="email"
              placeholder="tu.nombre@organizacion.com"
              required
              maxLength={320}
            />
            <button disabled={mailboxBusy}>Conectar buzón</button>
          </form>
        )}
      </section>

      <section
        className="panel"
        aria-labelledby="password-heading"
        style={{ marginTop: '2rem' }}
      >
        <h2 id="password-heading">Seguridad de la sesión</h2>
        <form onSubmit={(e) => void submitPassword(e)}>
          <label htmlFor="current-password">Contraseña actual</label>
          <input
            id="current-password"
            name="current"
            type="password"
            autoComplete="current-password"
            required
            maxLength={128}
          />
          <label htmlFor="new-password">Contraseña nueva</label>
          <input
            id="new-password"
            name="new"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            maxLength={128}
          />
          <label htmlFor="confirm-password">Confirmar contraseña nueva</label>
          <input
            id="confirm-password"
            name="confirm"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            maxLength={128}
          />
          <button disabled={busy}>Cambiar contraseña</button>
        </form>
      </section>
    </>
  );
}
