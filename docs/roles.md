# Roles: transición a buzones individuales

La revisión `0009_roles_employee` define tres roles activos: `ADMIN`, `ANALYST`
y `EMPLOYEE`. Cada usuario tiene un solo rol. Los valores históricos `MANAGER` y
`AUDITOR` se conservan únicamente en la bitácora, sin reescribir sus eventos.

Si hay usuarios `MANAGER` o `AUDITOR`, la migración se detiene sin cambiar sus
cuentas. Debe decidirse su reasignación explícita antes de volver a ejecutarla.
El downgrade también se detiene si hay usuarios o eventos históricos de EMPLOYEE,
para no perder información. No ejecutar downgrades sobre datos que se necesiten.

## Permisos durante esta etapa

Todavía no existe la relación entre usuario, buzón y correo. Para no exponer
información ajena, EMPLOYEE puede autenticarse pero recibe 403 para correos,
análisis, alertas, dashboard, contexto, reportes y auditoría. La interfaz muestra
una pantalla provisional hasta que se implemente su buzón personal.

ADMIN y ANALYST mantienen la vista compartida existente de correos y alertas hasta
implementar el aislamiento por propietario. Ambos pueden analizar correos, atender
alertas y descargar reportes; solo ADMIN puede editar contactos y leer auditoría.
ANALYST solo puede liberar o resolver los casos que tomó; ADMIN puede supervisar
casos ajenos. Esta vista compartida es una limitación temporal, no la política
final de privacidad descrita en [roadmap](../roadmap.md).

Aún no hay creación de usuarios desde la aplicación ni conexión de Gmail individual.
No se debe crear una cuenta EMPLOYEE para demostrar estas funciones como si ya
estuvieran terminadas. La próxima etapa del roadmap es la gestión de usuarios.
