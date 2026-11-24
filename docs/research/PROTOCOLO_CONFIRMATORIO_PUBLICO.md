# Protocolo prospectivo para un resultado confirmatorio

**Estado: herramienta preparada; faltan etiquetas de una persona.** Este protocolo se fijó después de
examinar el corpus Kaggle de 60.000 correos. Los ensayos anteriores de v1/v2
sobre todos sus registros permanecen como diagnósticos exploratorios; sus
resultados **no** se renombran como prueba final. Un modelo nuevo v3 y su
test se tratarán como un estudio distinto, con esta exploración previa
declarada.

## Pregunta y población antes de entrenar

**Opción BEC (prioritaria para este proyecto):** entre correos sintéticos de
este corpus con categoría BEC identificable, ¿alcanza un clasificador textual
recall binario >=0,60 manteniendo FPR <=0,05 sobre legítimos sintéticos
comparables? La unidad es el **correo**; campaña/plantilla o familia generativa
es la unidad de independencia. Los `Label=1` de otras categorías de phishing
**no** son positivos BEC. El alcance de la conclusión sería **BEC sintético**,
no incidentes empresariales reales. El test es del **clasificador textual
congelado**, no de las reglas ni de las alertas del sistema híbrido completo.

Antes de crear splits se requiere el mapa del autor `fila → categoría` y, si
están disponibles, `fila → plantilla/campaña` o semilla generativa. El CSV
publicado solo tiene `Subject`, `Body`, `Label`: sin ese mapa no se puede
construir la verdad de terreno BEC original. **Se implementó la alternativa
de un evaluador:** seleccionar determinísticamente, con semilla `20261121`,
2.000 mensajes `Label=1` y 1.000 `Label=0` (legítimos según el publicador,
sin fingir que fueron revisados). Antes de cualquier anotación BEC se
reservaron **grupos completos** para train/validation/test con la etiqueta
phishing/benigno publicada, nunca con scores del clasificador. Una regla
versionada `triage-text-v2` sugirió 71 posibles BEC, 807 dudosos y 1.122
otros phishing claros entre los 2.000. La versión previa pedía 1.200
decisiones humanas; **antes de la primera anotación y sin abrir el test** se
fijó una enmienda de supervisión débil: **56 posibles BEC de train reciben
etiqueta automática**, identificada como `AI_RULE_DRAFT_V1_NOT_ADRIAN`, y
los otros 1.353 phishing de train se **excluyen**. El evaluador revisará
**todos** los 591 phishing de validation/test, sin ver borradores, y elegirá
`BEC`, `OTHER_PHISHING` o `UNCERTAIN`, subtipo y justificación. No se atribuirá
al evaluador ninguna etiqueta automática ni consenso entre revisores que
no existió. Si validation no reúne 10 BEC revisados o test menos de 20 BEC
y 100 legítimos, el estudio se detiene.
Los borradores se generaron únicamente para los **1.409 phishing de train**
(56 posibles BEC, 800 otro phishing y 553 indeterminados). **No se produjeron
borradores de validation ni de test.**

**Opción phishing (si no aparecen categorías BEC):** usar los 30.194 `Label=1`
como phishing genérico y los 29.806 `Label=0` como legítimos sintéticos; cambiar
explícitamente pregunta, métricas y título del artículo. Eso constituye otra
tarea, no demuestra detección BEC.

## Procedimiento congelado para el estudio nuevo

1. Guardar SHA-256 del CSV (versión Kaggle inspeccionada), rúbrica, regla de
   triaje y semilla; eliminar duplicados exactos antes del muestreo. El paquete
   de 2.000 se baraja y no contiene scores. La firma vincula cada decisión
   al texto revisado.
2. Antes de categorizar BEC, unir mensajes con asunto normalizado igual o
   similitud Jaccard de trigramas >=0,85 y separar **grupos heurísticos
   completos** en train/validation/test (objetivo 70/15/15). Revisar todos
   los phishing de validation/test **sin sugerencia automática**. En train,
   usar solo los 56 posibles BEC de la regla como **etiquetas débiles**;
   excluir los otros 1.353 phishing de train en vez de declararlos negativos
   BEC. Tras completar los 591 casos humanos requeridos, congelar sus
   decisiones y los 1.000 legítimos publicados. El informe separará
   `weak_train_BEC`, `human_validation_BEC` y `human_test_BEC`. No disponer
   de la plantilla original del autor limita la garantía de independencia.
3. Solo train ajusta TF-IDF y regresión logística balanceada. La búsqueda
   predefinida tiene 4 configuraciones: n-gramas (1,1)/(1,2) × `C` 0,1/1,0
   en 3 folds agrupados, seleccionando recall medio sujeto a FPR media <=0,05.
   Solo validation elige el umbral de `{0,4; 0,5; 0,6; 0,7; 0,8; 0,9; 0,95}`
   bajo recall >=0,60 y FPR <=0,05. Si no hay configuración factible, no se
   abre test. Los resultados v1/v2 ya vistos en el corpus no se usan para
   seleccionar v3.
4. El test se reserva y se puntúa **una vez** tras fijar modelo, umbral y
   código. Un lock persistente por hash del manifiesto congelado bloquea un
   segundo intento, incluso con pesos diferentes. El informe no guarda
   correos ni predicciones individuales.
5. Reportar por clase y grupo TP, FP, TN, FN, recall, FPR y precisión con sus
   denominadores; calcular incertidumbre por remuestreo de grupos si hay
   suficientes grupos independientes. La precisión de un conjunto balanceado
   artificial no equivale a precisión operativa. Registrar también negativos
   difíciles y desempeño por familia BEC, sin inventar familias ausentes.
6. Criterio primario: recall binario >=0,60 con FPR <=0,05. Si FPR supera 0,05 o
   faltan positivos/grupos suficientes, reportar el fallo y **no promover**
   `assist`. El modo `shadow` permite observar sin afectar las alertas.

Herramientas y comandos: `docs/research/GUIA_ETIQUETADO_UN_REVISOR.md`;
implementación `backend/research/bec_training/single_review.py`,
`triage_rules.py`, `triage_workflow.py`, `ai_drafts.py`,
`weak_supervision.py`, `single_review_training.py` y
`backend/research/single_review_app.py`.
Justificación bibliográfica de cada rama de la regla, y límites de lo que
las fuentes **no** prueban: `docs/research/FUNDAMENTO_RUBRICA_BEC.md`.

Ni el número total de 60.000 ni un buen resultado sobre otros tipos de
phishing sustituyen positivos BEC identificables. Para una afirmación sobre
**BEC real** seguirá siendo necesario un corpus autorizado de incidentes
confirmados y legítimos comparables del mismo entorno; un experimento
confirmatorio sintético es científico, pero su población es sintética.
