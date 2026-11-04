# Orquestación BEC Guard — n8n 2.44.4

`workflows/bec-analysis-webhook.json` permite dos entradas: un webhook con
EmailIngestRequest normalizado y un Email Trigger (IMAP) desactivado inicialmente. Ambas
comparten ingestión idempotente, análisis FastAPI y enrutamiento ALERT / NO_ALERT /
ERROR. Solo el webhook recibe respuesta HTTP. No hay SMTP ni notificaciones.

## Configurar e importar

En `.env` local ignorado, configurar AUTOMATION_API_KEY aleatoria de al menos
32 caracteres (la misma para backend y n8n). No escribirla en el workflow.
Configurar también `AUTOMATION_MAILBOX_ID` en el backend para vincular la clave
a un único buzón activo; ver [propiedad y migración](../docs/mailbox-security.md).
`BEC_GUARD_BACKEND_URL` tiene default `http://backend:8000`, accesible dentro de
la red Compose; nunca usar localhost para conectar esos contenedores.

```bash
docker compose up --build -d --wait backend n8n
docker compose exec backend alembic upgrade head # Solo en bases nuevas sin correos
docker compose exec -T n8n node /opt/bec-guard-n8n/import-workflow.mjs --publish
docker compose restart n8n
docker compose up -d --wait n8n
```

Para importar sin publicar, omitir `--publish`. La importación usa el propietario/
proyecto personal que n8n asigna por defecto; no crea usuarios ni service accounts.
Los comandos CLI operan sobre la instancia local y sus datos, no sobre Git.

El JSON canónico está inactive, sin pinData ni secretos. Usa IDs lógicos estables
para que repetir el import actualice el mismo workflow/credencial. El importador
lee key y URL del entorno del contenedor, crea una credencial Generic Header Auth
`BEC Guard automation` (`X-BEC-Automation-Key`) y la importa mediante el CLI oficial.
n8n conserva el valor cifrado con la clave de su volumen. El archivo temporal de
credencial tiene permisos 0600 y se elimina al finalizar; nunca se exporta al repo.
La credencial se usa tanto en el Webhook como en los dos HTTP Request.

En esta versión instalada, `$env` está bloqueado si
N8N_BLOCK_ENV_ACCESS_IN_NODE no es exactamente `false`, confirmado en
`n8n-workflow/dist/cjs/workflow-data-proxy-env-provider.js`. No se relaja ese control.
El importador coloca la URL no secreta en el nodo Configuration; los HTTP Request
la referencian. Cambiar URL/key requiere reiniciar con el entorno actualizado y
reimportar. No se entrega el entorno a los nodos ni se usa una expresión con key.

También se puede importar el JSON desde el editor: crear/seleccionar la credencial
Header Auth anterior y reemplazar `SET_BACKEND_URL_ON_IMPORT` en Configuration por
la URL de backend. Publicar desde el editor. El CLI `publish:workflow` requiere
reiniciar n8n para registrar el webhook en el proceso que ya estaba ejecutándose.
Conservar `n8n_data`: contiene la clave de cifrado y credenciales.

## Invocar

Webhook publicado: `POST http://localhost:5678/webhook/bec-guard/analyze`.
Exige el mismo header de automatización. Ejemplo sin secretos reales:

```bash
curl -X POST http://localhost:5678/webhook/bec-guard/analyze \
  -H 'Content-Type: application/json' \
  -H 'X-BEC-Automation-Key: <LOCAL_AUTOMATION_KEY>' \
  --data '{"message_id":"<n8n-example@fixtures.becguard.example>","sender_email":"persona@organizacion.example","subject":"Revisión de expediente","body_text":"Revisar por el canal habitual.","received_at":"2026-10-21T05:00:00Z"}'
```

Sustituir el placeholder sin guardar la key real en shell history; para uso local
puede construirse la petición mediante un script que lea `.env` sin imprimirla.
El JSON debe cumplir el contrato de ingestión; no se acepta MIME ni metadata de
dataset. El endpoint del editor `/webhook-test/` solo sirve mientras está escuchando.

## Respuestas y reintentos

