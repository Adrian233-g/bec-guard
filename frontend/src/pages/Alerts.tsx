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
import { IconFilter } from '../icons';
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
        <div className="filters-top">
          <div className="filter-segmented" role="tablist" aria-label="Filtro rápido por estado">
            {[
              { id: '', title: 'Todas' },
              { id: 'OPEN', title: 'Abiertas' },
              { id: 'UNDER_REVIEW', title: 'En revisión' },
              { id: 'CLOSED', title: 'Cerradas' },
            ].map((tab) => {
              const active = (params.get('status') || '') === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={`segmented-tab ${active ? 'active' : ''}`}
                  onClick={() => filter('status', tab.id)}
                >
                  {tab.title}
                </button>
              );
            })}
          </div>
          <div className="filters-header">
            <IconFilter aria-hidden="true" />
            <span>Filtros avanzados</span>
          </div>
        </div>
        <div className="filters-controls">
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
      </div>
      {resource.loading ? (
        <LoadingState />
      ) : resource.error ? (
        <ErrorState error={resource.error} retry={resource.reload} />
      ) : !resource.data?.length ? (
        <EmptyState>No hay alertas con estos filtros.</EmptyState>
      ) : (
        <>
          <div className="table-toolbar">
            <span className="table-count-chip">
              <strong>{resource.data.length}</strong> {resource.data.length === 1 ? 'alerta' : 'alertas'} en cola
            </span>
          </div>
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
                    <div className="risk-cell">
                      <Badge value={a.risk_level} />
                      <span className="risk-score-pill">
                        <strong>{a.risk_score}</strong>
                        <small>/100</small>
                      </span>
                    </div>
                  </td>
                  <td className="subject-cell">
                    <Link to={`/alerts/${a.id}`}>
                      {a.subject || '(Sin asunto)'}
                    </Link>
                    <small className="sender-meta">
                      <span>{a.sender_name}</span> &lt;{a.sender_email}&gt;
                    </small>
                  </td>
                  {user?.role !== 'EMPLOYEE' && (
                    <td>
                      <div>{a.owner_name || 'Sin propietario'}</div>
                      {a.mailbox_email && (
                        <small className="mono">{a.mailbox_email}</small>
                      )}
                    </td>
                  )}
                  <td>
                    <span className="bec-type-tag">{label(a.bec_type)}</span>
                  </td>
                  <td>
                    <Badge value={a.status} />
                  </td>
                  <td>
                    {a.assigned_to_name || a.assigned_to ? (
                      <span className="assigned-tag">
                        {a.assigned_to_name || a.assigned_to}
                      </span>
                    ) : (
                      <span className="unassigned-tag">Sin asignar</span>
                    )}
                  </td>
                  <td>{date(a.received_at)}</td>
                  <td>{date(a.created_at)}</td>
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
