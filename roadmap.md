# Roadmap: BEC Guard por organización y buzones personales

Última actualización: 2026-10-31.

Este documento registra la dirección acordada con el usuario y el avance del
proyecto. Las casillas pendientes son trabajo por implementar, no funcionalidades
que ya existan. Actualizarlo al completar cada etapa y documentar decisiones nuevas.

## Objetivo

Una sola aplicación para una organización: el administrador crea usuarios; cada
persona conecta su propio Gmail; BEC Guard analiza los correos entrantes de cada
buzón y los relaciona con su dueño. Cuando un análisis genera una alerta, el caso
aparece en una cola compartida para que un analista lo investigue. El empleado
consulta sus propios correos y resultados; el equipo autorizado puede investigar
el correo concreto que originó una alerta.

El proyecto sigue siendo académico y se demostrará inicialmente con **una cuenta
Gmail conectada**, para ahorrar cuota de Groq. El diseño debe admitir varios usuarios
y buzones sin asumir que la demostración con uno prueba el aislamiento entre ellos.
No se ha solicitado soporte para múltiples organizaciones, otros proveedores de
correo ni instalación de una aplicación por empleado.

## Decisiones acordadas

- Tres roles objetivo: **ADMIN**, **ANALYST** y **EMPLOYEE**. Retirar **MANAGER**
  y **AUDITOR** como roles separados; el administrador asume su supervisión y
  acceso a bitácora. La migración de cuentas existentes requiere una decisión
  explícita si hay usuarios con esos roles: nunca cambiar su rol silenciosamente.
- El administrador crea las cuentas y asigna el rol. No hay registro público
  solicitado. Cada usuario, sea cual sea su rol, podrá conectar su propio Gmail.
- Conexión a Gmail mediante IMAP y **contraseña de aplicación** de Google, no la
  contraseña habitual. El usuario la ingresa desde su sesión en BEC Guard; no debe
  necesitar acceso al editor de n8n. Se podrá ver estado y desconectar la cuenta.
- La propiedad se aplica a cada buzón y a sus correos: una persona solo consulta
  los correos y resultados de sus propios buzones. Esta regla también alcanza a
  administradores y analistas cuando consultan bandejas personales.
- Excepción acordada: ADMIN y ANALYST pueden abrir el **correo completo asociado
  a una alerta**, junto con su análisis, para investigar el caso. No pueden navegar
  libremente los correos normales de otros usuarios. El control debe existir en el
  backend y abarcar también búsquedas, enlaces directos, reportes y automatización.
- Al generarse una alerta, entra automáticamente a la cola del equipo de análisis;
  un analista la toma para investigarla. No se acordó la asignación automática a una
  persona específica. ADMIN puede supervisar e intervenir en casos asignados.
- Los empleados solo ven sus propias alertas. El analista puede tomar, liberar y
  cerrar sus casos con veredicto; ADMIN puede actuar sobre casos de otros. Se
  conserva el cierre con **BEC confirmado** o **falso positivo** y la auditoría.
- La configuración y validación de permisos no debe depender de ocultar botones.
  La automatización debe identificar el buzón de forma verificable y no permitir
  que un cliente elija arbitrariamente el propietario de un correo.
- La política actual crea alertas con score >=70; no se ha aprobado cambiar el
  umbral. El correo sospechoso de prueba obtuvo 59 y no generó alerta, por lo que
  hay que revisar cómo tratar el riesgo medio antes de depender de esa regla.
- Se mantiene la preferencia de **no procesar correos que llegaron mientras el
  workflow estaba apagado**: al iniciar cada receptor se toma un punto de partida
  propio del buzón. Una desconexión IMAP temporal mientras el workflow permanece
  activo puede recuperar correos; ese comportamiento debe documentarse y probarse.
- La información enviada al proveedor de IA incluye contenido de correos. Las
  contraseñas de aplicación deben guardarse cifradas, no volver a mostrarse ni
  aparecer en logs, respuestas, bitácora o ejecuciones de n8n. Los correos en el
  historial de n8n son sensibles: revisar su acceso y tratamiento para no saltarse
  la privacidad entre empleados.

## Matriz de permisos objetivo

| Acción | ADMIN | ANALYST | EMPLOYEE |
| --- | --- | --- | --- |
| Crear/desactivar usuarios y asignar roles | Sí | No | No |
| Gestionar ejecutivos y proveedores | Sí | No | No |
| Conectar/desconectar y consultar su propio Gmail | Sí | Sí | Sí |
| Ver correos y análisis de su propio buzón | Sí | Sí | Sí |
| Ver correo normal de otro usuario | No | No | No |
| Ver alertas de la organización y el correo asociado | Sí | Sí | No |
| Ver sus propias alertas | Sí | Sí | Sí |
| Tomar, liberar y resolver alertas | Sí, también casos de otros | Sí, sus casos | No |
| Consultar estado general y reportes | Sí | Sí | No |
| Consultar bitácora | Sí | No | No |

