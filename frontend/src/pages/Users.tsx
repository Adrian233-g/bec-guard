import { useState } from 'react';
import type { FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, ApiError, message } from '../api';
import { useAuth } from '../auth';
import {
  Dialog,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Pagination,
  label,
} from '../components';
import { IconPlus } from '../icons';
import type { Role, User } from '../types';
import { useResource } from '../useResource';

type ManagedUser = User & { is_active: boolean; created_at: string };
const roles: Role[] = ['EMPLOYEE', 'ANALYST', 'ADMIN'];

export function Users() {
  const { user } = useAuth();
  return user?.role === 'ADMIN' ? (
    <UserManagement />
  ) : (
    <ErrorState error="No tienes permisos para gestionar usuarios." />
  );
}

function UserManagement() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get('offset')) || 0);
  const resource = useResource<ManagedUser[]>(
    `/users?limit=25&offset=${offset}`,
  );
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    if (data.get('password') !== data.get('confirm')) {
      setError('Las contraseñas no coinciden.');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await api('/users', {
        method: 'POST',
        body: JSON.stringify({
          name: data.get('name'),
          email: data.get('email'),
          role: data.get('role'),
          password: data.get('password'),
        }),
      });
      form.reset();
      setCreating(false);
      setNotice(
        'Usuario creado. Comparte la contraseña inicial por un medio privado.',
      );
      resource.reload();
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? 'Ese correo ya está registrado.'
          : message(e),
      );
    } finally {
      setBusy(false);
    }
  }
  async function update(
    row: ManagedUser,
    changes: { role?: Role; is_active?: boolean },
  ) {
    setBusy(true);
    setNotice('');
    setError('');
    try {
      await api(`/users/${row.id}`, {
        method: 'PATCH',
        body: JSON.stringify(changes),
      });
      setNotice('Usuario actualizado.');
      resource.reload();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        title="Usuarios"
        description="Administra las cuentas y sus permisos."
      >
        <button
          onClick={() => {
            setCreating(!creating);
            setError('');
          }}
        >
          {creating ? (
            'Cancelar'
          ) : (
            <>
              <IconPlus aria-hidden="true" />
              <span>Añadir usuario</span>
            </>
          )}
        </button>
      </PageHeader>
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      {error && !creating && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {creating && (
        <Dialog
          title="Añadir usuario"
          busy={busy}
          onClose={() => {
            setCreating(false);
            setError('');
          }}
        >
          <form onSubmit={(e) => void create(e)}>
            <label htmlFor="user-name">Nombre</label>
            <input
              id="user-name"
              name="name"
              required
              maxLength={200}
              placeholder="Ej. Ana Morales"
              autoFocus
            />
            <div className="form-grid-2">
              <div>
                <label htmlFor="user-email">Correo</label>
                <input
                  id="user-email"
                  name="email"
                  type="email"
                  required
                  maxLength={320}
                  placeholder="ana@empresa.com"
                />
              </div>
              <div>
                <label htmlFor="user-role">Rol</label>
                <select id="user-role" name="role" defaultValue="EMPLOYEE">
                  {roles.map((r) => (
                    <option key={r} value={r}>
                      {label(r)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="form-grid-2">
              <div>
                <label htmlFor="user-password">Contraseña inicial</label>
                <input
                  id="user-password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={12}
                  maxLength={128}
                />
              </div>
              <div>
                <label htmlFor="user-confirm">Confirmar contraseña</label>
                <input
                  id="user-confirm"
                  name="confirm"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={12}
                  maxLength={128}
                />
              </div>
            </div>
            <p className="muted" style={{ margin: '8px 0 16px', fontSize: '0.8rem' }}>
              Mínimo 12 caracteres. El usuario puede cambiarla desde su cuenta.
            </p>
            {error && (
              <p role="alert" className="error" style={{ marginBottom: '14px' }}>
                {error}
              </p>
            )}
            <div className="actions">
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => {
                  setCreating(false);
                  setError('');
                }}
              >
                Cancelar
              </button>
              <button disabled={busy}>Crear usuario</button>
            </div>
          </form>
        </Dialog>
      )}
      {resource.loading ? (
        <LoadingState />
      ) : resource.error ? (
        <ErrorState error={resource.error} retry={resource.reload} />
      ) : !resource.data?.length ? (
        <EmptyState>No hay usuarios.</EmptyState>
      ) : (
        <>
          <div className="table-toolbar">
            <span className="table-count-chip">
              <strong>{resource.data.length}</strong> usuarios en el sistema
            </span>
          </div>
          <div
            className="table-wrap"
            tabIndex={0}
            role="region"
            aria-label="Tabla de usuarios"
          >
          <table>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Correo</th>
                <th>Rol</th>
                <th>Estado</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {resource.data.map((row) => (
                <tr key={row.id}>
                  <td>
                    <div className="user-cell">
                      <span className="user-avatar-sm" aria-hidden="true">
                        {row.name ? row.name[0].toUpperCase() : 'U'}
                      </span>
                      <span className="user-name-strong">{row.name}</span>
                    </div>
                  </td>
                  <td>
                    <span className="mono">{row.email}</span>
                  </td>
                  <td>
                    <select
                      className="table-select"
                      aria-label={`Rol de ${row.name}`}
                      value={row.role}
                      disabled={busy || row.id === user?.id}
                      onChange={(e) =>
                        void update(row, { role: e.target.value as Role })
                      }
                    >
                      {roles.map((r) => (
                        <option key={r} value={r}>
                          {label(r)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <span
                      className={`badge ${row.is_active ? 'badge-low' : 'badge-closed'}`}
                    >
                      <span className="badge-dot" aria-hidden="true" />
                      {row.is_active ? 'Activo' : 'Inactivo'}
                    </span>
                  </td>
                  <td>
                    <button
                      className="secondary table-btn-action"
                      aria-label={`${row.is_active ? 'Desactivar' : 'Activar'} ${row.name}`}
                      disabled={busy || row.id === user?.id}
                      onClick={() =>
                        void update(row, { is_active: !row.is_active })
                      }
                    >
                      {row.is_active ? 'Desactivar' : 'Activar'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </>
      )}
      <Pagination
        offset={offset}
        count={resource.data?.length || 0}
        onChange={(n) => setParams({ offset: String(n) })}
      />
    </>
  );
}
