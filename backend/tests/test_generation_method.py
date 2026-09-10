"""Coverage for the --generate-without-source / --force-general-knowledge
bypass of the app's core anti-fabrication rule (see gemini_generator.py's
module docstring and test_gemini_prompts.py's existing source-grounded
guards) - previously this whole path had zero test coverage.

Three things are checked here:
1. The no-source prompt/generation always carries the disclaimer
   (gemini_generator.py).
2. Lesson.generation_method (migration d8f3a1c9b274) is set correctly by
   upsert_lesson - "source" (default) vs "general_knowledge" - and a
   topic-only call never silently reclassifies an existing lesson
   (lesson_upsert.py).
3. seed_lessons.py actually wires generation_method through both no-source
   paths (--generate-without-source and --force-general-knowledge) as well
   as the normal source-grounded path, and Report.generated_no_source counts
   correctly (seed_lessons.py).

All Gemini/DB collaborators are monkeypatched in (2)/(3) - no real API or
DB calls. (1)'s generate_no_source_documentation test monkeypatches the
module's lazily-created client the same way.
"""
from types import SimpleNamespace

import pytest

from backend.services.ingestion import gemini_generator, seed_lessons
from backend.services.ingestion.gemini_generator import (
    NO_SOURCE_DISCLAIMER_MK,
    build_no_source_documentation_prompt,
    generate_no_source_documentation,
)
from backend.services.ingestion.lesson_upsert import (
    GENERATION_METHOD_GENERAL_KNOWLEDGE,
    GENERATION_METHOD_SOURCE,
)


# --------------------------------------------------------- 1. disclaimer ---

def test_no_source_prompt_embeds_course_and_lesson_and_is_conservative():
    prompt = build_no_source_documentation_prompt(course_name_mk="COURSE-MARKER", lesson_title="LESSON-MARKER")
    assert "COURSE-MARKER" in prompt
    assert "LESSON-MARKER" in prompt
    # Unlike build_documentation_prompt (which forbids ANY outside
    # knowledge, since a real source excerpt is given), this prompt has no
    # source to check against - it should still tell the model to stay
    # conservative rather than inventing specifics.
    assert "НЕ измислувај" in prompt


def test_generate_no_source_documentation_always_prepends_disclaimer(monkeypatch):
    fake_response = SimpleNamespace(text="генерирана содржина без извор")
    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: fake_response))
    monkeypatch.setattr(gemini_generator, "_get_client", lambda: fake_client)

    result = generate_no_source_documentation(course_name_mk="Тест предмет", lesson_title="Тема")

    assert result.startswith(NO_SOURCE_DISCLAIMER_MK)
    assert "генерирана содржина без извор" in result


# ------------------------------------------------ 2. Lesson.generation_method

@pytest.fixture
def db():
    from backend.database.session import SessionLocal
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def course(db):
    from backend.database.models import Course, Lesson
    c = Course(slug="genmethod-test-course", name="Тест предмет за generation_method", code="TESTGEN1")
    db.add(c)
    db.commit()
    db.refresh(c)
    yield c
    db.query(Lesson).filter(Lesson.course_id == c.id).delete()
    db.query(Course).filter(Course.id == c.id).delete()
    db.commit()


def test_upsert_lesson_defaults_generation_method_to_source(db, course):
    from backend.database.models import Lesson
    from backend.services.ingestion.lesson_upsert import upsert_lesson

    upsert_lesson(db, course.id, order_index=1, topic_title="Тема 1", documentation="докс")

    lesson = db.query(Lesson).filter(Lesson.course_id == course.id, Lesson.order_index == 1).first()
    assert lesson.generation_method == GENERATION_METHOD_SOURCE == "source"


def test_upsert_lesson_sets_general_knowledge_when_passed(db, course):
    from backend.database.models import Lesson
    from backend.services.ingestion.lesson_upsert import upsert_lesson

    upsert_lesson(
        db, course.id, order_index=1, topic_title="Тема 1", documentation="докс без извор",
        generation_method=GENERATION_METHOD_GENERAL_KNOWLEDGE,
    )

    lesson = db.query(Lesson).filter(Lesson.course_id == course.id, Lesson.order_index == 1).first()
    assert lesson.generation_method == "general_knowledge"


def test_upsert_lesson_topic_only_pass_does_not_touch_existing_generation_method(db, course):
    from backend.database.models import Lesson
    from backend.services.ingestion.lesson_upsert import upsert_lesson

    upsert_lesson(
        db, course.id, order_index=1, topic_title="Тема 1", documentation="докс без извор",
        generation_method=GENERATION_METHOD_GENERAL_KNOWLEDGE,
    )
    # Second call is a topic-only pass (documentation=None, no generation_method
    # passed either) - must NOT silently reclassify this lesson back to "source".
    upsert_lesson(db, course.id, order_index=1, topic_title="Тема 1 (ажурирана)")

    lesson = db.query(Lesson).filter(Lesson.course_id == course.id, Lesson.order_index == 1).first()
    assert lesson.generation_method == "general_knowledge"
    assert lesson.documentation == "докс без извор"


def test_upsert_lesson_brand_new_topic_only_row_defaults_to_source(db, course):
    from backend.database.models import Lesson
    from backend.services.ingestion.lesson_upsert import upsert_lesson

    # No documentation at all yet (e.g. below-confidence-threshold skip, or a
    # no-source course without --generate-without-source) - nothing to
    # classify yet, so it gets the column's own default.
    upsert_lesson(db, course.id, order_index=1, topic_title="Тема 1")

    lesson = db.query(Lesson).filter(Lesson.course_id == course.id, Lesson.order_index == 1).first()
    assert lesson.generation_method == "source"


