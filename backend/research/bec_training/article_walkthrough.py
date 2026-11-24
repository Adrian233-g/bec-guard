"""Recorre entrenamiento exportado -> HTTP -> PostgreSQL -> alerta en DB descartable."""

import argparse
import hashlib
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.api.email_analysis import get_analyzer_factory, get_model_predictor
from app.core.config import AuthSettings, LLMSettings, Settings, TrainedModelSettings
from app.core.passwords import hash_password
from app.main import create_app
from app.models import Mailbox, Role, User
from app.services.semantic_analysis import SemanticAnalyzer
from app.services.trained_model import ModelPrediction, predict_email


def walkthrough(db_url: str, model_dir: Path) -> dict:
    url = make_url(db_url)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host != "127.0.0.1"
        or url.port in {None, 5432}
        or not (url.database or "").startswith("bec_guard_test_")
        or not url.username
    ):
        raise ValueError("Walkthrough requires a separate local disposable test database")
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as connection:
            if set(inspect(connection).get_schema_names()) - {"public", "information_schema"}:
                raise ValueError("Walkthrough database has unexpected schemas")
            if inspect(connection).get_table_names(schema="public"):
                raise ValueError("Walkthrough requires an empty database")
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        password = secrets.token_urlsafe(30)
        auth = AuthSettings(_env_file=None, jwt_secret_key=secrets.token_urlsafe(48))
        with Session(engine) as session:
            user = User(
                name="Article Walkthrough",
                email="article-walkthrough@research.example",
                password_hash=hash_password(password),
                role=Role.ANALYST,
            )
            session.add(user)
            session.flush()
            session.add(Mailbox(user_id=user.id, email_address=user.email, status="ACTIVE"))
            session.commit()
        model_path = model_dir / "model.joblib"
        report_path = model_dir / "training_report.json"
        model_sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
        report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
        settings = Settings(
            _env_file=None,
            postgres_host="127.0.0.1",
            postgres_port=url.port,
            postgres_db=url.database or "",
            postgres_user=url.username or "",
            postgres_password=url.password or "local-disposable",
        )
        application = create_app(settings, auth)
        application.dependency_overrides[get_analyzer_factory] = lambda: (
            lambda: SemanticAnalyzer(LLMSettings(_env_file=None, llm_provider="", llm_model=""))
        )
        # Scope model configuration to this process; do not modify a product .env.
        os.environ.update(
            {
                "BEC_MODEL_PATH": str(model_path.resolve()),
                "BEC_MODEL_REPORT_PATH": str(report_path.resolve()),
                "BEC_MODEL_SHA256": model_sha,
                "BEC_MODEL_REPORT_SHA256": report_sha,
            }
        )
        results = {}
        with TestClient(application) as client:
            login = client.post(
                "/api/auth/login",
                json={"email": "article-walkthrough@research.example", "password": password},
            )
            if login.status_code != 200:
                raise ValueError("Login failed in isolated walkthrough")
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            for mode in ("shadow", "assist"):
                # Assist is simulated ONLY by an override in this isolated
                # TestClient; fixture reports cannot activate product assist.
                os.environ["BEC_MODEL_MODE"] = "shadow"

                def demo_predictor(email, mode=mode):
                    settings = TrainedModelSettings(
                        _env_file=None,
                        bec_model_mode="shadow",
                        bec_model_path=model_path,
                        bec_model_sha256=model_sha,
                        bec_model_report_path=report_path,
                        bec_model_report_sha256=report_sha,
                    )
                    prediction = predict_email(email, settings)
                    if prediction is not None and mode == "assist":
                        return ModelPrediction(
                            "assist", prediction.probability, prediction.score, prediction.sha256
                        )
                    return prediction

                def provide_demo_predictor():
                    return demo_predictor

                application.dependency_overrides[get_model_predictor] = provide_demo_predictor
                incoming = client.post(
                    "/api/emails",
                    headers=headers,
                    json={
                        "message_id": f"<article-{mode}@research.example>",
                        "sender_name": "Persona",
                        "sender_email": "person@other.example",
                        "to_recipients": ["article-walkthrough@research.example"],
                        "subject": "Pago urgente",
                        "body_text": "transferencia bancaria",
                        "received_at": datetime.now(UTC).isoformat(),
                    },
                )
                if incoming.status_code != 201:
                    raise ValueError("Ingestion failed in isolated walkthrough")
                email_id = incoming.json()["id"]
                response = client.post(f"/api/emails/{email_id}/analyze", headers=headers)
                if response.status_code != 200:
                    raise ValueError("Analysis failed in isolated walkthrough")
                analysis = response.json()
                reread = client.get(f"/api/emails/{email_id}/analysis", headers=headers)
                if reread.status_code != 200 or reread.json() != analysis:
                    raise ValueError("Analysis was not persisted")
                repeated = client.post(f"/api/emails/{email_id}/analyze", headers=headers)
                if repeated.status_code != 200 or repeated.json() != analysis:
                    raise ValueError("Analysis was not idempotent")
                alerts = client.get("/api/alerts", headers=headers)
                if alerts.status_code != 200:
                    raise ValueError("Alert queue failed")
                if mode == "assist":
                    if len(alerts.json()) != 1:
                        raise ValueError("Assisted alert was not queued")
                    detail = client.get(f"/api/alerts/{alerts.json()[0]['id']}", headers=headers)
                    if (
                        detail.status_code != 200
                        or detail.json()["analysis"]["id"] != analysis["id"]
                    ):
                        raise ValueError("Assisted alert detail is not linked to the analysis")
                results[mode] = {
                    "ingest_http": incoming.status_code,
                    "analysis_http": response.status_code,
                    "analysis_status": analysis["status"],
                    "deterministic_score": analysis["deterministic_score"],
                    "final_score": analysis["risk_score"],
                    "model_mode": analysis["score_breakdown"]["model_mode"],
                    "model_score": analysis["score_breakdown"]["model_score"],
                    "alert_count": len(alerts.json()),
                    "persisted": True,
                    "idempotent": True,
                    "alert_detail_linked": mode == "assist",
                }
        if (
            results["shadow"]["alert_count"] != 0
            or results["assist"]["alert_count"] != 1
            or results["shadow"]["final_score"] >= 50
            or results["assist"]["final_score"] < 50
        ):
            raise ValueError("Model modes did not produce the expected alert behavior")
        return {
            "status": "ISOLATED_SYNTHETIC_HTTP_DB_WALKTHROUGH",
            "model_sha256": model_sha,
            "database": "temporary_empty_postgresql",
            "llm_calls": 0,
            "modes": results,
        }
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-db-url", required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = walkthrough(args.test_db_url, args.model_dir)
    descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
