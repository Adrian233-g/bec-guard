# Software listo para el diagnóstico con datos públicos (v2)

## Contrato entre los dos programas

El laboratorio Streamlit (`backend/research/streamlit_app.py`) conserva el flujo
de entrenamiento con corpus JSONL del proyecto; la vista **Transferencia**
muestra informes agregados de ensayos externos sin cargar mensajes. El nuevo
CLI `research.bec_training.public_retraining` es un experimento *aparte*,
identificado como `PUBLIC_DIAGNOSTIC_TRAINING_ONLY`; no finge que las etiquetas
públicas sean anotaciones adjudicadas. Usa únicamente `subject + "\n" + body`
como feature, igual que el modelo cargado por FastAPI.

La API mantiene `POST /api/emails/{email_id}/analyze` y
`GET /api/emails/{email_id}/analysis` con el mismo contrato de respuesta. El
programa funcional solo deserializa un modelo local cuyo SHA-256 está fijado y
comprueba **también** el SHA-256 del informe de entrenamiento que fija el
umbral. `disabled` permanece como valor por defecto. Tanto el modelo del
fixture original como el candidato público v2 pueden observarse en `shadow`;
**ninguno puede activar `assist`**. Para este último modo el informe debe
declarar entrenamiento autorizado y test independiente ejecutado, con al
menos 20 positivos y 100 negativos, recall >= 60 % y FPR <= 5 %. Esa puerta
es una condición técnica mínima, no una certificación de representatividad.

## Entrenamiento v2 reproducible

Desde `backend/`, descargar los CSV de Dube y Zenodo como explica
`PAQUETE_ARTICULO.md`, en `$tmp` **fuera del repositorio**. El corpus y su
manifiesto sintéticos originales deben existir en
`artifacts/research/training_v1/`. Ejecutar una sola vez por directorio de
salida (nunca se sobrescriben artefactos):

```powershell
uv run --no-sync python -m research.bec_training.public_retraining --synthetic ..\artifacts\research\training_v1\dataset.jsonl --split ..\artifacts\research\training_v1\split_manifest.json --enron (Join-Path $tmp 'Enron.csv') --bec2 (Join-Path $tmp 'BEC-2-human.csv') --ceas08 (Join-Path $tmp 'CEAS_08.csv') --output-dir ..\artifacts\research\public_v2_nuevo
```

El entrenamiento emplea solo el split `train` del fixture (84 BEC y 266
legítimos) y hasta 12.000 correos `ham` (`label=0`) de Enron tras eliminar
duplicados exactos. Un reparto estable por hash del texto reserva otro
subconjunto Enron para validar junto con el split sintético `validation`;
ni BEC-2 ni CEAS participan en la selección del umbral. TF-IDF + regresión
logística (`C=0,1`, peso `balanced`, unigramas) usa una configuración fija.
Se elige de `{0,5; 0,6; 0,7; 0,8; 0,9; 0,95; 0,99}` el umbral que maximiza
recall en validación con FPR <= 5 %; sin candidato factible no se guarda
modelo. Después se ejecuta una única prueba diagnóstica por fuente en BEC-2
sintético y CEAS `ham`, y se emiten únicamente conteos, hashes, versiones y
criterios. El script comprueba solapamientos exactos entre conjuntos.

Las etiquetas de Enron/CEAS son `ham`/spam según sus publicadores, **no**
veredictos BEC; las familias BEC-2 son sintéticas. El reparto Enron por hash
evita duplicados exactos entre train/validation, no garantiza independencia
de hilos o remitentes. El `diagnostic_gate` es una señal de investigación,
jamás una autorización para activar `assist`.

## Resultados observados con el software actual

El primer modelo, entrenado solo en el fixture, produjo TP 276/276 en BEC-2
pero FP 31.396/32.763 en `ham` Enron+CEAS (FPR proxy 95,8 %).
`external_benchmark.py` guarda ese contraste en
`artifacts/research/training_v1/external_benchmark.json`.

