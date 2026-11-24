# Fase 1 — Protocolo predeclarado (sin resultados nuevos)

Versión de diseño `research-v1`, 2026-11-18; base `51cdebf87939a7877c3a44b2a4b8cd1d6c09d648`. Este documento **define un experimento futuro** y no acredita rendimiento. El punto de partida verificado está en `DIAGNOSTICO_FASE_0.md`. Se conservarán `det-v3 / semantic-v2 / hybrid-v2 / alert-v2`, detección >=40 y alerta operativa >=50; solo simulación externa podrá comparar otros umbrales. No se usarán como entrenamiento/test nuevo los 98 development o 42 holdout históricos.

## Pregunta, hipótesis y desenlaces

Unidad: correo único, con dependencia agrupada por hilo/campaña/plantilla/remitente/fuente. Objetivo primario: BEC (1) frente a legítimo (0), confirmado por dos revisores ciegos al score; tipología secundaria `EXECUTIVE_IMPERSONATION`, `VENDOR_FRAUD`, `BANK_ACCOUNT_CHANGE`, `SENSITIVE_DATA_REQUEST`, `OTHER`. Los legítimos con urgencia, pagos, directivos o información confidencial se marcan `is_hard_negative=true` después de evaluar el contexto, sin convertirlos en BEC. H1 (a contrastar): C3 aumenta recall frente a C1 con FPR de alertas operativas <=0.05 sobre una muestra independiente común. H0: no hay mejora detectable. Analizar también cambios de FP entre negativos difíciles; jamás inferir causalidad de un estudio solo sintético.

Primario: recall de **alertas >=50 sujeto a FPR <=0.05**, con denominadores y cobertura completa; si no se cumple FPR, se reporta sin declarar victoria. Secundarios: recall de detección >=40, precision, F1, especificidad, FPR, falsos avisos/100 legítimos, TP/FP/TN/FN, PR-AUC cuando haya scores individuales comparables, tipos, cobertura LLM, latencia mediana/p95, llamadas y costo (si disponibles). Score 0–100 es ordinal, no probabilidad calibrada; ROC/PR no reemplazan los puntos 40/50. Un fallo semántico en modo C3 produce FALLBACK con score por reglas; reportar dos coberturas: score disponible y análisis semántico completo, más métricas separadas por estado. No contabilizar `ERROR` como TN ni inventar `risk_score=0`.

## Diccionario mínimo para un corpus NUEVO

Formato propuesto: JSONL UTF-8, un objeto por correo. El contrato HTTP de entrada sigue siendo `EmailIngestRequest` (en `email`); **ningún metadato de etiqueta llega a la API ni al LLM**. El corpus histórico usa `DatasetCase` con `split=development|holdout`; para un corpus nuevo se prefiere manifiesto de particiones externo en lugar de alterar esos valores productivos.

| Campo de investigación | Tipo / regla | Uso |
| --- | --- | --- |
| `case_id` | ID opaco único, sin clase ni fuente codificada | Parear predicciones y auditar sin exponer remitentes. |
| `email` | `EmailIngestRequest` (message_id único, sender_email, subject, body_text, received_at; campos opcionales según schema) | Solo entrada al detector; eliminar credenciales, referencias reales y adjuntos. |
| `label` | `BEC` o `LEGITIMATE`, obligatorio | Etiqueta mantenida fuera de la entrada. |
| `expected_bec_type` | Enum existente para BEC, null para legítimo | Resultado secundario. |
| `is_hard_negative` | boolean solo en legítimos | Costo de FP. |
| `group_id` | ID no vacío del componente conectado por hilo/campaña/plantilla/remitente/fuente | Nunca cruzar particiones ni folds; si no puede determinarse, aislar/descartar, no inventar independencia. |
| `source_id` | ID opaco de origen autorizado; obligatorio | Control de procedencia y posible dominio de generalización; no como feature. |
| `label_rationale` | Justificación breve, sin texto sensible; revisada | Auditoría de anotación; nunca feature. |
| `annotation_status` | `ADJUDICATED` o `SYNTHETIC_GENERATED` solo para fixtures de entrenamiento | Solo casos `ADJUDICATED` entran en métricas científicas; `SYNTHETIC_GENERATED` queda limitado a entrenamiento técnico offline. |

Diccionario complementario **fuera del archivo de predicciones**: fecha/lote, permiso y alcance de uso, dos decisiones ciegas, discrepancia, árbitro, duplicados y exclusiones. No guardar PII en Git; en caso autorizado almacenar corpus en ruta local restringida y versionar solo esquema/agregados/hashes. Dominios reales no pasan por el loader sintético `services/dataset.py`, que los prohíbe expresamente; una importación nueva requerirá protección y revisión de privacidad separadas. Primero usar solo fixtures `.example`.

## Recolección, control de calidad y splits