ALERT exige COMPLETED o FALLBACK, score >=50 y alert_id; NO_ALERT exige COMPLETED o FALLBACK,
score <50 y alert_id null. ERROR se evalúa primero; también es el fallback para
errores de transporte, respuestas inesperadas o inconsistentes. Nunca se enruta
un fallo a NO_ALERT. Las respuestas exitosas incluyen IDs, status, score, nivel,
tipo, summary y recommended_action. No incluyen body, sender, subject, secretos,
prompt, AuditLog ni raw provider output.

Los HTTP Request capturan status/body de respuestas no 2xx, sin retry automático.
ERROR semántico conserva error_code e IDs cuando existen. Fallos de ingestión o
infraestructura usan BACKEND_INGEST_ERROR / BACKEND_ANALYSIS_ERROR sanitizados.
El webhook responde 200 para ALERT/NO_ALERT; ERROR usa 503 para LLM_NOT_CONFIGURED
y 502 para otros errores del pipeline. No sustituye la autenticación HTTP del
Webhook: un header ausente/incorrecto recibe 401 de n8n antes de ejecutar.

Repetir el Message-ID exacto recupera el Email sin sobrescribirlo ni otra auditoría
EMAIL_INGESTED. COMPLETED y FALLBACK se reutilizan; ERROR histórico permite retry explícito sobre el mismo
análisis. La creación de BECAlert y su política >=50 pertenecen a FastAPI.

## Historial de ejecuciones

n8n guarda las ejecuciones exitosas, fallidas y manuales para que se puedan revisar
los pasos del workflow. El historial puede incluir remitentes, asunto y contenido del
correo, además de respuestas del backend. Solo debe acceder a n8n quien esté
autorizado para verlos. Los datos de cada paso no se guardan progresivamente durante la ejecución.

Compose desactiva la limpieza automática del historial; las ejecuciones permanecen
hasta que se eliminen manualmente o se borre el almacenamiento. El historial anterior a este
cambio, que se descartó con la configuración previa, no se puede recuperar. La
base de datos de BEC Guard sigue conservando correos, análisis y bitácora según sus
propias políticas. En el editor evita fijar datos sensibles con pinning o exportar
ejecuciones que los contengan.