La ejecución v2 verificada se guardó en `artifacts/research/public_v2_release/`, ignorada por
Git. Seleccionó umbral 0,5 en validación (18/18 BEC sintéticos y 31 FP de
3.176 negativos mixtos), pero en la prueba entre fuentes detectó **0/276**
BEC-2 y produjo **0/17.289** FP CEAS. Su puerta proxy resultó
`FAILS_PROXY_TARGETS`. Esto mostró que añadir un corpus de `ham` externo
eliminó falsos avisos a costa de perder todos los ataques del benchmark
sintético externo: el fallo era de datos/generalización, no un error de
persistencia o del contrato HTTP.

Para inspeccionar cualquiera de los dos informes en el programa de
entrenamiento: abrir la vista **Transferencia** y subir solo el JSON agregado,
no los CSV originales. Se verifican denominadores/tasas antes de mostrar
las cifras. Los archivos de pesos y correos permanecen locales.

## Corpus sintético adicional: 60.000 correos phishing/legítimos

La ficha [Kaggle Zero-Day Phishing Emails Corpus](https://www.kaggle.com/datasets/mutahirshaukat/zero-day-phishing-emails-corpus)
declara escenarios BEC, pero el CSV contiene solo `Subject`, `Body` y
`Label` (phishing genérico frente a legítimo). `Label=1` **no es una etiqueta
BEC**. `auxiliary_phishing_benchmark.py` comprueba la versión del CSV, elimina
duplicados exactos y reporta exclusivamente FPR sobre legítimos sintéticos y
fracción de phishing genérico marcada, con `bec_recall=NOT_ESTIMABLE...`.
Desde `backend/`, con `$tmp` apuntando a una carpeta temporal externa:

```powershell
Invoke-WebRequest -UseBasicParsing 'https://www.kaggle.com/api/v1/datasets/download/mutahirshaukat/zero-day-phishing-emails-corpus' -OutFile (Join-Path $tmp 'zero-day-phishing-emails-corpus.zip')
uv run --no-sync python -m research.bec_training.auxiliary_phishing_benchmark --corpus-zip (Join-Path $tmp 'zero-day-phishing-emails-corpus.zip') --v1-model ..\artifacts\research\training_v1\model\model.joblib --v1-report ..\artifacts\research\training_v1\model\training_report.json --v2-model ..\artifacts\research\public_v2_release\model.joblib --v2-report ..\artifacts\research\public_v2_release\training_report.json --output ..\artifacts\research\zero_day_phishing_stress_NUEVO.json
```

En 59.677 correos únicos, v1 marcó todos los legítimos y todos los phishing;
v2 no marcó ninguno. Es una comprobación de cambio de distribución, no una
estimación de detección BEC. El JSON agregado también se puede abrir en la
vista **Transferencia** sin subir el ZIP. Fuente, hashes, conteos y requisito
exacto para aislar la categoría BEC: `REVISION_DATASETS_PUBLICOS.md`.

La ruta posterior **confirmatoria para BEC sintético con un único evaluador**
está preparada por separado en `GUIA_ETIQUETADO_UN_REVISOR.md`. Su test v3
permanece sellado hasta finalizar las anotaciones; no reutiliza como
resultados confirmatorios las predicciones v1/v2 ya observadas.

## Comprobación del programa funcional en observación

Para probar v2 sin cambiar alertas, configurar rutas locales (o el volumen
de solo lectura en Compose) y calcular ambos hashes sobre los archivos
generados:

```powershell
Get-FileHash -Algorithm SHA256 ..\artifacts\research\public_v2_release\model.joblib
Get-FileHash -Algorithm SHA256 ..\artifacts\research\public_v2_release\training_report.json
```

Asignar `BEC_MODEL_MODE=shadow`, `BEC_MODEL_PATH`, `BEC_MODEL_SHA256`,
`BEC_MODEL_REPORT_PATH` y `BEC_MODEL_REPORT_SHA256`. La puntuación se registra
en `score_breakdown`, mientras el score final y las alertas siguen las
reglas/contexto. No utilizar `BEC_MODEL_MODE=assist` con v1 ni v2: el servicio
lo rechaza antes de deserializar el modelo. El recorrido histórico del
artículo sobre una base descartable usa una inyección de predicción **solo en
TestClient** para comprobar el efecto contrafactual de `assist`; no equivale a
activarlo con el fixture en el servicio desplegado.

Para afirmar eficacia BEC real se necesitarían fuentes pertinentes con ambas
clases y etiquetas fiables. Este software dejó preparada la separación,
trazabilidad y promoción técnica sin inventar tal corpus.
