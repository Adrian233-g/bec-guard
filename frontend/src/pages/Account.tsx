import { useState } from 'react';
import type { FormEvent } from 'react';
import { api, ApiError, message } from '../api';
import { PageHeader } from '../components';

export function Account() {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  async function submit(e: FormEvent<HTMLFormElement>) {
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
  return (
    <>
      <PageHeader
        title="Mi cuenta"
        description="Actualiza tu contraseña de BEC Guard."
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
      <section className="panel">
        <form onSubmit={(e) => void submit(e)}>
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
