import { it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { AuthProvider } from '../auth';
import { tokenKey } from '../api';
import { response, user } from './fixtures';
import type { Role } from '../types';

function setup(path: string, role: Role) {
  sessionStorage.setItem(tokenKey, 't');
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/auth/me')) return response({ ...user, role });
    if (url.startsWith('/api/users') && init?.method === 'POST')
      return response({ id: 'new' }, 201);
    if (url.startsWith('/api/users') && init?.method === 'PATCH')
      return response({});
    if (url.startsWith('/api/users?'))
      return response([
        { ...user, role, is_active: true },
        {
          id: 'other',
          name: 'Ana',
          email: 'ana@example.com',
          role: 'EMPLOYEE',
          is_active: true,
        },
      ]);
    if (url.endsWith('/auth/change-password'))
      return new Response(null, { status: 204 });
    return response([]);
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

it('admin creates an employee and does not render the password afterwards', async () => {
  const fetch = setup('/users', 'ADMIN');
  await userEvent.click(
    await screen.findByRole('button', { name: 'Añadir usuario' }),
  );
  await userEvent.type(screen.getByLabelText('Nombre'), 'Ana');
  await userEvent.type(screen.getByLabelText('Correo'), 'ana@example.com');
  await userEvent.type(
    screen.getByLabelText('Contraseña inicial'),
    'initial password 123',
  );
  await userEvent.type(
    screen.getByLabelText('Confirmar contraseña'),
    'initial password 123',
  );
  await userEvent.click(screen.getByRole('button', { name: 'Crear usuario' }));
  await screen.findByText(/Usuario creado/);
  const call = fetch.mock.calls.find(
    ([url, options]) => url === '/api/users' && options?.method === 'POST',
  );
  expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
    email: 'ana@example.com',
    role: 'EMPLOYEE',
  });
  expect(screen.queryByLabelText('Contraseña inicial')).not.toBeInTheDocument();
});

it('admin can change another user status but cannot change own role', async () => {
  const fetch = setup('/users', 'ADMIN');
  expect(await screen.findByLabelText('Rol de Lucía')).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Desactivar Ana' }));
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(
        ([url, init]) =>
          url === '/api/users/other' &&
          init?.method === 'PATCH' &&
          String(init.body).includes('false'),
      ),
    ).toBe(true),
  );
});

it('analyst cannot open user management', async () => {
  const fetch = setup('/users', 'ANALYST');
  await screen.findByText('No tienes permisos para gestionar usuarios.');
  expect(fetch.mock.calls.some(([url]) => url.startsWith('/api/users'))).toBe(
    false,
  );
});

it('employee can change their own password', async () => {
  const fetch = setup('/account', 'EMPLOYEE');
  await userEvent.type(
    await screen.findByLabelText('Contraseña actual'),
    'old password 123',
  );
  await userEvent.type(
    screen.getByLabelText('Contraseña nueva'),
    'new password 456',
  );
  await userEvent.type(
    screen.getByLabelText('Confirmar contraseña nueva'),
    'new password 456',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Cambiar contraseña' }),
  );
  await screen.findByText('Contraseña actualizada.');
  expect(
    fetch.mock.calls.some(
      ([url, init]) =>
        url.endsWith('/auth/change-password') && init?.method === 'POST',
    ),
  ).toBe(true);
  expect(screen.getByLabelText('Contraseña actual')).toHaveValue('');
});

it('employee can register a mailbox in account', async () => {
  const fetch = setup('/account', 'EMPLOYEE');
  await userEvent.type(
    await screen.findByLabelText('Dirección de correo electrónico'),
    'emp@example.com',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Registrar dirección' }),
  );
  await screen.findByText(
    'Dirección registrada. La conexión de Gmail aún está pendiente.',
  );
  expect(
    fetch.mock.calls.some(
      ([url, init]) =>
        url === '/api/mailboxes' &&
        init?.method === 'POST' &&
        String(init.body).includes('emp@example.com'),
    ),
  ).toBe(true);
});