# --------------------------------------------- 3. seed_lessons.py wiring ---

def _course(num_lessons=2, has_source=True):
    course = {
        "course_code": "TEST101",
        "course_name_mk": "Тест предмет",
        "lessons": [{"topic_title": f"Тема {i}"} for i in range(1, num_lessons + 1)],
    }
    if has_source:
        course["source"] = {"url": "https://example.com/book", "title": "T", "author": "A"}
    return course


def test_generate_lessons_no_source_tags_general_knowledge_and_counts_report(monkeypatch):
    monkeypatch.setattr(seed_lessons, "get_existing_documentation", lambda *a, **k: None)
    monkeypatch.setattr(seed_lessons, "generate_no_source_documentation", lambda **kwargs: "docs")
    monkeypatch.setattr(seed_lessons, "generate_quiz", lambda **kwargs: {"questions": []})

    upserted = []
    monkeypatch.setattr(
        seed_lessons, "upsert_lesson",
        lambda db, course_id, i, topic_title, documentation=None, quiz=None, generation_method=GENERATION_METHOD_SOURCE:
            upserted.append((topic_title, generation_method)),
    )

    report = seed_lessons.Report()
    seed_lessons._generate_lessons_no_source(
        db=None, course_id=1, course_name="Тест предмет",
        lessons=[{"topic_title": "Тема 1"}, {"topic_title": "Тема 2"}],
        force_regenerate=False, generate_quiz_flag=True, report=report,
    )

    assert upserted == [
        ("Тема 1", GENERATION_METHOD_GENERAL_KNOWLEDGE),
        ("Тема 2", GENERATION_METHOD_GENERAL_KNOWLEDGE),
    ]
    assert report.generated_no_source == 2
    assert report.generated == 0


def test_seed_course_generate_without_source_routes_to_no_source_path(monkeypatch):
    monkeypatch.setattr(seed_lessons, "find_course_id", lambda db, code, name: 1)
    monkeypatch.setattr(seed_lessons, "has_fetchable_source", lambda course: False)

    calls = []
    monkeypatch.setattr(
        seed_lessons, "_generate_lessons_no_source",
        lambda db, course_id, course_name, lessons, force_regenerate, generate_quiz_flag, report: calls.append(course_name),
    )

    report = seed_lessons.Report()
    seed_lessons.seed_course(
        db=None, course=_course(has_source=False), cache_dir=None, threshold=0.5,
        force_regenerate=False, report=report, generate_without_source=True,
    )

    assert calls == ["Тест предмет"]


def test_seed_course_without_generate_without_source_flag_stays_topic_only(monkeypatch):
    monkeypatch.setattr(seed_lessons, "find_course_id", lambda db, code, name: 1)
    monkeypatch.setattr(seed_lessons, "has_fetchable_source", lambda course: False)

    no_source_calls = []
    monkeypatch.setattr(
        seed_lessons, "_generate_lessons_no_source",
        lambda *a, **k: no_source_calls.append(1),
    )
    topic_only_calls = []
    monkeypatch.setattr(
        seed_lessons, "upsert_lesson",
        lambda db, course_id, i, topic_title, **kwargs: topic_only_calls.append(topic_title),
    )

    report = seed_lessons.Report()
    seed_lessons.seed_course(
        db=None, course=_course(has_source=False), cache_dir=None, threshold=0.5,
        force_regenerate=False, report=report,  # generate_without_source defaults False
    )

    assert no_source_calls == []
    assert topic_only_calls == ["Тема 1", "Тема 2"]
    assert report.skipped_no_source == 2


def test_seed_course_force_general_knowledge_overrides_even_a_real_source(monkeypatch):
    monkeypatch.setattr(seed_lessons, "find_course_id", lambda db, code, name: 1)
    # has_fetchable_source=True (this course DOES have a real source) - but
    # --force-general-knowledge must still route to the no-source path
    # without ever consulting has_fetchable_source or fetching anything.
    monkeypatch.setattr(
        seed_lessons, "has_fetchable_source",
        lambda course: (_ for _ in ()).throw(AssertionError("should not be called under --force-general-knowledge")),
    )
    monkeypatch.setattr(
        seed_lessons, "extract_sections_multi",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not fetch the source at all")),
    )

    calls = []
    monkeypatch.setattr(
        seed_lessons, "_generate_lessons_no_source",
        lambda db, course_id, course_name, lessons, force_regenerate, generate_quiz_flag, report: calls.append(course_name),
    )

    report = seed_lessons.Report()
    seed_lessons.seed_course(
        db=None, course=_course(has_source=True), cache_dir=None, threshold=0.5,
        force_regenerate=False, report=report, force_general_knowledge=True,
    )

    assert calls == ["Тест предмет"]


def test_seed_course_normal_source_path_tags_lessons_as_source(monkeypatch):
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
    monkeypatch.setattr(seed_lessons, "generate_documentation", lambda **kwargs: "generated docs")
    monkeypatch.setattr(seed_lessons, "generate_quiz", lambda **kwargs: {"questions": []})

    upserted = []
    monkeypatch.setattr(
        seed_lessons, "upsert_lesson",
        lambda db, course_id, i, topic_title, documentation=None, quiz=None, generation_method=None:
            upserted.append((topic_title, generation_method)),
    )

    report = seed_lessons.Report()
    seed_lessons.seed_course(db=None, course=_course(), cache_dir=None, threshold=0.5,
                              force_regenerate=False, report=report)

    assert upserted == [("Тема 1", GENERATION_METHOD_SOURCE), ("Тема 2", GENERATION_METHOD_SOURCE)]
    assert report.generated == 2
    assert report.generated_no_source == 0
