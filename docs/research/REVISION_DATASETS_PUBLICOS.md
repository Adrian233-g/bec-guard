# Revisión de datasets públicos para BEC Guard

Fecha de revisión: 2026-11-20. Esta revisión incluyó una **prueba diagnóstica
externa** con el modelo v1 congelado, sin reentrenarlo en esa prueba ni
incorporar correos externos al repositorio. Se realizó después un
reentrenamiento público v2 **exploratorio**, descrito en `SOFTWARE_PUBLICO_V2.md`.
Los CSV se consultaron fuera del proyecto; el archivo
de resultados contiene únicamente agregados y hashes.

## Decisión

Ninguno de los datasets revisados representa por sí solo correo empresarial
real con BEC y legítimos comparables. BEC-2 es un **benchmark sintético
externo**; Enron/CEAS 2008 proporcionan negativos etiquetados *ham* por sus
publicadores, no negativos difíciles BEC adjudicados. Su combinación permite
medir una **transferencia diagnóstica entre fuentes**, no eficacia operativa
ni precisión extrapolable a la prevalencia real. No alimentan el loader
autorizado ni los splits del estudio principal.

El resultado fue decisivo: el clasificador congelado identificó los 276
positivos BEC-2, pero señaló 31.396/32.763 mensajes *ham* externos (FPR
descriptiva 95,8 %). Por ello, el 0 % de falsos positivos del test generado
localmente **no se generalizó**. No se promovió el modo `assist`.

## Criterios de selección

Se exigieron asunto y cuerpo de correo, etiquetas con semántica BEC/legítimo,
origen independiente del generador propio, licencia comprobable, acceso
reproducible y unidades de agrupación por campaña/hilo/plantilla. Sin ambas
clases y grupos comparables, se informan métricas **por fuente**; una matriz
de confusión formada por distintas fuentes tiene sesgo de procedencia y su
precisión depende de la mezcla artificial elegida.

| Conjunto | Unidad / origen | Clases pertinentes | Acceso y licencia | Uso defendible |
| --- | --- | --- | --- | --- |
| Dube BEC-2 | Asunto y cuerpo; BEC sintético GPT-3.5, 4 familias | 276 positivos humanos, 3 neutrales; 0 negativos | CSV público; AGPL-3.0 del repositorio, licencia de datos no separada | Recall descriptivo externo, no FPR |
| Champa et al., Enron y CEAS 2008 | Asunto y cuerpo; correo histórico *ham* y spam/phishing | Ambas etiquetas 0/1, pero 1 **no significa BEC** | Zenodo DOI 10.5281/zenodo.8339691; CC BY 4.0 | FPR descriptiva sobre *ham*; no inferir validez BEC |
| Invictus IR M365 | 9.608 eventos UAL reales de incidentes BEC, sin cuerpos | Eventos, no mensajes etiquetados binariamente | GitHub, CC BY 4.0 | Contexto de amenaza; incompatible con TF-IDF de correo |
| Adjei, Kaggle | 4.211 BEC sintéticos Gemini 2.5 Flash; 30 % con ofuscación | Solo positivos | Kaggle, CC BY 4.0 | Robustez sintética, no FPR |
| `rahuljangir78`, Kaggle | 1.000 mensajes con asunto y cuerpo; origen no explicado | Etiquetas 0/1 sin criterio documentado | Kaggle, Apache 2.0 | Excluir: trazabilidad insuficiente |
| Almutairi, tesis 2025 | 21 semillas BEC, 1.050 sintéticos LLaMA, Enron y phishing | Mixto según la tesis | Repositorio citado sin acceso público el 20/11/2026 | No reproducible en esta revisión |

## BEC-2

Fuente principal: `r-dube/bec`, repositorio público del autor.

- Archivo: `data/BEC-2-human.csv`.
- Tamaño observado: 279 filas de datos.
- Campos: `subject`, `body`, `Model`, `Q1`, `Q2`, `Q3`, `Q4`, `Human`.
- Etiqueta humana: 276 `positive`, 3 `neutral`, 0 `negative`.
- Etiqueta del modelo: 262 `positive`, 17 `neutral`.
- Acuerdo `Model`/`Human`: 261/279 filas (93.5%), con solo tres casos humanos no positivos.
- Concentración: cuatro familias de escenario aproximadamente: wire transfer/Jennifer (68), cell-number/Dakota (65), invoice/Sue (75) y fund-transfer/Alvin (71).
- Diversidad: 77 asuntos exactos y 258 cuerpos únicos; se repiten asuntos, cuerpos y plantillas.
- Origen: `bec_gen.ipynb` muestra generación de variaciones con GPT-3.5-turbo; `bec_val.ipynb` muestra validación mediante un rubricado LLM de negocio, autoridad, acción y urgencia.
- Los datos no declaran `group_id`, campañas, hilos ni una separación independiente adecuada para evitar fuga por plantilla.
- La distribución no permite estimar FPR ni especificidad **dentro de BEC-2** porque no contiene negativos humanos. El archivo `BEC-1-human.csv` tiene 20 positivos; `bec_examples_split.csv` aporta solo 6 ejemplos de otra composición y no cambia este límite.

