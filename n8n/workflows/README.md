# Workflows de n8n

`bec-analysis-webhook.json` es el workflow canónico de Fase 6, inactive y sin datos
pineados ni secretos. Orquesta FastAPI y admite entradas por webhook e IMAP.

La instancia usa PostgreSQL (esquema `n8n`) y el volumen `n8n_data` conserva su
configuración y claves de cifrado. El primer acceso pide crear su cuenta propietaria;
es la administración propia de n8n, no autenticación de BEC Guard.

Configuración, importación, publicación, webhook, privacidad y pruebas:
[guía n8n](../README.md). La lógica BEC y la creación de alertas pertenecen a FastAPI.

El mismo workflow incluye un Email Trigger (IMAP) desactivado por defecto. Configura la credencial
y habilítalo siguiendo la [guía de Gmail](../README.md#gmail-recepción-de-correos-nuevos).
