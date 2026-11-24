# Paquete reproducible para redactar el artículo técnico

La fuente vigente del manuscrito es `ARTICULO_BEC_GUARD_Q1.md`; su entrega Word
actualizada es `ARTICULO_BEC_GUARD_Q1_ACTUALIZADO.docx` (20 páginas, 6 tablas,
6 figuras, 22 referencias). Se reconstruye con
`python docs/research/build_article_docx.py` desde la raíz del repositorio.

El borrador está en `BORRADOR_ARTICULO_TECNICO.md`. Su tabla procede del archivo
agregado `artifacts/research/training_v1/article_evidence_software.json`, generado por
código y sin cuerpos, direcciones ni predicciones individuales. Este archivo
queda ignorado por Git; para compartir resultados, exportar únicamente el
agregado y el borrador, con su contexto metodológico.

El recorrido funcional reproducido con el software actual se registró en
`artifacts/research/training_v1/http_walkthrough_software.json` (local,
ignorado por Git): migraciones 0001–0019, login, ingesta HTTP, inferencia del
modelo guardado, consulta GET, idempotencia y cola/detalle de alertas en una
base descartable. Resultado: `shadow` score 16 y cero alertas; `assist` score
50 y una alerta. Ambos devolvieron HTTP 200 y quedaron persistidos. El LLM
estuvo expresamente desactivado; la evidencia no mide eficacia real.
La repetición actual de ese recorrido utiliza una inyección de predicción
solo en `TestClient` y base descartable para simular `assist` con el fixture;
el producto rechaza `assist` para esos pesos desde la puerta de promoción.

## Reproducir desde cero (PowerShell, directorio `backend/`)

En un checkout con dependencias instaladas según `backend/pyproject.toml` y
extras de `backend/research/requirements.txt` para Streamlit:

```powershell
uv run --no-sync python -m research.bec_training.create_training_dataset --output-dir ..\artifacts\research\training_nueva
uv run --no-sync python -m research.bec_training ..\artifacts\research\training_nueva\dataset.jsonl --output ..\artifacts\research\training_nueva\split_manifest.json
uv run --no-sync python -m research.bec_training.train_dataset ..\artifacts\research\training_nueva\dataset.jsonl --output-dir ..\artifacts\research\training_nueva\model --evaluate-test
uv run --no-sync python -m research.bec_training.article_evidence --corpus-dir ..\artifacts\research\training_nueva --context ..\datasets\context.json --output ..\artifacts\research\training_nueva\article_evidence.json
```

Las salidas no sobrescriben un destino existente. `dataset.jsonl` tiene
etiquetas generadas, **no** etiquetas adjudicadas. La comparación reutiliza el
test sintético del informe de entrenamiento, no abre un nuevo test real. El
archivo agregado registra hashes del corpus, modelo, contexto, manifiesto,
informe y código de exportación, semilla, tamaños y conteos por condición.
Las marcas `SYNTHETIC_FIXTURE_REUSE_DESCRIPTIVE_ONLY`, `NOT_RUN` y
`NOT_ESTABLISHED` son parte de la evidencia.

## Reproducir el diagnóstico externo sin reentrenar

La revisión de fuentes, criterios y cifras está en
`REVISION_DATASETS_PUBLICOS.md`. Descargar los tres CSV públicos a una carpeta
temporal **fuera del repositorio** (Enron ~45 MB, CEAS ~68 MB); las etiquetas
son las publicadas por los autores, no anotaciones nuevas. Desde `backend/`:

```powershell
$tmp = Join-Path $env:TEMP 'bec-external'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/r-dube/bec/main/data/BEC-2-human.csv' -OutFile (Join-Path $tmp 'BEC-2-human.csv')
Invoke-WebRequest -UseBasicParsing 'https://zenodo.org/records/8339691/files/Enron.csv?download=1' -OutFile (Join-Path $tmp 'Enron.csv')
Invoke-WebRequest -UseBasicParsing 'https://zenodo.org/records/8339691/files/CEAS_08.csv?download=1' -OutFile (Join-Path $tmp 'CEAS_08.csv')
uv run --no-sync python -m research.bec_training.external_benchmark --model ..\artifacts\research\training_v1\model\model.joblib --report ..\artifacts\research\training_v1\model\training_report.json --bec2 (Join-Path $tmp 'BEC-2-human.csv') --enron (Join-Path $tmp 'Enron.csv') --ceas08 (Join-Path $tmp 'CEAS_08.csv') --output ..\artifacts\research\training_v1\external_benchmark_NUEVO.json
```

