"""Populates `lessons` / `course_sources` from courses_db.json, via the real
Gemini pipeline (gemini_generator.py) - the model writes the documentation
and quiz, this module only prepares its input (a source excerpt matched to
each lesson topic - see lesson_matching.py) and stores its output.

Not used by any live API request path - standalone, invoked via:
    python -m backend.services.ingestion.cli --source lessons \\
        --courses-db-path "C:\\Users\\stoja\\Downloads\\courses_db.json" \\
        --course-codes F23L1W005,F23L1W020,...

Per course, one of three things happens:
  1. No source at all (status pending_source / deferred_user_will_provide_materials)
     -> Lesson rows created with topic_title only, nothing generated, no API calls
     (unless --generate-without-source is passed - see _generate_lessons_no_source
     below - an explicit opt-in to generate from the model's general knowledge
     instead, clearly disclaimed and tracked separately in the report and via
     Lesson.generation_method).
  2. Source is a local file only (source.url is None - see courses_db.py's
     LOCAL_FILE_ONLY_CODES) -> course is skipped entirely for now (not even
     topic-only rows), logged clearly. Revisit once local_path support exists.
  3. Source has a real URL -> full pipeline: fetch+extract (source_text.py),
     match each lesson to its best excerpt (lesson_matching.py), and only
     call Gemini for lessons that clear the confidence threshold. Lessons
     that don't clear it get a topic-only row (documentation/quiz stay NULL)
     - by design, per-lesson silence rather than fabricated content. This
     path can also be overridden per-course via --force-general-knowledge
     (see seed_course() below).

Every run writes a markdown report (see Report below) listing what happened
to every single lesson it touched - matched heading + confidence for
generated lessons, and the reason for every skip. Intended to be skimmed
after the run, not watched live.

Resumable by default: a lesson that already has non-NULL documentation is
left alone unless --force-regenerate is passed (re-running a batch that
crashed partway through just picks up where it left off, without re-spending
API calls on lessons already done).
"""
import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.genai import errors as genai_errors
from sqlalchemy.orm import Session

from backend.database.models import CourseMaterial
from backend.services.ingestion.courses_db import (
    LOCAL_FILE_ONLY_CODES,
    get_courses_by_codes,
    has_fetchable_source,
    load_courses,
)
from backend.services.ingestion.gemini_generator import (
    MAX_DOCUMENTATION_WORDS,
    documentation_word_count,
    generate_documentation,
    generate_no_source_documentation,
    generate_quiz,
)
from backend.services.ingestion.lesson_matching import DEFAULT_CONFIDENCE_THRESHOLD, find_best_excerpt
from backend.services.ingestion.lesson_upsert import (
    GENERATION_METHOD_GENERAL_KNOWLEDGE,
    GENERATION_METHOD_SOURCE,
    find_course_id,
    get_existing_documentation,
    replace_course_sources,
    upsert_lesson,
)
from backend.services.ingestion.source_text import extract_local_files_sections, extract_sections_multi
from backend.services.ingestion.title_translation import translate_title_mk_to_en
from backend.utils.time import utcnow

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(".lesson_source_cache")

# Where local-file courses' materials live - see courses_db.py's
# LOCAL_FILE_ONLY_CODES. One subfolder per course_code, one file per topic
# (e.g. course_materials/F23L2S017/1. Процеси.pdf). Defaults to a sibling of
# courses_db.json itself (both live in the user's Downloads folder), but can
# be overridden via --local-materials-dir for a different layout.
DEFAULT_LOCAL_MATERIALS_DIR_NAME = "course_materials"

# Gemini call retry policy - rate limits are the expected failure mode at
# this volume (up to ~2 calls/lesson x ~10-17 lessons/course).
MAX_RETRIES = 4
BASE_RETRY_DELAY_SECONDS = 5.0


