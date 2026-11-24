# Borrador de artículo: integración reproducible de un clasificador de correo BEC en un sistema híbrido

**Tipo de contribución:** implementación y demostración técnica con corpus sintético.
**Estado:** borrador listo para revisión editorial; **no** es un estudio de precisión en correo empresarial real.

## Resumen

Se presenta una arquitectura de detección de compromiso de correo empresarial
(BEC) que combina reglas con contexto organizacional, análisis semántico opcional
y un clasificador supervisado local. Se implementó un pipeline reproducible de
partición por grupos, búsqueda de hiperparámetros mediante validación cruzada y
despliegue configurable del clasificador en modos `disabled`, `shadow` y
`assist`. Para verificar el flujo se generaron 500 mensajes **sintéticos**,
incluidos 120 candidatos BEC, 380 legítimos y 100 negativos difíciles. En el
test sintético reutilizado (18 BEC, 56 legítimos), el clasificador produjo
18 verdaderos positivos y ningún falso positivo, mientras que las reglas
produjeron 4 verdaderos positivos y 8 falsos positivos. El modo `assist`
produjo 18 verdaderos positivos y 8 falsos positivos: su tasa de falsos
positivos fue 14,3 %, por encima del objetivo predeclarado de 5 %. Las
familias de plantillas se repiten entre particiones y las etiquetas sintéticas
no fueron adjudicadas por personas. Por tanto, los resultados solo verifican
el funcionamiento técnico y no permiten inferir eficacia frente a BEC real.

**Palabras clave:** BEC; seguridad del correo; clasificación supervisada;
evaluación reproducible; datos sintéticos; integración híbrida.

## 1. Introducción y objetivo

Las solicitudes fraudulentas de pago y de información empresarial plantean un
problema de detección que combina señales de contenido y contexto. El objetivo
de este trabajo técnico es describir una implementación reproducible y
comprobar que el clasificador entrenado puede ejecutarse dentro del análisis
principal sin confundir la probabilidad del modelo con el score ordinal del
producto. La eficacia frente a correo real constituye una pregunta posterior,
descrita en `PROTOCOLO_FASE_1.md`, y **no se prueba aquí**.

## 2. Arquitectura

El backend recibe un correo mediante su contrato `EmailIngestRequest`. El
servicio `app/services/email_analysis.py` calcula señales por reglas y contexto,
y llama al analizador semántico cuando está configurado. El servicio
`app/services/trained_model.py` carga un modelo local `joblib` únicamente con
ruta y SHA-256 configurados; el modelo utiliza asunto y cuerpo y devuelve una
probabilidad de la clase BEC. El umbral viene del informe de entrenamiento.
Una predicción positiva equivale a un **piso ordinal de alerta de 50**, no a
una probabilidad calibrada de riesgo. En `shadow` se registra sin cambiar la
decisión; en `assist` el score final es el máximo del score anterior y el piso
del modelo, tanto para análisis semántico completo como en fallback. El
desglose persistido registra modo, probabilidad, score y hash del artefacto.
La activación está descrita en `INTEGRACION_MODELO.md`.

## 3. Materiales y métodos

**Datos.** `generate_corpus.py` produce mensajes ficticios en dominios
reservados; `create_training_dataset.py` los exporta con estado
`SYNTHETIC_GENERATED`. No se trata de correos capturados de ataques. El corpus
contiene 250 grupos de dos mensajes relacionados; el particionador reserva
350 mensajes para train, 76 para validation y 74 para test. Los grupos no
cruzan particiones. Se usa el contexto ficticio de `datasets/context.json`.
Aunque los grupos declarados están separados, **las familias de plantillas
comparten vocabulario y estructura entre train y test**; el resultado puede
estar inflado por esas regularidades y por etiquetas definidas en la generación.

**Aprendizaje.** El clasificador usa TF-IDF de palabras y regresión logística
L2 (`liblinear`, `tol=1e-4`, máximo 1000 iteraciones), con 12 combinaciones
predefinidas de n-gramas, `C` y balanceo y tres folds agrupados en train.
La selección de umbral se hace sobre validation entre 0,4/0,5/0,6; el modelo
guardado seleccionó unigramas, `C=0.1`, pesos balanceados y umbral 0,5. El
test no se usa para ajustar estos parámetros.

**Comparación descriptiva.** `article_evidence.py` vuelve a puntuar el mismo
test sintético que ya se había evaluado en el informe de entrenamiento; no
constituye una segunda prueba independiente. Compara baseline mayoritario,
reglas C1 a umbral de alerta 50, modelo solo a su umbral y reglas + modelo en
`assist`. Se reportan TP, FP, TN, FN, recall, FPR y precision, con BEC como
clase positiva. No se usó LLM real; C2/C3 y comparaciones estadísticas con IA
quedan `NOT_RUN`. No se calcularon intervalos ni pruebas de significación
como si este fixture midiera generalización.