### Uso permitido en este proyecto

Se usó únicamente como prueba descriptiva de transferencia a paráfrasis
sintéticas externas: 276/276 detectados con el umbral 0,5 congelado. Esta
exhaustividad **no estima** detección de ataques reales ni independencia entre
las cuatro familias de plantilla. No se entrenó ni ajustó un nuevo umbral.

No se hará un adaptador al contrato `ResearchCase` por ahora: faltan grupos,
metadatos de procedencia, anotación binaria completa y una autorización de uso
que cubra también los correos derivados de Enron presentes en el repositorio.

## Enron y CEAS 2008 curados por Champa et al.

El depósito Zenodo publicó 11 CSV (1995–2022) bajo CC BY 4.0. Se examinaron
los archivos originales `Enron.csv` (44.837.129 bytes) y `CEAS_08.csv`
(67.902.056 bytes). Se filtró **exclusivamente** `label=0` (*ham*); el valor
`label=1` es spam/phishing, no BEC. La entrada al modelo fue exactamente
`subject + "\n" + body`, igual que en el programa funcional. Se excluyeron
duplicados exactos normalizados dentro de cada fuente antes de inferir. Las
etiquetas de origen no fueron revisadas por el equipo del proyecto.

| Fuente | Filas / etiquetas originales | *Ham* evaluado | FP | TN | FPR descriptiva |
| --- | ---: | ---: | ---: | ---: | ---: |
| Enron | 29.767 (15.791 `0`, 13.976 `1`) | 15.474 (317 duplicados excluidos) | 14.976 | 498 | 96,8 % |
| CEAS 2008 | 39.154 (17.312 `0`, 21.842 `1`) | 17.289 (23 duplicados excluidos) | 16.420 | 869 | 95,0 % |
| Ambas | — | 32.763 | 31.396 | 1.367 | 95,8 % |

`Nazario.csv` del mismo depósito contenía 1.565 registros, todos con
`label=1` y URL; no se interpretó phishing genérico como BEC. Enron y CEAS
son corpus históricos de distinta procedencia y no constituyen una muestra
de legítimos contemporáneos de una organización. No se midieron reglas ni
modo `assist` sobre estos CSV: carecen de los metadatos/contexto necesarios.

## Otros candidatos

| Fuente | Utilidad | Motivo de exclusión del experimento principal |
| --- | --- | --- |
| Enron Email Dataset | Negativos/legítimos corporativos y análisis de dominio | No tiene etiquetas BEC confiables; no puede convertirse en negativo por defecto. |
| SpamAssassin Public Corpus | Spam/ham auxiliar | Spam no es equivalente a BEC y produce un objetivo distinto. |
| MeAJOR Corpus | Phishing multifuente auxiliar | Phishing no es BEC; requiere otra taxonomía y control de procedencia. |
| `r-dube/bec` BEC-1/BEC-2 | Benchmark de generación/paráfrasis | Sintético, altamente templado y sin clase negativa humana suficiente. |
| Invictus IR `o365_dataset` | Eventos UAL reales de BEC; `auditrecords.7z` (598.237 bytes) | No contiene asunto/cuerpo; la unidad de análisis no coincide con el clasificador. |
| Adjei, *Adversarial BEC Email Dataset* | Dos versiones (limpia y ofuscada) de 4.211 positivos sintéticos | No ofrece clase legítima; no permite FPR. |
| `rahuljangir78`, *business_email_compromise_dataset* | 1.000 filas, 11 columnas; sin descripción en la ficha | La fuente, el criterio de etiquetas y la generación no están documentados. |
| Almutairi, *synthetic-bec-dataset* | La tesis declara 21 semillas reales, 1.050 BEC generados y otros corpus | El enlace citado devolvió 404; la cuenta del autor no mostró repositorios públicos. |

## Prueba ejecutada y lectura de métricas

