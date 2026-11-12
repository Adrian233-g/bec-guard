# Evaluación formal congelada - eval-v1

> **Alcance histórico:** estos resultados corresponden a `det-v1`, no a la
> revisión posterior `det-v2`. No se repitió el holdout ni se evaluó el sistema
> híbrido real para esta revisión; no atribuir sus métricas a la versión nueva.

Evaluación académica del baseline determinista, ejecutada **una vez** el
2026-10-21 a las 15:21:51 UTC. El corpus es sintético: **42 casos holdout, 30
legítimos y 12 BEC**, incluidos 9 hard negatives legítimos. No es un benchmark
real-world ni permite afirmar rendimiento productivo. Development (98 casos)
se usó antes para desarrollar el motor; holdout permaneció reservado hasta el freeze.

## Freeze y procedencia

Antes de ejecutar: 451 tests backend aprobados con PostgreSQL 18, Ruff check y
format --check aprobados, validador estructural y regression development aprobados.
Detector y dataset con diff vacío respecto a Fase 7. No había cambios rastreados
pendientes; skills-lock.json preexistente permaneció sin seguimiento.

| Dato | Valor |
| --- | --- |
| Git SHA evaluado | `71f5697312072c106730dbc5d594f5ab11816bb5` |
| Dataset SHA-256 | `1a62cf39afbd8f7c59ecb7b7d2f25c78826e92df9a5425aa39f0fcf8e1460979` |
| Context SHA-256 | `32e2e91b5827abf3ad84db43e4d99e7bfec903f4cc8b3b28cccb134ae75b69ff` |
| Políticas | det-v1 / semantic-v1 / hybrid-v1 / alert-v1 |
| Detección | score >=40 |
| Umbral al congelar el baseline | score >=70; la política vigente usa >=50 |
| Niveles vigentes | LOW 0–39, MEDIUM 40–69, HIGH 70–84, CRITICAL 85–100 |
| Proveedor / modelo | null / null; baseline sin LLM |
| Completados / errores / coverage | 42 / 0 / 100% |

El CLI escribió freeze.json antes de predecir, con versiones, commit, hashes del
corpus/contexto y de siete archivos del detector. Resultados locales ignorados:
`artifacts/evaluation/20261021T152151453992Z-4506b4d1/` contiene freeze.json,
result.json, predictions.json y hybrid-status.json (NOT_RUN). No se versionan
predicciones por caso ni correos.
En esta documentación solo se registran agregados; no se inspeccionaron cuerpos
fallidos para diseñar reglas. **No hubo tuning post-holdout ni cambios del dataset.**

## Detección >=40

| | Real BEC | Real legítimo |
| --- | ---: | ---: |
| Predicción BEC | TP 10 | FP 0 |
| Predicción legítimo | FN 2 | TN 30 |

| Métrica | Resultado |
| --- | ---: |
| Precision | 100.00% |
| Recall / sensibilidad | 83.33% |
| F1 | 90.91% |
| Accuracy | 95.24% |
| Specificity | 100.00% |
| False positive rate | 0.00% |

El baseline identifica diez ataques bajo este criterio, pero omite dos. Precision
100% describe diez predicciones positivas sin FP en este pequeño corpus; no indica
que el motor sea infalible. El conjunto no mide todas las formas de fraude real.

## Alerta operativa >=70

| | Real BEC | Real legítimo |
| --- | ---: | ---: |
| Predicción BEC | TP 0 | FP 0 |
| Predicción legítimo | FN 12 | TN 30 |

| Métrica | Resultado |
| --- | ---: |
| Precision | Indefinida (null: no hubo predicciones positivas) |
| Recall / sensibilidad | 0.00% |
| F1 | 0.00% |
| Accuracy | 71.43% |
| Specificity | 100.00% |
| False positive rate | 0.00% |

Subir de 40 a 70 reduce los TP de diez a cero sin reducir FP (ya eran cero).
El baseline determinista por sí solo no alcanza el umbral operativo en ninguno de
los doce ataques reservados. Accuracy 71.43% refleja los treinta negativos; oculta
el fallo de sensibilidad si se interpreta aisladamente. Esto no es una evaluación
del pipeline híbrido productivo: falta el score semántico real.

## Hard negatives y tipos

Hard negatives: **9**, completados9/errores0, FP detección0 y FP alerta0; FPR0%
en ambos criterios. Un cero observado en nueve ejemplos no demuestra una FPR
poblacional nula. Las tasas usan hard negatives COMPLETED como denominador;
si hubiese ERROR se mostrarían por separado, sin contarlos como negativos.

