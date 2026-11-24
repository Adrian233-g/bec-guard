# Clasificador entrenado en el análisis principal

El análisis HTTP de `POST /api/emails/{email_id}/analyze` carga opcionalmente un
artefacto local entrenado por `research.bec_training.train_dataset` o
`research.bec_training.public_retraining`. El modelo
no recibe metadatos del corpus ni etiquetas: usa `subject + "\n" + body_text`.
La respuesta existente incluye `score_breakdown.model_mode`,
`model_probability`, `model_score` y `model_sha256` cuando está habilitado.
`GET /api/emails/{email_id}/analysis` devuelve el desglose persistido.

## Activación

1. Crear el corpus y entrenar según `CORPUS_SINTETICO_V1.md`. El modelo de ese
   ejemplo es **sintético**: sirve para integrar el flujo, no para certificar
   detección en producción.
2. Calcular los SHA-256 de **ambos** archivos `model.joblib` y
   `training_report.json` con `Get-FileHash -Algorithm SHA256 <ruta>`.
3. En `.env` (o variables del proceso) definir `BEC_MODEL_MODE=shadow` y
   `BEC_MODEL_SHA256=<hash en minúsculas>` y
   `BEC_MODEL_REPORT_SHA256=<hash del informe>`. En Compose, el directorio
   `BEC_MODEL_HOST_DIR` se monta de solo lectura en `/opt/bec-guard-model` y
   `BEC_MODEL_PATH` / `BEC_MODEL_REPORT_PATH` apuntan respectivamente al modelo
   y a su `training_report.json`. Para ejecución local sin Docker, asignar
   ambas rutas a los archivos locales de `artifacts/research/training_v1/model/`.
4. Aplicar `uv run alembic upgrade head` en `backend/` a la base correspondiente
   antes de analizar. `shadow` es la única opción habilitable con los modelos
   de fixture o de diagnóstico público v2.
5. Con un **informe de entrenamiento autorizado y test independiente** que
   satisfaga la puerta técnica, `BEC_MODEL_MODE=assist` hace que
   una predicción positiva eleve el score ordinal **como mínimo a 50**, incluso
   si el LLM está caído; se conserva el score por reglas y se marca el modo en
   `policy_version`. La predicción negativa nunca disminuye un score de reglas
   o semántica. `disabled` (default) mantiene exactamente el score anterior.

El umbral de clasificación sale del informe congelado del entrenamiento. La
probabilidad del clasificador **no es** un score de riesgo; `model_score` vale
50 si supera el umbral y 0 en caso contrario. El modelo no genera tipología BEC;
si es la única señal que eleva el score se usa `OTHER`. No se hacen llamadas de
red durante la inferencia local.

**Modelos actuales:** v1 fue un fixture técnico; el contraste externo dio
FPR 95,8 % sobre `ham` histórico. v2, entrenado con `ham` Enron, obtuvo 0 % de
FPR proxy en CEAS pero perdió los 276/276 BEC-2 sintéticos. Ambos informes
son `shadow` únicamente y son rechazados en `assist` aun si el archivo de
pesos está correctamente fijado. La puerta de `assist` exige estado
`AUTHORIZED_TRAINING_VALIDATION`, `AUTHORIZED_TEST_EVALUATED`, al menos 20
positivos y 100 negativos, recall >= 60 % y FPR <= 5 %. Es un chequeo de
software, no una certificación científica. Guía y reproducción:
`SOFTWARE_PUBLICO_V2.md`.

Solo cargar artefactos `joblib` generados localmente y aprobados: el formato
puede ejecutar código al deserializar. Un hash incorrecto, archivo ausente o
reporte inválido o sin hash detienen el análisis en lugar de dar un resultado falso. Un
correo ya analizado no se reanaliza por cambiar el modo: el endpoint conserva
su idempotencia. Para evaluar un modelo nuevo usar mensajes nuevos y una
revisión independiente, sin recalibrar sobre el test sintético.
