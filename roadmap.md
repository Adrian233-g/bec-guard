# Roadmap: BEC Guard por organización y buzones personales

Última actualización: 2026-11-11.

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
- La política actual crea alertas con score >=50. MEDIUM 50–69 genera alerta;
  MEDIUM 40–49 no. La UI explica el umbral y que el
  correo queda para revisión manual; falta validar la regla con más datos.
- Se mantiene la preferencia de **no procesar correos que llegaron mientras el
  workflow estaba apagado**: al iniciar cada receptor se toma un punto de partida
  propio del buzón. Una desconexión IMAP temporal mientras el workflow permanece
  activo puede recuperar correos; ese comportamiento debe documentarse y probarse.
- La información enviada al proveedor de IA incluye contenido de correos. Las
  contraseñas de aplicación deben guardarse cifradas, no volver a mostrarse ni
  aparecer en logs, respuestas, bitácora o ejecuciones de n8n. Los correos en el
  historial de n8n son sensibles: revisar su acceso y tratamiento para no saltarse
  la privacidad entre empleados.
- Los avisos al empleado y al equipo de seguridad son **solo in-app**: una campana
  dentro de BEC Guard con contador de no leídos y enlace al caso. No se envían
  correos externos ni se integra otro canal. Cada aviso se crea una sola vez por
  alerta y destinatario; no hay asignación automática del caso.

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

## Estado local tras la limpieza y actualización

- El usuario decidió empezar sin los correos de prueba. Se eliminaron los 16
  correos existentes y sus 5 análisis; no había alertas. Se conservaron los
  dos usuarios, ejecutivos, proveedores y la bitácora, así como el historial de
  ejecuciones de n8n.
- La base local se migró hasta `0014_llm_rate_limited_error_code` sin correos
  históricos. Hay dos usuarios activos, la tabla de avisos in-app y el código de
  error de límite del proveedor.
- El workflow IMAP anterior se despublicó para evitar receptores duplicados.
  Los servicios actualizados están sanos; se comprobó el acceso de lectura desde
  el backend a la API de n8n con la llave configurada. El empleado ya conectó
  su Gmail: buzón y receptor aparecen activos, sin reconciliación pendiente.
  Aún no hay correos ni análisis nuevos; falta probar el recorrido completo real.
- Los avisos in-app están implementados y probados con servicios simulados; backend
  y frontend locales reconstruidos, con la campana disponible en la aplicación.

## Estado real al comenzar

- [x] Aplicación React, API FastAPI, PostgreSQL y n8n; autenticación y RBAC básicos.
- [x] Código y migración para ADMIN, ANALYST y EMPLOYEE; cada cuenta tiene un rol.
      Los roles MANAGER y AUDITOR se preservan en eventos históricos de auditoría.
      La migración se validó en PostgreSQL aislado y se aplicó a la instancia local
      el 2026-10-31; otras instalaciones deben aplicar la revisión 0009.
- [x] Contactos ejecutivos/proveedores, ingestión, análisis híbrido con LangChain,
      alertas >=50 para COMPLETED/FALLBACK, cola y revisión humana; bitácora y
      reportes operativos.
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
      código y contenedores locales actualizados.
- [x] Permisos por dueño de buzón y aislamiento multiusuario implementados;
      las revisiones 0010 y 0011 ya se aplicaron a la base local.
- [x] Asociación explícita usuario → buzón → correo con unicidad (mailbox_id, message_id).
- [x] Conexión individual de Gmail desde la aplicación y múltiples receptores
      implementada en código; falta validar el ciclo completo con n8n y Gmail reales.
- [x] Notificaciones in-app a empleados y equipo de seguridad: campana con avisos
      al dueño del buzón y a ADMIN/ANALYST activos, sin envío de correo externo.
      Revisión 0013 aplicada a la base local.
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
- [x] Completar la matriz de permisos por propietario y verificarla en la etapa 2.

**Terminado cuando:** el administrador puede crear un analista y un empleado sin
usar SQL manual, y los permisos de cada rol se verifican en el servidor.

### 2. Buzones, propiedad y acceso por caso

- [x] Diseñar y migrar la entidad de buzón: propietario, dirección, estado de
      conexión y vínculo con correo/alerta (revisión 0010_mailboxes_and_ownership).
      Garantiza un buzón por usuario en esta entrega con modelo extensible.
- [x] Definir y aplicar permisos en listas, detalles, filtros, dashboard, reportes,
      bitácora y APIs: dueño para correos propios; acceso de ADMIN/ANALYST solo al
      correo concreto asociado a una alerta. No permitir acceso indirecto por UUID.
- [x] Actualizar el modelo de idempotencia: Message-ID único por buzón
      (uq_emails_mailbox_message_id). Cada dueño tiene acceso a su propia recepción
      sin filtraciones ni colisiones.
- [x] Restringir la automatización actual a un único buzón configurado en el servidor.
      Las credenciales independientes para varios conectores están implementadas en código.
