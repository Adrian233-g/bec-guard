import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { api, ApiError, message } from '../api';
import { useAuth } from '../auth';
import {
  ALERT_THRESHOLD,
  AlertThresholdNote,
  AnalysisHeadline,
  AnalysisView,
  EmailContent,
  ErrorExplanation,
} from '../analysis';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Pagination,
  date,
} from '../components';
import type {
  AlertSummary,
  Analysis,
  EmailDetail as EmailData,
  EmailSummary,
} from '../types';
import { useResource } from '../useResource';
export function Emails() {
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get('offset')) || 0);
  const resource = useResource<EmailSummary[]>(
    `/emails?limit=25&offset=${offset}`,
  );
  return (
    <>
      <PageHeader
        title="Correos"
        description="Mensajes normalizados recibidos por BEC Guard."
      />
      {resource.loading ? (
        <LoadingState />
      ) : resource.error ? (
        <ErrorState error={resource.error} retry={resource.reload} />
      ) : !resource.data?.length ? (
        <EmptyState>Aún no hay correos recibidos.</EmptyState>
      ) : (
        <div
          className="table-wrap"
          tabIndex={0}
          role="region"
          aria-label="Tabla de correos"
        >
          <table>
            <thead>
              <tr>
                <th>Recibido</th>
                <th>Remitente</th>
                <th>Asunto</th>
                <th>Reply-To</th>
              </tr>
            </thead>
            <tbody>
              {resource.data.map((e) => (
                <tr key={e.id}>
                  <td>{date(e.received_at)}</td>
                  <td>
                    <div className="sender-name">{e.sender_name}</div>
                    <small className="mono">{e.sender_email}</small>
                  </td>
                  <td className="subject-cell">
                    <Link to={`/emails/${e.id}`}>
                      {e.subject || '(Sin asunto)'}
                    </Link>
                    <small className="mono message-id-tag">{e.message_id}</small>
                  </td>
                  <td>
                    <span className="mono">{e.reply_to || '—'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination
        offset={offset}
        count={resource.data?.length || 0}
        onChange={(offset) => setParams({ offset: String(offset) })}
      />
    </>
  );
}
export function EmailDetail() {
  const { emailId } = useParams();
  const resource = useResource<EmailData>(`/emails/${emailId}`);
  return (
    <>
      <Link className="back-link" to="/emails">
        Volver a correos
      </Link>
      <PageHeader
        title="Detalle del correo"
        description="Contenido original y resultado del análisis BEC."
      />
      {resource.loading ? (
        <LoadingState />
      ) : resource.error ? (
        <ErrorState error={resource.error} retry={resource.reload} />
      ) : (
        resource.data && (
          <>
            <ManualAnalysis key={resource.data.id} id={resource.data.id} />
            <EmailContent email={resource.data} />
          </>
        )
      )}
    </>
  );
}
function ManualAnalysis({ id }: { id: string }) {
  const { user } = useAuth();
  const [state, setState] = useState<{
    analysis: Analysis | null;
    loading: boolean;
    error: string;
  }>({ analysis: null, loading: true, error: '' });
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [notice, setNotice] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    api<Analysis>(`/emails/${id}/analysis`, { signal: controller.signal })
      .then((analysis) => {
        if (!controller.signal.aborted)
          setState({ analysis, loading: false, error: '' });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setState({
            analysis: null,
            loading: false,
            error:
              error instanceof ApiError && error.status === 404
                ? ''
                : message(error),
          });
      });
    return () => controller.abort();
  }, [id, attempt]);
  async function analyze() {
    setBusy(true);
    setNotice('');
    try {
      const analysis = await api<Analysis>(`/emails/${id}/analyze`, {
        method: 'POST',
      });
      setState({ analysis, loading: false, error: '' });
      setNotice('Análisis completado.');
    } catch (e) {
      if (
        e instanceof ApiError &&
        e.data &&
        typeof e.data === 'object' &&
        'status' in e.data &&
        e.data.status === 'ERROR'
      ) {
        setState({ analysis: e.data as Analysis, loading: false, error: '' });
      } else setNotice(message(e));
    } finally {
      setBusy(false);
    }
  }
  const analysis = state.analysis;
  return (
    <>
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      {state.loading ? (
        <LoadingState />
      ) : state.error ? (
        <ErrorState
          error={state.error}
          retry={() => setAttempt((n) => n + 1)}
        />
      ) : (
        <>
          {analysis?.status === 'COMPLETED' ? (
            <>
              <section className="alert-overview">
                <AnalysisHeadline analysis={analysis} />
                <AnalysisAlertLink analysis={analysis} />
              </section>
              <AnalysisView analysis={analysis} />
            </>
          ) : (
            <section className="panel">
              {analysis ? (
                <ErrorExplanation code={analysis.error_code} />
              ) : (
                <>
                  <h2>Sin análisis</h2>
                  <p>Este correo todavía no tiene una evaluación BEC.</p>
                </>
              )}
              {(user?.role === 'ADMIN' || user?.role === 'ANALYST') && (
                <button disabled={busy} onClick={() => void analyze()}>
                  {busy
                    ? 'Analizando…'
                    : analysis
                      ? 'Reintentar análisis'
                      : 'Analizar correo'}
                </button>
              )}
            </section>
          )}
        </>
      )}
    </>
  );
}
function AnalysisAlertLink({ analysis }: { analysis: Analysis }) {
  const belowThreshold = (analysis.risk_score || 0) < ALERT_THRESHOLD;
  const resource = useResource<AlertSummary[]>(
    belowThreshold ? null : `/alerts?analysis_id=${analysis.id}&limit=1`,
  );
  if (belowThreshold) return <AlertThresholdNote analysis={analysis} />;
  return resource.loading ? (
    <LoadingState />
  ) : resource.error ? (
    <ErrorState error={resource.error} retry={resource.reload} />
  ) : resource.data?.[0] ? (
    <Link
      className="associated-alert-link"
      to={`/alerts/${resource.data[0].id}`}
    >
      Abrir alerta asociada
    </Link>
  ) : (
    <p className="muted">No hay alerta asociada a este análisis.</p>
  );
}
