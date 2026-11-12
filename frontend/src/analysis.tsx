import { Link } from 'react-router-dom';
import { Badge, EmptyState, date, label } from './components';
import { IconExternalLink } from './icons';
import type { Analysis, EmailDetail, Signal } from './types';

export const ALERT_THRESHOLD = 50;

const signalTitles: Record<string, string> = {
  EXECUTIVE_IDENTITY_MISMATCH: 'Dirección de ejecutivo no reconocida',
  EXECUTIVE_DOMAIN_LOOKALIKE: 'Dominio similar al de un ejecutivo',
  VENDOR_IDENTITY_MISMATCH: 'Identidad de proveedor no coincidente',
  VENDOR_DOMAIN_LOOKALIKE: 'Dominio similar al de un proveedor',
  REPLY_TO_MISMATCH: 'Dirección de respuesta diferente',
  RETURN_PATH_MISMATCH: 'Dominio de envío diferente',
  SPF_FAIL: 'Authentication-Results declara SPF fail',
  DKIM_FAIL: 'Authentication-Results declara DKIM fail',
  DMARC_FAIL: 'Authentication-Results declara DMARC fail',
  PAYMENT_REQUEST: 'Solicitud de pago o transferencia',
  BANK_ACCOUNT_CHANGE: 'Cambio de cuenta o beneficiario',
  SENSITIVE_DATA_REQUEST: 'Solicitud de información sensible',
  URGENCY: 'Presión para actuar con urgencia',
  AUTHORITY_PRESSURE: 'Solicitud en nombre de una autoridad',
  SECRECY_REQUEST: 'Solicitud de evitar la verificación',
  REQUEST_OUTSIDE_ROLE: 'Solicitud fuera del rol registrado',
  IMPERSONATION_REQUEST: 'Suplantación con solicitud de acción',
  IMPERSONATION_SENSITIVE_REQUEST: 'Suplantación con solicitud sensible',
};

const sourceTitles: Record<Signal['source'], string> = {
  RULE: 'Regla determinista',
  CONTEXT: 'Contexto organizacional',
  SEMANTIC: 'Análisis semántico',
};

const floorTitles: Record<string, string> = {
  DETERMINISTIC_SCORE_GE_70: 'score determinista igual o superior a 70',
  IMPERSONATION_REQUEST: 'solicitud asociada a una suplantación',
  IMPERSONATION_SENSITIVE_REQUEST:
    'suplantación combinada con una solicitud sensible',
};

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
  const threshold =
    analysis.score_breakdown?.alert_threshold ?? ALERT_THRESHOLD;
  if (score >= threshold) return null;
  return (
    <p className="threshold-note">
      Riesgo {label(analysis.risk_level).toLowerCase()} ({score}/100): no
      alcanza el umbral de {threshold} y no genera alerta automática.
      {analysis.risk_level === 'MEDIUM' &&
        ' Revisa las señales del correo antes de descartarlo.'}
    </p>
  );
}