- [x] Diseñar una migración que exige confirmar explícitamente el dueño y dirección
      de los correos anteriores, sin inventarlos. La base local se limpió y migró
      sin correos anteriores; otras instalaciones deben confirmar su propiedad.
- [x] Probar al menos dos empleados con buzones distintos, el mismo Message-ID en
      ambos y acceso cruzado denegado; verificar la excepción para alertas reales.

**Terminado cuando:** ningún usuario puede leer el correo normal de otro por API o
interfaz, y el equipo de análisis puede abrir el correo vinculado a una alerta.

El registro de una dirección queda pendiente y no equivale a una conexión verificada.
La migración y el conector existente requieren configuración explícita: ver
[seguridad de buzones](docs/mailbox-security.md).

### 3. Conectar Gmail desde BEC Guard

- [x] Añadir pantalla para ingresar Gmail y contraseña de aplicación; verificar,
      conectar y desconectar. La pantalla también muestra cuando una conexión
      quedó pendiente de revisión y evita ofrecer un reintento inválido. Falta
      validar con n8n y Gmail reales, además de actualizar credenciales revocadas
      y recuperar operaciones interrumpidas.
- [x] Definir almacenamiento cifrado y gestión de claves/secretos; el código usa
      credenciales cifradas de n8n y no guarda la contraseña en BEC Guard. Falta
      comprobar el ciclo real y el respaldo de claves y credenciales.
- [x] Crear, activar y detener receptores IMAP por buzón sin acceso del empleado
      a n8n. El código usa credenciales separadas y checkpoints; falta validar
      contra n8n real y automatizar la reconciliación de fallos.
- [x] Garantizar en el código el punto de partida independiente por buzón y la
      regla de omitir correos recibidos mientras el workflow estaba apagado. Falta
      probar los receptores reales y sus reinicios de extremo a extremo.
- [ ] Gestionar credenciales inválidas o revocadas y errores de conexión sin marcar
      correos como seguros. Evitar reintentos que consuman cuota sin necesidad.
- [ ] Revisar el historial de ejecuciones de n8n y permisos al editor: conservar
      evidencia útil para la demo sin exponer buzones o contraseñas a otros empleados.
- [ ] Integrar el Gmail ya configurado con su empleado propietario sin publicar
      credenciales ni perder los datos existentes.

**Terminado cuando:** cada usuario puede conectar su Gmail desde BEC Guard y los
mensajes nuevos se guardan bajo el dueño correcto, con separación verificada.

### 4. Alertas, escalamiento y comunicación

Trabajar cada minitarea por separado, con pruebas simuladas y commit al terminar.
La cuota restante de Codex no está disponible para el agente: el usuario puede
consultarla con `/status` y avisar cuando quiera detenerse, por ejemplo al bajar
al 5 %. No iniciar una minitarea nueva después del aviso; dejar el avance claro.

- [x] **4.1. Cola por rol:** mostrar el dueño del buzón a ADMIN/ANALYST y evitar
      filtros confusos para EMPLOYEE, que ya ve solo sus propias alertas.
      Implementado y verificado en la interfaz; requiere actualizar frontend
      para verlo en los contenedores locales.
- [x] **4.2. Detalle para investigación:** mostrar claramente el empleado y el
      buzón en el caso, y comprobar el acceso al correo asociado por rol.
      Validado con datos simulados; actualizar frontend para verlo localmente.
- [x] **4.3. Revisión humana:** comprobar tomar, liberar y cerrar casos, estados,
      permisos y bitácora; corregir los problemas concretos que aparezcan.
      La repetición de una resolución cerrada también exige ser el analista
      asignado o ADMIN; validado con pruebas simuladas y PostgreSQL aislado.
- [x] **4.4. Avisos in-app:** campana con contador de no leídos para el empleado
      dueño y el equipo de seguridad (ADMIN/ANALYST activos), enlace al caso y
      acciones de marcar uno o todos como leídos. Sin canal externo ni duplicados
      por alerta/destinatario. Guardado en `notifications` (revisión 0013) y
      probado con API y frontend simulados. Sin backfill para alertas anteriores.
- [x] **4.5. Riesgo medio y errores:** la UI muestra que MEDIUM 40–49 no genera
      alerta automática, MEDIUM 50–69 sí genera alerta y el umbral operativo es >=50.
      Se añadió `LLM_RATE_LIMITED` (HTTP 429) con detección por metadatos del
      proveedor y mensajes accionables; los reintentos siguen siendo manuales.
      Revisión 0014 aplicada.
- [x] **4.6. Verificación integrada:** `tests/test_integrated_flow.py` recorre con
      automatización y analizador simulados el correo de un empleado, la creación
      de alerta y avisos, la cola del analista, claim/resolve y la bitácora.
      Incluye aislamiento entre empleados y un caso MEDIUM sin alerta ni aviso.

**Terminado cuando:** una alerta llega a la cola correcta, el empleado recibe el
aviso definido y un analista puede investigar y cerrar el caso con trazabilidad.
La prueba real con Gmail y Groq continúa en la etapa 5.

