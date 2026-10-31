import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth';
import {
  Badge,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Pagination,
  date,
  label,
} from '../components';
import { becTypes } from '../types';
import type { AlertSummary } from '../types';
import { useResource } from '../useResource';
export function Alerts() {
  const [params, setParams] = useSearchParams();
  const { user } = useAuth();
  const offset = Math.max(0, Number(params.get('offset')) || 0);
  const query = new URLSearchParams(params);
  query.set('limit', '25');
  query.set('offset', String(offset));
  if (user?.role === 'EMPLOYEE') query.delete('assigned_to');
  const resource = useResource<AlertSummary[]>(`/alerts?${query}`);
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params);
    next.delete('offset');
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  }
  return (
    <>
      <PageHeader
        title="Alertas"
        description={
          user?.role === 'EMPLOYEE'
            ? 'Consulta el estado de las alertas de tus correos.'
            : 'Prioriza la evidencia y registra una decisión por caso.'
        }
      />
      <div className="filters">
        <label>
          Estado
          <select
            value={params.get('status') || ''}
            onChange={(e) => filter('status', e.target.value)}
          >
            <option value="">Todos</option>
            {['OPEN', 'UNDER_REVIEW', 'CLOSED'].map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Riesgo
          <select
            value={params.get('risk_level') || ''}
            onChange={(e) => filter('risk_level', e.target.value)}
          >
            <option value="">Todos</option>
            {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tipo BEC
          <select
            value={params.get('bec_type') || ''}
            onChange={(e) => filter('bec_type', e.target.value)}
          >
            <option value="">Todos</option>
            {becTypes.map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
        </label>
        {user?.role !== 'EMPLOYEE' && (
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={params.get('assigned_to') === user?.id}
              onChange={(e) =>
                filter('assigned_to', e.target.checked ? user!.id : '')
              }
            />
            Asignadas a mí
          </label>
        )}
      </div>
      {resource.loading ? (
        <LoadingState />
      ) : resource.error ? (
        <ErrorState error={resource.error} retry={resource.reload} />
      ) : !resource.data?.length ? (
        <EmptyState>No hay alertas con estos filtros.</EmptyState>
      ) : (
        <div
          className="table-wrap"
          tabIndex={0}
          role="region"
          aria-label="Tabla de alertas"
        >
          <table>
            <thead>
              <tr>
                <th>Riesgo</th>
                <th>Correo / remitente</th>
                {user?.role !== 'EMPLOYEE' && <th>Empleado / buzón</th>}
                <th>Tipo BEC</th>
                <th>Estado</th>
                <th>Responsable</th>
                <th>Recibido</th>
                <th>Alerta creada</th>
              </tr>
            </thead>
            <tbody>
              {resource.data.map((a) => (
                <tr key={a.id}>
                  <td>
                    <Badge value={a.risk_level} />
                    <small>{a.risk_score}/100</small>
                  </td>
                  <td className="subject-cell">
                    <Link to={`/alerts/${a.id}`}>
                      {a.subject || '(Sin asunto)'}
                    </Link>
                    <small>{a.sender_name}</small>
                    <small>{a.sender_email}</small>
                  </td>
                  {user?.role !== 'EMPLOYEE' && (
                    <td>
                      {a.owner_name || 'Sin propietario'}
                      {a.mailbox_email && <small>{a.mailbox_email}</small>}
                    </td>
                  )}
                  <td>{label(a.bec_type)}</td>
                  <td>
                    <Badge value={a.status} />
                  </td>
                  <td>
                    {a.assigned_to_name || a.assigned_to || 'Sin asignar'}
                  </td>
                  <td>{date(a.received_at)}</td>
                  <td>{date(a.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
