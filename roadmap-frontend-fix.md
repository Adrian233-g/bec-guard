# Hoja de Ruta: Refinamiento Frontend (Estándar Impeccable - Precision SOC & Threat Radar)

Este documento detalla la hoja de ruta para eliminar la tosquedad visual del frontend de **BEC Guard** y elevarlo a una consola de operaciones de ciberseguridad moderna y precisa (**Modo Operate** de Impeccable, benchmark *Cloudflare Radar + Stripe Radar + GitHub Security*).

Mantenemos intacta la paleta de colores institucional (`#172e3f`, `#126b70`, `#f3f6f8`, `#d5dfe5`, `#9f253d`) y aseguramos que el 100% de la suite de pruebas (65 tests en Vitest) y la accesibilidad continúen pasando en cada entrega.

---

## Estado Global del Progreso

- [x] **Fase 1: Fundamentos y Ruta Raíz (`/`) [COMPLETADO]**
  - [x] **1.1 Tokens y base CSS**: Escala tipográfica con `tabular-nums`, radios uniformes (6px/8px), eliminación de anti-patrones `border-left: 4px` y elevaciones sutiles.
  - [x] **1.2 Shell global**: Sidebar con isotipo de escudo estilizado, iconografía SVG por sección, topbar de mando pulida y campana de notificaciones.
  - [x] **1.3 Dashboard (`/`)**: Reemplazo de `.workload` por tarjeta de guardia operativa balanceada, tira de métricas en tarjetas nítidas, barras de riesgo y lista reciente con dot de severidad.
  - [x] **1.4 Login (`/login`)**: Pulido del formulario y panel de bienvenida institucional sin bloques pesados.
- [x] **Fase 2: Triage de Alertas y Detalle Forense (`/alerts` y `/alerts/:id`) [COMPLETADO]**
  - [x] **2.1 Cola de alertas (`/alerts`)**: Barra de filtros compacta y tabla de triage de alta densidad (padding 11px) con badges y micro-dots de estado.
  - [x] **2.2 Detalle de alerta y evidencia (`/alerts/:id`)**: *Signature Move* (desglose visual de reglas, semántica LLM y contexto de identidad), cabeceras de correo forenses y panel de resolución humana.
- [ ] **Fase 3: Exploración de Correos y Evidencia MIME (`/emails` y `/emails/:id`)**
  - [ ] **3.1 Bandeja de correos (`/emails`)**: Tabla optimizada con indicadores de análisis, estado de riesgo y filtros por remitente.
  - [ ] **3.2 Vista de correo y cabeceras (`/emails/:id`)**: Bloque monospace técnico refinado para cabeceras (SPF/DKIM/Message-ID) y visor de cuerpo seguro.
- [ ] **Fase 4: Contexto Organizacional y Gestión (`/executives`, `/vendors`, `/users`, `/account`)**
  - [ ] **4.1 Contexto VIP y Proveedores (`/executives`, `/vendors`)**: Tarjetas de entidad con estados activos/desconectados y formularios modales pulidos.
  - [ ] **4.2 Usuarios y Perfil (`/users`, `/account`)**: Tablas de gestión RBAC y formularios de credenciales consistentes.
- [ ] **Fase 5: Auditoría y Reportes Operativos (`/audit` y `/reports`)**
  - [ ] **5.1 Trazabilidad forense (`/audit`)**: Tabla de eventos de auditoría con diffs estructurados y filtros por acción/usuario.
  - [ ] **5.2 Exportación de reportes (`/reports`)**: Panel de generación PDF/Excel con feedback de descarga accesible.
- [ ] **Fase 6: Auditoría final Impeccable (Craft Floor, a11y, responsive y suite verde)**
  - [ ] **6.1 Auditoría técnica**: Verificación con detector `impeccable detect`, contraste WCAG AAA/AA, responsive en breakpoints 800px y 1150px, y ejecución íntegra de tests de Vitest.

---

## Registro de Tareas y Commits

| Commit / Tarea | Módulo / Archivos | Estado | Descripción del cambio |
| :--- | :--- | :--- | :--- |
| `feat(ui): roadmap` | `roadmap-frontend-fix.md` | ✅ Completado | Hoja de ruta para el refinamiento de diseño Impeccable |
| `feat(ui): design-tokens` | `frontend/src/styles.css` | ✅ Completado | Variables de diseño, elevación, tipografía tabular y resets de anti-patrones |
| `feat(ui): shell-navigation` | `frontend/src/App.tsx`, `frontend/src/icons.tsx`, `NotificationBell.tsx` | ✅ Completado | Iconos SVG y sidebar/topbar de alta precisión |
| `feat(ui): dashboard-operate` | `frontend/src/pages/Dashboard.tsx`, `frontend/src/components.tsx` | ✅ Completado | Rediseño de guardia operativa, métricas y badges con micro-dots |
| `feat(ui): login-polish` | `frontend/src/App.tsx`, `frontend/src/styles.css` | ✅ Completado | Pantalla de acceso alineada al estándar SOC |
| `feat(ui): alerts-queue` | `frontend/src/pages/Alerts.tsx`, `frontend/src/icons.tsx`, `frontend/src/styles.css` | ✅ Completado | Triage de alertas de alta densidad, filtros organizados y micro-chips |
| `feat(ui): alert-forensics` | `frontend/src/pages/AlertDetail.tsx`, `frontend/src/analysis.tsx`, `frontend/src/styles.css` | ✅ Completado | Signature Move: Threat Inspector, señales por origen y cabeceras forenses |