Tipos en los doce ground-truth BEC, usando la sugerencia natural del determinista
independientemente del threshold binario: **8/12 correctos, type accuracy66.67%**.
No se inventan tipos semánticos para el baseline.

| Tipo esperado | Total | Correctos | Incorrectos | No clasificados |
| --- | ---: | ---: | ---: | ---: |
| EXECUTIVE_IMPERSONATION | 4 | 4 | 0 | 0 |
| VENDOR_FRAUD | 3 | 3 | 0 | 0 |
| BANK_ACCOUNT_CHANGE | 2 | 1 | 1 | 0 |
| SENSITIVE_DATA_REQUEST | 2 | 0 | 2 | 0 |
| OTHER | 1 | 0 | 0 | 1 |

Estos subgrupos de uno a cuatro casos solo permiten descripción; no conclusiones
estadísticas fuertes ni comparaciones generales entre categorías.

## Latencia y definiciones

Determinista local: media **0.601490 ms**, mediana **0.485375 ms**, p95
**1.015705 ms**. Medida con perf_counter por caso; excluye carga de corpus/contexto,
serialización, HTTP y PostgreSQL. p95 usa nearest rank (ceil(0.95*n)). Depende del
hardware y carga del equipo; no es SLA ni requisito de CI. No se repitió holdout
para optimizar o estabilizar tiempos.

Precision=TP/(TP+FP), recall=TP/(TP+FN), F1=2TP/(2TP+FP+FN),
accuracy=(TP+TN)/N, specificity=TN/(TN+FP), FPR=FP/(FP+TN). División por cero devuelve
null, nunca NaN. Las matrices usan únicamente casos COMPLETED; coverage reporta su
proporción sobre todos los seleccionados. Effective recall=TP/total ground-truth BEC
incluye ERROR como no detectado en ese denominador; aquí coincide con recall.
Los errores no se convierten en LEGITIMATE ni score cero.

## Evaluación híbrida: NOT_RUN

**Reason: real external LLM evaluation requires explicit user authorization.**
No se llamó OpenAI, Gemini ni Groq aunque pudiera existir una key local. No hay
métricas híbridas de calidad inventadas con fakes. Los fakes solo prueban contratos,
coverage, errores y la reutilización de combine_scores/resolve_bec_type productivos.

El runner híbrido usa exactamente reglas/contexto, SemanticAnalyzer y scoring de
producción; no tiene otro prompt, temperatura o clasificador. Un futuro experimento
real autorizado deberá guardar nuevo freeze/provider/model. El resultado no será
independiente de esta primera observación del corpus y debe identificarse como otro
experimento; no se debe tunear contra estos resultados y presentarlo como holdout
intacto. Si se descubre un bug objetivo del detector se detienen nuevas evaluaciones
hasta documentar una nueva metodología, sin ajustes silenciosos.

## CLI y separación del producto

Desde backend/, la confirmación es obligatoria. La ejecución realizada fue:

```bash
uv run python -m app.scripts.evaluate_holdout \
  --mode deterministic --confirm-holdout \
  --output-dir ../artifacts/evaluation
```

Solo tras autorización explícita de gasto, la futura ejecución híbrida añade:
`--mode hybrid --confirm-holdout --allow-external-llm`. Sin ambas banderas no se
inicializa proveedor. El evaluador solo pasa case.email y contexto al detector;
anotaciones se leen después de obtener la predicción. No escribe DB ni ofrece HTTP.
CI prueba métricas con fixtures artificiales; no ejecuta holdout formal.
Los reportes operativos PDF/XLSX solo leen PostgreSQL y nunca importan este tooling.

## Simulación de alternativas de puntaje (2026-11-04)

`cd backend && .venv/bin/python -m app.scripts.compare_score_policies` compara la
política anterior (50/50, alerta >=70), bajar solo el umbral a 50, cambiar solo los
pesos a 30/70, y aplicar ambas propuestas. Todas conservan el piso vigente de 70
para reglas >=70. El script solo usa los 98 casos sintéticos de desarrollo, nunca
procesa holdout ni llama a un proveedor. No modifica la política operativa.

Se asigna la misma puntuación semántica **hipotética** (20, 50 u 80) a todos los
correos de cada escenario. No son resultados de un modelo ni estimaciones de su
precisión: sirven únicamente para visualizar el efecto aritmético y los riesgos
si la IA puntúa mal. Etiquetas y ejemplos de desarrollo no son independientes
para medir rendimiento generalizable.

