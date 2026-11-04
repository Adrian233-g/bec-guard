# Análisis BEC — Fase 5

> **Transición de roles:** las referencias históricas a MANAGER/AUDITOR y permisos
> anteriores se sustituyen por los [roles vigentes](roles.md).

El backend analiza un Email persistido y conserva un EmailAnalysis actual. Es un
monolito síncrono: reglas + contexto activo → semántica LangChain → scoring híbrido
→ resultado y auditoría en un commit. Fase 6 añade BECAlert OPEN para COMPLETED
>=50 en esa misma transacción, sin ejecutar recomendaciones.

## Motor determinista (`det-v3`)

`assess_deterministically(email, context)` es puro. `load_analysis_context(session)`
consulta ejecutivos y proveedores activos en PostgreSQL. Los lookups exactos de
Fase 3 conservan su contrato; el motor necesita además comparar nombres/dominios.
Solo el contexto activo participa. No se consulta DNS ni se verifica DKIM.

| Señal | Fuente | Contribución |
| --- | --- | --- |
| EXECUTIVE_IDENTITY_MISMATCH | CONTEXT | 35 cuando el nombre o una declaración explícita identifica a un ejecutivo y la dirección no coincide. |
| EXECUTIVE_DOMAIN_LOOKALIKE | CONTEXT | 25 |
| VENDOR_IDENTITY_MISMATCH | CONTEXT | 30 |
| VENDOR_DOMAIN_LOOKALIKE | CONTEXT | 25 |
| REPLY_TO_MISMATCH | RULE | 15 entre dominios; 3 entre direcciones del mismo dominio. |
| RETURN_PATH_MISMATCH | RULE | 4 por dominio distinto. |
| SPF_FAIL / DKIM_FAIL / DMARC_FAIL | RULE | 8 / 8 / 18 |
| PAYMENT_REQUEST | RULE | 8 |
| BANK_ACCOUNT_CHANGE | RULE | 24 |
| SENSITIVE_DATA_REQUEST | RULE | 22 |
| URGENCY | RULE | 8, únicamente junto a una solicitud de pago, cambio bancario o datos. |
| AUTHORITY_PRESSURE | RULE | 10, únicamente junto a una solicitud relevante. |
| SECRECY_REQUEST | RULE | 12 por evitar verificación, registro o consulta independiente. |
| REQUEST_OUTSIDE_ROLE | CONTEXT | 18 si una categoría sensible excede el ámbito explícito. |
| IMPERSONATION_REQUEST / IMPERSONATION_SENSITIVE_REQUEST | CONTEXT | Contribución necesaria para llegar a 50 / 70. |

Cada código aparece como máximo una vez. El score es `min(100, suma de
contribution)`, sin parámetros aprendidos ni bonus ocultos. Por el límite, la suma
de contribuciones puede superar el score. Las descripciones son plantillas cortas,
sin copiar fragmentos del correo. Dominio desconocido por sí solo no genera riesgo.

Nombres: comparación por tokens completos, lowercase y sin acentos; se admiten
títulos/tokens adicionales. Para ejecutivos se requieren al menos dos tokens
conocidos y email distinto; un primer nombre aislado no basta. Un email ejecutivo
oficial no produce suplantación por sí mismo salvo que afirme otra identidad.
Para proveedores con contacto registrado, una dirección distinta genera mismatch
incluso dentro del mismo dominio. Sin contacto se usa el dominio como referencia.
Una coincidencia no descarta una cuenta comprometida.

Similitud de dominios: hostnames ASCII/punycode, lowercase y sin punto final.
Se exige igual número de labels y exactamente uno distinto, con longitud mínima
5 en ambos lados. Ese label debe tener distancia Levenshtein 1 o equivalencia
visual ASCII `rn`/`m`. `ernpresa.example` puede parecerse a `empresa.example`;
compartir `.example` no hace lookalike a `otroproveedor` y `proveedor`.
No hay public suffix list, Unicode confusable analysis ni detección exhaustiva de
subdominios abusivos, transposiciones o sustituciones de TLD cortos.

Authentication-Results solo interpreta tokens explícitos `spf=fail`, `dkim=fail`,
`dmarc=fail`, sin confundir softfail con fail. Pass no reduce el score ni certifica
legitimidad; la cabecera almacenada tampoco es una validación independiente.
Return-Path tiene peso bajo porque puede pertenecer a infraestructura legítima.
Reply-To null o idéntico no genera señal.