### Revisión del puntaje tras los correos de prueba

- [x] Corregir casos objetivos de negación, urgencia y evasión de controles en
      las reglas (`det-v2`), con ejemplos contrapuestos y pruebas sin proveedor.
      Umbral >=70 y combinación híbrida sin cambios; los análisis anteriores no
      se recalculan automáticamente.
- [ ] Diseñar y validar una política de escalamiento más sensible para la
      combinación de cambio bancario y evasión de aprobación, comparando falsos
      positivos y negativos sin ajustar al holdout histórico. El primer correo
      de prueba pasaría de 40 a 52 puntos en reglas, pero con la puntuación de IA
      anterior daría 46/100: aún no produciría alerta. Una nueva llamada real
      podría devolver otro puntaje y requiere autorización.
- [ ] Revisar si presentar las señales deterministas con pesos al modelo ancla
      su respuesta; diseñar un experimento antes de afirmar causalidad o cambiar
      el prompt. La combinación también es asimétrica: reglas=0 e IA=100
      producen 50 y no generan alerta. No existe aún una evaluación híbrida real
      representativa para decidir un cambio de política.

### 5. Verificación y demostración

- [x] Cubrir permisos, acceso directo entre usuarios, escalamiento, duplicados entre
      buzones, errores IMAP/IA y migraciones con pruebas locales, fakes y PostgreSQL
      aislado. No gastar llamadas a proveedores para pruebas que pueden simularse.
- [ ] Probar un buzón real con pocos mensajes y cuota controlada: correo legítimo,
      correo sospechoso y correo enviado con Docker apagado. Confirmar que el último
      no se procese al arrancar y que los nuevos sí. Registrar los límites observados.
- [x] Verificar con al menos dos usuarios y buzones simulados que no hay acceso
      cruzado; no inferir aislamiento multiusuario de una demo con una sola cuenta.
- [ ] Demostrar administrador → empleado conecta Gmail → correo entrante → resultado
      → alerta → analista investiga y resuelve → empleado ve estado → bitácora.
- [x] Actualizar README, guías y estado de este roadmap con lo realmente terminado.

## Pendiente de definir antes de implementar cada parte

- Recuperación de contraseñas olvidadas y revocación inmediata de sesiones.
  La contraseña inicial la establece ADMIN y el usuario puede cambiarla con la actual.
- Cifrado y custodia de credenciales IMAP, y mecanismo concreto de receptores por
  usuario sin darles acceso al editor de n8n.
- Tratamiento de correos sin análisis y criterios para revisar manualmente los
  casos MEDIUM que no generan alerta.
- Cómo presentar y migrar el buzón y los mensajes actuales al empleado propietario.
- Política exacta de acceso de n8n a datos sensibles y del historial de ejecuciones.

No cambiar umbrales ni ejecutar evaluaciones masivas con proveedores externos sin
acordar el alcance y consumo. El usuario prefiere usar pocos ejemplos reales para
proteger su cuota de Groq.

### Simulación de pesos y umbral

- [x] Comparar sin proveedor 50/50 >=70, solo umbral 50, solo pesos 30/70 y
      ambos cambios, con puntuaciones semánticas hipotéticas; conservar piso de
      reglas fuertes y no evaluar holdout. Ver [evaluación](docs/evaluation.md).
- [ ] Preparar casos nuevos etiquetados independientemente y evaluar resultados
      semánticos reales con consumo autorizado antes de decidir la política.
- [x] Implementar respaldo FALLBACK por reglas ante fallo de IA, con señales,
      código sanitizado y alerta desde 70; no reintenta el proveedor al repetir POST.

### Umbral de alerta

- [x] Activar alerta desde 50 por decisión del usuario, mantener pesos 50/50 y
      niveles de riesgo; adaptar interfaz y enrutamiento de n8n.

### Novedades en la sesión

- [x] Mostrar avisos emergentes de correos propios y alertas autorizadas sin
      recargar; actualizar vistas y campana durante la sesión. Consulta local cada
      10 segundos, sin llamadas a IA; el primer resultado no reproduce historial.
- [x] Evitar que un analista que pierde el rol siga viendo avisos de alertas de
      buzones ajenos. Las alertas permanecen visibles hasta cerrarlas o abrirlas;
      los avisos de correo se cierran después de ocho segundos.

### Organización y suplantación

- [x] Registrar un contexto ficticio BEC Guard con ejecutivos, proveedores,
      funciones y categorías de solicitud configurables y auditadas.
- [x] Escalar identidad discrepante con solicitud: mínimo 50 para una solicitud
      reconocida y 70 para pago, cambio bancario o datos sensibles. Señalar
      categorías fuera del ámbito configurado sin asumir permisos cuando falta.
- [ ] Evaluar con más casos reales o simulados y contexto actualizado: las reglas
      son heurísticas, no verifican la autenticidad del remitente por sí solas.
