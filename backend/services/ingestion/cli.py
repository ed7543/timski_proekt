"""Standalone ingestion entrypoint - never triggered by live API traffic.

Usage:
    python -m backend.services.ingestion.cli --source all
    python -m backend.services.ingestion.cli --source snimki
    python -m backend.services.ingestion.cli --source snimki --slugs strukturno-programiranje,algoritmi-i-podatochni-strukturi
    python -m backend.services.ingestion.cli --source snimki --limit 3
    python -m backend.services.ingestion.cli --source predmeti
    python -m backend.services.ingestion.cli --source predmeti --create-missing
    python -m backend.services.ingestion.cli --source lessons \\
        --courses-db-path "C:\\Users\\stoja\\Downloads\\courses_db.json" \\
        --course-codes F23L1W005,F23L1W020,F23L2W002,F23L2W031,F23L2W041,F23L1S003,F23L1S016,F23L1S023,F23L1S045,F23L1S146 \\
        --skip-quiz
"""
import argparse
import asyncio
import logging
from pathlib import Path

from backend.database.session import SessionLocal
from backend.services.ingestion.finki_hub_client import FinkiHubClient
from backend.services.ingestion.predmeti_scraper import fetch_predmeti_courses
from backend.services.ingestion.snimki_scraper import fetch_course, list_course_files
from backend.services.ingestion import seed_lessons
from backend.services.ingestion.lesson_matching import DEFAULT_CONFIDENCE_THRESHOLD
from backend.services.ingestion.upsert import (
    create_course_from_predmeti,
    find_course_by_name,
    upsert_course_from_snimki,
    upsert_course_metadata_from_predmeti,
    upsert_materials_for_course,
    upsert_recordings_for_course,
)
from backend.utils.time import utcnow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _transliterate_slug(name: str) -> str:
    """Best-effort Cyrillic -> Latin slugify for predmeti-only courses that have
    no snimki page (and therefore no source-of-truth URL slug to reuse). Not
    guaranteed to match finki-hub's own (hand-curated, occasionally
    inconsistent) slugs - only used as a fallback key for courses this pipeline
    itself is the first to introduce."""
    table = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ѓ": "gj", "е": "e",
        "ж": "zh", "з": "z", "ѕ": "dz", "и": "i", "ј": "j", "к": "k", "л": "l",
        "љ": "lj", "м": "m", "н": "n", "њ": "nj", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "ќ": "kj", "у": "u", "ф": "f", "х": "h", "ц": "c",
        "ч": "ch", "џ": "dzh", "ш": "sh",
    }
    out = []
    for ch in name.lower():
        if ch in table:
            out.append(table[ch])
        elif ch.isalnum():
            out.append(ch)
        elif ch in " -_/":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


async def ingest_snimki(limit: int | None, slugs: list[str] | None) -> None:
    async with FinkiHubClient() as client:
        await client.check_robots("https://snimki.finki-hub.com")

        course_files = await list_course_files(client)
        if slugs:
            course_files = [(sem, slug) for sem, slug in course_files if slug in slugs]
        if limit:
            course_files = course_files[:limit]

        logger.info("Ingesting %d course page(s) from snimki.finki-hub.com", len(course_files))

        db = SessionLocal()
        try:
            for semester, slug in course_files:
                logger.info("Fetching %s/%s", semester, slug)
                scraped = await fetch_course(client, semester, slug)
                if not scraped:
                    logger.warning("Skipping %s/%s (fetch/parse failed)", semester, slug)
                    continue

                course_id = upsert_course_from_snimki(db, scraped)
                rec_count = upsert_recordings_for_course(db, course_id, scraped.recordings, scraped.source_url)
                mat_count = upsert_materials_for_course(db, course_id, scraped.materials)
                logger.info(
                    "  -> course_id=%s '%s': %d recordings, %d materials",
                    course_id, scraped.name, rec_count, mat_count,
                )
        finally:
            db.close()


async def ingest_predmeti(limit: int | None, create_missing: bool) -> None:
    async with FinkiHubClient() as client:
        await client.check_robots("https://predmeti.finki-hub.com")
        courses = await fetch_predmeti_courses(client)
        if limit:
            courses = courses[:limit]

        logger.info(
            "Fetched %d predmeti.finki-hub.com course record(s) (create_missing=%s)",
            len(courses), create_missing,
        )

        db = SessionLocal()
        try:
            enriched = 0
            created = 0
            for predmeti in courses:
                existing = find_course_by_name(db, predmeti.name)
                if existing:
                    upsert_course_metadata_from_predmeti(db, existing.id, predmeti)
                    enriched += 1
                elif create_missing:
                    slug = _transliterate_slug(predmeti.name)
                    create_course_from_predmeti(db, slug, predmeti)
                    created += 1
            logger.info("Enriched %d existing course(s), created %d new course(s)", enriched, created)
        finally:
            db.close()