El contenido usa regex/frases modestas en español e inglés. Se excluyen cláusulas
negadas de solicitudes de pago/cambio/datos, con una excepción para la expresión
afirmativa «no dudes en». Se reconocen «transfiere», urgencia negada y algunas
formas de omitir aprobación o verificación; se protege la expresión «no omitas
verificar». Las solicitudes de evitar controles se buscan en cláusulas negativas. No es NLP avanzado: hay negaciones,
paráfrasis, mensajes reenviados y solicitudes sutiles que se pueden interpretar mal.
Urgencia o confidencialidad ordinarias no equivalen a BEC.

## Funciones y comparación de identidad

Cada ejecutivo o proveedor puede tener `responsibilities` (descripción) y
`allowed_actions` (categorías explícitas). `null` significa que no se han definido;
`[]` significa que no se ha registrado ninguna de las categorías sensibles. Las
categorías describen el ámbito esperado, no constituyen una autorización de pago.

Un ejecutivo identificado por nombre mostrado o declaración explícita se compara
con su dirección exacta. Un proveedor identificado por nombre o dominio se compara con su
correo de contacto cuando existe, incluso si el dominio coincide; sin contacto se
compara el dominio. Un dominio parecido también se trata como discrepancia. Una identidad o dominio
discrepante con una solicitud reconocida suma
`IMPERSONATION_REQUEST` hasta 50; si es una solicitud de pago, cambio bancario o
datos sensibles se usa `IMPERSONATION_SENSITIVE_REQUEST` hasta 70. `REQUEST_OUTSIDE_ROLE`
añade 18 cuando una categoría solicitada no figura en un ámbito definido. La
combinación híbrida mantiene pisos de 50 y 70 para estas señales, respectivamente.
Son indicios para revisión humana, no pruebas de fraude o de autoridad. Remitentes
no registrados que no afirman una identidad conocida no se clasifican por eso.
Las expresiones de solicitud e identidad son heurísticas y no cubren todas las
paráfrasis, hilos citados, mensajes multilingües ni cuentas legítimas comprometidas.

## Análisis semántico (`semantic-v2`)

`SemanticAnalyzer` crea un único chat model mediante `create_chat_model(settings)`
y llama `with_structured_output(SemanticAssessment, method="json_schema")`.
Se usan langchain-core y los adaptadores mantenidos langchain-openai,
langchain-google-genai y langchain-groq, fijados en uv.lock para Python 3.14.
No se instala LangGraph ni se construye un agente. No hay tools, memory ni RAG.

| Variable | Uso |
| --- | --- |
| LLM_PROVIDER | `openai`, `google` (alias `gemini`) o `groq`. |
| LLM_MODEL | ID del modelo seleccionado; obligatorio al analizar. Debe soportar JSON Schema nativo. |
| OPENAI_API_KEY | Solo para OpenAI. |
| GOOGLE_API_KEY | Solo para Gemini Developer API; se fuerza vertexai=False. |
| GROQ_API_KEY | Solo para Groq. |
| LLM_TIMEOUT_SECONDS | Default 30 segundos, entre 1 y 120; timeout del adaptador/HTTP. |

La configuración se lee al ejecutar el análisis, no al arrancar ni migrar.
Proveedor/modelo/key ausentes o configuración inválida producen FALLBACK por reglas. No hay un
modelo predeterminado ni fallback entre proveedores. SDK max_retries=0: el retry
de aplicación es un POST explícito. La disponibilidad y compatibilidad JSON Schema
del modelo elegido se deben comprobar en el proveedor; un modelo incompatible
produce error, nunca una interpretación libre de texto.

SemanticAssessment exige risk_score entero 0–100, bec_type nullable del catálogo,
hasta 8 señales SEMANTIC (code estable, descripción hasta 240 caracteres), summary
no vacío hasta 600 y recommended_action no vacía hasta 400. Rechaza campos extra,
fuentes distintas, scores boolean/string, textos vacíos y NUL. Se valida de nuevo
localmente; no se conserva la respuesta cruda.