Reunir casos nuevos de múltiples campañas y fuentes, con ataques sutiles, suplantación, cambio bancario, solicitud de datos, cuenta comprometida, y legítimos difíciles de pagos/urgencia. Documentar periodo, fuente y sesgos. Dos revisores etiquetan sin ver la salida automática; discrepancias se arbitran antes del freeze. Descartar vacío, etiqueta ambigua sin adjudicación, cuerpo no autorizado, datos cuya procedencia no pueda verificarse y duplicados exactos por Message-ID o hash de texto normalizado. Revisar similitud de texto y plantillas manualmente y unir familias relacionadas en un mismo `group_id`. Unir transitivamente hilos, campañas, plantillas, remitentes y fuente cuando sean dependencias reales, sin introducir relaciones artificiosas que hagan imposible dividir. Documentar tamaños y clase de cada grupo antes de elegir número de folds. Una prueba de uso real requiere autorización de mensajes anonimizados y consentimiento para transmitirlos al proveedor (no implícito en el acceso al corpus); en su defecto evaluar solo reglas offline y no afirmar calidad híbrida real.

Si se autoriza **entrenamiento nuevo**, asignar grupos enteros con semilla `20261118` a 70% train / 15% validation / 15% test, aproximando proporciones por clase y documentando desviaciones por grupos. Rechazar particiones sin ambas clases o con grupos compartidos. Ajustar solo train; reservar validation para elegir umbral/calibración ya predeclarada; congelar parámetros, políticas y versión antes de una **única** ejecución test. Si no hay corpus entrenable, un conjunto nuevo `evaluation` independiente permite comparar detectores fijos C1–C7 sin dividir para entrenar; jamás mezclarlo con el histórico. Evaluar estabilidad por fuente/campaña y evitar usar el test para iterar. Un tamaño mínimo de 3 grupos de cada clase en training es condición técnica de 3 folds, **no** potencia científica suficiente; definir tamaño de muestra/potencia en función de diferencias esperadas y discordancias antes de publicar conclusiones. Como objetivo inicial de recolección, >=400 mensajes y >=100 BEC, con varios grupos por clase y negativos difíciles; revisar potencia/IC, no tratar ese número como garantía estadística.

## Condiciones y baselines (mismos casos y contexto congelado)

| Condición | Implementación/reproducibilidad | Estado científico actual |
| --- | --- | --- |
| Baseline trivial | Mayoría legítima aprendida **solo de train**; detectar siempre no BEC, explicitar recall=0. No publicar como calidad del detector. | NO EJECUTADO. |
| C1 reglas/contexto | `assess_deterministically`, `det-v3`, score fijo, >=40 detección / >=50 alerta; sin IA. | Ejecutable offline, resultados nuevos NO EJECUTADOS. |
| C2 semántica sola | `SemanticAnalyzer`/`semantic-v2`, score semántico directo, sin media ni pisos; fallos sin score reportados como falta de cobertura. | NO EJECUTADO: requiere LLM autorizado; no sustituir por score hipotético. |
| C3 híbrido | `combine_scores`, `hybrid-v2`, 50/50 redondeo half-up, pisos 70 (reglas fuertes/suplantación sensible) y 50 (suplantación con solicitud); fallback reglas. | NO EJECUTADO con IA real. |
| C4 sin contexto | Reglas con `AnalysisContext([],[])`; semántica recibiría solo hechos derivados sin contexto; advertir que cambia varias señales. | NO EJECUTADO; adaptación aislada antes de usar. |
| C5 sin pisos | Simular media 50/50 sobre scores **ya obtenidos**, comparar con `hybrid-v2`; no modificar servicio. | NO EJECUTADO sin scores semánticos reales. |
| C6 umbral alternativo | Score idéntico de C3, simular alerta >=50 y >=70; >=40 es detección, no alerta vigente. | NO EJECUTADO para nueva muestra. |
| C7 fallo proveedor | Inyectar `SemanticAnalysisError`, comprobar FALLBACK y score por reglas, medir cobertura/latencia; no atribuir calidad semántica. | Verificable con fakes, calidad externa NO EJECUTADA. |

Para cada corrida sin entrenamiento: guardar hash de dataset/contexto, commit + estado de cambios, hashes de módulos, versiones de reglas/prompt/híbrido/alerta, umbrales, pesos, pisos, proveedor/modelo (o null), temperatura **no especificada explícitamente por el backend, registrar valor efectivo antes de llamadas**, timeout 30 s por defecto, SDK retries=0 y códigos de FALLBACK. No existe proveedor por defecto ni reroute entre proveedores. Llamadas externas **0** en modo offline. Cotizar precio/modelo, tokens estimados, límite de llamadas y costo máximo antes de ejecutar cualquier C2/C3 real. No leer `.env` del producto desde la herramienta de investigación.

## Modelo supervisado candidato (condicional, no entrenado)