| Semántica hipotética | Política | Alertas BEC (28) | Alertas legítimos (70) |
| --- | --- | ---: | ---: |
| 20 | Actual | 11 | 0 |
| 20 | 30/70 y >=50 | 11 | 0 |
| 50 | Actual | 11 | 0 |
| 50 | 30/70 y >=50 | 19 | 0 |
| 80 | Actual | 17 | 0 |
| 80 | 30/70 y >=50 | 28 | 70 |

Con 30/70 y umbral 50, una puntuación semántica de 80 genera alerta incluso si
las reglas dan 0; un error alto del modelo podría afectar correos legítimos.
Estos escenarios no justifican activar ni descartar la propuesta por sí solos.
Falta un conjunto nuevo, etiquetado independientemente, con resultados semánticos
reales y medición de errores y consumo. Además, el respaldo determinista ante
fallo de IA se implementó después como FALLBACK: su resultado es limitado y no
 demuestra precisión híbrida.

## Protocolo actual `eval-v2`

`eval-v1` queda cerrado como registro histórico. El runner actual usa `eval-v2` y
no debe ejecutarse contra el holdout histórico para ajustar reglas, pesos, prompts,
umbrales o selección de proveedor. El árbol de trabajo debe estar limpio para que
`freeze_metadata` pueda registrar un commit reproducible; cualquier cambio del
detector o del dataset hace que el freeze falle.

### Modos y estados

| Modo | Entrada al detector | Estado esperado | Métricas principales |
| --- | --- | --- | --- |
| `deterministic` | Reglas y contexto activo | `COMPLETED` | Baseline sin proveedor |
| `hybrid` | Reglas más un único proveedor autorizado | `COMPLETED` | Solo casos con salida semántica válida |
| `fallback` | Reglas, simulando indisponibilidad de IA | `FALLBACK` | Respaldo determinista, separado del híbrido |
| Cualquier modo con fallo sin score | Sin resultado evaluable | `ERROR` | Cuenta como error, nunca como legítimo |

Cuando el proveedor falla durante `hybrid`, el runner conserva el score y tipo
deterministas y registra `FALLBACK`. `ERROR` queda reservado para una ejecución sin
score evaluable. Así, un error no se convierte en score cero ni en una predicción
legítima.

El resultado registra `completed`, `fallback`, `errors`, `coverage` de casos con
score, `completed_coverage`, `fallback_rate` y `error_rate`. La cobertura completa
de IA es distinta de la cobertura con respaldo.

### Matrices y métricas

Para cada grupo de ejecución se generan dos matrices independientes:

| Criterio | Definición |
| --- | --- |
| Detección | `score >= 40` |
| Alerta | `score >= 50` |

Las métricas disponibles son TP, TN, FP, FN, denominador, precision,
recall/sensibilidad, F1, accuracy, specificity, FPR y sensibilidad efectiva.

`detection_metrics` y `alert_metrics` representan todos los casos con score válido.
`completed_*_metrics` solo contiene resultados híbridos completos y
`fallback_*_metrics` solo contiene respaldos. La sensibilidad efectiva conserva como
denominador todos los BEC seleccionados, incluidos casos con `ERROR`.

Las métricas de hard negatives informan total, completados, fallback, errores y FP
con el denominador de hard negatives evaluables. Los tipos BEC se informan de forma
análoga, siempre con el tamaño de cada categoría.

### ROC y precision-recall

`curves` se genera únicamente cuando cada caso seleccionado tiene etiqueta y score
individual válido, y existen ambas clases. Se guardan puntos por umbral de score,
no una curva reconstruida desde una matriz agregada. `completed_curves` y
`fallback_curves` permiten observar cada régimen por separado. Si existen errores,
la curva global se omite; no se imputan scores.

Las curvas no sustituyen el punto operativo de detección 40 ni el de alerta 50.
ROC-AUC y PR-AUC son descriptivos del conjunto evaluado y no son evidencia de
calibración probabilística.

### Conjunto independiente futuro

Una evaluación nueva debe usar un archivo distinto de `datasets/bec_eval.jsonl` con
split `evaluation`, `group_id` obligatorio y `label_rationale` para cada caso. Un
`group_id` debe agrupar hilo, plantilla, campaña o familia de mensajes; el loader
rechaza que un grupo cruce splits. Las etiquetas y sus justificaciones se congelan
antes de medir y no se pasan al detector.

El comando futuro tendrá esta forma:

```bash
uv run python -m app.scripts.evaluate_holdout \
  --mode deterministic \
  --split evaluation \
  --dataset ../datasets/bec_eval_v2.jsonl \
  --context ../datasets/context-v2.json \
  --confirm-evaluation \
  --output-dir ../artifacts/evaluation
```

