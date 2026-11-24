"""Borradores por regla SOLO de TRAIN: NO son revisión humana ni gold labels.

No se leen textos de validation/test para crear borradores, ni se consulta
el clasificador v3. Esos conjuntos permanecen íntegros para ADRIAN.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from research.bec_training import triage_rules
from research.bec_training.external_benchmark import _sha
from research.bec_training.single_review import _exclusive, load_packet

STATUS = "AI_ASSISTED_DETERMINISTIC_DRAFT_NOT_GROUND_TRUTH"


def _proposal(subject: str, body: str) -> dict:
    text = f"{subject}\n{body}"
    triage = triage_rules.suggest(subject, body)
    if triage.bucket == "POSIBLE_BEC":
        if any(word in text.casefold() for word in ("ceo", "cfo", "chief executive")):
            subtype = "EXECUTIVE_IMPERSONATION"
        elif any(word in text.casefold() for word in ("vendor", "supplier")):
            subtype = "VENDOR_FRAUD"
        elif any(word in text.casefold() for word in ("bank account", "routing number")):
            subtype = "BANK_ACCOUNT_CHANGE"
        elif any(word in text.casefold() for word in ("payroll", "w-2")):
            subtype = "SENSITIVE_DATA_REQUEST"
        else:
            subtype = "OTHER"
        label = "BEC"
    elif triage.bucket == "OTRO_CLARO":
        label, subtype = "OTHER_PHISHING", None
    else:
        label, subtype = "UNCERTAIN", None
    matched = [
        match.group(0).casefold()
        for pattern in (
            triage_rules._FINANCE,
            triage_rules._BUSINESS,
            triage_rules._ACTION,
            triage_rules._ACCOUNT_PHISHING,
            triage_rules._CONSUMER,
        )
        if (match := pattern.search(text)) is not None
    ]
    return {
        "proposed_label": label,
        "proposed_type": subtype,
        "bucket": triage.bucket,
        "reason_es": triage.reason_es,
        "matched_patterns": matched,
    }


def build_drafts(review_dir: Path, output: Path) -> dict:
    packet, packet_sha256 = load_packet(review_dir / "blind_packet.jsonl")
    triage_path = review_dir / "triage_manifest.json"
    triage = json.loads(triage_path.read_text(encoding="utf-8"))
    if (
        triage.get("status") != "TRIAGE_REVIEW_PENDING"
        or triage.get("packet_sha256") != packet_sha256
        or triage.get("rules_code_sha256") != _sha(Path(triage_rules.__file__))
        or set(triage.get("rule_buckets", {})) != {row["case_id"] for row in packet}
    ):
        raise ValueError("Triage rule or blind packet differs from the pinned version")
    proposals = {}
    training_ids = set(triage["publisher_splits"]["train"])
    for row in packet:
        case_id = row["case_id"]
        if case_id not in training_ids:
            continue
        proposal = _proposal(row["subject"], row["body"])
        if proposal["bucket"] != triage["rule_buckets"][case_id]:
            raise ValueError("Pinned triage and draft labels disagree")
        proposals[case_id] = {
            "content_sha256": row["content_sha256"],
            **proposal,
        }
    result = {
        "status": STATUS,
        "annotator_id": "AI_RULE_DRAFT_V1_NOT_ADRIAN",
        "packet_sha256": packet_sha256,
        "triage_manifest_sha256": _sha(triage_path),
        "code_sha256": _sha(Path(__file__)),
        "method": "FIXED_TEXT_RULE_WITH_SPAN_MATCHES; NO_SEMANTIC_MODEL; HUMAN_TEST_REQUIRED",
        "counts": dict(Counter(row["proposed_label"] for row in proposals.values())),
        "train_phishing_drafted": len(proposals),
        "test_status": "SEALED_NOT_EVALUATED",
        "real_world_validity": "NOT_ESTABLISHED",
        "proposals": proposals,
    }
    _exclusive(output, (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode())
    return {
        key: result[key]
        for key in ("status", "annotator_id", "counts", "train_phishing_drafted", "test_status")
    }


def load_drafts(review_dir: Path, *, packet_sha256: str, triage_sha256: str) -> dict:
    path = review_dir / "ai_drafts.json"
    if not path.is_file():
        return {}
    contents = path.read_bytes()
    if len(contents) > 2_000_000:
        raise ValueError("Draft file exceeds its local budget")
    data = json.loads(contents)
    if (
        data.get("status") != STATUS
        or data.get("packet_sha256") != packet_sha256
        or data.get("triage_manifest_sha256") != triage_sha256
        or data.get("annotator_id") != "AI_RULE_DRAFT_V1_NOT_ADRIAN"
        or data.get("code_sha256") != _sha(Path(__file__))
    ):
        raise ValueError("Draft provenance does not match the blind packet")
    return data["proposals"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_drafts(args.review_dir, args.review_dir / "ai_drafts.json")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
