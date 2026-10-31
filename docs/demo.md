# Datos de demostración para analizar correos

El seed opcional crea **dos ejecutivos, dos proveedores y doce correos nuevos** de
Oriona Demo. Son ficticios, usan dominios `.example` y referencias bancarias sin
valor real. No lee ni reutiliza development/holdout. No carga análisis, scores,
alertas o veredictos preparados: todos los correos nuevos esperan análisis real.
No llama al LLM ni envía correos.

Con Compose levantado y migraciones aplicadas, desde la raíz:

```bash
docker compose up -d --build --wait backend
docker compose exec backend python -m app.scripts.seed_demo \
  --confirm-demo --actor-email '<EMAIL_DE_TU_ADMIN>'
```

Usa el email de un ADMIN activo existente. El seed no crea usuarios, contraseñas ni
permisos; si no hay ADMIN, utiliza primero el bootstrap interactivo documentado en
[autenticación](authentication.md). La confirmación es obligatoria antes de acceder
a la DB. No se ejecuta automáticamente durante arranque o migraciones.

Los Message-ID estables `bec-guard-demo-v1-*` hacen la carga repetible. Si una
identidad de contexto o Message-ID ya existe, se conserva íntegramente: no se
sobrescriben ediciones, fechas, activación o análisis. Repetir el seed no duplica
eventos de auditoría. Cada creación usa los servicios existentes y su auditoría
atómica con el ADMIN indicado; si la carga se interrumpe puede reanudarse. No hay
reset ni borrado automático. El contexto demo activo participa en el análisis;
usa estos datos en tu entorno local de demostración.

## Recorrido

Configura en `.env` `LLM_PROVIDER=google`, `LLM_MODEL` con el modelo elegido y tu
`GOOGLE_API_KEY`; recrea backend para cargar cambios. Nunca subas `.env` a Git.
El modelo elegido para esta demo local fue
[`gemini-3.5-flash-lite`](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite).
La disponibilidad/cuota de la key se comprueba cuando el usuario solicita análisis,
no mediante el seed.

Entra con tu cuenta y abre **Correos**. Los ejemplos aparecen como `[DEMO 01]`
hasta `[DEMO 12]`. Abre un correo y pulsa **Analizar correo**:
reglas/contexto → Google/LangChain → scoring → análisis persistido. Si el resultado
es HIGH/CRITICAL, el backend crea la alerta correspondiente. ERROR conserva riesgo
null y permite retry; COMPLETED se reutiliza sin otro gasto LLM. Si aparece un 429,
la clave alcanzó su cuota o límite: espera y usa **Reintentar análisis**; no hay
reintentos automáticos. Un riesgo MEDIUM no crea alerta y la interfaz lo indica.

| Correo | Situación ficticia |
| --- | --- |
| DEMO 01 | Planificación desde la dirección oficial. |
| DEMO 02 | Factura con referencia conocida y aprobaciones normales. |
| DEMO 03 | Urgencia operativa sin petición financiera. |
| DEMO 04 | Identidad ejecutiva, dominio parecido y controles omitidos. |
| DEMO 05 | Supuesto ejecutivo desde buzón externo y anticipo. |
| DEMO 06 | Proveedor con dominio parecido y desvío de cobro. |
| DEMO 07 | Cambio bancario desde dominio oficial con verificación eludida. |
| DEMO 08 | Solicitud de nóminas e identidades evitando RRHH. |
| DEMO 09 | Informe agregado sin datos personales. |
| DEMO 10 | Aviso administrativo que conserva controles y cuenta. |
| DEMO 11 | Instrucciones de pago en inglés desde dominio parecido. |
| DEMO 12 | Instrucciones para manipular al modelo dentro de un email. |

Las decisiones las produce el detector vigente; no se garantizan scores o rutas
concretos y estos ejemplos no son un benchmark ni sustituyen una evaluación formal.
Pulsar Analizar/reintentar puede consumir cuota del proveedor. No se ajustan reglas,
prompt ni políticas a partir de estos ejemplos.
