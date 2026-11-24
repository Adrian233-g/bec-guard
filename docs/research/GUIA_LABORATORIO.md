# Laboratorio de entrenamiento BEC Guard (Python + Streamlit)

**Implementado y probado con fixtures** en `backend/research/`. Admite corpus autorizados en memoria mediante declaración explícita de permiso; esa declaración **no verifica legalmente** el permiso. No interviene en FastAPI, React, PostgreSQL ni n8n; no usa claves ni `.env`. Guía metodológica y estados: `PROTOCOLO_FASE_1.md` y `PHASE_STATUS.md`. SHA inicial de código: `51cdebf87939a7877c3a44b2a4b8cd1d6c09d648`. Los manifiestos registran el estado del árbol Git y hashes de los módulos de investigación.

## Iniciar en Windows (PowerShell)

Desde `backend/`, con Python 3.14 y uv. La instalación de extras es solo local y no actualiza `uv.lock` del servicio:

```powershell
uv sync --frozen
uv pip install --python .venv\Scripts\python.exe -r research\requirements.txt
uv run --no-sync streamlit run research/streamlit_app.py --server.address=127.0.0.1 --server.port=8501
```

En Linux/macOS sustituir el intérprete por `.venv/bin/python` y las rutas con barra invertida por `/`. Abrir `http://127.0.0.1:8501`. Detener con Ctrl+C. La barra lateral agrupa cinco vistas (Resumen, Datos, Entrenamiento, Comparación e Informe) y muestra el avance 0–3 de pasos preparados; el tema visual se define en `backend/.streamlit/config.toml` (solo tokens nativos, sin CSS personalizado). Para probar sin insumos, en «Datos» pulsar «Cargar ejemplo local». La opción «Autorizado» acepta dominios reales únicamente con una referencia opaca de permiso **previamente concedido**, un JSONL nuevo y, para comparar condiciones, un contexto organizacional válido. No habilita envíos externos. En «Entrenamiento» se ejecuta CV con el botón «Iniciar entrenamiento»; en «Comparación», «Ejecutar comparación offline»; en «Informe» se descarga el agregado con «Descargar informe JSON». El toggle de score hipotético 50 **no es salida de IA**. C7 simula una caída y respalda por reglas.

## Datos y reproducción

Para JSONL nuevo seguir el diccionario en `PROTOCOLO_FASE_1.md`; cada línea debe incluir `case_id`, `group_id`, `source_id`, `label`, `expected_bec_type`, `is_hard_negative`, `label_rationale`, `annotation_status` y `email` conforme a `EmailIngestRequest`. Un corpus autorizado exige `annotation_status="ADJUDICATED"`; `SYNTHETIC_GENERATED` queda reservado al fixture técnico creado por el generador y no entra en métricas científicas. La etiqueta adjudicada y la autorización declarada requieren **verificación humana externa**. En modo ficticio también se validan `sender_name`, `authentication_results`, direcciones, URLs y Message-ID para impedir dominios reales; el modo autorizado no constituye verificación legal. Se rechazan IDs, Message-ID o textos normalizados duplicados y textos casi idénticos que crucen grupos (Jaccard de trigramas >=0.75; la ausencia de coincidencia no demuestra independencia). Remitente, fuente e hilo compartidos deben pertenecer a un grupo común; revisar también campañas y plantillas por expertos. El histórico `datasets/bec_eval.jsonl` no entra como entrenamiento nuevo. Máximo 20 MB y 5000 casos en la carga offline. Para entrenamiento, 70/15/15 es objetivo por grupos; un corpus declarado «Evaluación independiente» permanece entero y **no puede entrenar**. La vista solo muestra conteos/hashes, nunca correos. `split_manifest` registra SHA-256 de entradas, código completo del laboratorio, `uv.lock`, versiones de Python/Pydantic/scikit-learn/Streamlit, semilla, commit y dirty flag.

