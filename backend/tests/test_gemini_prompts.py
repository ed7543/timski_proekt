"""Locks in the anti-fabrication rule in gemini_generator.py's prompts - the
same kind of guard test_ai_chat.py already has for chat.py's SYSTEM_PROMPT
(test_system_prompt_forbids_fabricated_resources). The module's own docstring
states the constraint explicitly: "Neither prompt is allowed to produce
citations/references the model invents itself."
"""
from backend.services.ingestion.gemini_generator import build_documentation_prompt, build_quiz_prompt


def test_documentation_prompt_forbids_content_outside_the_source():
    prompt = build_documentation_prompt(
        course_name_mk="Структурно програмирање",
        lesson_title="Циклуси",
        source_excerpt="За циклуси и while циклуси.",
        source_title="Некоја книга",
        source_author="Некој автор",
    )
    assert "НЕ измислувај" in prompt
    assert "ИСКЛУЧИВО на текстот" in prompt


def test_documentation_prompt_embeds_all_inputs():
    prompt = build_documentation_prompt(
        course_name_mk="COURSE-MARKER",
        lesson_title="LESSON-MARKER",
        source_excerpt="EXCERPT-MARKER",
        source_title="TITLE-MARKER",
        source_author="AUTHOR-MARKER",
    )
    for marker in ("COURSE-MARKER", "LESSON-MARKER", "EXCERPT-MARKER", "TITLE-MARKER", "AUTHOR-MARKER"):
        assert marker in prompt


def test_quiz_prompt_forbids_knowledge_outside_the_documentation():
    prompt = build_quiz_prompt(lesson_title="Циклуси", documentation_text="DOC-MARKER")
    assert "НЕ надворешно знаење" in prompt
    assert "DOC-MARKER" in prompt
