"""Regression tests for two fixes in seed_lessons.py::seed_course:

1. Batch-crashing exception handling - the per-lesson try/except used to only
   catch genai_errors.APIError. A RuntimeError (e.g. GEMINI_API_KEY unset) or
   a json.JSONDecodeError (a malformed quiz response, explicitly documented
   as a real possibility in gemini_generator.py) propagated out of
   seed_course(), aborting the entire multi-course run and losing the report
   for every lesson already processed. Fixed by widening the except clause,
   so one bad lesson logs a report entry and the batch continues.

2. Resumability (get_existing_documentation / force_regenerate) - a lesson
   that already has documentation should be skipped (not re-spend an API
   call) unless --force-regenerate is passed.

All Gemini/network/DB collaborators are monkeypatched - these only exercise
seed_course()'s control flow, no real DB or API calls.
"""
import json
from types import SimpleNamespace

import pytest

from backend.services.ingestion import seed_lessons


def _course(num_lessons=2):
    return {
        "course_code": "TEST101",
        "course_name_mk": "Тест предмет",
        "source": {"url": "https://example.com/book", "title": "T", "author": "A"},
        "lessons": [{"topic_title": f"Тема {i}"} for i in range(1, num_lessons + 1)],
    }


@pytest.fixture
def patched_pipeline(monkeypatch):
    """Wires seed_course()'s collaborators to succeed by default; each test
    below overrides generate_documentation/generate_quiz/get_existing_documentation
    to exercise one specific behavior."""
    monkeypatch.setattr(seed_lessons, "find_course_id", lambda db, code, name: 1)
    monkeypatch.setattr(seed_lessons, "has_fetchable_source", lambda course: True)
    monkeypatch.setattr(seed_lessons, "replace_course_sources", lambda *a, **k: None)
    monkeypatch.setattr(seed_lessons, "get_existing_documentation", lambda *a, **k: None)
    monkeypatch.setattr(
        seed_lessons, "extract_sections_multi",
        lambda urls, cache_dir: [SimpleNamespace(heading="H", text="body")],
    )
    monkeypatch.setattr(seed_lessons, "translate_title_mk_to_en", lambda title, cache_dir: title)
    monkeypatch.setattr(
        seed_lessons, "find_best_excerpt",
        lambda title, sections, threshold, title_en: SimpleNamespace(
            excerpt="an excerpt", confidence=0.9, matched_heading="H",
        ),
    )
    upserted = []
    monkeypatch.setattr(
        seed_lessons, "upsert_lesson",
        lambda db, course_id, i, topic_title, documentation=None, quiz=None: upserted.append(topic_title),
    )
    return upserted


# --- 1. exception handling ---------------------------------------------------

def test_runtime_error_on_one_lesson_does_not_abort_the_batch(monkeypatch, patched_pipeline):
    calls = {"n": 0}

    def fake_generate_documentation(**kwargs):
        calls["n"] += 1
        if kwargs["lesson_title"] == "Тема 1":
            raise RuntimeError("GEMINI_API_KEY not set")
        return "generated docs"

    monkeypatch.setattr(seed_lessons, "generate_documentation", fake_generate_documentation)
    monkeypatch.setattr(seed_lessons, "generate_quiz", lambda **kwargs: {"questions": []})

    report = seed_lessons.Report()
    seed_lessons.seed_course(db=None, course=_course(), cache_dir=None, threshold=0.5,
                              force_regenerate=False, report=report)

    assert calls["n"] == 2          # both lessons were attempted - batch didn't stop
    assert report.errors == 1
    assert report.generated == 1
    assert patched_pipeline == ["Тема 2"]  # only the surviving lesson got upserted


def test_json_decode_error_on_quiz_does_not_abort_the_batch(monkeypatch, patched_pipeline):
    def fake_generate_quiz(**kwargs):
        if kwargs["lesson_title"] == "Тема 1":
            raise json.JSONDecodeError("bad json", "doc", 0)
        return {"questions": []}

    monkeypatch.setattr(seed_lessons, "generate_documentation", lambda **kwargs: "generated docs")
    monkeypatch.setattr(seed_lessons, "generate_quiz", fake_generate_quiz)

    report = seed_lessons.Report()
    seed_lessons.seed_course(db=None, course=_course(), cache_dir=None, threshold=0.5,
                              force_regenerate=False, report=report)

    assert report.errors == 1
    assert report.generated == 1
    assert patched_pipeline == ["Тема 2"]


# --- 2. resumability ----------------------------------------------------------

def test_lesson_with_existing_documentation_is_skipped_unless_force_regenerate(monkeypatch, patched_pipeline):
    generate_calls = []

    def fake_generate_documentation(**kwargs):
        generate_calls.append(kwargs["lesson_title"])
        return "generated docs"

    monkeypatch.setattr(
        seed_lessons, "get_existing_documentation",
        lambda db, course_id, i: i == 1,  # lesson 1 (Тема 1) already has documentation
    )
    monkeypatch.setattr(seed_lessons, "generate_documentation", fake_generate_documentation)
    monkeypatch.setattr(seed_lessons, "generate_quiz", lambda **kwargs: {"questions": []})

    report = seed_lessons.Report()
    seed_lessons.seed_course(db=None, course=_course(), cache_dir=None, threshold=0.5,
                              force_regenerate=False, report=report)

    assert generate_calls == ["Тема 2"]          # Тема 1 never re-generated
    assert report.skipped_already_done == 1
    assert report.generated == 1
    assert patched_pipeline == ["Тема 2"]


def test_force_regenerate_regenerates_already_done_lessons_too(monkeypatch, patched_pipeline):
    generate_calls = []

    def fake_generate_documentation(**kwargs):
        generate_calls.append(kwargs["lesson_title"])
        return "generated docs"

    monkeypatch.setattr(seed_lessons, "get_existing_documentation", lambda db, course_id, i: True)
    monkeypatch.setattr(seed_lessons, "generate_documentation", fake_generate_documentation)
    monkeypatch.setattr(seed_lessons, "generate_quiz", lambda **kwargs: {"questions": []})

    report = seed_lessons.Report()
    seed_lessons.seed_course(db=None, course=_course(), cache_dir=None, threshold=0.5,
                              force_regenerate=True, report=report)

    assert generate_calls == ["Тема 1", "Тема 2"]  # both regenerated despite already-done
    assert report.skipped_already_done == 0
    assert report.generated == 2
