# Corpus sintético candidato V1

El generador `backend/research/bec_training/generate_corpus.py` crea un paquete reproducible de 500 mensajes ficticios nuevos:

- 120 candidatos BEC, 30 por tipo: suplantación ejecutiva, fraude de proveedor, cambio bancario y solicitud sensible.
- 380 candidatos legítimos, incluidos 100 negativos difíciles.
- 250 grupos independientes, con dos mensajes relacionados por grupo.
- Dominios reservados `.example`; no contiene correos reales ni llamadas externas.

## Generación

Desde `backend/`:

```powershell
uv run --no-sync python -m research.bec_training.generate_corpus --output-dir ..\artifacts\research\corpus_v1
```

El directorio de salida está ignorado por Git y contiene:

- `gold_reference.jsonl`: etiquetas generadas para control del investigador; no entregar a los revisores.
- `blind_review.jsonl`: paquete sin etiquetas ni justificaciones para anotación ciega.
- `generation_manifest.json`: distribución de referencia y hashes completos.
- `blind_manifest.json`: metadatos que pueden acompañar al paquete de revisión.

## Revisión y adjudicación

Iniciar el formulario de anotación desde `backend/`:

```powershell
uv run --no-sync streamlit run research\annotation_app.py --server.address=127.0.0.1 --server.port=8502
```

Cada revisor debe usar un ID distinto (`REVIEWER_A` y `REVIEWER_B`) y un directorio privado común. La aplicación guarda un archivo separado por revisor en `artifacts/research/annotations/`; no mezcla sus respuestas durante la revisión.

Cuando ambos terminen, resolver los desacuerdos con:

```powershell
uv run --no-sync streamlit run research\adjudication_app.py --server.address=127.0.0.1 --server.port=8503
```

La segunda aplicación genera `bec-synthetic-v1-adjudicated.jsonl`, que sí puede validarse con el pipeline porque contiene `annotation_status=ADJUDICATED`. No se debe cargar el archivo dorado en ninguna de las dos aplicaciones.

## Estado científico

Este material es un **candidato sintético**, no una muestra independiente real. Sus etiquetas fueron generadas por reglas/templates y deben ocultarse durante una revisión humana doble. Después de la anotación:

1. Comparar las etiquetas de los dos revisores.
2. Adjudicar discrepancias.
3. Crear un JSONL final con `annotation_status=ADJUDICATED` y sin usar la referencia generada para resolver casos automáticamente.
4. Revisar manualmente campañas, grupos, duplicados cercanos y calidad lingüística.
5. Solo entonces decidir si sirve como demostración técnica o como evaluación sintética predeclarada.

Los resultados de este corpus no deben presentarse como rendimiento sobre correo empresarial real.

## Dataset entrenable inmediato

Para ejecutar ya un entrenamiento técnico sin convertir la etiqueta generada en
una falsa revisión humana:

```powershell
uv run --no-sync python -m research.bec_training.create_training_dataset --output-dir ..\artifacts\research\training_v1
uv run --no-sync python -m research.bec_training ..\artifacts\research\training_v1\dataset.jsonl --output ..\artifacts\research\training_v1\split_manifest.json
uv run --no-sync python -m research.bec_training.train_dataset ..\artifacts\research\training_v1\dataset.jsonl --output-dir ..\artifacts\research\training_v1\model --evaluate-test
```

El resultado contiene 500 casos, 120 BEC, 380 legítimos, 100 negativos
difíciles y 250 grupos. `annotation_status=SYNTHETIC_GENERATED` permite que el
pipeline lo distinga de un corpus `ADJUDICATED`. El entrenamiento queda marcado
como `TECHNICAL_FIXTURE_ONLY`; sirve para probar el modelo y el pipeline, no
para afirmar precisión sobre correo real.

El tercer comando produce `model/model.joblib` y `model/training_report.json`.
Ese modelo solo contiene patrones del corpus sintético y no debe desplegarse
como detector de producción.