Motor: baseline mayoritario + `TfidfVectorizer` dentro de `Pipeline` y `LogisticRegression` L2/liblinear, `tol=1e-4`, `max_iter=1000`, semilla `20261118`. Búsqueda explícita 2 n-gramas × 3 valores de C × 2 balanceos = 12 candidatos, 3 folds `StratifiedGroupKFold` en *train*, 36 ajustes + refit. Rechaza folds sin ambas clases o grupos cruzados. La selección aplica recall, FPR, dispersión y `C` en ese orden. Solo *validation* selecciona umbral {0.4, 0.5, 0.6} después de la comprobación Brier predeclarada; *test* queda `NOT_RUN` por defecto. Una ejecución opcional tras congelar selección registra `selection_frozen_sha256`, hash de datos/código y `FIXTURE_DEMO_ONLY` o `AUTHORIZED_TEST_EVALUATED`; para corpus autorizado exige un candado persistente en `artifacts/research/test-locks/<dataset_sha256>.json`, además del bloqueo de sesión. Un nuevo intento sobre el mismo corpus queda rechazado. Objetivo de recursos <=4 GiB, <=2 h de CPU, <=5000 casos; las pruebas de fixture duran segundos. Modelo solo en memoria; informe JSON sin cuerpos ni direcciones.

### Contexto y scores semánticos ya capturados

«Datos» carga contexto JSON con `executives` y `vendors`, validado con los contratos del backend. El ejemplo usa `datasets/context.json` ficticio; el archivo autorizado se usa únicamente en memoria. El panel muestra `dataset_sha256` y `context_sha256` para construir el cache. «Comparación» acepta JSON **sin cuerpos, prompts ni salidas textuales**:

```json
{
  "metadata": {
    "provider": "proveedor",
    "model": "modelo-v1",
    "prompt_version": "semantic-v2",
    "dataset_sha256": "<hash SHA-256 mostrado en Datos>",
    "context_sha256": "<hash SHA-256 mostrado en Datos>"
  },
  "scores": {"DEMO-001": 75, "DEMO-002": null}
}
```

El ejemplo es **solo esquema**, no contiene resultados reales ni IDs suficientes para correr: cada `case_id` del JSONL debe aparecer exactamente una vez. `null` es falta de cobertura (C2/C5: ERROR; C3/C6: FALLBACK), nunca un negativo. La carga rechaza hashes distintos y campos extra. C4 híbrido exige un **segundo cache** calculado sin contexto, con hash de `{"executives":[],"vendors":[]}` que muestra el panel; sin ese cache queda `NOT_RUN`. Ambos caches deben conservar proveedor, modelo, versión de prompt y hash propio, y usar el mismo proveedor/modelo/prompt; solo cambia el contexto. Si no se proporciona ningún score, C4 representa solo ablación de reglas y así se etiqueta. El sistema **no captura ni llama al LLM**; preparar caches reales exige aprobación independiente para transmitir datos. C5 quita pisos sobre los mismos scores; C6 compara alerta 70 con la vigente 50 sin modificar producción.

Para validar un archivo autorizado por CLI (desde `backend/`; crear antes el directorio de salida ignorado por Git):

```powershell
uv run --no-sync python -m research.bec_training RUTA_PRIVADA\nuevo.jsonl --authorized --permission-ref PERM_001 --role independent_evaluation --output ../artifacts/research/manifest.json
```

La referencia es un identificador, **no** una contraseña ni la prueba legal del permiso. Los manifiestos CLI contienen IDs opacos; no versionar el corpus ni distribuir esos archivos sin revisión.

### Contrastes e incertidumbre