Una cuenta conserva **un único rol**, pero ser ADMIN o ANALYST no impide ser dueño
de un buzón. Los permisos de propietario y los permisos para investigar alertas se
combinan sin conceder acceso a otros correos normales.

## Estado real al comenzar

- [x] Aplicación React, API FastAPI, PostgreSQL y n8n; autenticación y RBAC básicos.
- [x] Código y migración para ADMIN, ANALYST y EMPLOYEE; cada cuenta tiene un rol.
      Los roles MANAGER y AUDITOR se preservan en eventos históricos de auditoría.
      La migración se validó en PostgreSQL aislado y se aplicó a la instancia local
      el 2026-10-31; otras instalaciones deben aplicar la revisión 0009.
- [x] Contactos ejecutivos/proveedores, ingestión, análisis híbrido con LangChain,
      alertas >=70, cola y revisión humana; bitácora y reportes operativos.
- [x] Un Gmail conectado manualmente a un workflow n8n mediante IMAP. Se probó
      la llegada y el análisis de dos correos con Groq.
- [x] La instancia de n8n guarda historial sin borrado automático. El historial
      puede contener datos del correo y hoy requiere revisión de acceso para el
      modelo multiusuario.
- [x] Ajuste específico de n8n 2.44.4 para partir del UIDNEXT del buzón al iniciar.
      Tiene pruebas locales y el trigger arrancó; falta probar de extremo a extremo
      un correo recibido con Docker apagado y el funcionamiento con varios buzones.
- [x] Rol EMPLOYEE con acceso provisional restringido hasta implementar propiedad.
- [x] Gestión de usuarios por ADMIN y cambio de contraseña por cada usuario en el
      código; reconstruir los contenedores locales para usar esta funcionalidad.
- [ ] Permisos por dueño de buzón.
- [ ] Asociación explícita usuario → buzón → correo; actualmente ADMIN y ANALYST
      comparten acceso a los correos guardados y EMPLOYEE aún no puede leerlos.
- [ ] Conexión individual de Gmail desde la aplicación y múltiples receptores.
- [ ] Notificaciones automáticas a empleados/seguridad: la cola en la app no es
      equivalente al envío de un aviso.
- [ ] Validación formal de la calidad del detector híbrido con datos suficientes.

## Etapas y tareas

### 1. Usuarios y roles

- [x] Diseñar e implementar la migración de roles a ADMIN / ANALYST / EMPLOYEE, conservando
      la integridad de la bitácora histórica y sin convertir cuentas existentes de
      forma silenciosa. Documentar y resolver los usuarios con roles retirados.
- [x] Implementar gestión por ADMIN: crear usuarios, asignar rol, consultar y
      activar/desactivar cuentas. Definir una forma segura de establecer credenciales
      iniciales; nunca registrar contraseñas ni mostrar hashes.
- [x] Añadir pantallas de gestión y una experiencia de inicio provisional para EMPLOYEE.
- [x] Comprobar gestión de usuarios y que un usuario desactivado pierde acceso.
- [ ] Completar la matriz de permisos por propietario y verificarla en la etapa 2.

**Terminado cuando:** el administrador puede crear un analista y un empleado sin
usar SQL manual, y los permisos de cada rol se verifican en el servidor.

### 2. Buzones, propiedad y acceso por caso

- [ ] Diseñar y migrar la entidad de buzón: propietario, dirección, estado de
      conexión y vínculo con correo/alerta. Mantener la posibilidad de un buzón por
      usuario en la primera entrega sin impedir ampliaciones posteriores.
- [ ] Definir y aplicar permisos en listas, detalles, filtros, dashboard, reportes,
      bitácora y APIs: dueño para correos propios; acceso de ADMIN/ANALYST solo al
      correo concreto asociado a una alerta. No permitir acceso indirecto por UUID.
- [ ] Actualizar el modelo de idempotencia: Message-ID es globalmente único hoy,
      pero un mismo mensaje puede llegar a varios buzones. Cada dueño debe tener
      acceso a su propia recepción sin filtraciones ni análisis repetidos indebidos;
      decidir cómo representar y asociar cada recepción antes de migrar el índice.
- [ ] Adaptar la API de automatización para asociar cada entrada al buzón correcto
      mediante identidad confiable y autorización acotada; evitar suplantar dueños.
- [ ] Diseñar una migración para la cuenta Gmail y los correos de prueba actuales.
      Identificar al empleado dueño y confirmar el mapeo antes de asignarlos; no
      inventar un propietario ni borrar datos existentes.
