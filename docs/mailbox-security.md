# Propiedad de buzones y migración de correos existentes

Registrar una dirección desde la aplicación crea un buzón `PENDING`. Eso no
comprueba que el usuario controle Gmail ni inicia una conexión. La API no permite
activar el buzón manualmente: la verificación real y la gestión de contraseñas de
aplicación pertenecen a la etapa 3. Las direcciones pendientes no reservan una
dirección frente a otra persona; solo puede haber un buzón activo por dirección.

El conector n8n existente utiliza una sola clave de automatización y queda limitado
a **un buzón** definido en el backend mediante `AUTOMATION_MAILBOX_ID`. No elige el
dueño a partir de los campos To/Cc ni acepta que el workflow lo especifique. Si la
variable falta, el buzón no está activo o su dueño está desactivado, la API rechaza
la ingestión y el análisis. La API también admite credenciales derivadas limitadas a un buzón concreto,
pero aún falta aprovisionarlas y administrar sus receptores desde la aplicación.

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

Desconectar un buzón en la API impide que el backend procese nuevas entradas para
él, pero todavía no detiene por sí mismo el trigger IMAP de n8n. Las ejecuciones de
n8n pueden contener correos y requieren control de acceso independiente.
