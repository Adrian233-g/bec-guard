"""Generic phishing labels never silently become BEC ground truth."""

import csv
import hashlib
import io
import zipfile

import pytest

from research.bec_training import auxiliary_phishing_benchmark as benchmark


def _archive(tmp_path, rows, monkeypatch):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Subject", "Body", "Label"])
    writer.writerows(rows)
    data = output.getvalue().encode("utf-8")
    monkeypatch.setattr(benchmark, "MEMBER_SHA256", hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(benchmark, "LABEL_COUNTS", {"0": 2, "1": 1})
    path = tmp_path / "phishing.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(benchmark.MEMBER, data)
    return path


def test_auxiliary_corpus_deduplicates_without_converting_phishing_to_bec(tmp_path, monkeypatch):
    path = _archive(
        tmp_path,
        [
            ["Invoice", "Meeting tomorrow", "0"],
            [" invoice ", "meeting   tomorrow", "0"],
            ["Urgent", "Confirm credentials", "1"],
        ],
        monkeypatch,
    )
    groups, metadata = benchmark.load_phishing_zip(path)
    assert metadata["excluded_exact_duplicates"] == 1
    assert metadata["unique_labels"] == {"0": 1, "1": 1}
    assert groups["0"] == ["Invoice\nMeeting tomorrow"]
    assert groups["1"] == ["Urgent\nConfirm credentials"]


def test_auxiliary_corpus_rejects_conflicting_labels_for_same_email(tmp_path, monkeypatch):
    path = _archive(
        tmp_path,
        [
            ["Invoice", "Meeting tomorrow", "0"],
            ["Other", "Legitimate", "0"],
            ["INVOICE", "meeting tomorrow", "1"],
        ],
        monkeypatch,
    )
    with pytest.raises(ValueError, match="Conflicting publisher labels"):
        benchmark.load_phishing_zip(path)
