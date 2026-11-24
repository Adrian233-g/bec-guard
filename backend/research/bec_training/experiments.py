"""Ablaciones pareadas en memoria, sin DB, proveedor ni cambios de política."""

import re
from collections.abc import Mapping
from time import perf_counter

from app.services.alerts import ALERT_POLICY_VERSION, ALERT_THRESHOLD
from app.services.deterministic_analysis import (
    DETERMINISTIC_POLICY_VERSION,
    AnalysisContext,
    assess_deterministically,
)
from app.services.hybrid_scoring import HYBRID_POLICY_VERSION, combine_scores
from app.services.semantic_analysis import SEMANTIC_PROMPT_VERSION
from research.bec_training.data import (
    FIXTURE,
    CorpusUse,
    ResearchCase,
    ResearchDataError,
    validate_cases,
)

CONDITIONS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")


def compare_offline(
    cases: list[ResearchCase],
    context: AnalysisContext,
    *,
    semantic_scores: Mapping[str, int | None] | None = None,
    semantic_source: str | None = None,
    semantic_provenance: dict[str, str] | None = None,
    no_context_scores: Mapping[str, int | None] | None = None,
    no_context_semantic_provenance: dict[str, str] | None = None,
    no_context_cache_sha256: str | None = None,
    use: CorpusUse = FIXTURE,
) -> dict[str, list[dict] | str | dict[str, str]]:
    """C2/C3/C5/C6 requieren scores por caso, capturados con procedencia o simulados.

    En una demostración, `semantic_source='HYPOTHETICAL'` nunca se comunica como IA.
    C7 simula indisponibilidad de proveedor y respaldo por reglas (no mide su latencia).
    """
    validate_cases(cases, use=use)
    ids = {case.case_id for case in cases}
    if semantic_scores is None and (semantic_source is not None or semantic_provenance):
        raise ResearchDataError("Semantic provenance requires a score for every case")
    if no_context_scores is not None and semantic_scores is None:
        raise ResearchDataError("No-context semantic scores require the paired semantic cache")
    if no_context_semantic_provenance and no_context_scores is None:
        raise ResearchDataError("No-context semantic provenance requires its score cache")
    if (
        no_context_scores is not None
        and semantic_source == "CACHED_AUTHORIZED"
        and (
            no_context_cache_sha256 is None
            or not re.fullmatch(r"[0-9a-f]{64}", no_context_cache_sha256)
        )
    ):
        raise ResearchDataError("No-context scores require a frozen cache hash")
    if semantic_scores is not None:
        if semantic_source not in {"HYPOTHETICAL", "CACHED_AUTHORIZED"}:
            raise ResearchDataError("Semantic scores require explicit provenance")
        if semantic_source == "HYPOTHETICAL" and semantic_provenance:
            raise ResearchDataError("Hypothetical scores cannot claim a provider")
        if semantic_source == "CACHED_AUTHORIZED" and (
            semantic_provenance is None
            or not all(
                semantic_provenance.get(key)
                for key in ("provider", "model", "prompt_version", "cache_sha256")
            )
            or set(semantic_provenance) != {"provider", "model", "prompt_version", "cache_sha256"}
            or not re.fullmatch(r"[0-9a-f]{64}", semantic_provenance["cache_sha256"])
            or any(
                not re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", semantic_provenance[key])
                for key in ("provider", "model", "prompt_version")
            )
        ):
            raise ResearchDataError(
                "Authorized scores require provider, model, prompt and cache hash"
            )
        if no_context_scores is not None and semantic_source == "CACHED_AUTHORIZED":
            required = {"provider", "model", "prompt_version", "cache_sha256"}
            if (
                no_context_semantic_provenance is None
                or set(no_context_semantic_provenance) != required
                or not all(no_context_semantic_provenance.get(key) for key in required)
                or not re.fullmatch(r"[0-9a-f]{64}", no_context_semantic_provenance["cache_sha256"])
                or any(
                    not re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", no_context_semantic_provenance[key])
                    for key in ("provider", "model", "prompt_version")
                )
            ):
                raise ResearchDataError(
                    "No-context scores require provider, model, prompt and cache hash"
                )
            assert semantic_provenance is not None
            assert no_context_semantic_provenance is not None
            if any(
                semantic_provenance[key] != no_context_semantic_provenance[key]
                for key in ("provider", "model", "prompt_version")
            ):
                raise ResearchDataError(
                    "Paired semantic caches must use the same provider, model and prompt"
                )
        if set(semantic_scores) != ids or any(
            value is not None and (type(value) is not int or not 0 <= value <= 100)
            for value in semantic_scores.values()
        ):
            raise ResearchDataError("Semantic score cache must match case IDs exactly")
        if no_context_scores is not None and (
            set(no_context_scores) != ids
            or any(
                value is not None and (type(value) is not int or not 0 <= value <= 100)
                for value in no_context_scores.values()
            )
        ):
            raise ResearchDataError("No-context score cache must match case IDs exactly")
    results: dict[str, list[dict] | str | dict[str, str]] = {key: "NOT_RUN" for key in CONDITIONS}
    rows = {key: [] for key in CONDITIONS}

    def add(
        key: str,
        case: ResearchCase,
        score: int | None,
        *,
        status="COMPLETED",
        threshold=50,
        elapsed_ms=None,
    ) -> None:
        rows[key].append(
            {
                "case_id": case.case_id,
                "group_id": case.group_id,
                "label": case.label.value,
                "bec_type": case.expected_bec_type.value if case.expected_bec_type else None,
                "is_hard_negative": case.is_hard_negative,
                "score": score,
                "detect": None if score is None else score >= 40,
                "alert": None if score is None else score >= threshold,
                "alert_threshold": threshold,
                "status": status,
                "elapsed_ms": elapsed_ms,
            }
        )

    no_context = AnalysisContext([], [])
    for case in cases:
        started = perf_counter()
        det = assess_deterministically(case.email, context)
        elapsed = (perf_counter() - started) * 1000
        add("C1", case, det.score, threshold=ALERT_THRESHOLD, elapsed_ms=elapsed)
        started = perf_counter()
        absent = assess_deterministically(case.email, no_context)
        absent_elapsed = (perf_counter() - started) * 1000
        if semantic_scores is None:
            add("C4", case, absent.score, elapsed_ms=absent_elapsed)
        add("C7", case, det.score, status="FALLBACK")
        if semantic_scores is not None:
            if semantic_source == "HYPOTHETICAL" or no_context_scores is not None:
                alternate = (
                    semantic_scores[case.case_id]
                    if no_context_scores is None
                    else no_context_scores[case.case_id]
                )
                if alternate is None:
                    add("C4", case, absent.score, status="FALLBACK")
                else:
                    add(
                        "C4",
                        case,
                        combine_scores(
                            absent.score,
                            alternate,
                            signal_codes={signal.code for signal in absent.signals},
                        ),
                    )
            semantic = semantic_scores[case.case_id]
            if semantic is None:
                add("C2", case, None, status="ERROR")
                add("C3", case, det.score, status="FALLBACK")
                add("C5", case, None, status="ERROR")
                add("C6", case, det.score, status="FALLBACK", threshold=70)
                continue
            combined = combine_scores(
                det.score, semantic, signal_codes={signal.code for signal in det.signals}
            )
            add("C2", case, semantic)
            add("C3", case, combined)
            add("C5", case, (det.score + semantic + 1) // 2)
            add("C6", case, combined, threshold=70)
    for key, values in rows.items():
        if values:
            results[key] = values
    results["semantic_source"] = semantic_source or "NOT_RUN"
    results["semantic_provenance"] = semantic_provenance or {}
    results["no_context_semantic_provenance"] = no_context_semantic_provenance or {}
    results["no_context_cache_sha256"] = no_context_cache_sha256 or "NOT_RUN"
    results["corpus_use"] = use.model_dump()
    results["policies"] = {
        "rules": DETERMINISTIC_POLICY_VERSION,
        "semantic": SEMANTIC_PROMPT_VERSION,
        "hybrid": HYBRID_POLICY_VERSION,
        "alert": ALERT_POLICY_VERSION,
    }
    return results
