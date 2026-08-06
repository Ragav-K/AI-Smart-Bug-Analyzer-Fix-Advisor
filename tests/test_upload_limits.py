"""Bounds on untrusted uploads.

Every value extracted here flows into the retrieval query, the agents, and the
``log_text`` field persisted to bug_reports.json, so an unbounded extraction is
a storage and memory problem as much as a security one. These tests pin the
limits that keep a hostile or merely huge upload from reaching that path.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from utils.rag_search import (
    MAX_EXTRACTED_CHARS,
    MAX_ZIP_MEMBERS,
    MAX_ZIP_TOTAL_BYTES,
    extract_uploaded_text,
    extract_zip_text,
)
from utils.storage import sanitize_filename


class FakeUpload(io.BytesIO):
    """Minimal stand-in for Streamlit's UploadedFile."""

    def __init__(self, name: str, data: bytes) -> None:
        super().__init__(data)
        self.name = name
        self.size = len(data)


def make_zip(members: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_oversized_text_upload_is_truncated_and_reported():
    payload = ("ERROR: disk full\n" * 400_000).encode()
    assert len(payload) > MAX_EXTRACTED_CHARS

    extracted = extract_uploaded_text(FakeUpload("huge.log", payload))

    assert len(extracted) < MAX_EXTRACTED_CHARS + 200
    assert "Truncated" in extracted
    assert "huge.log" in extracted


def test_upload_within_the_limit_is_returned_whole():
    payload = b"ValueError: token expired\n"
    assert extract_uploaded_text(FakeUpload("small.log", payload)) == payload.decode()
    assert "Truncated" not in extract_uploaded_text(FakeUpload("small.log", payload))


def test_decompression_bomb_cannot_expand_past_the_total_limit():
    """A small archive of repeated text previously expanded to ~270 MB."""
    bomb = make_zip({f"log{index}.log": "A" * 900_000 for index in range(300)})
    assert len(bomb) < 1_000_000

    extracted = extract_zip_text(FakeUpload("bomb.zip", bomb))

    assert len(extracted) <= MAX_ZIP_TOTAL_BYTES + 5_000
    assert "Truncated" in extracted
    assert extracted.count("--- log") <= MAX_ZIP_MEMBERS


def test_archive_member_count_is_capped():
    archive = make_zip({f"n{index}.log": "ValueError: x" for index in range(MAX_ZIP_MEMBERS + 25)})

    extracted = extract_zip_text(FakeUpload("many.zip", archive))

    assert extracted.count("--- n") == MAX_ZIP_MEMBERS
    assert "Truncated" in extracted


def test_small_archive_is_extracted_completely():
    extracted = extract_zip_text(
        FakeUpload("ok.zip", make_zip({"a.log": "NullPointerException", "b.txt": "second"}))
    )

    assert "NullPointerException" in extracted
    assert "second" in extracted
    assert "Truncated" not in extracted


def test_traversal_member_name_is_a_label_not_a_path():
    """A zip-slip entry is read into memory and shown, never used to open a file."""
    extracted = extract_zip_text(
        FakeUpload("slip.zip", make_zip({"../../../evil.log": "ValueError: pwned"}))
    )

    assert "ValueError: pwned" in extracted
    assert "../../../evil.log" in extracted


@pytest.mark.parametrize(
    "name",
    ["../../../../etc/passwd", "..\\..\\windows\\system32\\cfg", "evil\x00.txt", "a/b/c.log"],
)
def test_sanitized_filenames_cannot_escape_the_upload_directory(name):
    safe = sanitize_filename(name)

    assert "/" not in safe
    assert "\\" not in safe
    assert "\x00" not in safe


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("broken.pdf", b"not a pdf at all"),
        ("broken.docx", b"nope"),
        ("payload.exe", b"MZ\x90\x00"),
        ("binary.txt", bytes(range(256))),
        ("empty.log", b""),
    ],
)
def test_invalid_and_unsupported_uploads_never_raise(name, data):
    assert isinstance(extract_uploaded_text(FakeUpload(name, data)), str)


def test_unicode_upload_survives_extraction():
    text = "错误 🐛 ошибка"
    assert extract_uploaded_text(FakeUpload("u.log", text.encode())) == text
