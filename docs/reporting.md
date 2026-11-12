# Reportes operativos

> **Transición de roles:** las referencias históricas a MANAGER/AUDITOR y permisos
> anteriores se sustituyen por los [roles vigentes](roles.md).

Los reportes pertenecen al producto y consultan únicamente datos persistidos en
PostgreSQL. No importan el dataset, no leen ground truth y no llaman al evaluador
académico. La evaluación de holdout tiene metodología y resultados separados en
[evaluation.md](evaluation.md).

## API y permisos

| Ruta | Permiso | Descarga |
| --- | --- | --- |
| `GET /api/reports/operational.pdf` | ADMIN, ANALYST | `application/pdf` |
| `GET /api/reports/operational.xlsx` | ADMIN, ANALYST | XLSX Open XML |

EMPLOYEE recibe 403. Ambas rutas requieren el JWT humano actual; la automation key
no concede acceso. `from_date` y `to_date` son filtros opcionales `YYYY-MM-DD`,
interpretados como días UTC inclusivos. Fechas invertidas responden 400. Se usa
`ingested_at` para correos, `analyzed_at` para análisis y `created_at` para alertas.
Sin fechas, se consideran todos los datos.

Los agregados incluyen total de emails, análisis completos, fallback y errores,
distribución de riesgo, tipo BEC, alertas por estado y veredictos. Las tablas de
distribución incluyen cantidad, denominador y porcentaje. El denominador de riesgo
es el de análisis con riesgo asignado; el de tipo BEC es el de análisis con tipo
identificado; el de veredictos es únicamente el de alertas con decisión humana.
La lista de alertas contiene ID, fecha de creación, score, risk level, tipo, modo de
análisis, estado, veredicto y nombre de la persona asignada. Los estados y veredictos
de alertas son sus valores actuales; no se conserva una historia temporal para
reconstruirlos como estaban al cierre de un periodo.

Las respuestas usan `Content-Disposition: attachment` con nombre estable
`bec-guard-operational-YYYYMMDD.pdf` o `.xlsx`, añaden `Cache-Control: no-store` y
`X-Content-Type-Options: nosniff`. Los archivos se generan como bytes en memoria y
no se guardan en disco ni en una tabla.

## Contenido y privacidad

El PDF presenta cabecera, periodo, fecha UTC de generación, resumen, distribuciones,
denominadores, interpretaciones, tabla de alertas y la nota: “Los scores representan
una evaluación del sistema y no probabilidades de fraude.” El XLSX contiene las
hojas `Resumen`, `Distribución de riesgo`, `Tipos BEC`, `Estados de alerta`,
`Veredictos humanos` y `Alertas`; fechas y números conservan sus tipos de celda. No
hay macros.

Los formatos nunca consultan ni incluyen cuerpo, subject, remitente, destinatarios,
headers de autenticación, reply-to, return-path, referencia bancaria, prompts,
respuesta cruda del proveedor, AuditLog, contraseñas, JWT, API keys o etiquetas de
evaluación. Los textos de XLSX se guardan como celdas de texto, no fórmulas. HTML del
PDF se escapa y el renderer rechaza la carga de recursos externos.

## Implementación

`operational_summary.py` comparte las consultas de agregación con el dashboard.
`reporting.py` prepara una estructura transitoria y selecciona solamente los campos
de alerta autorizados. `report_formats.py` genera PDF mediante WeasyPrint 70 y XLSX
mediante openpyxl 3.1.5. El backend instala las bibliotecas Pango/HarfBuzz y DejaVu
que WeasyPrint requiere en Linux. No se incorpora un servicio de reporting aparte ni
se persiste un historial de exportaciones.
La imagen usa `XDG_CACHE_HOME=/tmp` para que Fontconfig disponga de una caché
temporal escribible como usuario no root; esa caché no almacena los reportes.
En Windows, WeasyPrint necesita además un runtime GTK nativo. Si no está instalado,
las pruebas que renderizan PDF se marcan como omitidas con una razón explícita; las
pruebas XLSX, RBAC y validación de fechas siguen ejecutándose. La validación completa
del renderer PDF se realiza en la imagen Linux del backend.

La UI `/reports` es visible para ADMIN y ANALYST. El helper de descarga
envía `Authorization: Bearer` desde `sessionStorage`, lee el blob y usa una URL
temporal que revoca después de descargar. Un 401 limpia la sesión; un 403 muestra
permisos insuficientes y mantiene la sesión. Las fechas inválidas se detectan antes
de pedir el archivo y también se validan en backend.

Las pruebas cubren autorización, fechas, límites UTC, base vacía, agregados,
denominadores, modo de análisis, Content-Type/Disposition, archivo PDF y workbook
XLSX, valores y hojas, protección contra fórmulas y ausencia de datos privados. Las
descargas frontend prueban header de autorización, permisos, errores y revocación
de URL.

## Límites

Los reportes reflejan el estado actual de las alertas y se calculan sin caché. Las
consultas no representan un snapshot histórico de cambios de estado y no ofrecen
comparaciones, filtros por usuario, reportes configurables ni envío programado.
No calculan sensibilidad, precisión ni calidad poblacional del detector: la cola de
alertas no contiene los correos que nunca generaron alerta ni etiquetas independientes.
Las métricas académicas viven únicamente en los artefactos del evaluador.

### Ejemplo operativo ilustrativo

Los siguientes valores son ficticios y muestran cómo debe interpretarse una salida:

| Riesgo | Cantidad | Denominador | Porcentaje |
| --- | ---: | ---: | ---: |
| Bajo | 48 | 114 | 42.1% |
| Medio | 30 | 114 | 26.3% |
| Alto | 24 | 114 | 21.1% |
| Crítico | 12 | 114 | 10.5% |

Interpretación: durante el periodo hubo 114 análisis con riesgo asignado; esto
describe distribución operativa, no cuántos ataques fueron detectados en la población.
De forma análoga, una tabla de veredictos con `3 CONFIRMED_BEC` y `2 FALSE_POSITIVE`
usa 5 como denominador y deja fuera las alertas aún sin decisión.

## Estructura propuesta para el informe académico

El informe universitario debe consumir los artefactos de `eval-v2`, no un PDF o XLSX
operativo. Cada tabla debe incluir una interpretación breve y su denominador:

| Sección | Contenido | Interpretación requerida |
| --- | --- | --- |
| Proveniencia | versión, commit, hashes, política, umbrales y proveedor | Permite reproducir bajo las mismas condiciones. |
| Corpus | casos por split, etiqueta, tipo BEC y hard negatives | Describe la población evaluada, no la producción completa. |
| Calidad | matriz de confusión, precision, recall, F1, specificity y FPR | Resume el comportamiento sobre etiquetas independientes. |
| Cobertura | `COMPLETED`, `FALLBACK`, errores y latencia | Explica qué parte del corpus recibió cada modo de análisis. |
| Estratificación | hard negatives y tipos BEC | Muestra dónde se concentran aciertos y errores. |

Las figuras recomendadas son ROC, precision-recall, distribución de scores y latencia.
Si una institución exige formato ráster, deben exportarse a 600 DPI desde el artefacto
académico; el producto operativo actual no genera figuras académicas ni exportación
Word.
La respuesta se construye en memoria, por lo que el tamaño práctico depende del
volumen operativo; el MVP no implementa exportaciones asíncronas ni almacenamiento
de archivos.
