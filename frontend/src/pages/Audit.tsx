import { useState } from 'react';
import type { FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Pagination,
  date,
  label,
} from '../components';
import type { AuditEvent } from '../types';
import { useResource } from '../useResource';

const actions: Record<string, string> = {
  ADMIN_BOOTSTRAPPED: 'Administrador inicial creado',
  USER_CREATED: 'Usuario creado',
  USER_UPDATED: 'Usuario actualizado',
  USER_PASSWORD_CHANGED: 'Contraseña de usuario cambiada',
  LOGIN_SUCCEEDED: 'Inicio de sesión exitoso',
  LOGIN_FAILED: 'Inicio de sesión fallido',
  LOGIN_INACTIVE: 'Inicio de sesión de usuario inactivo',
  RBAC_DENIED: 'Acceso denegado por permisos',
  EMAIL_INGESTED: 'Correo recibido',
  EMAIL_ANALYZED: 'Correo analizado',
  EMAIL_ANALYSIS_FAILED: 'Análisis de correo fallido',
  BEC_ALERT_CREATED: 'Alerta creada',
  BEC_ALERT_CLAIMED: 'Revisión de alerta asignada',
  BEC_ALERT_RELEASED: 'Revisión de alerta liberada',
  BEC_ALERT_CONFIRMED: 'Alerta confirmada como BEC',
  BEC_ALERT_FALSE_POSITIVE: 'Alerta marcada como falso positivo',
  EXECUTIVE_CREATED: 'Ejecutivo creado',
  EXECUTIVE_UPDATED: 'Ejecutivo actualizado',
  EXECUTIVE_DEACTIVATED: 'Ejecutivo desactivado',
  EXECUTIVE_REACTIVATED: 'Ejecutivo reactivado',
  VENDOR_CREATED: 'Proveedor creado',
  VENDOR_UPDATED: 'Proveedor actualizado',
  VENDOR_DEACTIVATED: 'Proveedor desactivado',
  VENDOR_REACTIVATED: 'Proveedor reactivado',
  MAILBOX_CREATED: 'Buzón creado',
  MAILBOX_UPDATED: 'Buzón actualizado',
  MAILBOX_DISCONNECTED: 'Buzón desconectado',
};

const resourceTypes: Record<string, string> = {
  user: 'Usuario',
  email: 'Correo',
  email_analysis: 'Análisis de correo',
  bec_alert: 'Alerta',
  executive: 'Ejecutivo',
  vendor: 'Proveedor',
  mailbox: 'Buzón',
};

function auditLabel(value: string, labels: Record<string, string>) {
  return labels[value] ?? value.replace(/_/g, ' ');
}

export function Audit() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  return user?.role === 'ADMIN' ? (
    <AuditList
      key={JSON.stringify([params.get('action'), params.get('resource_type')])}
    />
  ) : (
    <ErrorState error="No tienes permisos para consultar la auditoría." />
  );
}
function AuditList() {
  const [params, setParams] = useSearchParams();
  const [action, setAction] = useState(params.get('action') || '');
  const [resourceType, setResourceType] = useState(
    params.get('resource_type') || '',
  );
  const offset = Math.max(0, Number(params.get('offset')) || 0);
  const query = new URLSearchParams(params);
  query.set('limit', '25');
  query.set('offset', String(offset));
  const resource = useResource<AuditEvent[]>(`/audit?${query}`);
  function filter(e: FormEvent) {
    e.preventDefault();
    const next = new URLSearchParams();
    if (action.trim()) next.set('action', action.trim());
    if (resourceType.trim()) next.set('resource_type', resourceType.trim());
    setParams(next);
  }
  return (
    <>
      <PageHeader
        title="Auditoría"
        description="Trazabilidad de acciones humanas y automatizadas. Solo lectura."
      />
      <form className="filters audit-filters" onSubmit={filter}>
        <label>
          Acción
          <select value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="">Todas las acciones</option>
            {action && !actions[action] && (
              <option value={action}>{auditLabel(action, actions)}</option>
            )}
            {Object.entries(actions).map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        </label>
        <label>
          Recurso
          <select
            value={resourceType}
            onChange={(e) => setResourceType(e.target.value)}
          >
            <option value="">Todos los recursos</option>
            {resourceType && !resourceTypes[resourceType] && (
              <option value={resourceType}>
                {auditLabel(resourceType, resourceTypes)}
              </option>
            )}
            {Object.entries(resourceTypes).map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">Aplicar filtros</button>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setAction('');
            setResourceType('');
            setParams(new URLSearchParams());
          }}
          disabled={
            !action &&
            !resourceType &&
            !params.get('action') &&
            !params.get('resource_type')
          }
        >
          Limpiar filtros
        </button>
      </form>
      {resource.loading ? (
        <LoadingState />
      ) : resource.error ? (
        <ErrorState error={resource.error} retry={resource.reload} />
      ) : !resource.data?.length ? (
        <EmptyState>No hay eventos con estos filtros.</EmptyState>
      ) : (
        <>
          <div className="table-toolbar">
            <span className="table-count-chip">
              <strong>{resource.data.length}</strong> eventos en esta página
            </span>
          </div>
          <div
            className="table-wrap"
            tabIndex={0}
            role="region"
            aria-label="Tabla de auditoría"
          >
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Acción</th>
                  <th>Actor</th>
                  <th>Rol</th>
                  <th>Recurso</th>
                  <th>IP</th>
                </tr>
              </thead>
              <tbody>
                {resource.data.map((e) => (
                  <tr key={e.id}>
                    <td>{date(e.created_at)}</td>
                    <td>
                      <strong>{auditLabel(e.action, actions)}</strong>
                      {e.details && Object.keys(e.details).length > 0 && (
                        <details>
                          <summary>Detalles</summary>
                          <dl className="facts">
                            {Object.entries(e.details).map(([key, value]) => (
                              <div key={key}>
                                <dt>{key}</dt>
                                <dd>{value}</dd>
                              </div>
                            ))}
                          </dl>
                        </details>
                      )}
                    </td>
                    <td>
                      {e.actor_name || e.actor_user_id || 'Sin actor humano'}
                    </td>
                    <td>{label(e.actor_role)}</td>
                    <td>
                      {e.resource_type
                        ? auditLabel(e.resource_type, resourceTypes)
                        : '—'}
                      <small className="mono">{e.resource_id}</small>
                    </td>
                    <td>
                      <span className="mono">{e.ip_address || '—'}</span>
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
        onChange={(n) => {
          const next = new URLSearchParams(params);
          next.set('offset', String(n));
          setParams(next);
        }}
      />
    </>
  );
}