async def main_async(args: argparse.Namespace) -> None:
    slugs = [s.strip() for s in args.slugs.split(",")] if args.slugs else None

    if args.source in ("all", "snimki"):
        await ingest_snimki(limit=args.limit, slugs=slugs)
    if args.source in ("all", "predmeti"):
        await ingest_predmeti(limit=args.limit, create_missing=args.create_missing)


def run_lessons(args: argparse.Namespace) -> None:
    """--source lessons is synchronous (local JSON + sync Gemini calls, no
    finki-hub scraping involved) and takes its own required args - handled
    outside main_async()/asyncio entirely. See seed_lessons.py for what
    actually happens per course."""
    if not args.courses_db_path or not args.course_codes:
        raise SystemExit("--source lessons requires --courses-db-path and --course-codes")

    course_codes = [c.strip() for c in args.course_codes.split(",") if c.strip()]
    report_path = args.report_path or Path(
        f"lesson_seed_report_{utcnow().strftime('%Y%m%d_%H%M%S')}.md"
    )

    db = SessionLocal()
    try:
        report = seed_lessons.run(
            db,
            courses_db_path=args.courses_db_path,
            course_codes=course_codes,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest FINKI course data from finki-hub.com")
    parser.add_argument("--source", choices=["all", "predmeti", "snimki", "lessons"], default="all")
    parser.add_argument("--limit", type=int, default=None, help="Cap the number of courses processed")
    parser.add_argument(
        "--slugs", type=str, default=None,
        help="Comma-separated list of snimki course slugs to restrict ingestion to",
    )
    parser.add_argument(
        "--create-missing", action="store_true",
        help="For --source predmeti: also create new Course rows for courses with no snimki page "
             "(default: only enrich courses that already exist)",
    )
    parser.add_argument(
        "--courses-db-path", type=Path, default=None,
        help="For --source lessons: path to courses_db.json (lives outside the repo, e.g. in Downloads)",
    )
    parser.add_argument(
        "--course-codes", type=str, default=None,
        help="For --source lessons: comma-separated course_code list to process (one batch)",
    )
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD,
        help="For --source lessons: minimum lesson<->source-section match confidence to generate content for",
    )
    parser.add_argument(
        "--force-regenerate", action="store_true",
        help="For --source lessons: regenerate lessons that already have documentation (default: skip them)",
    )
    parser.add_argument(
        "--skip-quiz", action="store_true",
        help="For --source lessons: documentation-only pass, skip the quiz Gemini call "
             "(halves API usage per generated lesson - quiz can be backfilled later)",
    )
    parser.add_argument(
        "--report-path", type=Path, default=None,
        help="For --source lessons: where to write the run's markdown report (default: timestamped file in cwd)",
    )
    parser.add_argument(
        "--local-materials-dir", type=Path, default=None,
        help="For --source lessons: base folder for LOCAL_FILE_ONLY_CODES courses, one subfolder "
             "per course_code (default: 'course_materials' next to --courses-db-path)",
    )
    parser.add_argument(
        "--generate-without-source", action="store_true",
        help="For --source lessons: explicit opt-in - for courses with NO source in "
             "courses_db.json (status pending_source/deferred_user_will_provide_materials), "
             "generate documentation from the model's general knowledge instead of leaving "
             "topic-only rows. Every such lesson is clearly disclaimed (see gemini_generator.py's "
             "NO_SOURCE_DISCLAIMER_MK) and tracked separately in the run report - review these "
             "before trusting them like properly-sourced lessons.",
    )
    parser.add_argument(
        "--force-general-knowledge", action="store_true",
        help="For --source lessons: explicit override - IGNORE this course's source entirely "
             "(even a real, confirmed one) and always generate from the model's general "
             "knowledge. Use for a course where the source technically exists but coverage "
             "was poor in practice (many lessons ended up empty or very thin) - a human "
             "judgment call to make per course, not automatic. Combine with --force-regenerate "
             "to also overwrite lessons that already have some (poor) documentation.",
    )
    args = parser.parse_args()

    if args.source == "lessons":
        run_lessons(args)
    else:
        asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
