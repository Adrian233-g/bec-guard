"""Pruebas técnicas con mensajes fabricados; ninguna medición científica."""

import json
from collections import Counter
from datetime import UTC, datetime

import pytest

from research.bec_training.data import (
    CorpusUse,
    ResearchDataError,
    load_research_bytes,
    load_research_jsonl,
    split_groups,
    split_manifest,
)


def synthetic_rows(count=12):
    rows = []
    for label in ("BEC", "LEGITIMATE"):
        for index in range(count):
            kind = "attack" if label == "BEC" else "normal"
            rows.append(
                {
                    "case_id": f"{kind.upper()}-{index:03}",
                    "group_id": f"GROUP_{kind.upper()}_{index:03}",
                    "source_id": f"SOURCE_{kind.upper()}_{index:03}",
                    "label": label,
                    "expected_bec_type": "VENDOR_FRAUD" if label == "BEC" else None,
                    "is_hard_negative": label == "LEGITIMATE" and index % 3 == 0,
                    "label_rationale": "Caso ficticio revisado por dos anotadores.",
                    "annotation_status": "ADJUDICATED",
                    "email": {
                        "message_id": f"<{kind}-{index}@fixture.example>",
                        "sender_email": f"{kind}{index}@fixture.example",
                        "thread_id": f"THREAD_{kind}_{index}",
                        "subject": f"Caso {kind} {index}",
                        "body_text": f"Mensaje sintético {kind} número {index}",
                        "received_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                    },
                }
            )
    return rows


def write_corpus(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def test_grouped_split_is_reproducible_disjoint_and_has_both_classes(tmp_path):
    path = write_corpus(tmp_path / "fictitious.jsonl", synthetic_rows())
    cases = load_research_jsonl(path)
    first = split_groups(cases)
    assert first == split_groups(list(reversed(cases)))
    assert set(first) == {"train", "validation", "test"}
    assert len(set().union(*(set(ids) for ids in first.values()))) == len(cases)
    assert all(
        set(first[a]).isdisjoint(first[b])
        for a, b in (("train", "test"), ("train", "validation"), ("test", "validation"))
    )
    groups = {case.case_id: case.group_id for case in cases}
    assert all(
        not {groups[id_] for id_ in first[a]} & {groups[id_] for id_ in first[b]}
        for a, b in (("train", "test"), ("train", "validation"), ("test", "validation"))
    )
    labels = {case.case_id: case.label.value for case in cases}
    for ids in first.values():
        assert set(labels[id_] for id_ in ids) == {"BEC", "LEGITIMATE"}
    counts = Counter(labels[id_] for id_ in first["train"])
    assert all(counts[label] >= 3 for label in ("BEC", "LEGITIMATE"))
    report = split_manifest(path, cases)
    assert report["status"] == "TECHNICAL_FIXTURE_ONLY"
    assert report["splits"] == first
    assert len(report["dataset_sha256"]) == len(report["pipeline_sha256"]) == 64
    assert len(report["uv_lock_sha256"]) == 64
    assert report["dependencies"]["pydantic"]
    assert "streamlit_app.py" in report["research_code_sha256"]
    serialized = json.dumps(report)
    assert "body_text" not in serialized and "Mensaje" not in serialized
    assert "sender_email" not in serialized


@pytest.mark.parametrize("change", ["id", "message", "text", "sender", "thread", "source"])
def test_duplicates_and_cross_group_relations_fail_closed(tmp_path, change):
    rows = synthetic_rows()
    left, right = rows[0], rows[1]
    if change == "id":
        right["case_id"] = left["case_id"]
    elif change == "message":
        right["email"]["message_id"] = left["email"]["message_id"]
    elif change == "text":
        right["email"]["subject"] = left["email"]["subject"]
        right["email"]["body_text"] = left["email"]["body_text"]
    elif change == "sender":
        right["email"]["sender_email"] = left["email"]["sender_email"]
    elif change == "source":
        right["source_id"] = left["source_id"]
    else:
        right["email"]["thread_id"] = left["email"]["thread_id"]
    with pytest.raises(ResearchDataError, match="Duplicate|Related"):
        load_research_jsonl(write_corpus(tmp_path / "duplicate.jsonl", rows))


@pytest.mark.parametrize("field", ["sender_email", "body_text", "subject"])
def test_real_identifiers_are_rejected_even_in_free_text(tmp_path, field):
    rows = synthetic_rows()
    rows[0]["email"][field] = "persona@empresa.org"
    with pytest.raises(ResearchDataError):
        load_research_jsonl(write_corpus(tmp_path / "private.jsonl", rows))


def test_fixture_rejects_real_domains_in_metadata(tmp_path):
    rows = synthetic_rows()
    rows[0]["email"]["authentication_results"] = "mx.real-corp.example.org; spf=pass"
    with pytest.raises(ResearchDataError, match="authentication domains"):
        load_research_jsonl(write_corpus(tmp_path / "private-auth.jsonl", rows))
    rows = synthetic_rows()
    rows[0]["email"]["sender_name"] = "Alice persona@empresa.org"
    with pytest.raises(ResearchDataError):
        load_research_jsonl(write_corpus(tmp_path / "private-name.jsonl", rows))


def test_insufficient_groups_or_malformed_rows_never_leak_contents(tmp_path):
    small = load_research_jsonl(write_corpus(tmp_path / "small.jsonl", synthetic_rows(2)))
    with pytest.raises(ResearchDataError, match="groups|cases"):
        split_groups(small)
    rows = synthetic_rows()
    rows[0]["annotation_status"] = "SECRET_PRIVATE_TEXT"
    with pytest.raises(ResearchDataError) as failure:
        load_research_jsonl(write_corpus(tmp_path / "malformed.jsonl", rows))
    assert "SECRET_PRIVATE_TEXT" not in str(failure.value)


def test_historical_dataset_cannot_be_loaded_as_new_corpus():
    from app.services.dataset import DEFAULT_DATASET_PATH

    with pytest.raises(ResearchDataError, match="Invalid research row"):
        load_research_jsonl(DEFAULT_DATASET_PATH)


def test_cli_writes_manifest_once_without_private_email(tmp_path, capsys):
    from research.bec_training.__main__ import main

    dataset = write_corpus(tmp_path / "synthetic.jsonl", synthetic_rows())
    output = tmp_path / "manifest.json"
    args = [str(dataset), "--output", str(output)]
    assert main(args) == 0
    content = output.read_text(encoding="utf-8")
    assert json.loads(content)["status"] == "TECHNICAL_FIXTURE_ONLY"
    assert "body_text" not in content and "sender_email" not in content
    assert main(args) == 1
    assert "body_text" not in capsys.readouterr().err


def test_train_pipeline_uses_group_cv_and_test_is_opt_in(tmp_path):
    pytest.importorskip("sklearn")
    from research.bec_training.training import train_offline

    cases = load_research_jsonl(write_corpus(tmp_path / "demo.jsonl", synthetic_rows()))
    report, model = train_offline(cases)
    assert model is not None
    assert len(report["cv"]) == 12
    assert all(len(trial["folds"]) == 3 for trial in report["cv"])
    assert report["test_status"] == "NOT_RUN"
    assert report["test"] is None
    assert report["selected"]["threshold"] in (0.4, 0.5, 0.6)
    assert "body_text" not in json.dumps(report) and "Mensaje" not in json.dumps(report)
    second, _ = train_offline(cases, evaluate_test=True)
    assert second["selected"] == report["selected"]
    assert second["test_status"] == "FIXTURE_DEMO_ONLY"
    assert sum(second["test"][key] for key in ("tp", "fp", "tn", "fn")) == sum(
        second["split_counts"]["test"].values()
    )


def test_offline_conditions_paired_and_unavailable_semantics_are_not_scored(tmp_path):
    from app.services.deterministic_analysis import AnalysisContext
    from research.bec_training.experiments import compare_offline

    cases = load_research_jsonl(write_corpus(tmp_path / "demo.jsonl", synthetic_rows(3)))
    plain = compare_offline(cases, AnalysisContext([], []))
    assert plain["C2"] == plain["C3"] == plain["C5"] == plain["C6"] == "NOT_RUN"
    assert [row["case_id"] for row in plain["C1"]] == [row["case_id"] for row in plain["C7"]]
    assert all(
        a["score"] == b["score"] and b["status"] == "FALLBACK"
        for a, b in zip(plain["C1"], plain["C7"], strict=True)
    )
    scores = {case.case_id: 50 for case in cases}
    demo = compare_offline(
        cases, AnalysisContext([], []), semantic_scores=scores, semantic_source="HYPOTHETICAL"
    )
    assert all(len(demo[key]) == len(cases) for key in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"))
    assert all(
        not strict["alert"] or normal["alert"]
        for normal, strict in zip(demo["C3"], demo["C6"], strict=True)
    )
    assert all(row["alert_threshold"] == 70 for row in demo["C6"])
    with pytest.raises(ResearchDataError):
        compare_offline(cases, AnalysisContext([], []), semantic_scores=scores)
    with pytest.raises(ResearchDataError, match="provider, model"):
        compare_offline(
            cases,
            AnalysisContext([], []),
            semantic_scores=scores,
            semantic_source="CACHED_AUTHORIZED",
        )
    with pytest.raises(ResearchDataError):
        compare_offline(
            cases,
            AnalysisContext([], []),
            semantic_scores={"UNKNOWN": 50},
            semantic_source="HYPOTHETICAL",
        )


def test_research_report_aggregates_counts_and_does_not_export_email(tmp_path):
    from app.services.deterministic_analysis import AnalysisContext
    from research.bec_training.experiments import compare_offline
    from research.bec_training.reporting import summarize_experiment

    path = write_corpus(tmp_path / "demo.jsonl", synthetic_rows())
    cases = load_research_jsonl(path)
    raw = compare_offline(
        cases,
        AnalysisContext([], []),
        semantic_scores={case.case_id: 50 for case in cases},
        semantic_source="HYPOTHETICAL",
    )
    report = summarize_experiment(raw, provenance=split_manifest(path, cases))
    assert report["conditions"]["C2"]["alerts"]["fp"] == 12
    assert report["conditions"]["C7"]["completed"] == 0
    assert report["conditions"]["C7"]["fallback"] == 24
    assert report["conditions"]["C7"]["semantic_coverage"] is None
    assert report["conditions"]["C3"]["semantic_coverage"] is None
    assert report["conditions"]["C6"]["alert_threshold"] == 70
    assert report["scientific_inference"].startswith("NOT_EXECUTED")
    text = json.dumps(report)
    assert "body_text" not in text and "sender_email" not in text
    assert "ATTACK-" not in text and "Mensaje" not in text


def test_demo_fixture_is_valid_and_split_in_memory():
    from collections import Counter

    from research.bec_training.demo import demo_cases

    cases = demo_cases()
    assert len(cases) == 300
    assert Counter(case.label.value for case in cases) == {"BEC": 120, "LEGITIMATE": 180}
    assert Counter(case.expected_bec_type.value for case in cases if case.expected_bec_type) == {
        "BANK_ACCOUNT_CHANGE": 30,
        "EXECUTIVE_IMPERSONATION": 30,
        "VENDOR_FRAUD": 30,
        "SENSITIVE_DATA_REQUEST": 30,
    }
    assert sum(case.is_hard_negative for case in cases) == 30
    report = split_manifest(None, cases)
    assert sum(sum(counts.values()) for counts in report["counts"].values()) == 300
    assert report["status"] == "TECHNICAL_FIXTURE_ONLY"
    assert all(set(counts) == {"BEC", "LEGITIMATE"} for counts in report["counts"].values())


def test_technical_statistics_on_demo_fixture_is_labeled_demo():
    from pathlib import Path

    from research.bec_training.demo import demo_cases
    from research.bec_training.experiments import compare_offline
    from research.bec_training.inputs import load_context_bytes
    from research.bec_training.statistics import technical_statistics, wilson_interval

    assert wilson_interval(8, 10)["low"] < 0.8 < wilson_interval(8, 10)["high"]
    assert wilson_interval(0, 0) is None
    cases = demo_cases()
    context, _ = load_context_bytes(
        Path(__file__).resolve().parents[2].joinpath("datasets", "context.json").read_bytes(),
        use=CorpusUse(),
    )
    raw = compare_offline(
        cases,
        context,
        semantic_scores={case.case_id: 50 for case in cases},
        semantic_source="HYPOTHETICAL",
    )
    stats = technical_statistics(raw, resamples=200)
    assert stats["basis"] == "FIXTURE_DEMONSTRATION_ONLY"
    assert stats["scientific_inference"] == "NOT_EXECUTED"
    assert stats["conditions"]["C1"]["total"] == 300
    assert 0 < stats["conditions"]["C1"]["confusion"]["tp"] < 120
    assert stats["conditions"]["C3"]["confusion"]["tp"] > 0
    paired = stats["paired"]
    assert paired["status"] == "ESTIMATED_TECHNICAL_ONLY"
    assert paired["comparisons"]["C3_vs_C2"]["discordances"] > 10
    assert paired["comparisons"]["C3_vs_C2"]["p_mcnemar_exact"] is not None
    assert paired["comparisons"]["C3_vs_C2"]["ci95_group_bootstrap"]["recall"] is not None
    text = json.dumps(stats)
    assert "body_text" not in text and "sender_email" not in text and "DEMO-0001" not in text


def test_technical_statistics_reports_not_executed_without_semantics():
    from pathlib import Path

    from research.bec_training.demo import demo_cases
    from research.bec_training.experiments import compare_offline
    from research.bec_training.inputs import load_context_bytes
    from research.bec_training.statistics import technical_statistics

    cases = demo_cases()
    context, _ = load_context_bytes(
        Path(__file__).resolve().parents[2].joinpath("datasets", "context.json").read_bytes(),
        use=CorpusUse(),
    )
    stats = technical_statistics(compare_offline(cases, context), resamples=50)
    assert stats["conditions"]["C3"]["status"] == "NOT_RUN"
    assert stats["paired"]["status"] == "NOT_EXECUTED"


def test_authorized_corpus_requires_reference_and_can_use_real_domains(tmp_path):
    rows = synthetic_rows()
    rows[0]["email"]["sender_email"] = "persona@empresa.org"
    contents = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    with pytest.raises(ResearchDataError):
        load_research_bytes(contents)
    with pytest.raises(ValueError):
        CorpusUse(kind="authorized")
    use = CorpusUse(kind="authorized", permission_ref="APROBACION_001")
    cases = load_research_bytes(contents, use=use)
    report = split_manifest(None, cases, raw_bytes=contents, use=use)
    assert report["status"] == "AUTHORIZED_CORPUS_UNVERIFIED"
    assert report["corpus_use"]["permission_ref"] == "APROBACION_001"
    assert "persona@empresa.org" not in json.dumps(report)
    eval_use = CorpusUse(
        kind="authorized", permission_ref="APROBACION_001", role="independent_evaluation"
    )
    eval_report = split_manifest(None, cases, use=eval_use)
    assert set(eval_report["splits"]) == {"evaluation"}
    pytest.importorskip("sklearn")
    from research.bec_training.training import train_offline

    with pytest.raises(ResearchDataError, match="cannot train"):
        train_offline(cases, use=eval_use)


def test_synthetic_training_status_cannot_enter_authorized_or_evaluation_corpus():
    rows = synthetic_rows()
    rows[0]["annotation_status"] = "SYNTHETIC_GENERATED"
    contents = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    use = CorpusUse(kind="authorized", permission_ref="APROBACION_001")
    with pytest.raises(ResearchDataError, match="adjudicated"):
        load_research_bytes(contents, use=use)
    eval_use = CorpusUse(role="independent_evaluation")
    with pytest.raises(ResearchDataError, match="adjudicated"):
        load_research_bytes(contents, use=eval_use)


def test_near_duplicate_different_groups_is_rejected_but_same_group_allowed(tmp_path):
    rows = synthetic_rows()
    common = (
        "Solicitud documentada del equipo de compras y facturación con referencia verificada "
        "por el área administrativa mediante registros internos y procedimiento ordinario "
        "de revisión previa con la unidad responsable del contrato"
    )
    rows[0]["email"]["subject"] = "Revisión de solicitud administrativa"
    rows[1]["email"]["subject"] = "Revisión de solicitud administrativa"
    rows[0]["email"]["body_text"] = common + " en la oficina central hoy mismo."
    rows[1]["email"]["body_text"] = common + " en la oficina regional hoy mismo."
    with pytest.raises(ResearchDataError, match="Near-duplicate"):
        load_research_jsonl(write_corpus(tmp_path / "related.jsonl", rows))
    rows[1]["group_id"] = rows[0]["group_id"]
    assert len(load_research_jsonl(write_corpus(tmp_path / "grouped.jsonl", rows))) == 24


def test_exact_duplicate_is_rejected_even_within_same_group(tmp_path):
    rows = synthetic_rows()
    rows[1]["group_id"] = rows[0]["group_id"]
    rows[1]["email"]["subject"] = rows[0]["email"]["subject"]
    rows[1]["email"]["body_text"] = rows[0]["email"]["body_text"]
    with pytest.raises(ResearchDataError, match="Duplicate normalized"):
        load_research_jsonl(write_corpus(tmp_path / "exact.jsonl", rows))


def test_missing_semantic_scores_do_not_become_true_negatives(tmp_path):
    from app.services.deterministic_analysis import AnalysisContext
    from research.bec_training.experiments import compare_offline
    from research.bec_training.reporting import summarize_experiment

    cases = load_research_jsonl(write_corpus(tmp_path / "cases.jsonl", synthetic_rows()))
    scores = {case.case_id: 50 for case in cases}
    scores[cases[0].case_id] = None  # BEC sin evaluación semántica.
    scores[cases[-1].case_id] = None  # Legítimo sin evaluación semántica.
    raw = compare_offline(
        cases, AnalysisContext([], []), semantic_scores=scores, semantic_source="HYPOTHETICAL"
    )
    result = summarize_experiment(raw)
    c2, c3 = result["conditions"]["C2"], result["conditions"]["C3"]
    assert c2["errors"] == 2 and c2["score_coverage"] == 22 / 24
    assert sum(c2["alerts"][key] for key in ("tp", "fp", "tn", "fn")) == 22
    assert c2["alerts"]["effective_recall"] == 11 / 12
    assert c3["fallback"] == 2 and c3["score_coverage"] == 1
    assert result["conditions"]["C5"]["errors"] == 2


def test_group_bootstrap_paired_mcnemar_and_holm_are_reproducible():
    from research.bec_training.statistics import paired_inference

    rows = {key: [] for key in ("C1", "C2", "C3")}
    for index in range(40):
        label = "BEC" if index < 20 else "LEGITIMATE"
        truth = label == "BEC"
        for condition in rows:
            prediction = truth
            if condition == "C1" and index < 12:
                prediction = not truth
            if condition == "C2" and index >= 28:
                prediction = not truth
            rows[condition].append(
                {
                    "case_id": f"PAIR-{index}",
                    "group_id": f"GROUP-{index}",
                    "label": label,
                    "alert": prediction,
                    "status": "COMPLETED",
                }
            )
    rows.update(
        {
            "corpus_use": CorpusUse(
                kind="authorized", role="independent_evaluation", permission_ref="PERM_001"
            ).model_dump(),
            "semantic_source": "CACHED_AUTHORIZED",
        }
    )
    first = paired_inference(rows)
    assert first == paired_inference(rows)
    assert first["status"] == "ESTIMATED"
    assert first["resamples_requested"] == 2000
    for pair in first["comparisons"].values():
        assert pair["pairs"] == pair["groups"] == 40
        assert pair["p_mcnemar_exact"] < 0.01
        assert pair["p_holm"] >= pair["p_mcnemar_exact"]
        assert pair["ci95_group_bootstrap"]["recall"]["lower"] >= 0
    rows["corpus_use"]["kind"] = "fixture"
    assert paired_inference(rows)["status"] == "NOT_EXECUTED"


def test_statistical_analysis_declines_small_groups_and_errors():
    from research.bec_training.statistics import paired_inference

    rows = {
        key: [
            {
                "case_id": str(i),
                "group_id": str(i),
                "label": "BEC" if i < 3 else "LEGITIMATE",
                "alert": False,
                "status": "ERROR" if key == "C2" and i == 0 else "COMPLETED",
            }
            for i in range(6)
        ]
        for key in ("C1", "C2", "C3")
    }
    rows["corpus_use"] = CorpusUse(
        kind="authorized", role="independent_evaluation", permission_ref="PERM_001"
    ).model_dump()
    rows["semantic_source"] = "CACHED_AUTHORIZED"
    result = paired_inference(rows)
    assert result["status"] == "NOT_ESTIMABLE"
    assert result["pairs"] == 5


def test_context_and_score_cache_require_exact_input_hashes(tmp_path):
    import hashlib

    from research.bec_training.inputs import (
        EMPTY_CONTEXT_SHA256,
        load_context_bytes,
        load_semantic_cache,
    )

    cases = load_research_jsonl(write_corpus(tmp_path / "rows.jsonl", synthetic_rows()))
    contents = (tmp_path / "rows.jsonl").read_bytes()
    context_bytes = b'{"executives":[],"vendors":[]}'
    context, context_sha = load_context_bytes(context_bytes, use=CorpusUse())
    assert not context.executives and not context.vendors
    assert context_sha == EMPTY_CONTEXT_SHA256
    dataset_sha = hashlib.sha256(contents).hexdigest()
    cache = {
        "metadata": {
            "provider": "test-provider",
            "model": "model-v1",
            "prompt_version": "semantic-v2",
            "dataset_sha256": dataset_sha,
            "context_sha256": context_sha,
        },
        "scores": {case.case_id: (None if case == cases[0] else 80) for case in cases},
    }
    encoded = json.dumps(cache).encode()
    scores, provenance = load_semantic_cache(
        encoded,
        dataset_sha256=dataset_sha,
        context_sha256=context_sha,
        case_ids={case.case_id for case in cases},
    )
    assert scores[cases[0].case_id] is None
    assert len(provenance["cache_sha256"]) == 64
    with pytest.raises(ResearchDataError, match="does not match"):
        load_semantic_cache(
            encoded, dataset_sha256="f" * 64, context_sha256=context_sha, case_ids=set(scores)
        )
    cache["scores"][cases[1].case_id] = True
    with pytest.raises(ResearchDataError, match="structure"):
        load_semantic_cache(
            json.dumps(cache).encode(),
            dataset_sha256=dataset_sha,
            context_sha256=context_sha,
            case_ids=set(scores),
        )
    with pytest.raises(ResearchDataError, match="context"):
        load_context_bytes(b'{"executives":[{"email":"SECRET"}]}', use=CorpusUse())


def test_c4_real_cache_without_independent_no_context_scores_is_not_run(tmp_path):
    from app.services.deterministic_analysis import AnalysisContext
    from research.bec_training.experiments import compare_offline

    cases = load_research_jsonl(write_corpus(tmp_path / "cases.jsonl", synthetic_rows()))
    scores = {case.case_id: 50 for case in cases}
    provenance = {
        "provider": "mock",
        "model": "v1",
        "prompt_version": "v1",
        "cache_sha256": "a" * 64,
    }
    result = compare_offline(
        cases,
        AnalysisContext([], []),
        semantic_scores=scores,
        semantic_source="CACHED_AUTHORIZED",
        semantic_provenance=provenance,
    )
    assert result["C4"] == "NOT_RUN"
    paired = compare_offline(
        cases,
        AnalysisContext([], []),
        semantic_scores=scores,
        semantic_source="CACHED_AUTHORIZED",
        semantic_provenance=provenance,
        no_context_scores=scores,
        no_context_semantic_provenance={
            **provenance,
            "cache_sha256": "b" * 64,
        },
        no_context_cache_sha256="b" * 64,
    )
    assert len(paired["C4"]) == len(cases)
    with pytest.raises(ResearchDataError, match="same provider"):
        compare_offline(
            cases,
            AnalysisContext([], []),
            semantic_scores=scores,
            semantic_source="CACHED_AUTHORIZED",
            semantic_provenance=provenance,
            no_context_scores=scores,
            no_context_semantic_provenance={**provenance, "model": "different-model"},
            no_context_cache_sha256="b" * 64,
        )


def test_context_ablation_changes_identity_evidence():
    from app.scripts.check_development import DEFAULT_CONTEXT_PATH
    from research.bec_training.experiments import compare_offline
    from research.bec_training.inputs import load_context_bytes

    source = synthetic_rows(1)[0]
    source["email"]["sender_name"] = "Nora Prisma"
    source["email"]["sender_email"] = "nora@otra-empresa.example"
    source["email"]["body_text"] = "Transfiere el pago hoy a una cuenta nueva."
    case = load_research_bytes((json.dumps(source) + "\n").encode())[0]
    context, _ = load_context_bytes(DEFAULT_CONTEXT_PATH.read_bytes(), use=CorpusUse())
    result = compare_offline([case], context)
    assert result["C1"][0]["score"] > result["C4"][0]["score"]


def test_authorized_training_records_frozen_selection_before_optional_test(tmp_path):
    import hashlib

    pytest.importorskip("sklearn")
    from research.bec_training.demo import demo_cases
    from research.bec_training.training import train_offline

    rows = [case.model_dump(mode="json") for case in demo_cases()]
    rows[0]["email"]["sender_email"] = "persona@empresa.org"
    path = write_corpus(tmp_path / "new.jsonl", rows)
    use = CorpusUse(kind="authorized", permission_ref="PERM_001")
    cases = load_research_jsonl(path, use=use)
    with pytest.raises(ResearchDataError, match="dataset SHA"):
        train_offline(cases, use=use)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    training, _ = train_offline(cases, use=use, dataset_sha256=digest)
    final, _ = train_offline(
        cases,
        use=use,
        dataset_sha256=digest,
        evaluate_test=True,
        test_lock_dir=tmp_path / "locks",
    )
    assert training["test_status"] == "NOT_RUN"
    assert final["test_status"] == "AUTHORIZED_TEST_EVALUATED"
    assert training["selection_frozen_sha256"] == final["selection_frozen_sha256"]
    assert len(final["selection_frozen_sha256"]) == 64
    with pytest.raises(ResearchDataError, match="already claimed"):
        train_offline(
            cases,
            use=use,
            dataset_sha256=digest,
            evaluate_test=True,
            test_lock_dir=tmp_path / "locks",
        )


def test_ranking_metrics_use_scores_and_refuse_missing_scores():
    from research.bec_training.reporting import ranking_metrics

    rows = [
        {"label": "BEC", "score": 90},
        {"label": "LEGITIMATE", "score": 70},
        {"label": "BEC", "score": 50},
        {"label": "LEGITIMATE", "score": 10},
    ]
    metrics = ranking_metrics(rows)
    assert metrics["average_precision"] == pytest.approx((1 + 2 / 3) / 2)
    assert metrics["roc_auc"] == pytest.approx(0.75)
    rows[2]["score"] = None
    assert ranking_metrics(rows)["status"] == "NOT_ESTIMABLE_INCOMPLETE_COVERAGE"