Una sola línea base aprendible por simplicidad: texto `subject + "\n" + body_text` normalizado en el fold, `TfidfVectorizer` de palabras (minúsculas; tokenización default explícita al iniciar) + `LogisticRegression` de scikit-learn, sin metadatos identificables ni señales de reglas en esta primera comparación. Etiqueta binaria BEC=1; pérdida log-loss L2 y optimizador `liblinear` (versión y tolerancia exactas se fijarán en lock de investigación antes de entrenar). Tabla predeclarada:

| Parámetro | Inicial | Grid Search (train, CV interna) |
| --- | --- | --- |
| TF-IDF `ngram_range` | `(1, 2)` | `(1,1)`, `(1,2)` |
| TF-IDF `min_df`, `max_df` | `2`, `1.0` | `min_df=2` fijo, `max_df=1.0` fijo |
| TF-IDF `sublinear_tf`, `norm` | `True`, `l2` | fijos |
| LogReg `C`, `class_weight` | `1.0`, `None` | `C={0.1,1.0,10.0}` × `class_weight={None,"balanced"}` |
| LogReg `penalty`, `solver`, `tol` | `l2`, `liblinear`, `1e-4` | fijos |
| LogReg `max_iter`, `random_state` | `1000`, `20261118` | fijos; parada por convergencia/tolerancia o máximo; registrar `n_iter_` y warning; **no early stopping**. |

Total 12 configuraciones × 3 folds = **36 ajustes**, más refit sobre train y evaluación validation una vez; sin LLM, sin GPU, presupuesto objetivo CPU <=2 h, RAM <=4 GiB sobre corpus inicial (medir antes de ampliar). Si esos límites no bastan, no aumentar el presupuesto automáticamente. Vectorizador dentro de `Pipeline` para impedir fuga entre folds. `StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=20261118)` solo si train tiene suficientes grupos por clase y cada fold contiene ambas clases; si no, reducir a 2 solo si la precisión metodológica sigue siendo defendible; de otro modo **NO EJECUTAR búsqueda** y recolectar más datos. Selección: maximizar recall medio bajo FPR medio <=0.05, desempate menor FPR, menor dispersión (`std(recall) + std(FPR)`) y `C` menor; si no hay candidato factible declarar ninguno. El 15% validation sirve para escoger un umbral preespecificado `{0.4,0.5,0.6}` sobre probabilidades del modelo solo después de una comprobación de calibración predeclarada: al menos 20 casos, ambas clases, Brier <=0.25 y no peor que el Brier de la predicción constante de prevalencia. Si no se cumple, el umbral y el test quedan **NO EJECUTADOS** para corpus autorizado; en fixtures se permite continuar solo como demostración técnica marcada. Priorizar FPR <=0.05 y recall; reportar dispersión de folds. No usar validation ni test en el grid; no calibrar sobre test; no ajustar vectorizador fuera de train. Artefactos locales ignorados (`artifacts/research/`) incluyen hash de entradas, versión de scikit-learn, semilla, configuración/folds, selección, convergencia y modelo solo si la política de datos permite serializarlo; no versionar pesos entrenados con corpus privado. El test final autorizado requiere un candado persistente por hash del corpus en `artifacts/research/test-locks/`; un nuevo proceso no puede reclamarlo de nuevo. Si faltan corpus/permiso/versiones instaladas, estado `NO EJECUTADO`.

## Estadística y comunicación

Resultados por C1–C7 sobre los mismos IDs con TP/FP/TN/FN, denominadores por clase/tipo/estado y negativos difíciles; cobertura LLM completa y cobertura con fallback distintas. Reportar mediana/p95 de latencia por condición (incluye fallos), fallos, llamadas y costo real disponible; los ejemplos con fallo no entran en métricas condicionadas a predicción, pero permanecen en denominadores de cobertura y sensibilidad efectiva. Para diferencias binarias pareadas sobre intersección de ejemplos con score válido, McNemar exacto solo si suficientes discordancias; IC por bootstrap **de grupos** (semilla, >=2000 replicaciones, grupos como unidad) si el número de grupos y casos por clase permite recomputar métricas; reportar `NO ESTIMABLE` si no. Holm sobre comparaciones preespecificadas C3 vs C1 y C3 vs C2, no sobre todas las combinaciones exploradas. Presentar estimaciones descriptivas si la muestra es insuficiente; no inferir generalización de fixtures ni de holdout histórico. No publicar métricas sintéticas como evidencia científica.

## Bloqueos actuales y criterio de aprobación

No existe un conjunto nuevo aprobado con grupos ni permiso de uso/transmisión; no hay presupuesto LLM aprobado y no se ha fijado el modelo/proveedor efectivo. En fases siguientes solo pueden ejecutarse pruebas locales con fixtures claramente rotulados y adaptar infraestructura aislada; **entrenamiento y evaluación científica quedan NO EJECUTADOS** hasta reunir corpus, anotaciones, aprobación y presupuesto. Antes de iniciar inferencia externa: fijar hashes, protocolo, prueba de privacidad y techo de gasto. Las dependencias de investigación se instalarán solo tras aprobar una implementación concreta, sin alterar `backend/uv.lock` por una exploración sin datos.
