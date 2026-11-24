# Fase 2 — Pipeline offline de corpus nuevo (prueba técnica)

Código: `backend/research/bec_training/data.py` y `__main__.py`; pruebas: `backend/tests/test_research_pipeline.py`. No modifica API, base de datos, datos históricos ni `uv.lock`. El validador solo acepta correos ficticios en dominios `.example`/`.test` y exige `group_id`, `source_id`, etiqueta adjudicada, justificación y entrada `EmailIngestRequest`; el corpus histórico se rechaza por contrato. No leer ni enviar correos reales con esta herramienta.

## Contrato de entrada y salida

Cada línea JSON usa los campos `case_id`, `group_id`, `source_id`, `label`, `expected_bec_type`, `is_hard_negative`, `label_rationale`, `annotation_status="ADJUDICATED"` y `email`, conforme al diccionario de `PROTOCOLO_FASE_1.md`. El mensaje debe llevar campos mínimos del schema de ingestión (message_id, sender_email, subject, body_text, received_at con zona horaria); los demás son opcionales. Rechaza IDs duplicados, Message-ID duplicados, datos malformados y correos o URL de dominio no reservado en campos inspeccionados. Asunto+cuerpo normalizados idénticos, `thread_id`, remitente o `source_id` repetidos obligan a usar **el mismo** grupo. Un `group_id` jamás se divide. Las similitudes semánticas/plantillas no idénticas requieren agrupación y auditoría manual: el validador no puede demostrar independencia o anonimización de texto libre.

La partición busca 70/15/15 por tamaño y clase manteniendo grupos enteros, con semilla fija `20261118`. Requiere ambas clases en los tres conjuntos y al menos tres grupos de cada clase en train para permitir considerar una CV de 3 folds; si no, falla de forma cerrada. Es una búsqueda heurística de 512 ordenamientos con objetivo de mínimos cuadrados, **no** una prueba de estratificación exacta ni una garantía de tamaño/potencia; inspeccionar el manifiesto y las desviaciones antes de cualquier entrenamiento. La salida incluye IDs opacos, conteos, objetivo, semilla, hash SHA-256 del JSONL y del código, commit, árbol de trabajo sucio, versiones Python/Pydantic y timestamp. No incluye asuntos, cuerpos, remitentes ni predicciones. Estado de salida `TECHNICAL_FIXTURE_ONLY`.

## Ejecución local (solo fixture propio)

Desde `backend/` con Python 3.14 y dependencias del entorno ya instaladas:

```bash
uv run --no-sync python -m research.bec_training ../ruta/a/fixture-ficticio.jsonl --output ../artifacts/research/manifest.json
uv run --no-sync pytest -q tests/test_research_pipeline.py
uv run --no-sync ruff check research tests/test_research_pipeline.py
uv run --no-sync ruff format --check research tests/test_research_pipeline.py
```

Crear primero la carpeta local `artifacts/research/` si se usa la ruta propuesta. Está ignorada en `.gitignore`. El CLI no pisa un manifiesto existente y falla sin imprimir contenido. Las pruebas construyen mensajes artificiales en un directorio temporal. El manifiesto devuelve conteos técnicos del fixture; **no ejecutar `evaluate_holdout` para comprobar este pipeline**. No existe aún transformación TF-IDF ni modelo entrenado: quedan condicionados a datos nuevos con permiso.

## Comprobaciones observadas (2026-11-18)

`uv run --no-sync pytest -q tests/test_research_pipeline.py`: **13 aprobadas**; cubren partición reproducible/disjunta, ambas clases, duplicados, relaciones entre grupos, datos no ficticios, fallos sanitizados, rechazo del corpus histórico y escritura exclusiva de manifiesto. `uv run --no-sync pytest -q` desde `backend/`: **346 aprobadas, 277 omitidas, 1 advertencia de dependencia**; las omitidas requieren en su mayoría PostgreSQL de prueba aislado (`TEST_DATABASE_URL`). `uv run --no-sync ruff check .`: aprobado. `uv run --no-sync ruff format --check research tests/test_research_pipeline.py`: aprobado. El chequeo global `ruff format --check .` **no pasó** por dos archivos existentes y no tocados, `migrations/versions/0010_mailboxes_and_ownership.py` y `0011_mailbox_verification.py` (formato del `except` con la versión local de Ruff). No se alteraron migraciones históricas.

Al cierre de la Fase 2 todavía no existía transformación TF-IDF ni modelo; la Fase 3 añadió infraestructura de entrenamiento con fixture. Para ejecutar entrenamiento **científico** siguen pendientes: corpus independiente y autorizado, permisos explícitos, revisión humana de duplicados cercanos y grupos, tamaño y distribución suficientes, justificación de potencia y presupuesto si se invoca proveedor. Resultado científico: **NO EJECUTADO**.

**Ampliación posterior del punto 1:** el pipeline también acepta corpus con dominios reales solo mediante `CorpusUse(kind="authorized", permission_ref="ID_OPACO")`; el rol `independent_evaluation` conserva un único conjunto y no habilita entrenamiento. Se añadieron chequeos de textos similares entre grupos, hash de módulos, carga de contexto y caches offline. La guía vigente para estas capacidades es `GUIA_LABORATORIO.md`; las afirmaciones previas de este archivo describen el cierre original de la Fase 2.
