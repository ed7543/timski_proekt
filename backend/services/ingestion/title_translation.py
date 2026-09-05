"""Best-effort MK -> EN translation of lesson `topic_title`s, used only to
widen lesson_matching.py's word-overlap vocabulary.

Why this exists: courses_db.json lesson titles are Macedonian, but most of
the manually-curated `content_urls` sources (OpenStax, LibreTexts, MDN,
learncpp.com, discrete.openmathbooks.org, the UNLV MIPS book, ...) are
English-language pages, so their section headings are in English too.
lesson_matching.py's score_section() is a literal word-overlap heuristic - it
has no idea "мрежи" and "networks" mean the same thing - so without this
module, most Macedonian lesson titles score ~0 against English section
headings and get incorrectly skipped as "под прагот" (below threshold), even
when a perfectly good matching section exists. This was visible in the
20260821_200323 report: several courses came back with no matches anywhere
despite their sources having fetched fine (200 OK).

Uses deep-translator's free GoogleTranslator (no API key, no billing, and
crucially NOT the Gemini API - translation calls must never compete with the
already-scarce 20-requests/day free-tier Gemini quota that generation itself
needs). Translations are cached to disk (keyed by exact title text) so
repeated runs / threshold re-tuning never re-translate the same title twice,
and a translation failure never blocks a re-run.

Best-effort by design: any failure (library not installed, network hiccup,
translation service down) just returns None and the caller falls back to
matching on the Macedonian title alone - i.e. exactly the pre-existing
behaviour, never fatal to the run.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CACHE_FILENAME = "title_translations_mk_en.json"

# Manual corrections for domain-specific MK terms that generic MT commonly
# mistranslates when the term appears in isolation or a short phrase (no
# surrounding sentence to disambiguate). E.g. "наследност" (the OOP
# "inheritance" concept) gets machine-translated to "heredity" (the genetics
# sense) since that's the more common everyday meaning of the word - seen
# directly in the 20260822_094830 report, where this caused a real
# below-threshold match failure for a lesson that had perfectly good
# learncpp.com content available. Same for "множества" (math "sets") coming
# back as "multitudes".
#
# This is NOT a replacement for the translator - it's a small correction
# applied on top: if a known MK term appears in the original title but its
# correct EN equivalent is missing from the machine translation, the correct
# term is appended so lesson_matching.py's word-overlap vocabulary picks it
# up regardless of what the translator produced. Add more entries here as
# mismatches are spotted in future run reports.
_TERM_OVERRIDES: Dict[str, str] = {
    "наследност": "inheritance",
    "наследување": "inheritance",
    "множества": "sets",
    "множество": "set",
}


def _apply_term_overrides(original_title: str, translated: Optional[str]) -> Optional[str]:
    if not translated:
        return translated
    lower_title = original_title.lower()
    lower_translated = translated.lower()
    additions = [
        correct_en
        for mk_term, correct_en in _TERM_OVERRIDES.items()
        if mk_term in lower_title and correct_en not in lower_translated
    ]
    return f"{translated} {' '.join(additions)}" if additions else translated


def _cache_path(cache_dir: Path) -> Path:
    return cache_dir / CACHE_FILENAME


def _load_cache(cache_dir: Path) -> Dict[str, str]:
    path = _cache_path(cache_dir)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read translation cache at %s - starting fresh", path)
    return {}


def _save_cache(cache_dir: Path, cache: Dict[str, str]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    _cache_path(cache_dir).write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def translate_title_mk_to_en(title: str, cache_dir: Path) -> Optional[str]:
    """Returns an English translation of `title`, or None if unavailable
    (library missing, network failure, empty result, ...). Cached to disk
    per exact title string - a title once translated is never re-sent."""
    if not title:
        return None

    cache = _load_cache(cache_dir)
    if title in cache:
        cached = cache[title] or None
        return _apply_term_overrides(title, cached)

    translated: Optional[str] = None
    try:
        from deep_translator import GoogleTranslator

        result = GoogleTranslator(source="mk", target="en").translate(title)
        translated = result.strip() if result else None
    except Exception:
        logger.exception(
            "Could not translate title '%s' to English - matching will use "
            "the Macedonian title only for this lesson",
            title,
        )
        translated = None

    cache[title] = translated or ""
    _save_cache(cache_dir, cache)
    return _apply_term_overrides(title, translated)