Para `hybrid` se requiere además `--allow-external-llm`, con proveedor y modelo
registrados en `freeze.json`. El conjunto histórico de 42 casos no se reutiliza ni
se vuelve a puntuar.

### Incertidumbre y comparaciones

Solo con suficientes casos independientes se calcularán intervalos binomiales
Wilson o Clopper-Pearson para proporciones. Con muestras pequeñas se mostrarán
estimaciones descriptivas y denominadores, sin conclusiones fuertes.

McNemar exacto se reservará para predicciones binarias pareadas sobre exactamente
los mismos casos, reportando los dos conteos discordantes y el subconjunto común.
Comparaciones múltiples usarán corrección de Holm. No se aplicarán estas pruebas
entre el holdout histórico `eval-v1` y resultados de otra versión.

### Resultados disponibles y pendientes

| Experimento | Estado | Resultado |
| --- | --- | --- |
| Baseline determinista `eval-v1` sobre holdout histórico | Disponible | Matrices, métricas, hard negatives, tipos y latencia documentados arriba |
| Simulación de scores semánticos sobre development | Disponible | Escenarios aritméticos; no son resultados de IA |
| Híbrido real sobre holdout histórico | No ejecutar | Pendiente y prohibido para tuning |
| Fallback sobre conjunto independiente | Pendiente | Requiere dataset nuevo y freeze |
| ROC/PR del baseline histórico | No disponible en el repositorio | No se reconstruyen sin scores individuales congelados |
| ROC/PR híbrido real | Pendiente | Requiere proveedor autorizado y scores individuales |
| Intervalos y McNemar | Pendiente | Requiere tamaño y pares válidos |

No se publican cifras nuevas hasta que un experimento `eval-v2` produzca sus propios
artefactos, hashes, commit, proveedor, modelo, modo y denominadores.

## Fase 7: optimización experimental de políticas

Esta fase es una ampliación exploratoria y no cambia `hybrid-v2`, `alert-v2`, las
filas `EmailAnalysis` existentes ni las alertas ya creadas. El módulo
`app.evaluation.policy_experiment` no se importa desde FastAPI, no usa PostgreSQL,
no llama proveedores y no contiene una operación para promover automáticamente una
política. El CLI opcional es:

```bash
uv run python -m app.scripts.run_policy_experiment \
  --semantic-score 20 50 80 \
  --output ../artifacts/policy-experiment/development.json
```

El archivo de salida solo contiene métricas agregadas, parámetros y procedencia; no
contiene cuerpos, asuntos, remitentes ni predicciones por caso. La búsqueda filtra y
valida `split=development` antes de leer etiquetas para la evaluación. Si recibe un
caso `holdout` o `evaluation`, falla de forma cerrada.

### Objetivo y restricciones predeclarados

La finalidad es aumentar la detección de BEC sin perder control operativo sobre
falsos positivos, cobertura y consumo. Para cada trial se calcula:

```text
objective = recall - 0.25 * false_positive_rate - 0.10 * (1 - coverage)
```

Solo es seleccionable un trial que cumpla simultáneamente:

| Restricción | Valor inicial | Motivo |
| --- | ---: | --- |
| False positive rate | `<= 0.05` | Evita convertir una cola sintética en una alarma masiva. |
| Coverage | `>= 0.95` | Un fallo o score ausente no puede ocultarse como legítimo. |
| Piso de seguridad | determinista `>=70` conserva score `>=70` | Evita que una semántica contradictoria borre evidencia local fuerte. |
| Llamadas externas durante la búsqueda | `0` con escenarios hipotéticos | La comparación inicial es aritmética y reproducible. |

El tamaño de development es 98 casos sintéticos, 70 legítimos y 28 BEC. Por eso
estos límites son criterios de ingeniería para descartar candidatos, no intervalos
de rendimiento poblacional. Los resultados deben mostrar siempre numeradores,
denominadores y hard negatives; no se presentan como calidad productiva.

### Búsqueda inicial

Se usa una cuadrícula explícita de 25 trials, sin Optuna ni interfaz de trials:

| Parámetro | Valores iniciales |
| --- | --- |
| Peso de reglas | `30, 40, 50, 60, 70` |
| Peso semántico | `100 - peso de reglas` |
| Umbral de alerta | `50, 55, 60, 65, 70` |
| Piso determinista | fijo en `70` |
| Pisos por señal | `IMPERSONATION_SENSITIVE_REQUEST=70`, `IMPERSONATION_REQUEST=50` |

