# Estudio BEC sintético con un evaluador: instrucciones de ejecución

La cohorte inicial **ya se generó** en
`artifacts/research/bec_single_v3/` (fuera de Git). Se eligieron con semilla
`20261121` **2.000 phishing** y **1.000 benignos** según
la etiqueta publicada. El paquete `blind_packet.jsonl` presenta a la persona
que etiqueta solo ID, asunto y cuerpo: no muestra clase original, scores ni
predicciones. Su SHA-256 es
`c9b67e8a7e51ec45c1236d5e42d5146d6e7658f42f360f2e6f452f4ed4f05aea`.
El CSV original se lee desde
`C:\Users\Usuario\Downloads\Zero-Day_Phishing_Emails_Corpus.csv` y no se
copia al proyecto. Una regla de triaje separó grupos antes de ver etiquetas
BEC. La pasada automática guardó **1.409 borradores SOLO de train**, identificados como
`AI_RULE_DRAFT_V1_NOT_ADRIAN` (56 posibles BEC, 800 otro phishing y 553
indeterminados); **no son etiquetas humanas**. **No se generaron borradores de
validation/test.** El método actual usa **56
posibles BEC del train como etiquetas débiles**, excluye los otros 1.353
phishing de train y exige que **ADRIAN revise los 591 phishing de
validation/test**. Los borradores de estos 591 no se muestran al evaluador.
La rúbrica y reglas congeladas están en
`PROTOCOLO_CONFIRMATORIO_PUBLICO.md`. El sustento verificable de la rúbrica
y de las decisiones **de triaje, no de etiquetado humano**, está en
`FUNDAMENTO_RUBRICA_BEC.md` y en el panel de fuentes de la interfaz.

## 1. Revisar los 591 casos reservados para evaluar

Desde `backend/`, abrir la interfaz local:

```powershell
uv run --no-sync streamlit run research/single_review_app.py --server.address=127.0.0.1 --server.port=8502
```

Abrir `http://127.0.0.1:8502`: el paquete se carga automáticamente con el ID
fijo `ADRIAN` (sin introducir correo electrónico). Los textos originales del
dataset se muestran en inglés para conservar el contenido; la rúbrica,
categorías y subtipos visibles están en español. El panel **Ayuda para leer
el correo en inglés** explica expresiones habituales; en Edge/Chrome también
puedes usar clic derecho → **Traducir al español**. Si la traducción cambia
el sentido, elige **No se puede determinar**. Clasificar cada caso:

- **BEC · fraude empresarial** (`BEC`): solicita una acción empresarial fraudulenta por supuesta autoridad,
  proveedor o cuenta de trabajo comprometida; elegir subtipo y justificar.
- **Otro phishing (no BEC)** (`OTHER_PHISHING`): phishing sin la mecánica BEC; no marcar BEC solo por
  urgencia, enlace malicioso o una cuenta genérica.
- **No se puede determinar** (`UNCERTAIN`): información insuficiente; se excluye del análisis primario.

**No ver las predicciones v1/v2 durante la revisión.** La interfaz guarda
cada decisión en `single_annotations.jsonl` (solo local) y permite continuar
tras cerrar el navegador. Los otros 1.000 correos conservan el label benigno
del publicador, sin declarar que fueron revisados manualmente. No se añaden
direcciones ficticias ni se alteran cuerpos para simular evidencia original.
Todos los casos de validación/test se presentan **sin sugerencias de la regla
ni borradores automáticos**. Sus decisiones se registran bajo `ADRIAN`;
los 56 positivos débiles del entrenamiento permanecen identificados como
generados por regla, nunca como decisiones suyas.

## 2. Congelar etiquetas y grupos

Solo cuando se hayan revisado **los 591 casos requeridos**, desde `backend/`:

```powershell
uv run --no-sync python -m research.bec_training.weak_supervision freeze --csv "C:\Users\Usuario\Downloads\Zero-Day_Phishing_Emails_Corpus.csv" --review-dir ..\artifacts\research\bec_single_v3
```

La operación comprueba el hash del CSV, del paquete, de las etiquetas y del
código; registra `WEAK_RULE_TRAIN_BEC_HUMAN_VALIDATION_TEST`, cuenta casos
ambiguos y conserva las fuentes de cada etiqueta por separado. Se detiene
si validation no reúne **10 BEC humanos** o test **20 BEC humanos y 100
legítimos**. No se
reclasifican mensajes para forzar ese mínimo. El manifiesto queda bloqueado:
no editar anotaciones después. Los grupos son **heurísticos**, pues el autor
no publicó IDs de plantilla/campaña.

## 3. Entrenar v3 sin abrir test

Después de un freeze exitoso:

```powershell
uv run --no-sync python -m research.bec_training.single_review_training train --csv "C:\Users\Usuario\Downloads\Zero-Day_Phishing_Emails_Corpus.csv" --review-dir ..\artifacts\research\bec_single_v3 --model-dir ..\artifacts\research\bec_single_v3_model
```

Entrena 4 configuraciones × 3 folds solo en train, selecciona el umbral con
validation y guarda informe `SEALED_NOT_EVALUATED`. Si no existe candidato
factible no se crea modelo ni se abre test. Ningún artefacto de esta ruta es
elegible para `assist`; un modelo válido se podría observar en `shadow` con
hashes de modelo e informe, sin alterar alertas.

## 4. Abrir el test una sola vez

Cuando el modelo y la regla de decisión estén congelados, ejecutar **una
única vez** desde `backend/`:

```powershell
uv run --no-sync python -m research.bec_training.single_review_training test --csv "C:\Users\Usuario\Downloads\Zero-Day_Phishing_Emails_Corpus.csv" --review-dir ..\artifacts\research\bec_single_v3 --model-dir ..\artifacts\research\bec_single_v3_model --lock-dir ..\artifacts\research\test-locks --output ..\artifacts\research\bec_single_v3_final_test.json
```

Un candado persistente por hash de la cohorte congelada impide repetir el
test incluso con otros pesos. Se guardan TP, FP, TN, FN, recall, FPR,
precisión y, si hay grupos suficientes, IC 95 % por bootstrap de grupos.
La precisión depende de la prevalencia sintética construida. Si falla el
objetivo, se informa como fallo; **no se reajusta con el test**.

**Hasta terminar el paso 1 no existen etiquetas BEC específicas ni métricas
confirmatorias v3.** La conclusión, cuando exista, será sobre BEC sintético
revisado por una persona, no eficacia sobre incidentes reales.