function SignalTable({ signals }: { signals: Signal[] }) {
  return (
    <div className="evidence-table-wrapper">
      <table className="evidence-table">
        <caption className="sr-only">Señales observables del análisis</caption>
        <thead>
          <tr>
            <th scope="col">Código</th>
            <th scope="col">Origen</th>
            <th scope="col">Evidencia observable</th>
            <th scope="col">Contribución</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((signal, index) => {
            const semantic = signal.source === 'SEMANTIC';
            return (
              <tr key={`${signal.code}-${index}`}>
                <td>
                  <code>{signal.code}</code>
                </td>
                <td>{sourceTitles[signal.source]}</td>
                <td>
                  <strong>
                    {signalTitles[signal.code] ??
                      (semantic
                        ? 'Señal identificada por el análisis semántico'
                        : 'Señal detectada')}
                  </strong>
                  <p>{signal.description}</p>
                </td>
                <td>
                  {semantic ? (
                    <span className="no-contribution">No suma al score</span>
                  ) : signal.contribution == null ? (
                    <span className="no-contribution">No registrada</span>
                  ) : (
                    <span className="signal-contribution">
                      +{signal.contribution} puntos por reglas
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ScorePath({ analysis }: { analysis: Analysis }) {
  const breakdown = analysis.score_breakdown;
  if (!breakdown) {
    return (
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
          El desglose detallado no está disponible para este análisis histórico.
          El puntaje no es una probabilidad de fraude.
        </p>
      </details>
    );
  }
  const floorReason = breakdown.floor_reasons
    .map((reason) => floorTitles[reason] ?? reason)
    .join('; ');
  return (
    <details open>
      <summary>Recorrido del puntaje</summary>
      <p className="score-path-note">
        Las contribuciones deterministas pueden sumar más de 100; el score
        determinista se limita a 100 antes de la combinación.
      </p>
      <div className="score-table-wrapper">
        <table className="score-table">
          <caption className="sr-only">Reconstrucción del puntaje</caption>
          <tbody>
            <tr>
              <th scope="row">Suma bruta determinista</th>
              <td>{breakdown.raw_deterministic_total}</td>
              <td>Contribuciones de reglas y contexto</td>
            </tr>
            <tr>
              <th scope="row">Score determinista aplicado</th>
              <td>{breakdown.deterministic_score}/100</td>
              <td>Limitado por el máximo de 100</td>
            </tr>
            <tr>
              <th scope="row">Score semántico</th>
              <td>
                {breakdown.semantic_score == null
                  ? 'No disponible'
                  : `${breakdown.semantic_score}/100`}
              </td>
              <td>
                {breakdown.mode === 'FALLBACK'
                  ? 'Proveedor no disponible'
                  : 'Evaluación estructurada del proveedor'}
              </td>
            </tr>
            <tr>
              <th scope="row">Combinación híbrida</th>
              <td>
                {breakdown.weighted_score == null
                  ? 'No aplica'
                  : `${breakdown.weighted_score}/100`}
              </td>
              <td>Promedio con redondeo entero hacia arriba</td>
            </tr>
            <tr>
              <th scope="row">Piso de política</th>
              <td>{breakdown.floor_score}/100</td>
              <td>{floorReason || 'No aplicado'}</td>
            </tr>
            <tr className="score-table-final">
              <th scope="row">Resultado final</th>
              <td>{breakdown.final_score}/100</td>
              <td>
                Umbral de alerta: {breakdown.alert_threshold} ·{' '}
                {breakdown.alert_triggered
                  ? 'alerta creada'
                  : 'sin alerta automática'}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="muted">
        La política aplicada es <code>{analysis.policy_version}</code>. El score
        representa una evaluación ordinal, no una probabilidad ni una
        confirmación humana de fraude.
      </p>
    </details>
  );
}

export function AnalysisView({ analysis }: { analysis: Analysis }) {
  if (analysis.status === 'ERROR')
    return (
      <section className="panel analysis-error">
        <ErrorExplanation code={analysis.error_code} />
      </section>
    );
  const ruleSignals = analysis.signals.filter(
    (signal) => signal.source === 'RULE',
  );
  const contextSignals = analysis.signals.filter(
    (signal) => signal.source === 'CONTEXT',
  );
  const semanticSignals = analysis.signals.filter(
    (signal) => signal.source === 'SEMANTIC',
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
          <h2>
            {analysis.status === 'COMPLETED'
              ? 'Explicación textual del análisis semántico'
              : 'Resultado determinista'}
          </h2>
          <small>{date(analysis.analyzed_at)}</small>
        </div>
        <p className="evidence-disclaimer">
          {analysis.status === 'COMPLETED'
            ? 'El siguiente texto fue generado por el proveedor semántico. Es una explicación textual, no el razonamiento interno verificable del modelo ni una prueba concluyente.'
            : 'La IA no estuvo disponible. Esta información procede de reglas y contexto; no se generó una explicación semántica.'}
        </p>
        <p className="summary">{analysis.summary}</p>
        <div className="recommendation">
          <h3>Acción recomendada</h3>
          <p>{analysis.recommended_action}</p>
        </div>
      </section>
      <section className="panel evidence-panel">
        <h2>Evidencia observable</h2>
        <p className="evidence-intro">
          Las señales se muestran por separado para relacionar el resultado con
          datos observables y con la política aplicada. Ninguna señal confirma
          fraude por sí sola.
        </p>
        {!ruleSignals.length && !contextSignals.length && (
          <EmptyState>No se registraron señales adicionales.</EmptyState>
        )}
        {ruleSignals.length > 0 && (
          <div className="signal-group">
            <div className="signal-group-header">
              <h3>Señales deterministas</h3>
            </div>
            <SignalTable signals={ruleSignals} />
          </div>
        )}
        {contextSignals.length > 0 && (
          <div className="signal-group signal-group-context">
            <div className="signal-group-header">
              <h3>Señales derivadas del contexto</h3>
            </div>
            <SignalTable signals={contextSignals} />
          </div>
        )}
        {analysis.status === 'COMPLETED' && semanticSignals.length > 0 && (
          <div className="signal-group signal-group-semantic">
            <div className="signal-group-header">
              <h3>Análisis semántico</h3>
            </div>
            <p className="semantic-disclaimer">
              Estas señales están estructuradas por el proveedor y su influencia
              está incorporada en <code>semantic_score</code>. No se suman de
              nuevo individualmente al score.
            </p>
            <SignalTable signals={semanticSignals} />
          </div>
        )}
        <ScorePath analysis={analysis} />
        <div className="uncertainty-note">
          <strong>Cómo interpretar la incertidumbre</strong>
          <p>
            Un score bajo, una identidad coincidente o un resultado de
            autenticación declarado como <code>pass</code> no descartan una
            cuenta comprometida. Cuando la solicitud sea sensible, verifica por
            un canal conocido e independiente antes de actuar.
          </p>
        </div>
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
