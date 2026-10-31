# Roles: transición a buzones individuales

La revisión `0009_roles_employee` define tres roles activos: `ADMIN`, `ANALYST`
y `EMPLOYEE`. Cada usuario tiene un solo rol. Los valores históricos `MANAGER` y
`AUDITOR` se conservan únicamente en la bitácora, sin reescribir sus eventos.

Si hay usuarios `MANAGER` o `AUDITOR`, la migración se detiene sin cambiar sus
cuentas. Debe decidirse su reasignación explícita antes de volver a ejecutarla.
El downgrade también se detiene si hay usuarios o eventos históricos de EMPLOYEE,
para no perder información. No ejecutar downgrades sobre datos que se necesiten.

## Permisos por propietario y buzón (Etapa 2)

La revisión `0010_mailboxes_and_ownership` implementa la entidad `mailboxes` y la
asociación obligatoria entre cada correo y su buzón correspondiente:

- Cada usuario puede registrar y consultar su propio buzón personal desde `/account`.
- **Privacidad estricta por propietario:** `EMPLOYEE`, `ANALYST` y `ADMIN` solo
  consultan en `/emails` los correos pertenecientes a sus propios buzones.
- **Excepción para investigación de alertas:** `ADMIN` y `ANALYST` pueden acceder
  al correo completo y a su análisis en `/emails/{id}` únicamente cuando el correo
  está vinculado a una alerta (`BECAlert`). Si el correo no tiene alerta y no es
  propiedad del actor, el backend deniega el acceso con 404 (evitando enumeración).
- **Cola de alertas:** `EMPLOYEE` solo visualiza sus propias alertas en `/alerts`.
  `ADMIN` y `ANALYST` visualizan la cola de alertas organizacional con datos del
  destinatario/propietario.
- **Trazabilidad y auditoría:** las acciones sobre buzones (`MAILBOX_CREATED`,
  `MAILBOX_UPDATED`, `MAILBOX_DISCONNECTED`) quedan registradas en la bitácora.

ADMIN puede crear, consultar y activar/desactivar usuarios y asignar roles desde la
aplicación; consulta [gestión de usuarios](user-management.md). La conexión de Gmail
individual y el acceso a correos propios siguen pendientes del roadmap.
