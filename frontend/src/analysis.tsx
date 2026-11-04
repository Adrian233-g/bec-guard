import { Link } from 'react-router-dom';
import { Badge, EmptyState, date, label } from './components';
import { IconExternalLink } from './icons';
import type { Analysis, EmailDetail } from './types';

export const ALERT_THRESHOLD = 70;

const errorExplanations: Record<string, { title: string; detail: string }> = {
  LLM_NOT_CONFIGURED: {
    title: 'Proveedor de IA sin configurar',
    detail:
      'Un administrador debe configurar el proveedor y la clave del modelo. No se asignó riesgo ni se creó una alerta.',
  },
  LLM_TIMEOUT: {
    title: 'El proveedor no respondió a tiempo',
    detail:
      'El análisis quedó incompleto y no se creó una alerta. Puedes reintentarlo manualmente.',
  },
  LLM_RATE_LIMITED: {
    title: 'Límite de uso del proveedor',
    detail:
      'El proveedor rechazó la solicitud por cuota o límite de peticiones. No se creó una alerta. Espera un momento y reintenta manualmente; no hay reintentos automáticos.',
  },
  LLM_PROVIDER_ERROR: {
    title: 'Fallo del proveedor de IA',
    detail:
      'El proveedor devolvió un error inesperado. El análisis quedó incompleto y no se creó una alerta. Reintenta manualmente más tarde.',
  },
  LLM_INVALID_OUTPUT: {
    title: 'Respuesta del proveedor no válida',
    detail:
      'La respuesta no cumplió el formato esperado y no se usó para asignar riesgo ni crear alertas. Puedes reintentarlo manualmente.',
  },
};

export function analysisError(code: string | null) {
  return (
    errorExplanations[code ?? ''] ?? {
      title: 'Análisis incompleto',
      detail:
        'El análisis no terminó. No hay un nivel de riesgo disponible ni se creó una alerta.',
    }
  );
}

export function ErrorExplanation({ code }: { code: string | null }) {
  const { title, detail } = analysisError(code);
  return (
    <>
      <h2>{title}</h2>
      <p>{detail}</p>
      {code && <p className="error-code">{code}</p>}
    </>
  );
}

export function AlertThresholdNote({ analysis }: { analysis: Analysis }) {
  const score = analysis.risk_score ?? 0;
  if (score >= ALERT_THRESHOLD) return null;
  return (
    <p className="threshold-note">
      Riesgo {label(analysis.risk_level).toLowerCase()} ({score}/100): no
      alcanza el umbral de {ALERT_THRESHOLD} y no genera alerta automática.
      {analysis.risk_level === 'MEDIUM' &&
        ' Revisa las señales del correo antes de descartarlo.'}
    </p>
  );
}