El informe exporta TP/FP/TN/FN, recall efectivo, FPR, negativos difíciles, tipos BEC, cobertura con/sin fallback y latencia disponible por condición. Cuando hay ambas clases y todos los scores son comparables, informa average precision (resumen PR) y ROC-AUC; los omite ante fallos de cobertura o mezcla híbrido/fallback. En corpus declarado **autorizado + evaluación independiente** con cache semántico completo/pareado, calcula IC 95 % por bootstrap **de grupos** (2000 remuestreos, semilla `20261118`) solo con >=20 grupos y >=5 grupos por clase; aplica McNemar exacto sobre aciertos binarios C3 vs C1 y C3 vs C2 con >=10 discordancias por contraste. Holm se informa únicamente si ambos contrastes cumplen criterios. Faltantes quedan `NOT_EXECUTED` o `NOT_ESTIMABLE`; no se imprimen predicciones individuales. Un IC calculable **no prueba** por sí solo calidad externa del corpus, legitimidad de permisos ni ausencia de sesgo.

## Comprobaciones

```powershell
uv run --no-sync pytest -q tests/test_research_pipeline.py tests/test_research_app.py
uv run --no-sync pytest -q
uv run --no-sync ruff check research tests/test_research_pipeline.py tests/test_research_app.py
uv run --no-sync ruff format --check research tests/test_research_pipeline.py tests/test_research_app.py
uvx ty check research/streamlit_app.py research/bec_training
```

Las pruebas de interfaz usan `streamlit.testing.v1.AppTest`; se omiten si faltan los extras, igual que la prueba de entrenamiento si falta scikit-learn. CI de producción sigue instalando desde `backend/uv.lock`. Sin `TEST_DATABASE_URL`, las pruebas de integración con PostgreSQL se omiten. El chequeo global de formato con Ruff local reportó dos migraciones existentes no modificadas (0010/0011); el código de investigación pasa su chequeo aislado.

## Implementado, ejecutado y pendiente

| Área | Situación |
| --- | --- |
| Carga/partición, CV, baseline, entrenamiento, C1–C7, métricas e interfaz | IMPLEMENTADO y probado con fixture ficticio; entrada autorizada con dominios reales cubierta por pruebas sintéticas. |
| Entrenamiento sobre corpus autorizado; evaluación de modelo y C1–C7 con muestra nueva | Infraestructura LISTA; ejecución real NO EJECUTADA: falta corpus independiente, etiquetado y permiso de uso. |
| LLM real (C2/C3), costos y latencia de proveedor | NO EJECUTADO: no hay aprobación de transmisión, proveedor/modelo ni presupuesto. |
| McNemar, bootstrap grupal, Holm y rendimiento publicado | Código IMPLEMENTADO y probado con datos artificiales; inferencia científica real NO EJECUTADA. |
| Exportación | Informe agregado JSON y, si se seleccionó umbral, modelo `joblib` descargable con su SHA-256 incorporado en el informe. No se exportan correos ni predicciones individuales. Mantener pesos entrenados con datos autorizados fuera de Git. |
| Transferencia pública | Vista adicional para informes agregados de BEC-2 y Enron/CEAS; validación de denominadores, sin cargar CSV grandes en Streamlit. CLI de entrenamiento exploratorio v2 y detalle en `SOFTWARE_PUBLICO_V2.md`. |

Antes de una ejecución científica: registrar permisos, anotación ciega, grupos/duplicados cercanos, potencia, hashes, versiones y costo autorizado. Congelar configuración antes del test y evaluar ese test una sola vez. Una salida del LLM por API es inferencia, no entrenamiento del LLM. No desplegar ni promover pesos/umbrales de este laboratorio a producción sin otro proceso explícito.

La revisión de datasets públicos está en `REVISION_DATASETS_PUBLICOS.md`. En
particular, BEC-2 es sintético y no contiene negativos humanos para FPR. Los
modelos del fixture y del diagnóstico público pueden cargarse en `shadow` con
hashes del modelo **y del informe**, pero el servicio rechaza `assist` para
ambos; la puerta técnica de promoción está documentada en
`INTEGRACION_MODELO.md`.