El script verifica SHA-256 del modelo y del informe y rechaza cambios en la
distribución de etiquetas de los CSV; la salida no sobrescribe otro archivo.
Solo guarda agregados y hashes. Un FPR de 95,8 % sobre *ham* histórico mostró
que el modelo del fixture no generalizó a esos negativos; la precisión de la
mezcla artificial no representa la operación real. Repetir la ejecución con
otro nombre de salida; no usarla para elegir un umbral nuevo y llamarla test
independiente.

## Repetir el recorrido HTTP en PostgreSQL aislado

Crear una base PostgreSQL **vacía y descartable** con nombre
`bec_guard_test_<sufijo>` en `127.0.0.1`, en un puerto distinto de 5432. El
script rechaza bases con tablas/esquemas adicionales. Desde `backend/`:

```powershell
uv run --no-sync python -m research.bec_training.article_walkthrough --test-db-url postgresql+psycopg://bec_article_test@127.0.0.1:55438/bec_guard_test_NUEVA --model-dir ..\artifacts\research\training_v1\model --output ..\artifacts\research\training_v1\http_walkthrough_NUEVA.json
```

Repetir con una nueva base vacía y salida nueva. Se crean únicamente identidad,
buzón y correos ficticios en la base descartable; no se modifica `.env`.

## Verificaciones

```powershell
uv run --no-sync pytest -q
uv run --no-sync ruff check .
uv run --no-sync ruff format --check research tests/test_research_article_evidence.py
uvx ty check research/bec_training/article_evidence.py research/bec_training/article_walkthrough.py app/services/trained_model.py app/services/email_analysis.py
uv lock --check
```

Para repetir la validación de persistencia de `shadow` y `assist`, establecer
`TEST_DATABASE_URL` hacia una base PostgreSQL **vacía y descartable**, llamada
`bec_guard_test` o `bec_guard_test_<sufijo>`; el fixture rechaza otras bases y
realiza migraciones y limpieza. En ese entorno ejecutar:

```powershell
uv run --no-sync pytest -q tests/test_email_analysis.py
```

Se ejecutó la suite completa **después** de añadir la puerta de promoción,
la exportación del modelo desde Streamlit y el diagnóstico público v2: sobre
PostgreSQL 18 local aislado en puerto 55438, base
`bec_guard_test_software_20261120`, **666 passed, 4 skipped, 1 warning**.
Las omisiones son pruebas PDF que requieren la biblioteca nativa de WeasyPrint
en Windows; no hubo llamadas LLM. Una base nueva y descartable comprobó el
recorrido HTTP `shadow` + contrafactual `assist` vía TestClient, con 0/1 alertas
y consultas GET idempotentes. Se pasó Ruff, `ty`, `uv lock --check` y la
verificación en ejecución de las vistas Streamlit por Agent API.

Si no se configuran
proveedor, permisos y presupuesto, las condiciones con LLM real permanecen
`NOT_RUN` y no aparecen como experimentos realizados.

## Evidencia que falta para un artículo empírico sobre BEC real

El manuscrito vigente es un estudio de integración y transferencia diagnóstica:
las etiquetas públicas permitieron ejecutar ese contraste **sin reclutar otros
revisores**. Una afirmación distinta, sobre eficacia operativa de detección de
BEC real, todavía requeriría evidencia adicional:

- Corpus autorizado independiente y representativo, con ambas clases,
  campañas/plantillas agrupadas y negativos difíciles.
- Verificación de la verdad de terreno de BEC real (si las etiquetas no son
  fiables o disponibles, no se atribuye esta validez a los CSV públicos).
- Validación de un despliegue con correo **real autorizado** (las pruebas de
  integración anteriores utilizaron únicamente fixtures sobre PostgreSQL aislado).
- Comparación LLM real C2/C3 solo si hay permiso explícito de transmisión y
  presupuesto; informar cobertura, errores, latencia y costo reales.
- Evaluación final única sobre test nuevo y protocolo congelado, con intervalos
  y limitaciones adecuados a la potencia del conjunto.

Los resultados técnicos presentes permiten **redactar y revisar** un artículo
de ingeniería/viabilidad; no sustentan una conclusión científica sobre
eficacia real de BEC Guard.