`backend/research/bec_training/external_benchmark.py` verificó los SHA-256 del
modelo y del informe **antes** de cargar `joblib`; no cambió pesos ni umbral.
El agregado quedó en
`artifacts/research/training_v1/external_benchmark.json` (ignorado por Git).
Entradas: BEC-2 `ae818988b4fce7d25a8d02ac46825e4ca80f39b1b0d770017e82f4fd3463064c`,
Enron `11f28a5bdd3603f1829681ab6b55071b5f9af781b4e6694e39216b2996a96883`
y CEAS `22375e7d5f5a8229dbe987914ee9b3705656c590038662a7df6054629b376074`
(SHA-256). Sin filas vacías en las clases seleccionadas y sin duplicados
exactos de asunto+cuerpo en BEC-2. Se aplicó el umbral congelado 0,5.

La mezcla **artificial** de las tres fuentes dio TP 276, FN 0, FP 31.396,
TN 1.367, recall 100,0 %, FPR 95,8 % y precision 0,87 % con prevalencia
construida de 0,84 %. Esas dos últimas cifras **no representan** prevalencia
ni precisión operativas; son propiedades de la mezcla BEC sintético + *ham*
histórico. No se estimaron IC ni significación con mensajes tratados como
independientes: las familias BEC y los orígenes comparten dependencias.

El ensayo posterior v2 incorporó `ham` Enron al entrenamiento; en CEAS obtuvo
0/17.289 falsos positivos, pero en BEC-2 detectó 0/276 positivos. Ambas
fuentes ya se habían inspeccionado con v1, de modo que ese segundo resultado
fue exploratorio y no constituyó test final independiente. El informe registró
`FAILS_PROXY_TARGETS` y los pesos v2 quedaron limitados a `shadow`.

## Tres fuentes adicionales propuestas por el usuario

Se inspeccionaron sus fichas y, cuando había archivo disponible, sus etiquetas
y solapamientos por el texto completo normalizado (mayúsculas/minúsculas y
espacios unificados). **No** se reinterpretó la etiqueta «spam/phishing» como
«BEC». Los archivos se leyeron fuera del repositorio; no se añadieron mensajes
ni pesos a Git.

