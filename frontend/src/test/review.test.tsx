import { it, expect, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { AuthProvider } from '../auth';
import { tokenKey } from '../api';
import { alert, email, user, dashboard, summary, response } from './fixtures';
import type { AlertDetail, Role } from '../types';
function setup(
  path = '/',
  role: Role = 'ANALYST',
  initial: AlertDetail = alert,
  conflict = false,
) {
  sessionStorage.setItem(tokenKey, 'test-token');
  let current = structuredClone(initial);
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/auth/me')) return response({ ...user, role });
    if (url.includes('/dashboard/')) return response(dashboard);
    if (url === '/api/alerts?limit=5') return response([summary]);
    if (url.startsWith('/api/alerts?')) return response([summary]);
    if (url === '/api/emails/email-1') return response(email);
    if (url === '/api/alerts/alert-1') return response(current);
    if (url.endsWith('/claim')) {
      if (conflict) {
        current = {
          ...current,
          status: 'UNDER_REVIEW',
          assigned_to: 'other',
          assigned_to_name: 'Otra persona',
        };
        return response({}, 409);
      }
      current = {
        ...current,
        status: 'UNDER_REVIEW',
        assigned_to: user.id,
        assigned_to_name: user.name,
      };
      return response(current);
    }
    if (url.endsWith('/release')) {
      current = { ...current, status: 'OPEN', assigned_to: null };
      return response(current);
    }
    if (url.endsWith('/resolve')) {
      const body = JSON.parse(String(init?.body));
      current = {
        ...current,
        status: 'CLOSED',
        verdict: body.verdict,
        resolution: body.resolution,
        closed_at: '2026-10-21T14:00:00Z',
      };
      return response(current);
    }
    return response({}, 404);
  });
  vi.stubGlobal('fetch', fetch);
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
  return fetch;
}
it('dashboard displays real aggregates and recent links', async () => {
  setup();
  await screen.findByText('Correos recibidos');
  expect(screen.getByText('12')).toBeInTheDocument();
  expect(
    await screen.findByRole('link', { name: email.subject }),
  ).toHaveAttribute('href', '/alerts/alert-1');
});
it('dashboard error is actionable', async () => {
  sessionStorage.setItem(tokenKey, 't');
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        url.endsWith('/auth/me') ? response(user) : response({}, 503),
      ),
    ),
  );
  render(
    <MemoryRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
  await screen.findByRole('alert');
  expect(
    screen.getByRole('button', { name: 'Reintentar' }),
  ).toBeInTheDocument();
});
it('alert filters request backend filters', async () => {
  const fetch = setup('/alerts');
  await screen.findByRole('link', { name: email.subject });
  await userEvent.selectOptions(
    screen.getByLabelText('Estado'),
    'UNDER_REVIEW',
  );
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(([url]) => url.includes('status=UNDER_REVIEW')),
    ).toBe(true),
  );
  await userEvent.selectOptions(screen.getByLabelText('Riesgo'), 'HIGH');
  await userEvent.selectOptions(
    screen.getByLabelText('Tipo BEC'),
    'BANK_ACCOUNT_CHANGE',
  );
  await userEvent.click(screen.getByLabelText('Asignadas a mí'));
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(([url]) => url.includes('assigned_to=user-1')),
    ).toBe(true),
  );
});
it('alert queue has loading and empty states', async () => {
  sessionStorage.setItem(tokenKey, 't');
  let finish!: (r: Response) => void;
  const pendingAlerts = new Promise<Response>((resolve) => {
    finish = resolve;
  });
  const fetch = vi.fn((url: string) =>
    url.endsWith('/auth/me') ? Promise.resolve(response(user)) : pendingAlerts,
  );
  vi.stubGlobal('fetch', fetch);
  render(
    <MemoryRouter initialEntries={['/alerts']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
  await screen.findByRole('heading', { name: 'Alertas' });
  // Rendering the heading does not guarantee that the resource effect ran.
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      '/api/alerts?limit=25&offset=0',
      expect.any(Object),
    ),
  );
  expect(screen.getByRole('status')).toHaveTextContent('Cargando');
  await act(async () => {
    finish(response([]));
  });
  await screen.findByText('No hay alertas con estos filtros.');
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});
it('detail safely renders email and separates signals', async () => {
  setup('/alerts/alert-1');
  await screen.findByText(
    (_, element) =>
      element?.tagName === 'PRE' && element.textContent === email.body_text,
  );
  expect(screen.getAllByText('Análisis semántico').length).toBeGreaterThan(0);
  expect(
    screen.getByText('Cambio de cuenta o beneficiario'),
  ).toBeInTheDocument();
  expect(screen.getByText('+15 puntos por reglas')).toBeInTheDocument();
  expect(
    screen.getByText('Señal identificada por el análisis semántico'),
  ).toBeInTheDocument();
  expect(screen.getByText('Señal detectada')).toBeInTheDocument();
  expect(screen.getByText('SEMANTIC_REQUEST')).toBeInTheDocument();
  expect(screen.queryByText('+0 puntos por reglas')).not.toBeInTheDocument();
  expect(document.querySelector('.email-body script')).toBeNull();
  expect(document.querySelector('.email-body a')).toBeNull();
});
it('reconstructs the score path for a spoofing case', async () => {
  setup('/alerts/alert-1', 'ANALYST', {
    ...alert,
    analysis: {
      ...alert.analysis,
      signals: [
        {
          code: 'EXECUTIVE_IDENTITY_MISMATCH',
          source: 'CONTEXT',
          description: 'Nombre conocido con dirección distinta.',
          contribution: 35,
        },
        {
          code: 'BANK_ACCOUNT_CHANGE',
          source: 'RULE',
          description: 'Solicita cambiar la cuenta.',
          contribution: 24,
        },
        {
          code: 'SEMANTIC_REQUEST',
          source: 'SEMANTIC',
          description: 'Se solicita una transferencia.',
          contribution: 0,
        },
      ],
      score_breakdown: {
        mode: 'COMPLETED',
        raw_deterministic_total: 114,
        deterministic_score: 100,
        semantic_score: 42,
        weighted_score: 71,
        floor_score: 70,
        floor_reasons: ['IMPERSONATION_SENSITIVE_REQUEST'],
        final_score: 71,
        alert_threshold: 50,
        alert_triggered: true,
      },
    },
  });
  await screen.findByText('Suma bruta determinista');
  expect(screen.getByText('114')).toBeInTheDocument();
  expect(screen.getByText('Piso de política')).toBeInTheDocument();
  expect(
    screen.getByText('suplantación combinada con una solicitud sensible'),
  ).toBeInTheDocument();
  expect(screen.getByText('No suma al score')).toBeInTheDocument();
  expect(screen.getByText(/no una probabilidad/)).toBeInTheDocument();
});
it('explains a hard legitimate case without treating authentication as proof', async () => {
  setup('/alerts/alert-1', 'ANALYST', {
    ...alert,
    analysis: {
      ...alert.analysis,
      deterministic_score: 8,
      semantic_score: 12,
      risk_score: 10,
      risk_level: 'LOW',
      bec_type: null,
      signals: [
        {
          code: 'PAYMENT_REQUEST',
          source: 'RULE',
          description: 'El mensaje plantea un pago.',
          contribution: 8,
        },
      ],
      score_breakdown: {
        mode: 'COMPLETED',
        raw_deterministic_total: 8,
        deterministic_score: 8,
        semantic_score: 12,
        weighted_score: 10,
        floor_score: 0,
        floor_reasons: [],
        final_score: 10,
        alert_threshold: 50,
        alert_triggered: false,
      },
    },
  });
  await screen.findByText(/no descartan una cuenta comprometida/);
  expect(await screen.findByText('Authentication-Results')).toBeInTheDocument();
  expect(
    screen.getByText(/verifica por un canal conocido/),
  ).toBeInTheDocument();
});
it('keeps semantic and deterministic disagreement visible', async () => {
  setup('/alerts/alert-1', 'ANALYST', {
    ...alert,
    analysis: {
      ...alert.analysis,
      deterministic_score: 70,
      semantic_score: 10,
      risk_score: 70,
      risk_level: 'HIGH',
      score_breakdown: {
        mode: 'COMPLETED',
        raw_deterministic_total: 70,
        deterministic_score: 70,
        semantic_score: 10,
        weighted_score: 40,
        floor_score: 70,
        floor_reasons: ['DETERMINISTIC_SCORE_GE_70'],
        final_score: 70,
        alert_threshold: 50,
        alert_triggered: true,
      },
    },
  });
  await screen.findByText('40/100');
  expect(screen.getAllByText('70/100').length).toBeGreaterThan(1);
  expect(
    screen.getAllByText(/suplantación combinada|score determinista/).length,
  ).toBeGreaterThan(0);
});
it('does not present semantic explanation during fallback', async () => {
  setup('/alerts/alert-1', 'ANALYST', {
    ...alert,
    analysis: {
      ...alert.analysis,
      status: 'FALLBACK',
      semantic_score: null,
      risk_score: 58,
      risk_level: 'MEDIUM',
      summary: 'Evaluación limitada a reglas.',
      recommended_action: 'Verificar por canal conocido.',
      signals: [
        {
          code: 'BANK_ACCOUNT_CHANGE',
          source: 'RULE',
          description: 'Solicita cambiar la cuenta.',
          contribution: 24,
        },
      ],
      score_breakdown: {
        mode: 'FALLBACK',
        raw_deterministic_total: 58,
        deterministic_score: 58,
        semantic_score: null,
        weighted_score: null,
        floor_score: 0,
        floor_reasons: [],
        final_score: 58,
        alert_threshold: 50,
        alert_triggered: true,
      },
    },
  });
  await screen.findByText('Análisis limitado a reglas');
  expect(
    screen.queryByText(
      'El siguiente texto fue generado por el proveedor semántico.',
    ),
  ).not.toBeInTheDocument();
  expect(screen.getAllByText('No disponible').length).toBeGreaterThan(0);
  expect(screen.queryByText('Análisis semántico')).not.toBeInTheDocument();
});
it.each(['CONFIRMED_BEC', 'FALSE_POSITIVE'] as const)(
  'claim and resolve %s',
  async (verdict) => {
    const fetch = setup('/alerts/alert-1');
    await userEvent.click(
      await screen.findByRole('button', { name: 'Tomar revisión' }),
    );
    await screen.findByText('En revisión por ti');
    await userEvent.click(
      screen.getByRole('button', {
        name:
          verdict === 'CONFIRMED_BEC'
            ? 'Confirmar BEC'
            : 'Marcar falso positivo',
      }),
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await userEvent.type(
      screen.getByLabelText('Resolución'),
      'Identidad verificada fuera del correo.',
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Confirmar decisión' }),
    );
    await screen.findByText('Decisión final registrada en auditoría.');
    expect(
      screen.queryByRole('button', { name: 'Tomar revisión' }),
    ).not.toBeInTheDocument();
    expect(
      fetch.mock.calls.some(
        ([url, options]) =>
          url.endsWith('/resolve') && String(options?.body).includes(verdict),
      ),
    ).toBe(true);
  },
);
it('release returns to OPEN', async () => {
  setup('/alerts/alert-1', 'ANALYST', {
    ...alert,
    status: 'UNDER_REVIEW',
    assigned_to: user.id,
  });
  await userEvent.click(
    await screen.findByRole('button', { name: 'Liberar revisión' }),
  );
  await screen.findByRole('button', { name: 'Tomar revisión' });
});
it('409 refreshes current ownership', async () => {
  setup('/alerts/alert-1', 'ANALYST', alert, true);
  await userEvent.click(
    await screen.findByRole('button', { name: 'Tomar revisión' }),
  );
  await screen.findByText('En revisión por Otra persona');
  expect(screen.getByText(/La alerta cambió durante/)).toBeInTheDocument();
});
it('employee cannot access alert review', async () => {
  setup('/alerts/alert-1', 'EMPLOYEE');
  await screen.findByText(/Tu rol permite consultar la evidencia/);
  expect(
    screen.queryByRole('button', { name: 'Tomar revisión' }),
  ).not.toBeInTheDocument();
});
it('analyst cannot act on someone else review', async () => {
  setup('/alerts/alert-1', 'ANALYST', {
    ...alert,
    status: 'UNDER_REVIEW',
    assigned_to: 'other',
    assigned_to_name: 'Otra persona',
  });
  await screen.findByText('En revisión por Otra persona');
  expect(
    screen.queryByRole('button', { name: 'Confirmar BEC' }),
  ).not.toBeInTheDocument();
});
it('decision dialog cycles focus and closes without resolving', async () => {
  const fetch = setup('/alerts/alert-1', 'ANALYST', {
    ...alert,
    status: 'UNDER_REVIEW',
    assigned_to: user.id,
  });
  await userEvent.click(
    await screen.findByRole('button', { name: 'Confirmar BEC' }),
  );
  const close = screen.getByRole('button', { name: 'Cerrar diálogo' });
  close.focus();
  await userEvent.tab({ shift: true });
  expect(screen.getByRole('button', { name: 'Cancelar' })).toHaveFocus();
  await userEvent.tab();
  expect(close).toHaveFocus();
  await userEvent.click(close);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(fetch.mock.calls.some(([url]) => url.endsWith('/resolve'))).toBe(
    false,
  );
});

it.each(['ADMIN', 'ANALYST'] as const)(
  '%s sees the mailbox owner and original email in the alert detail',
  async (role) => {
    setup('/alerts/alert-1', role);
    expect(await screen.findByText('Bilton Novoa')).toBeInTheDocument();
    expect(screen.getByText('bilton@example.com')).toBeInTheDocument();
    await screen.findByText(
      (_, element) =>
        element?.tagName === 'PRE' && element.textContent === email.body_text,
    );
  },
);

it('employee sees the original email without organization owner metadata', async () => {
  setup('/alerts/alert-1', 'EMPLOYEE');
  await screen.findByText(
    (_, element) =>
      element?.tagName === 'PRE' && element.textContent === email.body_text,
  );
  expect(screen.queryByText('Bilton Novoa')).not.toBeInTheDocument();
  expect(screen.queryByText('bilton@example.com')).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: 'Tomar revisión' }),
  ).not.toBeInTheDocument();
});
