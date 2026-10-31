import { it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { AuthProvider } from '../auth';
import { tokenKey } from '../api';
import { notification, response, user } from './fixtures';

function setup(count = 1) {
  sessionStorage.setItem(tokenKey, 't');
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/auth/me')) return response(user);
    if (url.endsWith('/notifications/unread-count')) return response({ count });
    if (url === '/api/notifications?limit=10')
      return response(count ? [notification] : []);
    if (url.endsWith('/notifications/read-all') && init?.method === 'POST')
      return response({ updated: count });
    if (url.endsWith(`/notifications/${notification.id}/read`))
      return new Response(null, { status: 204 });
    if (url.startsWith('/api/alerts?')) return response([]);
    return response({}, 404);
  });
  vi.stubGlobal('fetch', fetch);
  render(
    <MemoryRouter initialEntries={['/alerts']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
  return fetch;
}

it('shows unread notices and marks them all as read', async () => {
  const fetch = setup();
  const bell = await screen.findByRole(
    'button',
    { name: 'Avisos, 1 sin leer' },
    { timeout: 3000 },
  );
  await userEvent.click(bell);
  expect(
    await screen.findByText(notification.subject, {}, { timeout: 3000 }),
  ).toBeInTheDocument();
  expect(screen.getByText(/Sin leer/)).toBeInTheDocument();
  expect(
    screen.getByRole('link', { name: /Dirección.*Riesgo Crítico/ }),
  ).toHaveAttribute('href', `/alerts/${notification.alert_id}`);

  await userEvent.click(
    screen.getByRole('button', { name: 'Marcar todos leídos' }),
  );
  await screen.findByRole('button', { name: 'Avisos' });
  expect(screen.queryByText(/Sin leer/)).not.toBeInTheDocument();
  expect(
    fetch.mock.calls.some(
      ([url, init]) =>
        url === '/api/notifications/read-all' && init?.method === 'POST',
    ),
  ).toBe(true);
});

it('marks a notice as read when opening its alert', async () => {
  const fetch = setup();
  await userEvent.click(
    await screen.findByRole(
      'button',
      { name: 'Avisos, 1 sin leer' },
      { timeout: 3000 },
    ),
  );
  const link = await screen.findByRole(
    'link',
    { name: /Cambio de cuenta/ },
    { timeout: 3000 },
  );
  await userEvent.click(link);
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(
        ([url, init]) =>
          url === `/api/notifications/${notification.id}/read` &&
          init?.method === 'POST',
      ),
    ).toBe(true),
  );
});

it('shows an empty state when there are no notices', async () => {
  setup(0);
  await userEvent.click(await screen.findByRole('button', { name: 'Avisos' }));
  expect(await screen.findByText('No tienes avisos.')).toBeInTheDocument();
});