| Opción | Inspección verificable | Decisión para el estudio BEC |
| --- | --- | --- |
| [Kaggle, N. A. Alam, *Phishing Email Dataset*](https://www.kaggle.com/datasets/naserabdullahalam/phishing-email-dataset) | Ficha API: ~82.486 mensajes agregados (42.891 spam, 39.595 legítimos); integra **Enron, Ling, CEAS, Nazario, Nigerian Fraud y SpamAssassin**. Licencia declarada CC BY-SA 4.0; tamaño publicado 261.289.686 bytes. | No hay etiqueta BEC. Comparte fuentes de origen con los CSV ya usados; no se puede presentar como muestra BEC independiente ni transformar sus positivos de spam en BEC. Sirve para una tarea **distinta** de phishing/spam. |
| `C:\Users\Usuario\Downloads\CEAS_08.csv.zip` | ZIP íntegro, 19.957.973 bytes; archivo interno `CEAS_08.csv` de 67.902.056 bytes, SHA-256 `22375e7d5f5a8229dbe987914ee9b3705656c590038662a7df6054629b376074`. Sus 39.154 filas: 21.842 `1`, 17.312 `0`. | El SHA-256 del CSV interno coincidió **exactamente** con el CEAS previamente evaluado. Es la misma fuente, no una tercera prueba. |
| [Hugging Face, `ealvaradob/phishing-dataset`](https://huggingface.co/datasets/ealvaradob/phishing-dataset) | Ficha Apache-2.0: mezcla URL, SMS, correo y HTML. Se inspeccionó **solo** `texts.json` (52.079.789 bytes, SHA-256 `2479fdb94abb59332cc747f7b823a1651921b9828240c5dad0ffdba66ab02581`): 20.137 registros `text,label` (12.465 `0`, 7.672 `1`), 20.000 textos únicos tras normalizar, uno vacío. | Es phishing/benigno, **no BEC**. De esos textos, **8.794** coinciden exactamente con `subject + body` de `Enron.csv` de Champa (4.607 `0`, 4.187 `1`; sin contradicciones de etiqueta). No constituye prueba independiente respecto de Enron. `texts.json` no separa asunto y cuerpo; los conjuntos combinados mezclan modalidades no compatibles con el clasificador de correo. |

Hugging Face incluye en su ficha código de carga con `trust_remote_code=True` y
un repositorio de 1,7 GB; la inspección leyó directamente el JSON de correo,
**sin ejecutar** ese código ni descargar URL/SMS/HTML. Los 11.343 registros
restantes de `texts.json` no son, por el hecho de no coincidir exactamente,
independientes: pueden compartir origen o variantes de mensajes. Un subconjunto
benigno deduplicado podría servir **solo** como otra prueba exploratoria de
falsos positivos, no de recall, precisión o eficacia BEC real.

**Conclusión de las tres opciones:** aportan ejemplos adicionales de la tarea
spam/phishing y permiten auditar fuga entre datasets, pero ninguna proporciona
correos BEC reales etiquetados junto con legítimos comparables. Las métricas
ya publicadas para v1/v2 no deben recalcularse como si estos archivos fueran
un test nuevo. Si el objetivo pasa a ser detección genérica de phishing, hay
que entrenar/evaluar un modelo para **esa** etiqueta y cambiar la pregunta y
el manuscrito; no basta con renombrar BEC.

## Corpus adicional de 60.000 correos generado con IA

[Kaggle, *Zero-Day Phishing Emails Corpus*](https://www.kaggle.com/datasets/mutahirshaukat/zero-day-phishing-emails-corpus)
se inspeccionó directamente mediante la descarga pública del ZIP, sin añadir
correos al repositorio. La ficha declara CC0, 60.000 correos generados con IA,
10 categorías de phishing, 7 tipos legítimos y ejemplos que incluyen BEC.
El ZIP descargado midió 7.386.164 bytes, SHA-256
`853094590bd2a40fc51503db0f3cac02ed04c68481b23fcdfee9f9fd20764792`;
su CSV interno `Zero-Day_Phishing_Emails_Corpus.csv` midió 31.427.587 bytes.

Se comprobaron **60.000 filas**, columnas `Subject`, `Body`, `Label`, sin
asuntos ni cuerpos vacíos: **30.194 `1` (phishing genérico)** y **29.806 `0`
(legítimo sintético)**. La proporción exacta difirió ligeramente del
«30.000/30.000» anunciado en la ficha. Hubo 59.677 textos asunto+cuerpo
únicos normalizados (323 repeticiones, sin conflictos de etiqueta). **No se
encontraron coincidencias textuales exactas** con el fixture de 500 casos,
BEC-2, Enron ni CEAS ya usados; esto respaldó un origen textual nuevo, aunque
no demostró independencia de plantillas o del proceso generativo.

**Uso defendible:** evaluación externa *sintética* de falsos positivos sobre
los 29.806 legítimos y de la frecuencia con que el modelo marca correos
phishing generales. `Label=1` **no identifica BEC**; la ficha menciona diez
categorías, pero el CSV no contiene columna de categoría ni IDs que permitan
separarlas. No se pueden calcular recall, precisión ni F1 **de BEC** tomando
los 30.194 phishing como positivos BEC. Para ese análisis se necesita el mapa
por fila `id → categoría/escenario` del generador o una anotación explícita
de un subconjunto BEC con criterios fijados antes de evaluar. Aun con esa
categoría, solo se estimaría transferencia a BEC **sintético externo**, nunca
eficacia sobre incidentes reales.
El diseño para convertir esa opción en un **nuevo estudio confirmatorio v3**,
sin reutilizar como test intacto los resultados v1/v2 ya observados, quedó
fijado en `PROTOCOLO_CONFIRMATORIO_PUBLICO.md`.
La selección ciega de 2.000 phishing y 1.000 benignos ya se materializó fuera
de Git. Una enmienda prospectiva agrupó y reservó train/validation/test
**antes** de anotar, y fijó la regla `triage-text-v2` que priorizó **1.200** revisiones humanas
(591 de validación/test y 609 de train). Los **800** descartes claros de train
quedaron excluidos, no etiquetados como si fueran decisiones del usuario.
En una segunda enmienda, también **anterior a cualquier etiqueta humana o
test v3**, se fijó la supervisión débil de train: **56 posibles BEC automáticos
con fuente `AI_RULE_DRAFT_V1_NOT_ADRIAN`**, 1.353 phishing de train excluidos
y **591 validation/test para revisión humana sin sugerencias**. El uso de
etiquetas débiles solo para entrenar se declara en
`PROTOCOLO_CONFIRMATORIO_PUBLICO.md` y `GUIA_ETIQUETADO_UN_REVISOR.md`.
Instrucciones en `GUIA_ETIQUETADO_UN_REVISOR.md`. Todavía **no** hay
etiquetas BEC humanas para validation/test ni se abrió el test.

Se ejecutó además un **stress test reproducible sin reentrenar** mediante
`backend/research/bec_training/auxiliary_phishing_benchmark.py`: tras eliminar
duplicados exactos quedaron **29.508 legítimos sintéticos** y **30.169 phishing
genéricos**. Con el umbral congelado 0,5, v1 señaló 29.508/29.508 legítimos
(FPR sintética 100 %) y 30.169/30.169 phishing; v2 señaló **0/29.508**
legítimos (FPR sintética 0 %) y **0/30.169** phishing. Es el patrón degenerado
«todo positivo» frente a «todo negativo», no evidencia de eficacia BEC. La
fracción de phishing señalada **no es recall BEC**: el CSV carece de ese
subtipo. El agregado con hashes se guardó localmente en
`artifacts/research/zero_day_phishing_stress.json` (ignorado por Git), sin
cuerpos ni predicciones individuales. Esta fuente no coincidió exactamente
por asunto+cuerpo normalizado con fixture propio, BEC-2, Enron o CEAS, aunque
la ausencia de duplicados exactos no prueba independencia de plantillas.

Para obtener métricas BEC **sintéticas** con este corpus, lo más rápido sería
pedir al publicador el archivo o campo que asigne a **cada fila** su categoría
entre las diez declaradas, junto con familia/plantilla o semilla de generación.
Entonces se reservarían familias completas como test y se puntuaría la
categoría BEC por separado. La etiqueta binaria actual solo alcanza para un
experimento de phishing/legítimo, que requeriría **otro objetivo y otro modelo**.

## Licencia y privacidad

El repositorio `r-dube/bec` declara AGPL-3.0 para el repositorio, pero no
presenta una licencia separada y clara para cada dataset. Esa licencia no
resuelve automáticamente los derechos de los correos de terceros, el material
derivado de Enron ni los datos personales incluidos en ejemplos financieros.
No se debe redistribuir ni versionar el contenido sin revisar la procedencia y
las condiciones aplicables.

## Fuentes consultadas

- https://github.com/r-dube/bec
- https://raw.githubusercontent.com/r-dube/bec/main/data/BEC-2-human.csv
- https://raw.githubusercontent.com/r-dube/bec/main/bec_gen.ipynb
- https://raw.githubusercontent.com/r-dube/bec/main/bec_val.ipynb
- https://raw.githubusercontent.com/r-dube/bec/main/bec_cm.ipynb
- https://doi.org/10.1007/s11416-024-00544-y
- https://www.cs.cmu.edu/~enron/
- https://spamassassin.apache.org/old/publiccorpus/
- https://arxiv.org/pdf/2507.17978
- https://doi.org/10.5281/zenodo.8339691
- https://github.com/invictus-ir/o365_dataset
- https://www.kaggle.com/datasets/yoadjei/adversarial-bec-email-dataset
- https://www.kaggle.com/datasets/rahuljangir78/business-email-compromise-dataset
- https://eprints.soton.ac.uk/505289/1/Almutairi_PhD_Thesis_2025_PDF-A3b.pdf
- https://github.com/AmirahCoding/synthetic-bec-dataset (404 el 20/11/2026)
- https://www.kaggle.com/datasets/naserabdullahalam/phishing-email-dataset
- https://www.kaggle.com/api/v1/datasets/view/naserabdullahalam/phishing-email-dataset
- https://huggingface.co/datasets/ealvaradob/phishing-dataset
- https://huggingface.co/datasets/ealvaradob/phishing-dataset/tree/main
- https://www.kaggle.com/datasets/mutahirshaukat/zero-day-phishing-emails-corpus
- https://www.kaggle.com/api/v1/datasets/view/mutahirshaukat/zero-day-phishing-emails-corpus

## Siguiente criterio de aprobación

**Solución inmediata sin revisores adicionales:** publicar el estudio como
implementación y **diagnóstico de transferencia fallida**, con métricas
separadas por fuente y sin atribuir eficacia real. Las etiquetas públicas
sirven para este diagnóstico reproducible; no sustituyen una verdad de
terreno BEC contemporánea. Para una afirmación futura de eficacia BEC real,
se necesitarán mensajes pertinentes con ambas clases, procedencia/permiso,
grupos por campaña e identificación confiable de las etiquetas. El protocolo
original sigue requiriendo revisión ciega para ese estudio distinto, pero
esta prueba pública no se presentó como tal.