Los rangos son deliberadamente pequeños porque el corpus es sintético, no
independiente y no permite justificar una optimización de alta dimensión. El empate
se resuelve por objetivo descendente, recall descendente, FPR ascendente y umbral
ascendente. `seed` se registra aunque la cuadrícula inicial sea determinista, para
que un futuro muestreador reproducible no pueda omitir la semilla.

El comparador `compare_score_policies.py` sigue siendo el primer instrumento para
entender escenarios 50/50, 30/70 y umbrales alternativos. Sus scores semánticos
constantes son hipótesis compartidas por todos los correos: no son observaciones de
IA. La búsqueda nueva conserva esa distinción. Para un resultado empírico se debe
proporcionar un cache de salidas reales, con un valor por `case_id`, sin permitir
que el módulo invoque el proveedor.

### Registro de trials

Cada `TrialRecord` serializado contiene como mínimo:

| Campo | Contenido |
| --- | --- |
| `trial_id` | Orden estable dentro de la búsqueda. |
| `status` | `COMPLETED` o `FAILED`. |
| `candidate` | Pesos, umbral y versión de pisos. |
| `objective` | Valor calculado o `null` si falló. |
| `feasible` / `constraints` | Resultado explícito de FPR y cobertura. |
| `metrics` | TP/TN/FP/FN, recall, FPR, precision, cobertura y hard negatives. |
| `seed` / `duration_ms` | Reproducibilidad y duración local. |
| `semantic_source` | `hypothetical` o `cached_model_output`. |
| `semantic_provider` / `semantic_model` / `semantic_prompt_version` | Procedencia de una salida real cacheada. |
| `semantic_cache_sha256` | Identidad del artefacto de salidas, nunca su contenido. |
| `estimated_external_calls` | Presupuesto declarado; la cuadrícula no realiza llamadas. |
| `failure_reason` | Error sanitizado sin datos del correo. |

No se registra el cuerpo del correo ni se envían etiquetas al motor. Una futura
integración con Optuna tendría que justificarla frente a esta cuadrícula, conservar
estos campos, fijar la semilla, registrar duración/estado y guardar el motivo de cada
fallo. Optuna no debe introducirse solo para hacer más grande una búsqueda con 98
ejemplos.

### Validación anidada propuesta

La selección final de una política experimental debe reservarse a una evaluación
nueva independiente. Si el conjunto de development obtiene grupos estables por hilo,
plantilla, campaña o familia, la propuesta es validación anidada de cinco folds
externos y tres internos:

1. Separar grupos, nunca filas, en cinco folds externos estratificados por etiqueta.
2. En cada fold externo, ajustar pesos/umbral únicamente en sus tres folds internos.
3. Evaluar una sola vez la política elegida en el fold externo y conservar sus
   denominadores, FPR, recall, cobertura y consumo.
4. Agregar los cinco resultados externos, sin seleccionar la política con el agregado
   de los folds externos.

Si alguna clase o grupo no permite cinco folds externos y tres internos sin fuga, se
reduce el número de folds antes de ejecutar y se registra el motivo. El corpus actual
no autoriza afirmar que esa condición ya se cumple: faltan grupos independientes
suficientes para convertir esta propuesta en una medición. No se reentrena ningún
LLM, no se comparten hilos entre folds y no se usa `holdout` histórico ni el conjunto
final nuevo para elegir parámetros.

### Consumo y procedencia externa

Con scores hipotéticos, el coste es cero. Con scores de modelo cacheados, la llamada
estimada es como máximo una por caso de development y se reutiliza la misma salida
para todos los trials; no se llama una vez por combinación. Antes de una captura real
se debe aprobar proveedor, modelo, versión de prompt, temperatura/configuración,
timeout, número de casos, precio unitario y presupuesto máximo. El freeze debe guardar
SHA del dataset, contexto, cache de salidas y configuración. Una salida simulada nunca
se etiqueta como medición de proveedor.

### Visualizaciones sin interfaz operativa

Los artefactos experimentales pueden generar, fuera del producto:

- Heatmap de `peso de reglas × umbral`, mostrando objetivo y una marca de factibilidad.
- Frontera recall-FPR con puntos factibles y no factibles separados.
- Barras por escenario semántico hipotético (`20/50/80`) con TP, FP y alertas.
- Tabla/historial de trials con estado, duración, semilla y motivo de fallo.
- Para datos reales cacheados, comparación por proveedor/modelo/prompt y consumo total.

Estas vistas son de investigación y no deben aparecer en dashboard, cola de alertas,
reportes operativos ni permisos de la aplicación. La política activa solo cambia
después de seleccionar una candidata con evidencia de development, congelarla y
ejecutar una única evaluación sobre un conjunto nuevo independiente.