def _call_with_retries(fn, *args, **kwargs):
    for attempt in range(MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except genai_errors.APIError as e:
            if attempt == MAX_RETRIES:
                raise
            delay = BASE_RETRY_DELAY_SECONDS * (2 ** attempt)
            logger.warning(
                "Gemini API error (attempt %d/%d): %s - retrying in %.0fs",
                attempt + 1, MAX_RETRIES + 1, e, delay,
            )
            time.sleep(delay)


class Report:
    """Collects one line per lesson/course decision made during a run, then
    writes it out as a markdown file - the thing you actually read after a
    batch finishes."""

    def __init__(self):
        self.lines: List[str] = []
        self.generated = 0
        self.generated_no_source = 0
        self.skipped_no_match = 0
        self.skipped_already_done = 0
        self.skipped_no_source = 0
        self.skipped_local_file = 0
        self.errors = 0
        self.length_warnings = 0

    def course_header(self, course_code: str, course_name: str, content_urls: List[str]) -> None:
        self.lines.append(f"\n## {course_code} — {course_name}\n\n_Користени страници ({len(content_urls)}):_\n")
        for u in content_urls:
            self.lines.append(f"- {u}\n")
        self.lines.append("\n")

    def local_file_skip(self, course_code: str, course_name: str) -> None:
        self.skipped_local_file += 1
        self.lines.append(
            f"\n## {course_code} — {course_name}\n\n"
            f"⏭️ Прескокнато целосно - извор е само локален фајл, не URL "
            f"(вклучено во LOCAL_FILE_ONLY_CODES, се работи подоцна).\n"
        )

    def course_not_found(self, course_code: str, course_name: str) -> None:
        self.errors += 1
        self.lines.append(
            f"\n## {course_code} — {course_name}\n\n"
            f"❌ Не е најден Course со code=`{course_code}` ниту со name=`{course_name}` во базата. Прескокнато.\n"
        )

    def course_extract_error(self, course_code: str, course_name: str, error: str) -> None:
        self.errors += 1
        self.lines.append(f"❌ Не успеа преземање/парсирање на изворот: {error}\n")

    def no_source_topics_only(self, course_code: str, course_name: str, lesson_count: int) -> None:
        self.skipped_no_source += lesson_count
        self.lines.append(
            f"\n## {course_code} — {course_name}\n\n"
            f"⏭️ Без извор ({lesson_count} лекции） - создадени се само наслови, "
            f"без документација/квиз, без Gemini повици.\n"
        )

    def lesson_no_match(
        self, topic_title: str, confidence: float, closest_heading: Optional[str],
        title_en: Optional[str] = None,
    ) -> None:
        self.skipped_no_match += 1
        en_note = f" _(EN: „{title_en}“)_" if title_en else ""
        self.lines.append(
            f"- ⏭️ **{topic_title}**{en_note} — под прагот (доверба={confidence:.2f}, "
            f"најблиску: „{closest_heading}\") - оставено празно.\n"
        )

    def lesson_already_done(self, topic_title: str) -> None:
        self.skipped_already_done += 1
        self.lines.append(f"- ⏩ **{topic_title}** — веќе генерирано порано, прескокнато (--force-regenerate за да се смени).\n")

    def lesson_generated(
        self, topic_title: str, confidence: float, matched_heading: str, word_count: int,
        title_en: Optional[str] = None,
    ) -> None:
        self.generated += 1
        warn = ""
        if word_count > MAX_DOCUMENTATION_WORDS * 1.5:
            self.length_warnings += 1
            warn = f" ⚠️ ПРЕДОЛГО ({word_count} зборови) - провери рачно."
        en_note = f" _(EN: „{title_en}“)_" if title_en else ""
        self.lines.append(
            f"- ✅ **{topic_title}**{en_note} — извор: „{matched_heading}\" (доверба={confidence:.2f}), "
            f"{word_count} зборови.{warn}\n"
        )

    def lesson_generated_no_source(self, topic_title: str, word_count: int) -> None:
        """Документацијата е генерирана БЕЗ вистински извор (--generate-without-source -
        см. gemini_generator.py's "4. ДОКУМЕНТАЦИЈА БЕЗ ИЗВОР"). Одделено од
        lesson_generated() за да извештајот јасно покаже кои лекции треба човек
        рачно да ги провери наспроти вистински учебник."""
        self.generated_no_source += 1
        warn = ""
        if word_count > MAX_DOCUMENTATION_WORDS * 1.5:
            self.length_warnings += 1
            warn = f" ⚠️ ПРЕДОЛГО ({word_count} зборови) - провери рачно."
        self.lines.append(
            f"- ⚠️ **{topic_title}** — генерирано БЕЗ извор (општо AI знаење, "
            f"провери точност), {word_count} зборови.{warn}\n"
        )

    def lesson_error(self, topic_title: str, error: str) -> None:
        self.errors += 1
        self.lines.append(f"- ❌ **{topic_title}** — грешка при генерирање: {error}\n")

    def write(self, path: Path) -> None:
        summary = (
            f"# Извештај за генерирање лекции\n\n"
            f"_{utcnow().isoformat()} UTC_\n\n"
            f"- Генерирани: {self.generated}\n"
            f"- Генерирани БЕЗ извор (општо AI знаење - провери точност): {self.generated_no_source}\n"
            f"- Прескокнати (без поклопување со извор): {self.skipped_no_match}\n"
            f"- Прескокнати (веќе генерирани порано): {self.skipped_already_done}\n"
            f"- Прескокнати (без извор воопшто): {self.skipped_no_source}\n"
            f"- Прескокнати (локален фајл извор, се работи подоцна): {self.skipped_local_file}\n"
            f"- Грешки: {self.errors}\n"
            f"- Предолги документации (провери рачно): {self.length_warnings}\n"
        )
        path.write_text(summary + "".join(self.lines), encoding="utf-8")
        logger.info("Report written to %s", path)


def _generate_lessons_no_source(
    db: Session,
    course_id: int,
    course_name: str,
    lessons: List[Dict[str, Any]],
    force_regenerate: bool,
    generate_quiz_flag: bool,
    report: Report,
) -> None:
    """Shared by both no-source paths in seed_course(): a course with no source
    at all (--generate-without-source) and a course whose source exists but is
    being explicitly overridden (--force-general-knowledge, e.g. because the
    source badly under-covers the curated topic list - see seed_course()).
    Generates every lesson from the model's general knowledge
    (generate_no_source_documentation, which always prepends
    NO_SOURCE_DISCLAIMER_MK itself), tags it with
    Lesson.generation_method = GENERATION_METHOD_GENERAL_KNOWLEDGE (so it's
    distinguishable from a source-grounded lesson at the data/API level, not
    just via the markdown disclaimer text), and tracks each one via
    report.lesson_generated_no_source() so it stays distinguishable in the
    run report too."""
    for i, lesson in enumerate(lessons, start=1):
        topic_title = lesson["topic_title"]
        if not force_regenerate and get_existing_documentation(db, course_id, i):
            report.lesson_already_done(topic_title)
            continue
        try:
            documentation = _call_with_retries(
                generate_no_source_documentation,
                course_name_mk=course_name,
                lesson_title=topic_title,
            )
            quiz = None
            if generate_quiz_flag:
                quiz = _call_with_retries(
                    generate_quiz, lesson_title=topic_title, documentation_text=documentation
                )
        except (genai_errors.APIError, RuntimeError, json.JSONDecodeError) as e:
            report.lesson_error(topic_title, str(e))
            continue
        word_count = documentation_word_count(documentation)
        upsert_lesson(
            db, course_id, i, topic_title, documentation=documentation, quiz=quiz,
            generation_method=GENERATION_METHOD_GENERAL_KNOWLEDGE,
        )
        report.lesson_generated_no_source(topic_title, word_count)


def seed_course(
    db: Session,
    course: Dict[str, Any],
    cache_dir: Path,
    threshold: float,
    force_regenerate: bool,
    report: Report,
    generate_quiz_flag: bool = True,
    local_materials_dir: Optional[Path] = None,
    generate_without_source: bool = False,
    force_general_knowledge: bool = False,
) -> None:
    course_code = course["course_code"]
    course_name = course["course_name_mk"]

    course_id = find_course_id(db, course_code, course_name)
    if course_id is None:
        report.course_not_found(course_code, course_name)
        return

    lessons = course["lessons"]

    if not lessons:
        # Fallback for a course with no curated topic list in courses_db.json at
        # all (doesn't happen for any of the current 67 courses as of this
        # writing, but keeps this from silently doing nothing for a future one) -
        # derive topic titles from this course's scraped CourseMaterial entries.
        materials = (
            db.query(CourseMaterial)
            .filter(CourseMaterial.course_id == course_id)
            .order_by(CourseMaterial.category, CourseMaterial.title)
            .all()
        )
        lessons = [{"topic_title": m.title} for m in materials]
        if not lessons:
            report.errors += 1
            report.lines.append(
                f"\n## {course_code} — {course_name}\n\n"
                f"❌ Нема ниту наслови на лекции ниту course_materials за овој предмет - прескокнато.\n"
            )
            return

    if force_general_knowledge:
        # --force-general-knowledge: explicit, per-run override that IGNORES
        # whatever source this course has (even a real, "confirmed" one) and
        # always generates from the model's general knowledge instead. For a
        # course where has_fetchable_source(course) is True but the actual
        # matching/coverage was poor in practice (many lessons ended up with
        # no documentation at all, or very thin documentation, despite a
        # legitimate source book existing) - a human judgment call, not
        # something has_fetchable_source() can detect on its own.
        report.course_header(
            course_code, course_name,
            ["(присилно - извор игнориран, генерирано од општо AI знаење)"],
        )
        _generate_lessons_no_source(
            db, course_id, course_name, lessons, force_regenerate, generate_quiz_flag, report,
        )
        return

    if course_code in LOCAL_FILE_ONLY_CODES:
        # Try the user-supplied files first (course_materials/<code>/*) -
        # only fall back to the old "skip entirely" behaviour if none have
        # been dropped in yet, so this stays safe to call before the files
        # exist too.
        materials_dir = local_materials_dir or (Path.cwd() / DEFAULT_LOCAL_MATERIALS_DIR_NAME)
        sections = extract_local_files_sections(course_code, materials_dir)
        if not sections:
            report.local_file_skip(course_code, course_name)
            return
        source = course.get("source") or {}
        display_pages = [f"[локален фајл] {s.heading}" for s in sections]
        report.course_header(course_code, course_name, display_pages)
        replace_course_sources(db, course_id, source, course.get("additional_sources"))
    elif not has_fetchable_source(course):
        if not generate_without_source:
            report.no_source_topics_only(course_code, course_name, len(lessons))
            for i, lesson in enumerate(lessons, start=1):
                upsert_lesson(db, course_id, i, lesson["topic_title"])
            return
        # --generate-without-source: explicit opt-in only (see gemini_generator.py's
        # "4. ДОКУМЕНТАЦИЈА БЕЗ ИЗВОР" section) - generates real documentation from
        # the model's general knowledge instead of leaving topic-only rows.
        report.course_header(course_code, course_name, ["(без извор - генерирано од општо AI знаење)"])
        _generate_lessons_no_source(
            db, course_id, course_name, lessons, force_regenerate, generate_quiz_flag, report,
        )
        return
    else:
        source = course["source"]
        # content_urls: manually-curated real chapter/section URLs (source.url
        # is often a catalog/landing page with no real text - see
        # source_text.py's module docstring). Курсеви без content_urls се
        # враќаат на едно-URL однесувањето од порано (fine кога source.url
        # веќе сочинува вистинска страница со содржина). Discovery преку
        # Gemini google_search беше напуштено - тоа alatka не постои на free
        # tier (бара billing на Google Cloud проектот), па наместо тоа овие
        # URL-ови се рачно истражени и проверени еднаш, надвор од
        # pipeline-от.
        content_urls = source.get("content_urls") or [source["url"]]
        sections = extract_sections_multi(content_urls, cache_dir)
        if not sections:
            report.course_extract_error(
                course_code, course_name,
                f"Ниту една од {len(content_urls)} страници не даде извлечлив текст",
            )
            return

        report.course_header(course_code, course_name, content_urls)
        replace_course_sources(db, course_id, source, course.get("additional_sources"))

    for i, lesson in enumerate(lessons, start=1):
        topic_title = lesson["topic_title"]

        if not force_regenerate and get_existing_documentation(db, course_id, i):
            report.lesson_already_done(topic_title)
            continue

        # Sources are mostly English-language pages (OpenStax/MDN/learncpp/...)
        # but topic_title is Macedonian - translate once (cached to disk, see
        # title_translation.py) so score_section() has a fair vocabulary to
        # match against instead of comparing two different languages.
        title_en = translate_title_mk_to_en(topic_title, cache_dir)
        match = find_best_excerpt(topic_title, sections, threshold=threshold, title_en=title_en)
        if match.excerpt is None:
            upsert_lesson(db, course_id, i, topic_title)
            report.lesson_no_match(topic_title, match.confidence, match.matched_heading, title_en)
            continue

        try:
            documentation = _call_with_retries(
                generate_documentation,
                course_name_mk=course_name,
                lesson_title=topic_title,
                source_excerpt=match.excerpt,
                source_title=source.get("title", ""),
                source_author=source.get("author", ""),
            )
            # generate_quiz_flag=False: documentation-only pass (see run()'s
            # docstring) - halves the Gemini calls/lesson, which matters a lot
            # against the 20/day free-tier cap. Quiz stays NULL - upsert_lesson
            # leaves an existing quiz column untouched when quiz=None is
            # passed, so a later quiz-only backfill pass (not built yet, but
            # get_existing_documentation() + a documentation-is-set/quiz-is-
            # NULL query would find exactly these lessons) can add it in
            # without re-spending a documentation call.
            quiz = None
            if generate_quiz_flag:
                quiz = _call_with_retries(
                    generate_quiz, lesson_title=topic_title, documentation_text=documentation
                )
        except (genai_errors.APIError, RuntimeError, json.JSONDecodeError) as e:
            # RuntimeError (e.g. GEMINI_API_KEY unset) and JSONDecodeError
            # (a malformed quiz response - gemini_generator.generate_quiz's
            # own docstring flags this as a real possibility despite the
            # schema constraint) used to propagate past this except clause,
            # which only caught genai_errors.APIError - either one aborted
            # the whole multi-course run and lost this report. One bad
            # lesson should never take down the rest of the batch.
            report.lesson_error(topic_title, str(e))
            continue

        word_count = documentation_word_count(documentation)
        upsert_lesson(
            db, course_id, i, topic_title, documentation=documentation, quiz=quiz,
            generation_method=GENERATION_METHOD_SOURCE,
        )
        report.lesson_generated(topic_title, match.confidence, match.matched_heading or "?", word_count, title_en)


def run(
    db: Session,
    courses_db_path: Path,
    course_codes: List[str],
    cache_dir: Path = DEFAULT_CACHE_DIR,
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    force_regenerate: bool = False,
    generate_quiz_flag: bool = True,
    local_materials_dir: Optional[Path] = None,
    generate_without_source: bool = False,
    force_general_knowledge: bool = False,
) -> Report:
    """generate_quiz_flag=False: documentation-only run, skips the quiz
    Gemini call entirely (see seed_course()) - halves API usage per generated
    lesson. Quizzes for these lessons can be backfilled later in a separate
    pass without re-spending a documentation call.

    local_materials_dir: base folder for LOCAL_FILE_ONLY_CODES courses (one
    subfolder per course_code - see extract_local_files_sections()). Defaults
    to a "course_materials" folder next to courses_db_path itself if not
    given, since that's where the user actually keeps courses_db.json."""
    all_courses = load_courses(courses_db_path)
    courses = get_courses_by_codes(all_courses, course_codes)

    if local_materials_dir is None:
        local_materials_dir = courses_db_path.parent / DEFAULT_LOCAL_MATERIALS_DIR_NAME

    report = Report()
    for course in courses:
        logger.info("=== %s: %s ===", course["course_code"], course["course_name_mk"])
        seed_course(
            db, course, cache_dir, threshold, force_regenerate, report, generate_quiz_flag,
            local_materials_dir=local_materials_dir,
            generate_without_source=generate_without_source,
            force_general_knowledge=force_general_knowledge,
        )
    return report


# ---------------------------------------------------------------------------
# CLI (also reachable via `python -m backend.services.ingestion.cli --source lessons`)
# ---------------------------------------------------------------------------

def main() -> None:
    from backend.database.session import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Seed lessons/course_sources from courses_db.json via Gemini")
    parser.add_argument("--courses-db-path", type=Path, required=True)
    parser.add_argument("--course-codes", type=str, required=True, help="Comma-separated course_code list")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--local-materials-dir", type=Path, default=None,
        help="Base folder for LOCAL_FILE_ONLY_CODES courses (default: "
             "'course_materials' next to --courses-db-path)",
    )
    parser.add_argument("--threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    parser.add_argument("--force-regenerate", action="store_true")
    parser.add_argument(
        "--skip-quiz", action="store_true",
        help="Documentation-only pass - skip the quiz Gemini call (halves API usage/lesson)",
    )
    parser.add_argument(
        "--generate-without-source", action="store_true",
        help="Explicit opt-in: for courses with NO source in courses_db.json, generate "
             "documentation from the model's general knowledge instead of leaving "
             "topic-only rows. Every such lesson is clearly disclaimed (see "
             "gemini_generator.py's NO_SOURCE_DISCLAIMER_MK) and tracked separately "
             "in the report and via Lesson.generation_method - review these before "
             "trusting them like sourced lessons.",
    )
    parser.add_argument(
        "--force-general-knowledge", action="store_true",
        help="Explicit override: IGNORE this course's source entirely (even a real, "
             "confirmed one) and always generate from the model's general knowledge. "
             "For a course where the source technically exists but coverage/matching "
             "was poor in practice (many lessons ended up empty or very thin) - a "
             "human judgment call to make per course, not automatic.",
    )
    parser.add_argument("--report-path", type=Path, default=None)
    args = parser.parse_args()

    course_codes = [c.strip() for c in args.course_codes.split(",") if c.strip()]
    report_path = args.report_path or Path(f"lesson_seed_report_{utcnow().strftime('%Y%m%d_%H%M%S')}.md")

    db = SessionLocal()
    try:
        report = run(
            db,
            courses_db_path=args.courses_db_path,
            course_codes=course_codes,
            cache_dir=args.cache_dir,
            threshold=args.threshold,
            force_regenerate=args.force_regenerate,
            generate_quiz_flag=not args.skip_quiz,
            local_materials_dir=args.local_materials_dir,
            generate_without_source=args.generate_without_source,
            force_general_knowledge=args.force_general_knowledge,
        )
    finally:
        db.close()

    report.write(report_path)
    print(f"Готово. Извештај: {report_path}")


if __name__ == "__main__":
    main()
