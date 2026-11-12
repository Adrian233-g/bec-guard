from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import LLMSettings
from app.models import Email, EmailAnalysis, User
from app.models.enums import AnalysisStatus
from app.schemas.analysis import Signal
from app.services.alerts import ensure_alert_for_analysis
from app.services.audit import AuditAction, record_analysis_event
from app.services.deterministic_analysis import (
    DETERMINISTIC_POLICY_VERSION,
    assess_deterministically,
    load_analysis_context,
)
from app.services.hybrid_scoring import (
    HYBRID_POLICY_VERSION,
    build_fallback_breakdown,
    build_score_breakdown,
    resolve_bec_type,
    risk_level,
)
from app.services.semantic_analysis import (
    SEMANTIC_PROMPT_VERSION,
    LLMErrorCode,
    SemanticAnalysisError,
    SemanticAnalyzer,
)

POLICY_VERSION = f"{DETERMINISTIC_POLICY_VERSION}/{SEMANTIC_PROMPT_VERSION}/{HYBRID_POLICY_VERSION}"


def create_semantic_analyzer() -> SemanticAnalyzer:
    return SemanticAnalyzer(LLMSettings())


def analyze_email(
    session: Session,
    email_id: UUID,
    *,
    actor: User | None,
    analyzer_factory: Callable[[], SemanticAnalyzer] = create_semantic_analyzer,
    peer: str | None = None,
) -> EmailAnalysis:
    started = perf_counter()
    try:
        # Lock the existing parent before checking the UNIQUE child. Two POSTs
        # cannot spend twice or insert duplicates. Unrelated emails do not block.
        email = session.scalar(select(Email).where(Email.id == email_id).with_for_update())
        if email is None:
            raise HTTPException(404, "Email not found")
        analysis = session.scalar(select(EmailAnalysis).where(EmailAnalysis.email_id == email_id))
        if analysis is not None and analysis.status in {
            AnalysisStatus.COMPLETED,
            AnalysisStatus.FALLBACK,
        }:
            ensure_alert_for_analysis(session, analysis, actor=actor, peer=peer)
            session.commit()  # Release the parent lock, without another audit/call.
            return analysis
        context = load_analysis_context(session)
        deterministic = assess_deterministically(email, context)
        if analysis is None:
            analysis = EmailAnalysis(email_id=email_id)
            session.add(analysis)
        analysis.status = AnalysisStatus.ERROR
        analysis.deterministic_score = deterministic.score
        analysis.signals = [s.model_dump() for s in deterministic.signals]
        analysis.semantic_score = analysis.risk_score = analysis.risk_level = None
        analysis.score_breakdown = None
        analysis.bec_type = analysis.summary = analysis.recommended_action = None
        analysis.provider = analysis.model = None
        analysis.error_code = None
        analysis.policy_version = POLICY_VERSION
        try:
            analyzer = analyzer_factory()
            provider = analyzer.settings.llm_provider.strip().lower()
            analysis.provider = (
                provider if provider in {"openai", "google", "gemini", "groq"} else None
            )
            analysis.model = analyzer.settings.llm_model.strip() or None
            semantic = analyzer.assess(email, deterministic, context)
        except ValidationError:
            analysis.error_code = LLMErrorCode.NOT_CONFIGURED.value
        except SemanticAnalysisError as error:
            analysis.error_code = error.code.value
        else:
            analysis.status = AnalysisStatus.COMPLETED
            analysis.semantic_score = semantic.risk_score
            breakdown = build_score_breakdown(
                deterministic.score,
                semantic.risk_score,
                signal_codes={signal.code for signal in deterministic.signals},
                raw_deterministic_total=sum(
                    signal.contribution for signal in deterministic.signals
                ),
            )
            analysis.risk_score = breakdown.final_score
            analysis.risk_level = risk_level(analysis.risk_score).value
            analysis.score_breakdown = breakdown.model_dump(mode="json")
            kind = resolve_bec_type(analysis.risk_score, deterministic, semantic)
            analysis.bec_type = kind.value if kind else None
            analysis.signals += [Signal(**s.model_dump()).model_dump() for s in semantic.signals]
            analysis.summary = semantic.summary
            analysis.recommended_action = semantic.recommended_action
        if analysis.error_code is not None:
            analysis.status = AnalysisStatus.FALLBACK
            analysis.risk_score = deterministic.score
            analysis.risk_level = risk_level(deterministic.score).value
            analysis.score_breakdown = build_fallback_breakdown(
                deterministic.score,
                raw_deterministic_total=sum(
                    signal.contribution for signal in deterministic.signals
                ),
            ).model_dump(mode="json")
            analysis.bec_type = (
                deterministic.bec_type.value
                if deterministic.score >= 40 and deterministic.bec_type
                else None
            )
            analysis.summary = (
                "Evaluación limitada a reglas; el análisis de IA no estuvo disponible."
            )
            analysis.recommended_action = (
                "Revisar las señales y verificar solicitudes sensibles por un canal conocido. "
                "Un puntaje bajo no descarta fraude."
            )
            analysis.policy_version = f"{DETERMINISTIC_POLICY_VERSION}/fallback-v1"
        analysis.analyzed_at = datetime.now(UTC)
        session.flush()
        record_analysis_event(
            session,
            AuditAction.EMAIL_ANALYZED
            if analysis.status in {AnalysisStatus.COMPLETED, AnalysisStatus.FALLBACK}
            else AuditAction.EMAIL_ANALYSIS_FAILED,
            actor=actor,
            analysis_id=analysis.id,
            peer=peer,
        )
        ensure_alert_for_analysis(session, analysis, actor=actor, peer=peer)
        analysis.duration_ms = round(max(0.0, (perf_counter() - started) * 1000), 3)
        session.commit()
        return analysis
    except SQLAlchemyError:
        session.rollback()
        raise