- [ ] Probar al menos dos empleados con buzones distintos, el mismo Message-ID en
      ambos y acceso cruzado denegado; verificar la excepción para alertas reales.

**Terminado cuando:** ningún usuario puede leer el correo normal de otro por API o
interfaz, y el equipo de análisis puede abrir el correo vinculado a una alerta.

### 3. Conectar Gmail desde BEC Guard

- [ ] Añadir pantalla de conexión para ingresar Gmail y contraseña de aplicación;
      verificar conexión, mostrar estado y permitir desconectar o actualizarla.
- [ ] Definir almacenamiento cifrado y gestión de claves/secretos; evitar exponer
      credenciales en navegador, logs, API, bitácora, exports o historial n8n.
- [ ] Diseñar cómo crear, activar y detener receptores IMAP por buzón sin que los
      empleados administren n8n, reutilizando el análisis existente y manteniendo
      identificadores y permisos de cada conexión separados.
- [ ] Garantizar el punto de partida independiente por buzón y la regla de omitir
      correos recibidos mientras el workflow estaba apagado. Adaptar el ajuste actual
      de n8n, que está vinculado al workflow y nodo existentes, al diseño elegido.
- [ ] Gestionar credenciales inválidas o revocadas y errores de conexión sin marcar
      correos como seguros. Evitar reintentos que consuman cuota sin necesidad.
- [ ] Revisar el historial de ejecuciones de n8n y permisos al editor: conservar
      evidencia útil para la demo sin exponer buzones o contraseñas a otros empleados.
- [ ] Integrar el Gmail ya configurado con su empleado propietario sin publicar
      credenciales ni perder los datos existentes.

**Terminado cuando:** cada usuario puede conectar su Gmail desde BEC Guard y los
mensajes nuevos se guardan bajo el dueño correcto, con separación verificada.

### 4. Alertas, escalamiento y comunicación

- [ ] Adaptar la cola de alertas al acceso por rol y propietario; mostrar empleado,
      señales, análisis y correo asociado solo a ADMIN/ANALYST autorizados.
- [ ] Mantener claim/release/resolve y auditoría con las reglas de la matriz; mostrar
      al empleado únicamente sus alertas y el estado de revisión.
- [ ] Diseñar e implementar avisos al empleado y al equipo de seguridad, indicando
      que el resultado es una sospecha y recomendando verificación independiente.
      Definir canal, destinatarios y prevención de avisos duplicados antes de enviar.
- [ ] Evaluar tratamiento visible del riesgo MEDIUM y política >=70 con datos de
      desarrollo; no cambiar pesos o umbrales solo por un ejemplo de demostración.
- [ ] Distinguir errores 429/límites de uso de otros errores del proveedor y ofrecer
      reintento explícito; un fallo no debe convertirse en correo seguro.

**Terminado cuando:** una alerta llega a la cola correcta, el empleado recibe el
aviso definido y un analista puede investigar y cerrar el caso con trazabilidad.

### 5. Verificación y demostración

- [ ] Cubrir permisos, acceso directo entre usuarios, escalamiento, duplicados entre
      buzones, errores IMAP/IA y migraciones con pruebas locales, fakes y PostgreSQL
      aislado. No gastar llamadas a proveedores para pruebas que pueden simularse.
- [ ] Probar un buzón real con pocos mensajes y cuota controlada: correo legítimo,
      correo sospechoso y correo enviado con Docker apagado. Confirmar que el último
      no se procese al arrancar y que los nuevos sí. Registrar los límites observados.
- [ ] Verificar con al menos dos usuarios y buzones simulados que no hay acceso
      cruzado; no inferir aislamiento multiusuario de una demo con una sola cuenta.
- [ ] Demostrar administrador → empleado conecta Gmail → correo entrante → resultado
      → alerta → analista investiga y resuelve → empleado ve estado → bitácora.
- [ ] Actualizar README, guías y estado de este roadmap con lo realmente terminado.

## Pendiente de definir antes de implementar cada parte

- Recuperación de contraseñas olvidadas y revocación inmediata de sesiones.
  La contraseña inicial la establece ADMIN y el usuario puede cambiarla con la actual.
- Cifrado y custodia de credenciales IMAP, y mecanismo concreto de receptores por
  usuario sin darles acceso al editor de n8n.
- Canal de avisos a empleados y seguridad y reglas para evitar duplicados.
- Tratamiento de correos sin análisis, análisis fallidos y riesgo medio en la UI.
- Cómo presentar y migrar el buzón y los mensajes actuales al empleado propietario.
- Política exacta de acceso de n8n a datos sensibles y del historial de ejecuciones.

No cambiar umbrales ni ejecutar evaluaciones masivas con proveedores externos sin
acordar el alcance y consumo. El usuario prefiere usar pocos ejemplos reales para
proteger su cuota de Groq.
