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
     -> Lesson rows created with topic_title only, nothing generated, no API calls.
  2. Source is a local file only (source.url is None - see courses_db.py's
     LOCAL_FILE_ONLY_CODES) -> course is skipped entirely for now (not even
     topic-only rows), logged clearly. Revisit once local_path support exists.
  3. Source has a real URL -> full pipeline: fetch+extract (source_text.py),
     match each lesson to its best excerpt (lesson_matching.py), and only
     call Gemini for lessons that clear the confidence threshold. Lessons
     that don't clear it get a topic-only row (documentation/quiz stay NULL)
     - by design, per-lesson silence rather than fabricated content.

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
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.genai import errors as genai_errors
from sqlalchemy.orm import Session

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
    generate_quiz,
)
from backend.services.ingestion.lesson_matching import DEFAULT_CONFIDENCE_THRESHOLD, find_best_excerpt
from backend.services.ingestion.lesson_upsert import (
    find_course_id,
    get_existing_documentation,
    replace_course_sources,
    upsert_lesson,
)
from backend.services.ingestion.source_text import extract_sections

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(".lesson_source_cache")

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
        self.skipped_no_match = 0
        self.skipped_already_done = 0
        self.skipped_no_source = 0
        self.skipped_local_file = 0
        self.errors = 0
        self.length_warnings = 0

    def course_header(self, course_code: str, course_name: str) -> None:
        self.lines.append(f"\n## {course_code} — {course_name}\n")

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

    def lesson_no_match(self, topic_title: str, confidence: float, closest_heading: Optional[str]) -> None:
        self.skipped_no_match += 1
        self.lines.append(
            f"- ⏭️ **{topic_title}** — под прагот (доверба={confidence:.2f}, "
            f"најблиску: „{closest_heading}\") - оставено празно.\n"
        )

    def lesson_already_done(self, topic_title: str) -> None:
        self.skipped_already_done += 1
        self.lines.append(f"- ⏩ **{topic_title}** — веќе генерирано порано, прескокнато (--force-regenerate за да се смени).\n")

    def lesson_generated(self, topic_title: str, confidence: float, matched_heading: str, word_count: int) -> None:
        self.generated += 1
        warn = ""
        if word_count > MAX_DOCUMENTATION_WORDS * 1.5:
            self.length_warnings += 1
            warn = f" ⚠️ ПРЕДОЛГО ({word_count} зборови) - провери рачно."
        self.lines.append(
            f"- ✅ **{topic_title}** — извор: „{matched_heading}\" (доверба={confidence:.2f}), "
            f"{word_count} зборови.{warn}\n"
        )

    def lesson_error(self, topic_title: str, error: str) -> None:
        self.errors += 1
        self.lines.append(f"- ❌ **{topic_title}** — грешка при генерирање: {error}\n")

    def write(self, path: Path) -> None:
        summary = (
            f"# Извештај за генерирање лекции\n\n"
            f"_{datetime.utcnow().isoformat()} UTC_\n\n"
            f"- Генерирани: {self.generated}\n"
            f"- Прескокнати (без поклопување со извор): {self.skipped_no_match}\n"
            f"- Прескокнати (веќе генерирани порано): {self.skipped_already_done}\n"
            f"- Прескокнати (без извор воопшто): {self.skipped_no_source}\n"
            f"- Прескокнати (локален фајл извор, се работи подоцна): {self.skipped_local_file}\n"
            f"- Грешки: {self.errors}\n"
            f"- Предолги документации (провери рачно): {self.length_warnings}\n"
        )
        path.write_text(summary + "".join(self.lines), encoding="utf-8")
        logger.info("Report written to %s", path)


def seed_course(
    db: Session,
    course: Dict[str, Any],
    cache_dir: Path,
    threshold: float,
    force_regenerate: bool,
    report: Report,
) -> None:
    course_code = course["course_code"]
    course_name = course["course_name_mk"]

    course_id = find_course_id(db, course_code, course_name)
    if course_id is None:
        report.course_not_found(course_code, course_name)
        return

    if course_code in LOCAL_FILE_ONLY_CODES:
        report.local_file_skip(course_code, course_name)
        return

    lessons = course["lessons"]

    if not has_fetchable_source(course):
        report.no_source_topics_only(course_code, course_name, len(lessons))
        for i, lesson in enumerate(lessons, start=1):
            upsert_lesson(db, course_id, i, lesson["topic_title"])
        return

    source = course["source"]
    try:
        sections = extract_sections(source["url"], cache_dir)
    except Exception as e:
        report.course_extract_error(course_code, course_name, str(e))
        return

    report.course_header(course_code, course_name)
    replace_course_sources(db, course_id, source, course.get("additional_sources"))

    for i, lesson in enumerate(lessons, start=1):
        topic_title = lesson["topic_title"]

        if not force_regenerate and get_existing_documentation(db, course_id, i):
            report.lesson_already_done(topic_title)
            continue

        match = find_best_excerpt(topic_title, sections, threshold=threshold)
        if match.excerpt is None:
            upsert_lesson(db, course_id, i, topic_title)
            report.lesson_no_match(topic_title, match.confidence, match.matched_heading)
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
            quiz = _call_with_retries(
                generate_quiz, lesson_title=topic_title, documentation_text=documentation
            )
        except genai_errors.APIError as e:
            report.lesson_error(topic_title, str(e))
            continue

        word_count = documentation_word_count(documentation)
        upsert_lesson(db, course_id, i, topic_title, documentation=documentation, quiz=quiz)
        report.lesson_generated(topic_title, match.confidence, match.matched_heading or "?", word_count)


def run(
    db: Session,
    courses_db_path: Path,
    course_codes: List[str],
    cache_dir: Path = DEFAULT_CACHE_DIR,
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    force_regenerate: bool = False,
) -> Report:
    all_courses = load_courses(courses_db_path)
    courses = get_courses_by_codes(all_courses, course_codes)

    report = Report()
    for course in courses:
        logger.info("=== %s: %s ===", course["course_code"], course["course_name_mk"])
        seed_course(db, course, cache_dir, threshold, force_regenerate, report)
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
    parser.add_argument("--threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    parser.add_argument("--force-regenerate", action="store_true")
    parser.add_argument("--report-path", type=Path, default=None)
    args = parser.parse_args()

    course_codes = [c.strip() for c in args.course_codes.split(",") if c.strip()]
    report_path = args.report_path or Path(f"lesson_seed_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md")

    db = SessionLocal()
    try:
        report = run(
            db,
            courses_db_path=args.courses_db_path,
            course_codes=course_codes,
            cache_dir=args.cache_dir,
            threshold=args.threshold,
            force_regenerate=args.force_regenerate,
        )
    finally:
        db.close()

    report.write(report_path)
    print(f"Готово. Извештај: {report_path}")


if __name__ == "__main__":
    main()
