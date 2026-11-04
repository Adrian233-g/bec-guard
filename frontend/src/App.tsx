import { useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import {
  BrowserRouter,
  Link,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom';
import { ApiError, message } from './api';
import { Emails, EmailDetail } from './pages/Emails';
import { ContextPage } from './pages/Context';
import { Audit } from './pages/Audit';
import { Reports } from './pages/Reports';
import { Users } from './pages/Users';
import { Account } from './pages/Account';
import { Dashboard } from './pages/Dashboard';
import { Alerts } from './pages/Alerts';
import { AlertDetail } from './pages/AlertDetail';
import { AuthProvider, useAuth } from './auth';
import { ErrorState, LoadingState, label } from './components';
import { NotificationBell } from './NotificationBell';
import { LiveUpdates } from './LiveUpdates';
import {
  IconAccount,
  IconAlerts,
  IconAudit,
  IconDashboard,
  IconExecutive,
  IconEye,
  IconEyeOff,
  IconLogOut,
  IconMail,
  IconReports,
  IconShield,
  IconUsers,
  IconVendor,
} from './icons';

function Login() {
  const { user, login } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [capsLockActive, setCapsLockActive] = useState(false);
  const location = useLocation();
  if (user)
    return (
      <Navigate
        to={(location.state as { from?: string } | null)?.from || '/'}
        replace
      />
    );
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const values = new FormData(form);
    setBusy(true);
    setError('');
    try {
      await login(String(values.get('email')), String(values.get('password')));
      form.reset();
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 401
          ? 'Correo o contraseña incorrectos.'
          : message(e),
      );
    } finally {
      setBusy(false);
    }
  }

  function handlePasswordKey(e: React.KeyboardEvent<HTMLInputElement>) {
    setCapsLockActive(e.getModifierState('CapsLock'));
  }

  return (
    <main className="login">
      <section className="login-intro">
        <div className="brand" aria-label="BEC Guard">
          <span className="brand-mark" aria-hidden="true">
            <IconShield width="20" height="20" />
          </span>
          <span>BEC Guard</span>
        </div>
        <h1>
          Una decisión informada.
          <br />
          Una amenaza contenida.
        </h1>
        <p>Revisa señales de fraude empresarial y documenta cada decisión.</p>
        <div className="login-rule">Detección explicable · Revisión humana</div>
        <div className="login-telemetry" aria-label="Estado del sistema">
          <span className="telemetry-dot" aria-hidden="true" />
          <span>Gateway SOC Operativo · Sesión Segura TLS</span>
        </div>
      </section>
      <section className="login-form">
        <form onSubmit={(e) => void submit(e)}>
          <h2>Iniciar sesión</h2>
          <p>Accede a tu espacio de revisión.</p>
          <fieldset disabled={busy} className="login-fieldset">
            <label htmlFor="email">Correo electrónico</label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              required
              autoFocus
              maxLength={320}
              disabled={busy}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? 'login-error' : undefined}
            />
            <label htmlFor="password">Contraseña</label>
            <div className="password-input-wrap">
              <input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                required
                maxLength={128}
                disabled={busy}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? 'login-error' : undefined}
                onKeyDown={handlePasswordKey}
                onKeyUp={handlePasswordKey}
                onBlur={() => setCapsLockActive(false)}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword((prev) => !prev)}
                disabled={busy}
                aria-label={
                  showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'
                }
                title={
                  showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'
                }
                tabIndex={-1}
              >
                {showPassword ? <IconEyeOff /> : <IconEye />}
              </button>
            </div>
            {capsLockActive && (
              <div className="caps-lock-pill" role="status">
                <span aria-hidden="true">⇪</span> Bloq Mayús activado
              </div>
            )}
          </fieldset>
          <div className="login-feedback-area" aria-live="polite">
            {error && (
              <div id="login-error" role="alert" className="login-error-banner">
                <span className="error-dot" aria-hidden="true" />
                <span>{error}</span>
              </div>
            )}
          </div>
          <button disabled={busy} type="submit" aria-busy={busy}>
            {busy ? 'Iniciando sesión…' : 'Iniciar sesión'}
          </button>
          <div className="login-support">
            <p className="login-support-prompt">
              ¿Problemas para acceder a tu cuenta?
            </p>
            <p className="login-support-help">
              Las cuentas son aprovisionadas por el administrador de seguridad.
              Si olvidaste tu contraseña o requieres acceso, contacta al{' '}
              <a href="mailto:soc-admin@becguard.local">equipo del SOC</a>.
            </p>
          </div>
        </form>
      </section>
    </main>
  );
}
function Protected() {
  const { user, loading, error, retry } = useAuth();
  const location = useLocation();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} retry={retry} />;
  return user ? (
    <Outlet />
  ) : (
    <Navigate to="/login" state={{ from: location.pathname }} replace />
  );
}
function Shell() {
  const { user, logout } = useAuth();
  const [menu, setMenu] = useState(false);

  type NavSection = { title: string; items: [string, string][] };

  const sections: NavSection[] =
    user?.role === 'EMPLOYEE'
      ? [
          {
            title: 'Operaciones',
            items: [
              ['/emails', 'Correos'],
              ['/alerts', 'Alertas'],
            ],
          },
          {
            title: 'Cuenta',
            items: [['/account', 'Mi cuenta']],
          },
        ]
      : [
          {
            title: 'Monitoreo',
            items: [
              ['/', 'Dashboard'],
              ['/alerts', 'Alertas'],
              ['/emails', 'Correos'],
            ],
          },
          {
            title: 'Contexto SOC',
            items: [
              ['/executives', 'Ejecutivos'],
              ['/vendors', 'Proveedores'],
            ],
          },
          {
            title: 'Gestión',
            items: [
              ...(user?.role === 'ADMIN' || user?.role === 'ANALYST'
                ? ([['/reports', 'Reportes']] as [string, string][])
                : []),
              ...(user?.role === 'ADMIN'
                ? ([
                    ['/audit', 'Auditoría'],
                    ['/users', 'Usuarios'],
                  ] as [string, string][])
                : []),
              ['/account', 'Mi cuenta'],
            ],
          },
        ];

  const iconMap: Record<string, ReactNode> = {
    '/': <IconDashboard />,
    '/alerts': <IconAlerts />,
    '/emails': <IconMail />,
    '/executives': <IconExecutive />,
    '/vendors': <IconVendor />,
    '/reports': <IconReports />,
    '/audit': <IconAudit />,
    '/users': <IconUsers />,
    '/account': <IconAccount />,
  };

  return (
    <div className="app">
      {user && <LiveUpdates key={user.id} />}
      <a className="skip" href="#content">
        Saltar al contenido
      </a>
      <aside className={menu ? 'sidebar expanded' : 'sidebar'}>
        <Link className="brand" to="/">
          <span className="brand-mark" aria-hidden="true">
            <IconShield width="20" height="20" />
          </span>
          <span>BEC Guard</span>
        </Link>
        <button
          className="menu-toggle secondary"
          aria-expanded={menu}
          aria-controls="main-nav"
          onClick={() => setMenu(!menu)}
        >
          Menú
        </button>
        <nav id="main-nav" aria-label="Navegación principal">
          {sections.map((sec) => (
            <div key={sec.title} className="nav-group">
              <span className="nav-group-title">{sec.title}</span>
              {sec.items.map(([path, title]) => (
                <NavLink
                  key={path}
                  to={path}
                  end={path === '/'}
                  onClick={() => setMenu(false)}
                >
                  <span className="nav-icon" aria-hidden="true">
                    {iconMap[path]}
                  </span>
                  <span>{title}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <p className="sidebar-note">
          Prevención de fraude
          <br />
          Revisión y trazabilidad
        </p>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="topbar-title">
            <span className="live-dot" aria-hidden="true" />
            <span>Centro de revisión</span>
          </div>
          <div className="topbar-user">
            <NotificationBell />
            <div className="user-profile-badge">
              <span className="user-avatar" aria-hidden="true">
                {user?.name ? user.name[0].toUpperCase() : 'U'}
              </span>
              <span className="identity">
                <span className="user-name">{user?.name}</span>
                <small>{label(user?.role)}</small>
              </span>
            </div>
            <button className="secondary logout-button" onClick={logout}>
              <IconLogOut aria-hidden="true" />
              <span>Cerrar sesión</span>
            </button>
          </div>
        </header>
        <main id="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
export function AppRoutes() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Protected />}>
        <Route element={<Shell />}>
          <Route
            index
            element={
              user?.role === 'EMPLOYEE' ? (
                <Navigate to="/emails" replace />
              ) : (
                <Dashboard />
              )
            }
          />
          <Route path="alerts" element={<Alerts />} />
          <Route path="alerts/:alertId" element={<AlertDetail />} />
          <Route path="emails" element={<Emails />} />
          <Route path="emails/:emailId" element={<EmailDetail />} />
          <Route
            path="executives"
            element={<ContextPage key="executives" kind="executives" />}
          />
          <Route
            path="vendors"
            element={<ContextPage key="vendors" kind="vendors" />}
          />
          <Route path="audit" element={<Audit />} />
          <Route path="reports" element={<Reports />} />
          <Route path="users" element={<Users />} />
          <Route path="account" element={<Account />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