export function AnalysisView({ analysis }: { analysis: Analysis }) {
  if (analysis.status === 'ERROR')
    return (
      <section className="panel analysis-error">
        <ErrorExplanation code={analysis.error_code} />
      </section>
    );
  return (
    <>
      {analysis.status === 'FALLBACK' && (
        <section className="panel analysis-error" role="status">
          <h2>Análisis limitado a reglas</h2>
          <p>
            La IA no estuvo disponible. Un puntaje bajo no descarta fraude;
            revisa las señales antes de actuar.
          </p>
          {analysis.error_code && (
            <p className="error-code">{analysis.error_code}</p>
          )}
        </section>
      )}
      <section className="panel">
        <div className="section-heading">
          <h2>Evaluación del sistema</h2>
          <small>{date(analysis.analyzed_at)}</small>
        </div>
        <p className="summary">{analysis.summary}</p>
        <div className="recommendation">
          <h3>Acción recomendada</h3>
          <p>{analysis.recommended_action}</p>
        </div>
      </section>
      <section className="panel">
        <h2>Evidencia explicable</h2>
        {!analysis.signals.length && (
          <EmptyState>No se registraron señales adicionales.</EmptyState>
        )}
        {(['CONTEXT', 'RULE', 'SEMANTIC'] as const).map((source) => {
          const signals = analysis.signals.filter((s) => s.source === source);
          return (
            signals.length > 0 && (
              <div
                className={`signal-group signal-group-${source.toLowerCase()}`}
                key={source}
              >
                <div className="signal-group-header">
                  <span
                    className={`signal-source-badge signal-source-${source.toLowerCase()}`}
                  >
                    {source}
                  </span>
                  <h3>
                    {source === 'CONTEXT'
                      ? 'Contexto organizacional'
                      : source === 'RULE'
                        ? 'Reglas técnicas y de contenido'
                        : 'Análisis semántico'}
                  </h3>
                </div>
                <ul className="signals">
                  {signals.map((s, i) => (
                    <li key={`${s.code}-${i}`}>
                      <div>
                        <strong>{s.code}</strong>
                        {source !== 'SEMANTIC' && !!s.contribution && (
                          <span className="signal-contribution">
                            +{s.contribution} puntos deterministas
                          </span>
                        )}
                      </div>
                      <p>{s.description}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )
          );
        })}
        <details>
          <summary>Detalle del cálculo</summary>
          <dl className="facts">
            <div>
              <dt>Determinista</dt>
              <dd>{analysis.deterministic_score}/100</dd>
            </div>
            <div>
              <dt>Semántico</dt>
              <dd>
                {analysis.semantic_score == null
                  ? 'No disponible'
                  : `${analysis.semantic_score}/100`}
              </dd>
            </div>
            <div>
              <dt>Política</dt>
              <dd>{analysis.policy_version}</dd>
            </div>
          </dl>
          <p className="muted">
            El score es una evaluación del sistema, no una probabilidad de
            fraude.
          </p>
        </details>
      </section>
    </>
  );
}
export function EmailContent({ email }: { email: EmailDetail }) {
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>Correo original</h2>
        <Link to={`/emails/${email.id}`} className="open-email-link">
          <span>Abrir correo</span>
          <IconExternalLink aria-hidden="true" />
        </Link>
      </div>
      <h3 className="email-subject">{email.subject || '(Sin asunto)'}</h3>
      <dl className="facts email-headers">
        <div>
          <dt>From</dt>
          <dd>
            <span className="sender-name">{email.sender_name}</span>{' '}
            <span className="mono">&lt;{email.sender_email}&gt;</span>
          </dd>
        </div>
        <div>
          <dt>Reply-To</dt>
          <dd className="mono">{email.reply_to || '—'}</dd>
        </div>
        <div>
          <dt>Return-Path</dt>
          <dd className="mono">{email.return_path || '—'}</dd>
        </div>
        <div>
          <dt>To</dt>
          <dd className="mono">{email.to_recipients.join(', ') || '—'}</dd>
        </div>
        <div>
          <dt>Cc</dt>
          <dd className="mono">{email.cc_recipients.join(', ') || '—'}</dd>
        </div>
        <div>
          <dt>Fecha</dt>
          <dd>{date(email.received_at)}</dd>
        </div>
        <div>
          <dt>Authentication-Results</dt>
          <dd className="mono">
            {email.authentication_results || 'Sin resultados'}
          </dd>
        </div>
      </dl>
      <details open>
        <summary>Contenido en texto plano</summary>
        <pre className="email-body">{email.body_text || '(Sin contenido)'}</pre>
      </details>
    </section>
  );
}
export function AnalysisHeadline({ analysis }: { analysis: Analysis }) {
  return (
    <div className="risk-headline">
      <div className="risk-score-wrapper">
        <Badge value={analysis.risk_level} />
        <strong className="score">
          {analysis.risk_score}
          <small>/100</small>
        </strong>
      </div>
      <div className="threat-summary-meta">
        <p className="threat-bec-title">{label(analysis.bec_type)}</p>
        <div className="score-sub-metrics">
          <span
            className="score-sub-pill"
            title="Puntaje determinista de reglas"
          >
            Reglas: <strong>{analysis.deterministic_score ?? 0}</strong>
          </span>
          <span
            className="score-sub-pill"
            title="Puntaje de análisis semántico"
          >
            Semántica:{' '}
            <strong>{analysis.semantic_score ?? 'No disponible'}</strong>
          </span>
        </div>
      </div>
    </div>
  );
}
