"""Heuristic matching between a lesson's `topic_title` (from courses_db.json)
and the Sections of its course's extracted source text (source_text.py) -
decides which excerpt, if any, gets fed into
gemini_generator.generate_documentation() for that lesson.

Deliberately simple (word-overlap scoring, no embeddings/ML) - this is a
tunable heuristic, not a precise classifier. seed_lessons.py logs every
decision (matched heading + confidence score, or "skipped, below threshold")
to a per-run report file so a human can spot-check it after the fact - see
that module's docstring. If the report shows too many lessons skipped that
you know are actually covered, lower DEFAULT_CONFIDENCE_THRESHOLD; if it
shows generated lessons that clearly don't match their source excerpt, raise
it.
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Set

from backend.services.ingestion.source_text import Section

# Tunable - see module docstring. 0.15 means: at least 15% of the lesson
# title's meaningful words (weighted double if found in a section heading)
# need to show up in that section for it to count as a match.
DEFAULT_CONFIDENCE_THRESHOLD = 0.15

# Caps how much source text goes into one excerpt (keeps prompts/costs
# reasonable - a few thousand words of source is plenty for a single lesson).
MAX_EXCERPT_CHARS = 6000

_STOPWORDS_MK = {
    "и", "во", "на", "за", "со", "од", "да", "се", "е", "но", "или", "кои",
    "која", "кој", "кое", "како", "при", "по", "до", "меѓу", "низ", "врз",
    "еден", "една", "едно", "овие", "тие", "ова", "тоа", "не", "што",
}
_STOPWORDS_EN = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with",
    "is", "are", "at", "by", "vs", "via",
}

_WORD_RE = re.compile(r"[а-шА-Шa-zA-Z0-9]+", re.UNICODE)


def _tokenize(text: str) -> Set[str]:
    words = _WORD_RE.findall(text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS_MK and w not in _STOPWORDS_EN}


def score_section(lesson_title: str, section: Section, title_en: Optional[str] = None) -> float:
    """Overlap ratio in [0, 1]: how much of the lesson title's vocabulary
    shows up in this section, with heading matches weighted 2x over body-text
    matches (headings are short and precise; body text is noisy).

    `title_en` (see title_translation.py) is an optional English translation
    of `lesson_title`, unioned into the vocabulary before matching. Sources
    like OpenStax/MDN/learncpp are English-only, so without this a Macedonian
    lesson title scores ~0 against every section no matter how well it
    actually matches - see title_translation.py's module docstring."""
    lesson_words = _tokenize(lesson_title)
    if title_en:
        lesson_words |= _tokenize(title_en)
    if not lesson_words:
        return 0.0

    heading_words = _tokenize(section.heading)
    body_words = _tokenize(section.text[:2000])  # first chunk carries plenty of signal

    heading_overlap = len(lesson_words & heading_words)
    body_overlap = len(lesson_words & body_words)

    score = (heading_overlap * 2 + body_overlap) / (len(lesson_words) * 2)
    return min(score, 1.0)


@dataclass
class MatchResult:
    excerpt: Optional[str]
    confidence: float
    matched_heading: Optional[str]


def find_best_excerpt(
    lesson_title: str,
    sections: List[Section],
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    title_en: Optional[str] = None,
) -> MatchResult:
    """Picks the best-matching section for `lesson_title`, plus immediately
    -following sections that still look related (in case one lesson's topic
    spans a couple of short sections), up to MAX_EXCERPT_CHARS.

    `title_en`: see score_section() - optional English translation of
    `lesson_title`, for matching against English-language sources.

    Returns MatchResult(excerpt=None, ...) if nothing clears `threshold` -
    the caller should then skip generation entirely for this lesson."""
    if not sections:
        return MatchResult(None, 0.0, None)

    scored = sorted(
        ((score_section(lesson_title, s, title_en), i, s) for i, s in enumerate(sections)),
        key=lambda triple: triple[0],
        reverse=True,
    )
    best_score, best_idx, best_section = scored[0]
    if best_score < threshold:
        return MatchResult(None, best_score, best_section.heading)

    excerpt_parts = []
    total_len = 0
    for s in sections[best_idx:]:
        if total_len >= MAX_EXCERPT_CHARS:
            break
        if s is not best_section and score_section(lesson_title, s, title_en) < threshold * 0.5:
            break  # ran into a clearly unrelated section - stop extending
        excerpt_parts.append(f"## {s.heading}\n{s.text}")
        total_len += len(s.text)

    excerpt = "\n\n".join(excerpt_parts)[:MAX_EXCERPT_CHARS]
    return MatchResult(excerpt, best_score, best_section.heading)
