"""Contratos offline de contexto y scores cacheados, sin exponer contenido."""

import hashlib

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from app.models import ExecutiveContact, Vendor
from app.schemas.organizational_context import ExecutiveContactCreate, VendorCreate
from app.services.deterministic_analysis import AnalysisContext
from research.bec_training.data import CorpusUse, ResearchDataError

EMPTY_CONTEXT_BYTES = b'{"executives":[],"vendors":[]}'
EMPTY_CONTEXT_SHA256 = hashlib.sha256(EMPTY_CONTEXT_BYTES).hexdigest()


class _Context(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    notice: str | None = None
    organization: str | None = None
    executives: list[ExecutiveContactCreate] = Field(max_length=100)
    vendors: list[VendorCreate] = Field(max_length=100)


class _CacheMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    provider: str = Field(pattern=r"^[A-Za-z0-9._/-]{1,200}$")
    model: str = Field(pattern=r"^[A-Za-z0-9._/-]{1,200}$")
    prompt_version: str = Field(pattern=r"^[A-Za-z0-9._/-]{1,200}$")
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _Cache(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    metadata: _CacheMetadata
    scores: dict[str, StrictInt | None] = Field(max_length=5000)


def load_context_bytes(contents: bytes, *, use: CorpusUse) -> tuple[AnalysisContext, str]:
    if len(contents) > 500_000:
        raise ResearchDataError("Context file exceeds the offline limit")
    try:
        parsed = _Context.model_validate_json(contents)
        if use.kind == "fixture" and (
            any(not row.email.lower().endswith((".example", ".test")) for row in parsed.executives)
            or any(
                not row.domain.lower().endswith((".example", ".test"))
                or (
                    row.contact_email is not None
                    and not row.contact_email.lower().endswith((".example", ".test"))
                )
                for row in parsed.vendors
            )
        ):
            raise ResearchDataError("Fixture context requires reserved domains")
        context = AnalysisContext(
            [ExecutiveContact(**row.model_dump()) for row in parsed.executives if row.is_active],
            [Vendor(**row.model_dump()) for row in parsed.vendors if row.is_active],
        )
    except ValidationError, ValueError, TypeError:
        raise ResearchDataError("Invalid organizational context") from None
    return context, hashlib.sha256(contents).hexdigest()


def load_semantic_cache(
    contents: bytes,
    *,
    dataset_sha256: str,
    context_sha256: str,
    case_ids: set[str],
) -> tuple[dict[str, int | None], dict[str, str]]:
    """Una salida por ID; `null` es fallo/ausencia y nunca score cero."""
    if len(contents) > 2_000_000:
        raise ResearchDataError("Semantic cache exceeds the offline limit")
    try:
        cache = _Cache.model_validate_json(contents)
    except ValidationError, ValueError:
        raise ResearchDataError("Invalid semantic cache structure") from None
    if (
        cache.metadata.dataset_sha256 != dataset_sha256
        or cache.metadata.context_sha256 != context_sha256
        or set(cache.scores) != case_ids
        or any(value is not None and not 0 <= value <= 100 for value in cache.scores.values())
    ):
        raise ResearchDataError("Semantic cache does not match frozen inputs")
    return cache.scores, {
        "provider": cache.metadata.provider,
        "model": cache.metadata.model,
        "prompt_version": cache.metadata.prompt_version,
        "cache_sha256": hashlib.sha256(contents).hexdigest(),
    }


def empty_context_cache_reference() -> str:
    """Hash para un segundo cache C4 generado explícitamente sin contexto."""
    return EMPTY_CONTEXT_SHA256
