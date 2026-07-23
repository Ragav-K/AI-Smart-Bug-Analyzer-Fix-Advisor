"""Tests for bounded historical-defect search."""

import time

from utils import rag_search


class EmptyCollection:
    def count(self):
        return 0


def test_vector_search_never_builds_index(monkeypatch):
    calls = []

    def fake_collection(build_if_missing=True):
        calls.append(build_if_missing)
        return EmptyCollection()

    monkeypatch.setattr(rag_search, "get_vector_collection", fake_collection)

    matches, indexed_count = rag_search._search_vector_bugs("login failure", 5)

    assert matches == []
    assert indexed_count == 0
    assert calls == [False]


def test_search_timeout_uses_local_fallback(monkeypatch, tmp_path):
    def slow_vector_search(_query, _limit):
        time.sleep(0.1)
        return [], 0

    ready_marker = tmp_path / ".index_ready"
    ready_marker.write_text("ready", encoding="utf-8")
    monkeypatch.setattr(rag_search, "INDEX_READY_MARKER", ready_marker)
    monkeypatch.setattr(rag_search, "_search_vector_bugs", slow_vector_search)
    monkeypatch.setattr(
        rag_search,
        "_search_local_fallback",
        lambda _query, _limit, timed_out=False: [{"timed_out": timed_out}],
    )

    matches = rag_search.search_similar_bugs(
        "login failure",
        limit=5,
        timeout_seconds=0.01,
    )

    assert matches == [{"timed_out": True}]