El prompt distingue BEC de phishing/malware general y prohíbe inventar contexto.
Email se delimita como JSON de datos no confiables en un HumanMessage, separado
del SystemMessage. Las instrucciones dentro de cualquier campo se ignoran como
instrucciones del modelo. Se incluyen sender, reply-to, subject, body y hechos
derivados: coincidencias de identidad y señales técnicas/contextuales. Para contactos
coincidentes también se envían el cargo, funciones y categorías configuradas (máximo
cinco coincidencias), sin direcciones de la agenda ni referencias bancarias. No se
serializan entidades completas, usuarios, JWT, hashes, AuditLog ni credenciales.
Las referencias bancarias conocidas que aparezcan en los campos se redactan
localmente, incluso con distinto casing; no se envía bank_account_reference.
No se realiza todavía comparación bancaria específica.

Se desactiva LangSmith tracing durante la invocación, incluso si estaba activado
por entorno. La aplicación no registra prompt, body, key, respuesta ni excepciones
crudas del proveedor. No habilitar logs HTTP/SDK de depuración en un despliegue con
correos reales: esos diagnósticos pertenecen a dependencias externas.

La defensa ante prompt injection es básica: separación de mensajes, instrucción
fuerte, JSON delimitado, contrato estructurado y ausencia de herramientas/acciones.
Los fakes prueban la frontera y el contrato, no demuestran inmunidad semántica de
un modelo real. Solo el proveedor seleccionado recibe los datos del correo.

