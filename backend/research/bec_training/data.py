"""Validación de corpus aislados y partición agrupada, sin llamadas externas.

El holdout histórico no satisface este contrato y nunca se carga aquí por defecto.
"""

import hashlib
import importlib.metadata
import io
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.schemas.dataset import DatasetLabel, ExpectedBECType
from app.schemas.email import EmailIngestRequest

SEED = 20261118
SPLITS = ("train", "validation", "test")
FRACTIONS = (0.70, 0.15, 0.15)
_ADDRESS = re.compile(r"[\w.+-]+@([\w.-]+)")
_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
_HOST = re.compile(
    r"(?<![\w.-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?![\w.-])",
    re.I,
)
MAX_CASES = 5_000
MAX_INPUT_BYTES = 20_000_000


class ResearchDataError(ValueError):
    """Error sin campos de correo ni contenido personal."""


class CorpusUse(BaseModel):
    """Declaración explícita de uso; no verifica jurídicamente una autorización."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["fixture", "authorized"] = "fixture"
    permission_ref: str | None = Field(default=None, pattern=r"^[A-Z0-9_-]{3,64}$")
    role: Literal["training", "independent_evaluation"] = "training"

    @model_validator(mode="after")
    def check_permission(self):
        if (self.kind == "authorized") != (self.permission_ref is not None):
            raise ValueError("Authorized corpus requires a non-sensitive permission reference")
        return self


FIXTURE = CorpusUse()


class ResearchCase(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    case_id: str = Field(pattern=r"^[A-Z0-9_-]{1,64}$")
    group_id: str = Field(pattern=r"^[A-Z0-9_-]{1,64}$")
    source_id: str = Field(pattern=r"^[A-Z0-9_-]{1,64}$")
    label: DatasetLabel
    expected_bec_type: ExpectedBECType | None
    is_hard_negative: bool = False
    label_rationale: str = Field(min_length=1, max_length=1000)
    annotation_status: Literal["ADJUDICATED", "SYNTHETIC_GENERATED"]
    email: EmailIngestRequest

    @model_validator(mode="after")
    def consistent_label(self):
        if (self.label == DatasetLabel.LEGITIMATE) != (self.expected_bec_type is None):
            raise ValueError("Inconsistent label/type")
        if self.is_hard_negative and self.label != DatasetLabel.LEGITIMATE:
            raise ValueError("Hard negative must be legitimate")
        return self


def _reserved(host: str) -> bool:
    return host.rstrip(".").lower().endswith((".example", ".test"))


def _check_synthetic(case: ResearchCase) -> None:
    email = case.email
    addresses = [
        email.sender_email,
        *email.to_recipients,
        *email.cc_recipients,
        *[value for value in (email.reply_to, email.return_path) if value],
    ]
    text = "\n".join(
        value
        for value in (
            email.message_id,
            email.thread_id,
            email.sender_name,
            email.subject,
            email.body_text,
            email.authentication_results,
            case.label_rationale,
        )
        if value
    )
    if any(not _reserved(value.rsplit("@", 1)[-1]) for value in addresses):
        raise ResearchDataError("Only fictitious reserved domains are allowed")
    if any(not _reserved(match.group(1)) for match in _ADDRESS.finditer(text)):
        raise ResearchDataError("Only fictitious reserved domains are allowed")
    try:
        if any(
            not _reserved(urlsplit(match.group()).hostname or "") for match in _URL.finditer(text)
        ):
            raise ResearchDataError("Only fictitious reserved URLs are allowed")
    except ValueError:
        raise ResearchDataError("Invalid fictitious URL") from None
    if any(not _reserved(host) for host in _HOST.findall(email.authentication_results or "")):
        raise ResearchDataError("Only fictitious authentication domains are allowed")


def _shingles(value: str) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", value.casefold())
    if len(words) < 8:
        return set()
    return {tuple(words[i : i + 3]) for i in range(len(words) - 2)}


def validate_cases(cases: list[ResearchCase], *, use: CorpusUse = FIXTURE) -> None:
    if not cases:
        raise ResearchDataError("Empty research corpus")
    if len(cases) > MAX_CASES:
        raise ResearchDataError("Research corpus exceeds the offline case limit")
    case_ids: set[str] = set()
    message_ids: set[str] = set()
    # Equal text, thread or sender must belong to the SAME independence group.
    related: dict[tuple[str, str], str] = {}
    exact_text: set[str] = set()
    signatures: list[set[tuple[str, ...]]] = []
    previous_groups: list[str] = []
    shingle_index: dict[tuple[str, ...], set[int]] = defaultdict(set)
    for case in cases:
        if (
            use.kind == "authorized" or use.role == "independent_evaluation"
        ) and case.annotation_status != "ADJUDICATED":
            raise ResearchDataError("Scientific corpora require adjudicated annotations")
        if use.kind == "fixture":
            _check_synthetic(case)
        if case.case_id in case_ids or case.email.message_id in message_ids:
            raise ResearchDataError("Duplicate case or Message-ID")
        case_ids.add(case.case_id)
        message_ids.add(case.email.message_id)
        text = " ".join((case.email.subject + " " + case.email.body_text).casefold().split())
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in exact_text:
            raise ResearchDataError("Duplicate normalized email content")
        exact_text.add(digest)
        keys = [
            ("sender", case.email.sender_email.casefold()),
            ("source", case.source_id),
        ]
        if text:
            keys.append(("content", digest))
        if case.email.thread_id:
            keys.append(("thread", case.email.thread_id.casefold()))
        for key in keys:
            other = related.setdefault(key, case.group_id)
            if other != case.group_id:
                raise ResearchDataError("Related messages cross independence groups")

        # Índice de trigramas: solo comparar candidatos que comparten texto.
        signature = _shingles(text)
        candidates = (
            set().union(*(shingle_index[item] for item in signature)) if signature else set()
        )
        for index in candidates:
            if previous_groups[index] == case.group_id:
                continue
            other = signatures[index]
            if len(signature & other) / len(signature | other) >= 0.75:
                raise ResearchDataError("Near-duplicate messages cross independence groups")
        index = len(signatures)
        signatures.append(signature)
        previous_groups.append(case.group_id)
        for item in signature:
            shingle_index[item].add(index)


def _parse_rows(stream, *, use: CorpusUse) -> list[ResearchCase]:
    cases: list[ResearchCase] = []
    for number, row in enumerate(stream, 1):
        try:
            cases.append(ResearchCase.model_validate_json(row))
        except ValidationError, ValueError:
            raise ResearchDataError(f"Invalid research row {number}") from None
    validate_cases(cases, use=use)
    return cases


def load_research_jsonl(path: Path, *, use: CorpusUse = FIXTURE) -> list[ResearchCase]:
    """Carga casos nuevos; dominios reales solo con autorización declarada."""
    try:
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise ResearchDataError("Research corpus exceeds the 20 MB offline limit")
        with path.open(encoding="utf-8") as stream:
            return _parse_rows(stream, use=use)
    except OSError, UnicodeError:
        raise ResearchDataError("Research corpus cannot be read as UTF-8") from None


def load_research_bytes(contents: bytes, *, use: CorpusUse = FIXTURE) -> list[ResearchCase]:
    """Entrada de Streamlit en memoria, sin archivos temporales."""
    if len(contents) > MAX_INPUT_BYTES:
        raise ResearchDataError("Research corpus exceeds the 20 MB offline limit")
    try:
        return _parse_rows(io.StringIO(contents.decode("utf-8")), use=use)
    except UnicodeError:
        raise ResearchDataError("Research corpus cannot be read as UTF-8") from None


def _increment(
    index: int,
    counts: list[Counter],
    sizes: list[int],
    classes: Counter,
    group_size: int,
    totals: Counter,
    total_size: int,
) -> float:
    """Cambio en error global cuadrático al agregar un grupo a un split."""
    return sum(
        ((counts[index][label] + classes[label]) / totals[label] - FRACTIONS[index]) ** 2
        - (counts[index][label] / totals[label] - FRACTIONS[index]) ** 2
        for label in DatasetLabel
    ) + (
        ((sizes[index] + group_size) / total_size - FRACTIONS[index]) ** 2
        - (sizes[index] / total_size - FRACTIONS[index]) ** 2
    )


def split_groups(
    cases: list[ResearchCase], *, seed: int = SEED, use: CorpusUse = FIXTURE
) -> dict[str, list[str]]:
    """Asigna grupos completos, minimizando desvío por clase y tamaño.

    La salida contiene solo IDs y se rechazan conjuntos sin clases/grupos suficientes.
    """
    validate_cases(cases, use=use)
    groups: dict[str, list[ResearchCase]] = defaultdict(list)
    for case in cases:
        groups[case.group_id].append(case)
    totals = Counter(case.label for case in cases)
    if any(totals[label] < 6 for label in DatasetLabel):
        raise ResearchDataError("At least six cases per class are required")
    group_class_counts = Counter(
        label for group in groups.values() for label in {case.label for case in group}
    )
    if any(group_class_counts[label] < 5 for label in DatasetLabel):
        raise ResearchDataError("At least five independence groups per class are required")

    ordered = sorted(groups)
    best: tuple[float, dict[str, int]] | None = None
    rng = random.Random(seed)
    for _ in range(512):
        rng.shuffle(ordered)
        assigned: dict[str, int] = {}
        counts = [Counter() for _ in SPLITS]
        sizes = [0] * len(SPLITS)
        for group_id in ordered:
            group = groups[group_id]
            classes = Counter(item.label for item in group)
            options = [
                (_increment(i, counts, sizes, classes, len(group), totals, len(cases)), sizes[i], i)
                for i in range(len(SPLITS))
            ]
            index = min(options)[2]
            assigned[group_id] = index
            counts[index].update(classes)
            sizes[index] += len(group)
        if any(not counts[i][label] for i in range(3) for label in DatasetLabel):
            continue
        training_groups = [group_id for group_id, index in assigned.items() if index == 0]
        if any(
            sum(
                any(case.label == label for case in groups[group_id])
                for group_id in training_groups
            )
            < 3
            for label in DatasetLabel
        ):
            continue
        score = sum(
            sum((counts[i][label] / totals[label] - FRACTIONS[i]) ** 2 for label in DatasetLabel)
            + (sizes[i] / len(cases) - FRACTIONS[i]) ** 2
            for i in range(3)
        )
        if best is None or score < best[0]:
            best = (score, assigned.copy())
    if best is None:
        raise ResearchDataError("No valid grouped 70/15/15 split; collect more groups")
    allocation = best[1]
    return {
        split: sorted(case.case_id for case in cases if allocation[case.group_id] == index)
        for index, split in enumerate(SPLITS)
    }


def split_manifest(
    path: Path | None,
    cases: list[ResearchCase],
    *,
    seed: int = SEED,
    raw_bytes: bytes | None = None,
    use: CorpusUse = FIXTURE,
) -> dict:
    """Metadatos sin contenido; raw_bytes conserva el hash de un upload en memoria."""
    if use.role == "independent_evaluation":
        validate_cases(cases, use=use)
        if {case.label for case in cases} != set(DatasetLabel):
            raise ResearchDataError("Independent evaluation requires both classes")
        parts = {"evaluation": sorted(case.case_id for case in cases)}
        ratios_target = {"evaluation": 1.0}
    else:
        parts = split_groups(cases, seed=seed, use=use)
        ratios_target = dict(zip(SPLITS, FRACTIONS, strict=True))
    root = Path(__file__).resolve().parents[3]
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True, stderr=subprocess.DEVNULL
        )
    except OSError, subprocess.CalledProcessError:
        commit, status = None, "UNKNOWN"
    research_root = Path(__file__).parent
    research_files = {
        "bec_training/data.py": research_root / "data.py",
        "bec_training/training.py": research_root / "training.py",
        "bec_training/experiments.py": research_root / "experiments.py",
        "bec_training/reporting.py": research_root / "reporting.py",
        "bec_training/statistics.py": research_root / "statistics.py",
        "bec_training/inputs.py": research_root / "inputs.py",
        "bec_training/demo.py": research_root / "demo.py",
        "bec_training/__main__.py": research_root / "__main__.py",
        "streamlit_app.py": research_root.parent / "streamlit_app.py",
        "requirements.txt": research_root.parent / "requirements.txt",
    }

    def package_version(name: str) -> str | None:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return None

    lock_path = root / "backend" / "uv.lock"
    return {
        "status": "TECHNICAL_FIXTURE_ONLY"
        if use.kind == "fixture"
        else "AUTHORIZED_CORPUS_UNVERIFIED",
        "corpus_use": use.model_dump(),
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": commit,
        "working_tree_dirty": bool(status),
        "python": sys.version.split()[0],
        "dependencies": {
            "pydantic": package_version("pydantic"),
            "scikit-learn": package_version("scikit-learn"),
            "streamlit": package_version("streamlit"),
        },
        "uv_lock_sha256": (
            hashlib.sha256(lock_path.read_bytes()).hexdigest() if lock_path.exists() else None
        ),
        "pipeline_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "research_code_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in research_files.items()
        },
        "dataset_sha256": hashlib.sha256(
            raw_bytes
            if raw_bytes is not None
            else (
                path.read_bytes()
                if path is not None
                else ("\n".join(case.model_dump_json() for case in cases)).encode("utf-8")
            )
        ).hexdigest(),
        "seed": seed,
        "ratios_target": ratios_target,
        "splits": parts,
        "counts": {
            split: dict(Counter(case.label.value for case in cases if case.case_id in set(ids)))
            for split, ids in parts.items()
        },
    }
