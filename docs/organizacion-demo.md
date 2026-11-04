# Organización ficticia de BEC Guard

Estos contactos son **datos de demostración**, no cuentas de correo creadas ni
identidades verificadas. El dominio `becguard.com` se usa como solicitó el usuario;
los dominios de proveedores `.example` están reservados para ejemplos. El nombre
y dirección deben tratarse como información de referencia, no como autenticación.

| Ejecutivo | Cargo y funciones | Correo de referencia |
| --- | --- | --- |
| Valeria Montes | Dirección general; solicita pagos con aprobación financiera. | valeria.montes@becguard.com |
| Mateo Rivas | Dirección financiera; coordina pagos y cambios bancarios con doble validación. | mateo.rivas@becguard.com |
| Camila Torres | Operaciones; coordina servicios y proveedores. | camila.torres@becguard.com |
| Gabriel Luna | Tecnología; dirige tecnología y seguridad. | gabriel.luna@becguard.com |

| Proveedor | Función | Contacto de referencia |
| --- | --- | --- |
| Andes Nube | Infraestructura de nube y facturación. | facturacion@andes-nube.example |
| Quipu Suministros | Equipos, facturación y cambios bancarios verificables. | cuentas@quipu-suministros.example |
| Llama Digital | Soporte de software, sin pedir contraseñas por correo. | soporte@llama-digital.example |
| Costa Logística | Entregas y seguimiento de envíos. | operaciones@costa-logistica.example |

Los administradores pueden ajustar la descripción y las categorías en la sección
Ejecutivos o Proveedores. Esas categorías solo describen qué solicitudes se
esperan; un pago o cambio bancario sigue requiriendo verificación y aprobación.
El script `python -m app.scripts.seed_becguard_context --actor-email <admin>
--confirm-fictional` crea los registros faltantes, audita las altas y nunca
sobrescribe contactos existentes. No crea usuarios ni cuentas de correo ni consume IA.
