# Fundamento verificable de la rúbrica y del triaje BEC

Fecha de comprobación: 2026-11-23. Alcance: **priorizar la revisión de correos
sintéticos en inglés**, no diagnosticar BEC automáticamente. Fuentes primarias:
dos estudios revisados por pares en USENIX Security, el artículo revisado de
Dube, un estudio de supervisión débil revisado por pares y las definiciones
oficiales FBI/IC3 y CISA. El trabajo de Brabec et al. es un **preprint** con
detalles técnicos útiles; no se presenta como artículo revisado por pares.

## Definición operativa frente a señales débiles

La [definición del FBI/IC3 (2024)](https://www.ic3.gov/PSA/2024/PSA240911)
incluyó solicitudes fraudulentas de transferencia mediante cuentas
comprometidas y variantes que pidieron datos personales de empleados. La
[actualización FBI/IC3 (2023)](https://www.ic3.gov/PSA/2023/PSA230609)
describió cambios de cuenta bancaria, W-2 y billeteras de criptomonedas. Su
concepto BEC es **más amplio** que el objetivo de este proyecto: se definió
*BEC ejecutivo sintético textual* como un mensaje que pretende actuar en una
relación empresarial (directivo, proveedor, cuenta laboral comprometida) y
solicita dinero, cambios de pago, datos o acceso organizacional. Un enlace,
urgencia o autoridad aparente **por sí solos** no cumplieron esa definición.

[Cidon et al. (2019, USENIX Security)](https://www.usenix.org/conference/usenixsecurity19/presentation/cidon)
examinaron suplantación y solicitudes de transferencia, pero combinaron texto
con cabeceras y patrones históricos de comunicación: no validaron que una
palabra como *wire* identifique BEC por sí misma.
[Ho et al. (2019, USENIX Security)](https://www.usenix.org/conference/usenixsecurity19/presentation/ho)
estudiaron phishing lateral desde cuentas empresariales comprometidas: un
mensaje de credenciales dirigido a una organización puede ser parte de una
cadena BEC, de modo que no se descarta automáticamente por contener URL.
[Brabec et al. (2023, §2 y Fig. 1)](https://arxiv.org/html/2308.10776v1#S2)
expusieron incluso un mensaje BEC cuyo contenido aislado no bastó para
clasificarlo sin identidad/historial. El CSV Kaggle solo proporcionó asunto y
cuerpo; **no** mostró remitente verificado, destinatario, hilo o campaña. Ante
contexto insuficiente, la rúbrica permitió `UNCERTAIN`.

La [guía CISA sobre phishing](https://www.cisa.gov/secure-our-world/recognize-and-report-phishing)
describió enlaces a sitios falsos, solicitudes de credenciales e información
personal y urgencia como señales **generales de phishing**, no evidencia
suficiente de BEC. [Brabec et al. (§5)](https://arxiv.org/html/2308.10776v1#S5)
señalaron que la urgencia aparece también en mensajes benignos y que las
detecciones aisladas son señales débiles que deben combinarse.

## Correspondencia entre código, fuentes y decisión humana

| Componente de `triage-text-v2` | Sustento y alcance | Consecuencia permitida |
| --- | --- | --- |
| `FINANCE` + `BUSINESS` + `ACTION` → `POSIBLE_BEC` | FBI 2023/2024: transferencias, cambio bancario, datos de empleados; Brabec §2: CEO, proveedor, cuenta laboral, acción sobre recursos organizacionales; Cidon 2019: texto + contexto. Las **expresiones inglesas exactas** son una adaptación local al corpus, no una regla publicada por esos autores. | **Enviar al evaluador**; la coincidencia no es una etiqueta BEC ni prueba suplantación. Si la solicitud es legítima o falta identidad, decidir `OTHER_PHISHING`/`UNCERTAIN` según el caso. |
| Verificación de cuenta, contraseña, premios, entregas o redes, **sin** contexto empresarial → `OTRO_CLARO` | CISA: patrones de phishing común. Cidon y Ho: una URL de credenciales **sí puede** participar en una cadena de compromiso de correo empresarial. | Solo **excluir de train** estos casos que la regla no priorizó; todos los mensajes de validation/test se revisan sin sugerencias. Si aparece contexto laboral se conserva como `DUDOSO`, no se descarta por el enlace. |
| `crypto`, `wallet`, inversión o relación empresarial ambigua → `DUDOSO` | FBI 2023 incluyó billeteras de criptomonedas en variantes BEC; Brabec §2 mencionó pagos en criptomonedas. La antigua regla v1 agrupaba crypto entre estafas de consumo; se corrigió **antes de la primera anotación**. | Revisión humana; no afirmar que «cripto = BEC», ni que «cripto = otro» sin contexto. |
| Contexto ausente, términos que no encajan o solicitud incompleta → `DUDOSO` | Brabec §2/Fig. 1 y Cidon 2019 mostraron el valor del historial y la identidad; el texto solo no resuelve todos los casos. | El evaluador usa `UNCERTAIN` si la información resulta insuficiente. No se fuerza una clase binaria. |
| 56 posibles BEC de train etiquetados débilmente por regla | [Ratner et al. (2017, *PVLDB*)](https://doi.org/10.14778/3157794.3157797) explicaron que las funciones heurísticas pueden tener precisión y correlaciones desconocidas; [Brabec et al. §6.1.1](https://arxiv.org/html/2308.10776v1#S6.SS1.SSS1) distinguieron etiquetas automatizadas de las humanas. **Ninguno** validó nuestra regla ni nuestros 56 casos. | Usar esos 56 **solo en train**, con fuente `AI_RULE_DRAFT_V1_NOT_ADRIAN`; los otros 1.353 phishing de train quedan excluidos. Los 591 phishing de validation/test se etiquetan por ADRIAN, sin mostrar sugerencias. |

`_heuristic_groups` unió asuntos normalizados y textos con similitud Jaccard
de trigramas >=0,85. **Ese número es una decisión de ingeniería
predeclarada, no un umbral avalado por los artículos citados.** Sin IDs de
plantilla/campaña del autor, la separación puede dejar parentescos no
detectados. Del mismo modo, el objetivo FPR <=5 % es del protocolo de este
proyecto, **no** una norma FBI/CISA ni una garantía de precisión operativa.

## Consecuencia para la anotación y la inferencia

El evaluador deberá elegir `BEC`, `OTHER_PHISHING` o `UNCERTAIN` según **todo el
correo**, no por presencia de un término. El software registrará subtipo,
justificación, identidad del evaluador y hash del texto. La interfaz muestra
el motivo automático solo en train; validation y test permanecen sin sugerencias.
En la versión `triage-text-v2`, sobre los 2.000 phishing seleccionados se
habían priorizado **1.200** para revisión (609 train + 291 validation + 300 test).
**Antes de la primera anotación**, la enmienda de supervisión débil dejó
**56 propuestas BEC de train** para entrenamiento automático identificado,
**1.353 phishing de train excluidos** y **591 validation/test para revisión
humana íntegra**. Los borradores se limitaron a los **1.409 phishing de
entrenamiento**; no se generó propuesta sobre validation/test. Estas cifras
describieron selección, **no precisión de la regla**: antes de tener etiquetas
humanas no pueden calcularse su sensibilidad o especificidad.

Un estudio de transferencia confirmatoria posterior puede calcular métricas
**del clasificador textual sobre BEC sintético** tras congelar las decisiones
humanas y abrir el test una sola vez. No se puede usar esta bibliografía para
atribuir veracidad humana a los descartes automáticos, ni para inferir eficacia
frente a BEC real.

## Referencias verificadas

- Cidon, A., Gavish, L., Bleier, I., Korshun, N., Schweighauser, M., & Tsitkin, A. (2019). *High Precision Detection of Business Email Compromise*. USENIX Security '19, 1291–1307. https://www.usenix.org/conference/usenixsecurity19/presentation/cidon
- Ho, G., Cidon, A., Gavish, L., Schweighauser, M., Paxson, V., Savage, S., Voelker, G. M., & Wagner, D. (2019). *Detecting and Characterizing Lateral Phishing at Scale*. USENIX Security '19, 1273–1290. https://www.usenix.org/conference/usenixsecurity19/presentation/ho
- Federal Bureau of Investigation / Internet Crime Complaint Center. (2023). *Business Email Compromise: The $50 Billion Scam* (I-060923-PSA). https://www.ic3.gov/PSA/2023/PSA230609
- Federal Bureau of Investigation / Internet Crime Complaint Center. (2024). *Business Email Compromise: The $55 Billion Scam* (I-091124-PSA). https://www.ic3.gov/PSA/2024/PSA240911
- Cybersecurity and Infrastructure Security Agency. *Recognize and Report Phishing* (página archivada). https://www.cisa.gov/secure-our-world/recognize-and-report-phishing
- Brabec, J., et al. (2023). *A Modular and Adaptive System for Business Email Compromise Detection* (preprint arXiv:2308.10776). https://arxiv.org/html/2308.10776v1
- Dube, R. (2025). Building a business email compromise research dataset with large language models. *Journal of Computer Virology and Hacking Techniques, 21*, 3. https://doi.org/10.1007/s11416-024-00544-y. Su [cuaderno de validación](https://github.com/r-dube/bec/blob/main/bec_val.ipynb) definió los factores negocio, autoridad, acción y urgencia; se usó como **referencia de diseño**, no como certificación de nuestra regla.
- Ratner, A., Bach, S. H., Ehrenberg, H., Fries, J., Wu, S., & Ré, C. (2017). Snorkel: Rapid training data creation with weak supervision. *Proceedings of the VLDB Endowment, 11*(3), 269–282. https://doi.org/10.14778/3157794.3157797
