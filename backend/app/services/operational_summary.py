"""Operational SQL aggregates shared by dashboard and reports; no dataset imports."""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BECAlert, Email, EmailAnalysis


def date_conditions(column, from_date: date | None, to_date: date | None) -> list:
    conditions = []
    if from_date:
        conditions.append(column >= datetime.combine(from_date, time.min, UTC))
    if to_date:
        if to_date == date.max:
            conditions.append(column <= datetime.max.replace(tzinfo=UTC))
        else:
            conditions.append(column < datetime.combine(to_date + timedelta(days=1), time.min, UTC))
    return conditions


def operational_summary(
    session: Session, from_date: date | None = None, to_date: date | None = None
) -> dict:
    def counts(column, model, timestamp):
        return dict(
            session.execute(
                select(column, func.count())
                .select_from(model)
                .where(*date_conditions(timestamp, from_date, to_date))
                .group_by(column)
            ).all()
        )

    analyses = counts(EmailAnalysis.status, EmailAnalysis, EmailAnalysis.analyzed_at)
    alerts = counts(BECAlert.status, BECAlert, BECAlert.created_at)
    verdicts = counts(BECAlert.verdict, BECAlert, BECAlert.created_at)
    risks = counts(EmailAnalysis.risk_level, EmailAnalysis, EmailAnalysis.analyzed_at)
    types = counts(EmailAnalysis.bec_type, EmailAnalysis, EmailAnalysis.analyzed_at)
    risk_denominator = sum(risks.get(key, 0) for key in ("LOW", "MEDIUM", "HIGH", "CRITICAL"))
    type_denominator = sum(count for key, count in types.items() if key is not None)
    alert_denominator = sum(alerts.get(key, 0) for key in ("OPEN", "UNDER_REVIEW", "CLOSED"))
    verdict_denominator = sum(verdicts.get(key, 0) for key in ("CONFIRMED_BEC", "FALSE_POSITIVE"))

    def percentages(counts_by_key: dict, denominator: int) -> dict:
        return {
            str(key): round(100 * count / denominator, 1) if denominator else 0.0
            for key, count in counts_by_key.items()
            if key is not None
        }

    risk_distribution = {key: risks.get(key, 0) for key in ("LOW", "MEDIUM", "HIGH", "CRITICAL")}
    alert_distribution = {
        key.lower(): alerts.get(key, 0) for key in ("OPEN", "UNDER_REVIEW", "CLOSED")
    }
    verdict_distribution = {
        key.lower(): verdicts.get(key, 0) for key in ("CONFIRMED_BEC", "FALSE_POSITIVE")
    }
    return {
        "emails_total": session.scalar(
            select(func.count())
            .select_from(Email)
            .where(*date_conditions(Email.ingested_at, from_date, to_date))
        ),
        "analyses_completed": analyses.get("COMPLETED", 0),
        "analyses_fallback": analyses.get("FALLBACK", 0),
        "analyses_error": analyses.get("ERROR", 0),
        "alerts": alert_distribution,
        "verdicts": verdict_distribution,
        "risk_distribution": risk_distribution,
        "bec_type_distribution": [
            {
                "bec_type": key,
                "count": count,
                "percentage": round(100 * count / type_denominator, 1) if type_denominator else 0.0,
            }
            for key, count in sorted(types.items(), key=lambda item: item[0] or "")
            if key is not None
        ],
        "distribution_denominators": {
            "risk": risk_denominator,
            "bec_type": type_denominator,
            "alert_status": alert_denominator,
            "verdict": verdict_denominator,
        },
        "distribution_percentages": {
            "risk": percentages(risk_distribution, risk_denominator),
            "alert_status": percentages(alert_distribution, alert_denominator),
            "verdict": percentages(verdict_distribution, verdict_denominator),
        },
    }