Referencias: [configuración de ejecuciones](https://docs.n8n.io/hosting/configuration/environment-variables/executions/),
[CLI import/publish](https://docs.n8n.io/hosting/cli-commands/).

## Alcance

Compose sigue siendo local, con puertos en loopback. El Webhook permite demostrar
orquestación sin una cuenta de correo externa. La entrada IMAP descrita abajo requiere credencial y activación; Graph y
notificaciones siguen pendientes. El frontend y la revisión humana ya existen.
ALERT/NO_ALERT se prueban con fakes backend; la validación local sin LLM usa ERROR LLM_NOT_CONFIGURED sin gastar tokens.

## Gmail por IMAP: recepción de correos

El mismo [`bec-analysis-webhook.json`](workflows/bec-analysis-webhook.json) incluye
un **Email Trigger (IMAP)** desactivado por defecto. Usa una conexión IMAP a la
bandeja INBOX y envía el correo al flujo de análisis existente. No modifica el
estado leído del mensaje. El código versionado no contiene credenciales.

### Conectar la cuenta

1. Mantén `AUTOMATION_API_KEY` y el proveedor, modelo y clave de IA configurados
   en el backend. Configura Groq en `.env` y recrea el backend para aplicar cambios.
2. Activa la verificación en dos pasos de tu cuenta de Google y crea una
   [contraseña de aplicación](https://myaccount.google.com/apppasswords). Algunas
   cuentas de universidad o trabajo no permiten esta opción. No compartas la clave.
3. En n8n, abre el workflow existente y el nodo **Email Trigger (IMAP)**. Crea una
   credencial IMAP con usuario igual a tu Gmail, la contraseña de aplicación,
   host `imap.gmail.com`, puerto `993` y SSL/TLS habilitado. Guarda la credencial.
4. Habilita el nodo IMAP, guarda y publica el workflow. Envía un correo de prueba
   desde otra cuenta y consulta **Correos** y **Alertas** en la aplicación.
   Registra tus ejecutivos y proveedores antes de probar la detección contextual.

Al arrancar el workflow, el receptor toma el UID siguiente de la bandeja como
punto de partida. Los correos que ya estaban en Gmail mientras el workflow estaba apagado se
omiten; solo se analizan los que llegan a partir de esa conexión. Esta política
también se aplica al reiniciar o volver a publicar el workflow. Una desconexión
IMAP temporal mientras el workflow sigue activo puede recuperar mensajes pendientes.
La conexión debe
poder obtener UIDNEXT del servidor IMAP; si no está disponible, falla sin procesar
la cola. Los mensajes no se marcan como leídos.

La imagen local deriva de n8n 2.44.4 y aplica un ajuste al nodo IMAP exclusivamente
para este workflow. La construcción falla si cambia la implementación compatible;
al actualizar n8n hay que revisar el ajuste. Si falla la normalización o ingestión,
el correo permanece en Gmail, pero no se registra en BEC Guard. Un análisis que
falla queda en ERROR y puede reintentarse desde su detalle en la aplicación.

Se guarda Message-ID para evitar duplicados; los correos sin Message-ID se rechazan
para no confundir mensajes de cuentas distintas. El nodo no reconstruye el hilo.
La fecha usada es la cabecera Date del mensaje; si falta o es inválida, se usa la
hora de procesamiento, no necesariamente la fecha real de recepción. El formato
Resolved de n8n descarga los adjuntos temporalmente como datos binarios para
interpretar el correo; la normalización no los envía al backend ni los analiza.
Las ejecuciones terminadas conservan sus datos sin borrado automático. Cada correo enviado al análisis comparte su texto con el
proveedor de IA elegido. No se envían avisos por correo automáticamente.

## Receptores por empleado desde la aplicación

1. Revisa la [migración y propiedad de buzones](../docs/mailbox-security.md)
   antes de actualizar si ya tienes correos existentes.
2. En la cuenta administradora de n8n crea una API key en Settings → n8n API.
   Guárdala como `N8N_API_KEY` en `.env`; no la compartas ni la subas a Git.
   Debe permitir crear, probar y eliminar credenciales y crear, publicar,
   despublicar y eliminar workflows. Mantén también `AUTOMATION_API_KEY`.
3. Reconstruye backend y n8n, aplica las migraciones según la guía y entra como
   empleado en «Mi cuenta». Registra su Gmail y usa su contraseña de aplicación
   para conectar. La app crea una credencial IMAP cifrada y un receptor propio.
4. Si ya usas el trigger manual anterior para ese mismo Gmail, no mantengas ambos
   receptores activos: coordina su migración al empleado y desactiva el anterior.

El backend registra los pasos y bloquea conexiones con resultados inciertos. Si
la app informa que se requiere revisión, un administrador debe comprobar los
recursos de n8n y el registro `mailbox_connections` antes de reintentar; no borrar
recursos a ciegas. Los receptores generados usan el mismo análisis que el workflow
canónico y tienen una clave de automatización limitada a su propio buzón.

Estas rutas tienen pruebas automatizadas con una API n8n simulada; todavía falta
una prueba de extremo a extremo con Gmail y n8n reales, incluida la regla de los
correos recibidos con Docker apagado. La API key y las contraseñas no deben
aparecer en el historial del workflow, pero los propios correos sí pueden quedar
en las ejecuciones y deben protegerse de otros usuarios.

### Actualizar receptores ya existentes

El JSON versionado se usa para crear nuevos receptores; no modifica los workflows
ya importados. En cada workflow existente se deben actualizar las condiciones
ALERT y NO_ALERT del nodo **Route result** con las expresiones del JSON canónico
y publicar el workflow. Las expresiones admiten COMPLETED y FALLBACK y comprueban
el puntaje frente a 50 junto con la presencia o ausencia de alert_id. No se deben
alterar las credenciales ni los demás nodos. Hasta actualizarlo, el backend puede
crear una alerta con score 50–69, pero el workflow antiguo la enrutará como ERROR.