**Recorrido funcional.** En una base PostgreSQL 18 local aislada se aplicaron
las migraciones 0001–0019. Se recorrieron endpoints HTTP de autenticación,
ingestión, análisis, consulta y alertas utilizando el artefacto entrenado, con
el proveedor LLM explícitamente desactivado. Los resultados agregados se
guardaron en `http_walkthrough_verified.json`.

## 4. Resultados observados (solo test sintético reutilizado)

| Condición | TP | FP | TN | FN | Recall | FPR | Precision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mayoría legítima | 0 | 0 | 56 | 18 | 0,0 % | 0,0 % | Indefinida |
| Reglas C1 | 4 | 8 | 48 | 14 | 22,2 % | 14,3 % | 33,3 % |
| Clasificador TF-IDF | 18 | 0 | 56 | 0 | 100 % | 0,0 % | 100 % |
| Reglas + clasificador (`assist`) | 18 | 8 | 48 | 0 | 100 % | 14,3 % | 69,2 % |

En el test hay ocho negativos difíciles y **los ocho** recibieron una alerta
falsa de las reglas y de `assist`. Por ello la combinación no cumple el FPR
objetivo de 5 % establecido en el protocolo. Estos números corresponden solo
al fixture y no son estimaciones de rendimiento real.

En el recorrido HTTP, `shadow` mantuvo score 16 y cero alertas; `assist`
elevó el score de 16 a 50 y creó una alerta. Ambos análisis respondieron 200,
se recuperaron mediante GET y fueron idempotentes; el detalle de la alerta
referenció el análisis correspondiente. Esto confirma la conexión técnica del
modelo con la API y la base, no eficacia frente a BEC real.

## 5. Validez y limitaciones

1. Los 500 textos son artificiales y de plantillas limitadas; existe
   similitud de familia entre particiones pese a la separación por `group_id`.
2. `SYNTHETIC_GENERATED` no equivale a `ADJUDICATED`; faltan dos revisores
   humanos y adjudicación para el paquete ciego del corpus candidato.
3. BEC-2 es igualmente sintético y carece de suficientes negativos humanos;
   no se mezcló con este experimento (`REVISION_DATASETS_PUBLICOS.md`).
4. La muestra de test es pequeña (18 positivos, 56 negativos) y fue reutilizada
   para esta comparación descriptiva. No estimar generalización ni optimizar
   políticas sobre estos resultados.
5. La comparación no ejecutó proveedor LLM ni calculó costos de inferencia.
6. La migración `0019` y la persistencia de `assist` se probaron en una
   instancia local **aislada y temporal** de PostgreSQL 18; esto comprueba la
   integración de software, no el comportamiento de un despliegue real ni la
   validez del modelo sobre correo externo.

## 6. Conclusión y trabajo siguiente

El laboratorio y el backend permiten entrenar, versionar y ejecutar un
clasificador con trazabilidad de score. Las pruebas automatizadas con
PostgreSQL temporal (655 aprobadas, 4 omitidas) verifican migraciones,
persistencia, API y alertas sin llamar a proveedores externos. El experimento sintético verifica el
pipeline y evidencia que el modo `assist` **no** satisface el objetivo de FPR
en este fixture. La siguiente fase requiere una muestra independiente con
permiso, ambas clases y grupos de campañas/plantillas y revisión ciega de
etiquetas. Solo después
podrán contrastarse hipótesis de detección sobre correo empresarial real.

## Referencias verificables y material de reproducción

- Protocolo predeclarado: `docs/research/PROTOCOLO_FASE_1.md`.
- Evidencia agregada calculada: `artifacts/research/training_v1/article_evidence.json`
  (local, ignorada por Git; generar con `PAQUETE_ARTICULO.md`).
- Recorrido HTTP y base aislada:
  `artifacts/research/training_v1/http_walkthrough_verified.json`.
- Dataset SHA-256: `0b51b2032004c2277bdff2a7f63c533512e0a5da2fd04307c705f3ba23cfc292`.
- Modelo SHA-256: `7a163d9141c3404ff28d428e2a7f4b14be4010c26811899c36a5840c0cdd0a06`.
- Artículo sobre BEC-2, para contextualizar límites de datos sintéticos:
  Dube, R. (2025), *Building a business email compromise research dataset with
  large language models*, DOI: https://doi.org/10.1007/s11416-024-00544-y.

**Antes de enviar a una revista:** adaptar formato y bibliografía a sus
normas; no convertir las métricas sintéticas en afirmaciones de desempeño real.
