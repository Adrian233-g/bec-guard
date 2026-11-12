import { useState } from 'react';
import type { FormEvent } from 'react';
import { api, ApiError, message } from '../api';
import { Badge, ErrorState, LoadingState, PageHeader } from '../components';
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
      setMailboxNotice(
        'Dirección registrada. La conexión de Gmail aún está pendiente.',
      );
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

  async function connectMailbox(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!mailbox) return;
    const form = e.currentTarget;
    const appPassword = String(new FormData(form).get('app_password') || '');
    if (!appPassword) return;
    setMailboxBusy(true);
    setMailboxError('');
    setMailboxNotice('');
    try {
      await api(`/mailboxes/${mailbox.id}/connect`, {
        method: 'POST',
        body: JSON.stringify({ app_password: appPassword }),
      });
      setMailboxNotice('Gmail conectado. Se analizarán los correos nuevos.');
      mailboxResource.reload();
    } catch (e) {
      setMailboxError(
        e instanceof ApiError && e.status === 400
          ? 'Gmail rechazó la contraseña de aplicación. Comprueba los datos e inténtalo de nuevo.'
          : 'No se pudo completar la conexión. Puede requerir una revisión del administrador.',
      );
      mailboxResource.reload();
    } finally {
      form.reset();
      setMailboxBusy(false);
    }
  }

  async function disconnectMailbox() {
    if (!mailbox) return;
    setMailboxBusy(true);
    setMailboxError('');
    setMailboxNotice('');
    try {
      await api(`/mailboxes/${mailbox.id}/disconnect`, { method: 'POST' });
      setMailboxNotice(
        'Gmail desconectado. Ya no se analizarán correos nuevos.',
      );
      mailboxResource.reload();
    } catch {
      setMailboxError(
        'No se pudo completar la desconexión. Puede requerir una revisión del administrador.',
      );
      mailboxResource.reload();
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
          Conecta tu Gmail con una contraseña de aplicación de Google. Se
          analizarán los correos nuevos mientras el sistema esté encendido.
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
        ) : mailboxResource.error ? (
          <ErrorState
            error={mailboxResource.error}
            retry={mailboxResource.reload}
          />
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
                <dt>Estado del registro</dt>
                <dd>
                  <Badge value={mailbox.status} />
                </dd>
              </div>
            </dl>
            {mailbox.status === 'ACTIVE' ? (
              <button
                disabled={mailboxBusy}
                onClick={() => void disconnectMailbox()}
              >
                Desconectar Gmail
              </button>
            ) : mailbox.needs_reconciliation ? (
              <p role="status" className="threshold-note">
                La conexión requiere revisión del administrador antes de volver
                a intentarlo.
              </p>
            ) : (
              <form onSubmit={(e) => void connectMailbox(e)}>
                <label htmlFor="app-password">
                  Contraseña de aplicación de Google
                </label>
                <input
                  id="app-password"
                  name="app_password"
                  type="password"
                  autoComplete="off"
                  required
                  maxLength={128}
                />
                <p className="muted">
                  Usa la contraseña de aplicación, no la contraseña habitual de
                  Gmail.
                </p>
                <button disabled={mailboxBusy}>
                  {mailboxBusy ? 'Conectando…' : 'Conectar Gmail'}
                </button>
              </form>
            )}
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
            <button disabled={mailboxBusy}>Registrar dirección</button>
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
          <div className="form-group">
            <label htmlFor="current-password">Contraseña actual</label>
            <input
              id="current-password"
              name="current"
              type="password"
              autoComplete="current-password"
              required
              maxLength={128}
            />
          </div>
          <div className="form-grid-2">
            <div>
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
            </div>
            <div>
              <label htmlFor="confirm-password">
                Confirmar contraseña nueva
              </label>
              <input
                id="confirm-password"
                name="confirm"
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={128}
              />
            </div>
          </div>
          <div style={{ marginTop: '18px' }}>
            <button disabled={busy}>Cambiar contraseña</button>
          </div>
        </form>
      </section>
    </>
  );
}
