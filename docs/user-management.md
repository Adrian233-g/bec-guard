# Gestión de usuarios

ADMIN puede crear y consultar usuarios, asignarles un rol y activar/desactivar sus
cuentas desde `/users`. No existe registro público ni eliminación de usuarios.

Al crear una cuenta, el administrador introduce una **contraseña inicial de BEC
Guard** (12 a 128 caracteres) y debe entregarla por un medio privado. No es la
contraseña de Gmail. La aplicación no envía invitaciones ni muestra de nuevo esa
contraseña. El usuario puede cambiarla desde **Mi cuenta**, con su contraseña actual;
la cuenta debe permanecer activa. No hay recuperación de contraseñas olvidadas ni
cambio obligatorio en el primer acceso. El administrador debe pedir al usuario que
cambie la contraseña inicial al recibirla.

Las contraseñas se almacenan con Argon2id. Al cambiarla, las sesiones existentes
no se revocan inmediatamente: los access tokens caducan según la configuración
(30 minutos por defecto). Los cambios de rol o de estado se consultan en cada
petición. El administrador no puede desactivar ni quitarse su propio rol; otro
administrador activo puede cambiarlo. Las modificaciones se serializan y se
vuelve a validar al administrador antes de guardar.

## Contratos API

El esquema OpenAPI se publica en `/docs`. Todas las rutas exigen Bearer JWT:

| Método y ruta | Permiso | Comportamiento |
| --- | --- | --- |
| `GET /api/users?limit=25&offset=0` | ADMIN | Lista paginada, sin hashes ni contraseñas; límite máximo 100. |
| `POST /api/users` | ADMIN | Crea usuario con `name`, `email`, `role` y `password`; devuelve 201 y datos públicos. Correo duplicado: 409. |
| `PATCH /api/users/{id}` | ADMIN | Modifica `role` y/o `is_active`. No admite null; usuario inexistente: 404; auto-desactivación o auto-reducción de rol: 409. |
| `POST /api/auth/change-password` | Usuario activo | Recibe `current_password` y `new_password`; devuelve 204. Requiere contraseña actual correcta y una nueva diferente. |

Las respuestas de validación no reflejan los valores recibidos. La bitácora registra
`USER_CREATED`, `USER_UPDATED` y `USER_PASSWORD_CHANGED` con actor y usuario
objetivo; no guarda contraseñas, hashes ni valores de los campos cambiados. Cada
cambio y su auditoría comparten transacción: un fallo de persistencia revierte ambos.

El rol EMPLOYEE sigue sin acceso a correos compartidos hasta implementar propiedad
por buzón, como se explica en [roles](roles.md) y [roadmap](../roadmap.md).
