# Propiedad de buzones y migración de correos existentes

Registrar una dirección desde la aplicación crea un buzón `PENDING`. Eso no
comprueba que el usuario controle Gmail ni inicia una conexión. La API no permite
activar el buzón manualmente: la conexión verifica la contraseña de aplicación
y crea un receptor mediante la API de n8n. La recepción se considera habilitada
solo cuando la pantalla confirma la conexión; eventos durante la publicación
pueden rechazarse antes de esa confirmación. Las direcciones pendientes no reservan una
dirección frente a otra persona; solo puede haber un buzón activo por dirección.

El conector n8n existente utiliza una sola clave de automatización y queda limitado
a **un buzón** definido en el backend mediante `AUTOMATION_MAILBOX_ID`. No elige el
dueño a partir de los campos To/Cc ni acepta que el workflow lo especifique. Si la
variable falta, el buzón no está activo o su dueño está desactivado, la API rechaza
la ingestión y el análisis. La API también admite credenciales derivadas limitadas a un buzón concreto,
y el backend aprovisiona un receptor por usuario mediante la API de n8n.
Cada clave derivada se vincula además a una conexión concreta activa; al
desactivarla, sustituirla o marcarla para reconciliación, deja de aceptarse.

## Instalaciones anteriores a 0010 con correos existentes

La migración no adivina el dueño ni usa la dirección de inicio de sesión como si
fuera la de Gmail. Antes de aplicarla, el operador debe confirmar quién es el dueño
de **todos** los correos existentes y qué dirección recibe realmente el workflow.
Si los correos pertenecen a más de un buzón, no usar esta migración para asignarlos
a uno solo: se necesita una migración específica. Respaldar la base primero.

Tras reconstruir el backend, ejecutar con los valores confirmados, sin escribir
contraseñas ni claves en el comando:

```bash
docker compose exec backend alembic -x legacy_owner_id=UUID_DEL_USUARIO -x legacy_mailbox_address=CORREO_GMAIL upgrade head
```

Esto asigna los correos históricos al buzón confirmado, inicialmente en estado
`PENDING`; no habilita su receptor. Para conservar activo el conector IMAP ya
configurado, añadir `-x legacy_connector_confirmed=true` **solo después de comprobar**
que corresponde a ese mismo propietario y dirección. Entonces configurar en `.env`
`AUTOMATION_MAILBOX_ID` con el UUID del buzón creado y recrear el backend para que
reciba el valor. La configuración y comprobación del conector no se han automatizado.
No activar la recepción hasta completar la migración y verificar la vinculación.

## Instalaciones ya migradas a 0010

La versión anterior pudo asignar automáticamente todos los correos al primer
empleado y permitir registros de direcciones sin verificar. Revisar y corregir
manualmente las asociaciones antes de aceptar su propiedad. Después de confirmar
cada asociación, usar `alembic -x confirm_existing_ownership=true upgrade head`.
La revisión 0011 pone los buzones previamente activos en `PENDING`; para conservar
un único conector, aportar además los tres parámetros explícitos de propietario,
dirección y `legacy_connector_confirmed=true` indicados arriba. Si los correos no
pertenecen todos a ese buzón, esta vía de conector único se rechaza.

La desconexión de una cuenta administrada por la app bloquea primero su acceso al
backend, luego despublica y elimina sus recursos de n8n. El conector anterior
configurado manualmente debe detenerse desde n8n. Las ejecuciones de n8n pueden
contener correos y requieren control de acceso independiente.

## Verificación previa de Gmail

`POST /api/mailboxes/{id}/verify-gmail` recibe `{"app_password": "..."}`
únicamente para un buzón del usuario autenticado. Conecta mediante TLS a
`imap.gmail.com`, comprueba el acceso a INBOX en modo de solo lectura y cierra
la conexión sin leer mensajes. Devuelve `{"verified": true}` si logra entrar,
`400` si Google rechaza la contraseña y `503` si la conexión no está disponible.
No guarda ni devuelve la contraseña y no cambia el estado del buzón; verificar
una vez no demuestra que seguirá siendo válida y no crea un receptor. El alta
final deberá verificarla otra vez al crear la credencial de n8n.

## Conexión por usuario y recuperación

El backend usa `N8N_API_KEY` para crear credenciales y publicar un workflow por
buzón. El empleado introduce la contraseña de aplicación en «Mi cuenta»; el
backend la verifica y la envía a n8n para guardarla cifrada. No la guarda en la
base de BEC Guard, en el JSON del workflow ni en la bitácora. El backend también
crea una credencial de automatización distinta para cada conexión.

La revisión `0012_mailbox_connection_progress` guarda los IDs de recursos y la
última etapa confirmada sin almacenar contraseñas ni tokens. Una interrupción
puede dejar recursos remotos y marca la conexión para revisión; no se reintenta
automáticamente. Por ahora la recuperación de una operación interrumpida requiere
revisión manual por el administrador de n8n. La contraseña revocada o fallos
posteriores del receptor aún no se detectan automáticamente.

La aplicación y la API de n8n deben operar en una red confiable: la configuración
local usa HTTP dentro de Docker. La clave de la API n8n es administrativa y solo
debe estar disponible en el backend. El conector multiusuario se ha probado con
simulaciones; falta verificar el ciclo completo con Gmail y n8n reales.
