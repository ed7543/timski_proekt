"""Tests for lesson_matching.py::find_best_excerpt - the confidence-threshold
gate that decides whether a lesson gets AI-generated documentation at all.
This is a deliberate design choice (see the module's docstring: "by design,
per-lesson silence rather than fabricated content"), so it's worth locking in
directly, independent of any bug history.
"""
from backend.services.ingestion.lesson_matching import DEFAULT_CONFIDENCE_THRESHOLD, find_best_excerpt
from backend.services.ingestion.source_text import Section


def test_returns_none_excerpt_when_no_sections():
    result = find_best_excerpt("Рекурзија", [])
    assert result.excerpt is None
    assert result.confidence == 0.0


def test_below_threshold_returns_none_excerpt_but_keeps_best_heading():
    # Section is about something completely unrelated to the lesson title.
    sections = [Section(heading="Историја на уметност", text="Ренесансата беше период на...")]
    result = find_best_excerpt("Рекурзија во програмирање", sections, threshold=DEFAULT_CONFIDENCE_THRESHOLD)
    assert result.excerpt is None
    # Best-guess heading is still reported, even on a skip - seed_lessons.py's
    # report.lesson_no_match() surfaces this so a human can spot-check it.
    assert result.matched_heading == "Историја на уметност"


def test_at_or_above_threshold_returns_an_excerpt():
    sections = [
        Section(heading="Рекурзија", text="Рекурзија е техника во програмирање каде функција повикува себеси."),
    ]
    result = find_best_excerpt("Рекурзија во програмирање", sections, threshold=DEFAULT_CONFIDENCE_THRESHOLD)
    assert result.excerpt is not None
    assert "Рекурзија" in result.excerpt
    assert result.confidence >= DEFAULT_CONFIDENCE_THRESHOLD


def test_english_translation_helps_match_english_only_sources():
    # Real-world case this exists for: Macedonian lesson title against an
    # English-only source (OpenStax/MDN/...) - see title_translation.py.
    sections = [Section(heading="Recursion", text="Recursion is a technique where a function calls itself.")]

    without_translation = find_best_excerpt("Рекурзија", sections)
    with_translation = find_best_excerpt("Рекурзија", sections, title_en="Recursion")

    assert with_translation.confidence > without_translation.confidence
    assert with_translation.excerpt is not None


def test_picks_the_higher_scoring_of_two_sections():
    sections = [
        Section(heading="Циклуси", text="За циклуси и while циклуси во програмирање."),
        Section(heading="Рекурзија", text="Рекурзија е техника каде функција повикува себеси."),
    ]
    result = find_best_excerpt("Рекурзија", sections)
    assert result.matched_heading == "Рекурзија"
