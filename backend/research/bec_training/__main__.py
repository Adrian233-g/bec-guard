"""Particionador offline para corpus nuevo FICTICIO (sin llamadas ni entrenamiento)."""

import argparse
import json
import os
import sys
from pathlib import Path

from research.bec_training.data import (
    SEED,
    CorpusUse,
    ResearchDataError,
    load_research_jsonl,
    split_manifest,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument(
        "--output", type=Path, required=True, help="Manifiesto JSON nuevo; sin correos"
    )
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument("--permission-ref", help="ID opaco de autorización, nunca un secreto")
    parser.add_argument(
        "--role", choices=["training", "independent_evaluation"], default="training"
    )
    args = parser.parse_args(argv)
    try:
        use = CorpusUse(
            kind="authorized" if args.authorized else "fixture",
            permission_ref=args.permission_ref,
            role=args.role,
        )
        cases = load_research_jsonl(args.dataset, use=use)
        manifest = split_manifest(args.dataset, cases, seed=args.seed, use=use)
        # O_EXCL impide sobrescribir una partición congelada o un archivo del usuario.
        descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(manifest, output, ensure_ascii=False, indent=2)
        print(json.dumps({"status": manifest["status"], "counts": manifest["counts"]}))
        return 0
    except ResearchDataError, OSError, ValueError:
        print(
            "No se pudo validar o guardar el corpus ficticio; revise esquema y destino.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
