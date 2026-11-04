import { afterEach, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LiveUpdates } from '../LiveUpdates';
import { email, notification, response } from './fixtures';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it('announces only new mail and alerts, refreshes views, and does not repeat them', async () => {
  vi.useFakeTimers();
  let emails = [email];
  let notifications = [notification];
  const newerEmail = { ...email, id: 'email-new', subject: 'Factura nueva' };
  const newerAlert = {
    ...notification,
    id: 'notice-new',
    alert_id: 'alert-new',
    subject: 'Pago sospechoso',
  };
  const fetch = vi.fn(async (url: string) => {
    if (url.includes('/emails?')) return response(emails);
    if (url.includes('/notifications?')) return response(notifications);
    return response({}, 404);
  });
  vi.stubGlobal('fetch', fetch);
  const updates = vi.fn();
  window.addEventListener('bec-live-update', updates);
  const view = render(
    <MemoryRouter>
      <LiveUpdates />
    </MemoryRouter>,
  );
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(screen.queryByText('Correo nuevo')).not.toBeInTheDocument();
  expect(
    screen.queryByText('Alerta de posible fraude'),
  ).not.toBeInTheDocument();
  emails = [newerEmail, email];
  notifications = [newerAlert, notification];
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10_000);
  });
  expect(screen.getByRole('status')).toHaveTextContent('Factura nueva');
  expect(screen.getByRole('alert')).toHaveTextContent('Pago sospechoso');
  expect(screen.getByRole('link', { name: 'Ver correo' })).toHaveAttribute(
    'href',
    '/emails/email-new',
  );
  expect(screen.getByRole('link', { name: 'Revisar alerta' })).toHaveAttribute(
    'href',
    '/alerts/alert-new',
  );
  expect(updates).toHaveBeenCalledTimes(1);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(8_000);
  });
  expect(screen.queryByText('Correo nuevo')).not.toBeInTheDocument();
  expect(screen.getByRole('alert')).toBeInTheDocument();
  await act(async () => {
    window.dispatchEvent(new Event('focus'));
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(screen.getAllByRole('alert')).toHaveLength(1);
  expect(updates).toHaveBeenCalledTimes(1);
  view.unmount();
  window.removeEventListener('bec-live-update', updates);
});

it('does not replay history after the first request fails', async () => {
  vi.useFakeTimers();
  let failed = true;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.includes('/emails?') && failed) return response({}, 503);
      if (url.includes('/emails?')) return response([email]);
      return response([]);
    }),
  );
  render(
    <MemoryRouter>
      <LiveUpdates />
    </MemoryRouter>,
  );
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  failed = false;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10_000);
  });
  expect(screen.queryByText('Correo nuevo')).not.toBeInTheDocument();
});