Referencias de integración: [ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai),
[Gemini](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai),
[Groq structured output](https://reference.langchain.com/python/langchain-groq/chat_models/ChatGroq/with_structured_output).

## Scoring híbrido (`hybrid-v2`)

`combine_scores` calcula 50% determinista + 50% semántico, con redondeo entero
half-up: `(deterministic_score + semantic_score + 1) // 2`. Salvaguardas:
si el determinista es >=70, el resultado final tiene floor 70. Un LLM contradictorio
no borra evidencia local fuerte. Una identidad discrepante con solicitud reconocida
tiene piso 50, o piso 70 si solicita pago, cambio bancario o datos sensibles.
La salvaguarda es asimétrica: reglas=0 e IA=100
producen 50 y generan alerta con el umbral actual. No hay entrenamiento ni
calibración estadística que demuestre que esa combinación es óptima.

| Score | RiskLevel |
| --- | --- |
| 0–39 | LOW |
| 40–69 | MEDIUM |
| 70–84 | HIGH |
| 85–100 | CRITICAL |

El umbral de alerta es **50**: MEDIUM 50–69, HIGH y CRITICAL generan alerta.
MEDIUM 40–49 no genera alerta automática. Los niveles no cambian.

El motor determinista sugiere un tipo, en este orden cuando coexisten señales:
BANK_ACCOUNT_CHANGE, SENSITIVE_DATA_REQUEST, EXECUTIVE_IMPERSONATION, VENDOR_FRAUD.
El resultado final usa null bajo 40; desde 40 prefiere ese tipo local y, si no
existe, el sugerido por semántica. Si ninguno identifica patrón sigue null.
OTHER requiere una sugerencia semántica; no se usa como sinónimo de legítimo.
Las señales semánticas se normalizan a Signal con contribution=0: no tienen peso
aditivo propio, participan mediante semantic_score en la media.

## Persistencia, transacción y concurrencia

`public.email_analysis`, revisión nueva `0006_email_analysis` sobre 0005:
UUID, FK RESTRICT a emails, UNIQUE email_id, status, deterministic_score,
semantic_score/risk_score/risk_level/bec_type nullable, signals JSONB, summary,
recommended_action, provider, model, policy_version, error_code y analyzed_at UTC.
Los análisis nuevos usan `det-v3/semantic-v2/hybrid-v2`; los históricos conservan
la versión con que se calcularon. No hay índices adicionales
a PK y UNIQUE; la consulta real es por email_id. CHECKs validan enums, rangos,
forma array, thresholds y consistencia entre status y resultado.

No guarda prompt, raw output, key, copia del cuerpo ni labels del dataset.
Un Email tiene como máximo un análisis actual; no hay historial de ejecuciones.
COMPLETED y FALLBACK se devuelven sin invocar LLM; Fase 6 recupera una alerta faltante cuando
corresponde y audita solo esa creación. Con alerta existente no repite auditoría. ERROR puede
reintentarse y actualiza el mismo UUID, recalculando con el contexto actual.
Un COMPLETED no se invalida al cambiar contexto/modelo/política: no existe endpoint
de reanálisis forzado en este MVP.

POST bloquea la fila padre Email con SELECT FOR UPDATE y después consulta el
análisis. Dos solicitudes del mismo email se serializan; UNIQUE protege además
la base. Correos distintos no comparten ese bloqueo. Se mantiene la transacción
durante el LLM: suficiente para el MVP, con coste de ocupación de conexión/worker.
Timeout es del transporte; no es un deadline global estricto para toda la petición.
Si falla la IA, la primera ejecución persiste FALLBACK y las solicitudes posteriores lo reutilizan.

El análisis y EMAIL_ANALYZED o EMAIL_ANALYSIS_FAILED comparten un commit.
Actor, rol actual, tipo email_analysis, UUID del análisis, IP del peer directo y
timestamp; details=null. No se auditan scores, señales, subject, sender ni body.
Un fallo de auditoría revierte tanto creación como retry, conservando un ERROR
anterior cuando existe. Errores de persistencia responden 503 genérico.
El trigger append-only histórico permanece intacto.

BEC_ALERT_CREATED se registra en la misma transacción para COMPLETED o FALLBACK >=50.
Las llamadas de automatización reutilizan este servicio con actor null y una API
key acotada, sin sustituir RBAC/JWT humano. Ver [alertas y orquestación](alerts-and-orchestration.md).

## API y respaldo por reglas

Si el proveedor falla, agota cuota, devuelve salida inválida o no está configurado,
el servicio guarda FALLBACK y responde HTTP 200. El puntaje final es el de reglas,
semantic_score queda null y error_code explica el fallo sanitizado. La interfaz
indica que el resultado es limitado; una puntuación baja no descarta fraude. Se
crea alerta con el umbral vigente >=50. No se reintenta automáticamente ni al
repetir POST; los análisis ERROR históricos sí pueden reintentarse. Los fallos de
base de datos y auditoría responden 503 y revierten la transacción. Ver el
[contrato](api-contracts.md).

## Regresión de development y límites

Desde backend/, sin PostgreSQL ni API keys:

```bash
uv run python -m app.scripts.validate_dataset
uv run python -m app.scripts.check_development
```

El loader heredado valida estructura/conteos del archivo completo. El harness
filtra `development` antes de leer labels para sus resúmenes o invocar motores;
solo `case.email` llega al motor. Usa el contexto sintético en memoria y no escribe
datos de prueba ni etiquetas en DB. Imprime agregados de scores/señales/errores,
sin cuerpos. No permite seleccionar holdout. `--llm` habilita explícitamente
llamadas externas con el proveedor configurado (98 posibles llamadas con coste);
sin esa bandera no llama LLM. En CI solo se usan reglas y fakes controlados.

Resultado histórico de `det-v1`: 98 development, legítimos 70 (0–26, media 3.83),
BEC 28 (15–90, media 62.64), los 21 hard negatives legítimos LOW. Distribución:
75 LOW, 12 MEDIUM, 7 HIGH, 4 CRITICAL. Es una comprobación de desarrollo, no
evaluación formal ni evidencia de rendimiento del pipeline con LLM real.
El detector quedó congelado antes de la evaluación determinista formal del holdout.
El corpus no se modificó y los resultados no se usaron para ajustar el detector.
La medición y sus límites están en [evaluación](evaluation.md). El holdout no se
vuelve una regresión de CI ni una fuente para tuning.

Las reglas pueden omitir ataques sutiles; el peso 50/50 también puede dejar en
MEDIUM ataques detectados solo por semántica. El corpus es sintético y los scores
no son probabilidades calibradas. No hubo llamadas reales pagadas para esta fase:
no se afirma calidad ni disponibilidad de un modelo externo particular.
El cuerpo se envía sin truncarlo: modelos con contexto insuficiente pueden fallar.
Sin análisis de adjuntos, DNS ni conectores. Fase 6 implementa BECAlert automática
y orquestación Webhook n8n; Fase 7 añade frontend y revisión humana, sin cambiar
estas políticas ni ajustar scoring con dataset. Ver [frontend](frontend.md).
