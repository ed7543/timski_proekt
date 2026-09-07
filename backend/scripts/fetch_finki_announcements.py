"""Pulls new posts from four official sources into the Ресурси/Blog
feed - the automated counterpart to an admin manually pasting a link through
"+ Додади нова статија" (see routes/blogRoute.py):

1. The FINKI student-announcement board (oldsite.finki.ukim.mk/mk/student-
   announcement) - category guessed by keyword (Конкурси / Уписи / Настани /
   Пракси и работа), uncategorized items (mostly menu/navigation links, not
   real announcements) are skipped.
2. The FINKI jobs & internships board (finki.ukim.mk/.../jobs-and-
   internships/) - every posting there always goes into "Пракси и работа"
   directly, no guessing needed since we already know what the source is.
3. The Ministry of Education and Science's own "Конкурси" board
   (mon.gov.mk/mk-MK/konkursi-i-stipendii/konkursi-mon) - national calls,
   filtered down to those relevant to students at a public/private faculty
   or university (see services/mon_konkursi.is_relevant_to_students).
4. The Ministry's "Стипендии" board (mon.gov.mk/mk-MK/konkursi-i-stipendii/
   stipendii-mon) - national scholarships, filtered the same way as #3.
   Both MON sources feed the same "Конкурси" category.

Safe to run repeatedly or on a schedule: it only ever adds posts whose URL
isn't already in blog_posts, never touches or duplicates existing rows.

Usage:
    python -m backend.scripts.fetch_finki_announcements
    python -m backend.scripts.fetch_finki_announcements --max-pages 3 --dry-run

See README.md ("Sync FINKI announcements into the Blog feed") for how to run
this on a schedule via Windows Task Scheduler / Linux crontab.
"""
import argparse
import time
from typing import Callable, Iterable, Optional

from sqlalchemy.orm import Session

from backend.database.models import BlogPost
from backend.database.session import SessionLocal
from backend.services.blog_fetcher import BlogFetchError, fetch_article_metadata
from backend.services.finki_announcements import (
    discover_announcement_urls,
    discover_job_urls,
    guess_category,
)
from backend.services.mon_konkursi import (
    discover_konkursi_urls,
    discover_stipendii_urls,
    is_relevant_to_students,
)

# Politeness delay between fetching each individual page - these hit real
# university servers, not an API meant for automation.
FETCH_DELAY_SECONDS = 1.5


def existing_source_urls(db: Session) -> set[str]:
    return {row[0] for row in db.query(BlogPost.source_url).all()}


def _import_urls(
    db: Session,
    urls: Iterable[str],
    dry_run: bool,
    category_of: Callable[[dict], Optional[str]],
    source_name: str = "ФИНКИ",
) -> int:
    added = 0
    for url in urls:
        try:
            meta = fetch_article_metadata(url)
        except BlogFetchError as exc:
            print(f"  ПРЕСКОКНАТО ({exc}): {url}")
            continue

        category = category_of(meta)
        if category is None:
            # No recognized category almost always means this is a menu/
            # navigation link (e.g. "Лаборатории на ФИНКИ", "Академски
            # календар"), not a real post - skip it rather than importing
            # site navigation as a "post".
            print(f"  ПРЕСКОКНАТО (без препознаена категорија): {meta['title']}")
            time.sleep(FETCH_DELAY_SECONDS)
            continue

        print(f"  + [{category}] {meta['title']}")

        if not dry_run:
            db.add(BlogPost(
                title=meta["title"],
                excerpt=meta["excerpt"],
                image_url=meta["image_url"],
                source_url=url,
                # Hardcoded rather than whatever blog_fetcher guesses from
                # the page's own og:site_name/domain - we already know
                # exactly where these come from.
                source_name=source_name,
                category=category,
                added_by_id=None,  # system-added, not a specific admin
            ))
            db.commit()
        added += 1
        time.sleep(FETCH_DELAY_SECONDS)

    return added


def sync(db: Session, max_pages: int, dry_run: bool) -> int:
    known = existing_source_urls(db)

    announcement_urls = discover_announcement_urls(max_pages=max_pages)
    new_announcements = [u for u in announcement_urls if u not in known]
    print(f"Огласна табла: најдов {len(announcement_urls)} огласи, {len(new_announcements)} се нови.")
    added = _import_urls(
        db, new_announcements, dry_run,
        category_of=lambda meta: guess_category(meta["title"]),
    )

    # Refresh, since the announcements above may have just been committed.
    known = existing_source_urls(db)
    job_urls = discover_job_urls(max_pages=max_pages)
    new_jobs = [u for u in job_urls if u not in known]
    print(f"Пракси и вработувања: најдов {len(job_urls)} огласи, {len(new_jobs)} се нови.")
    added += _import_urls(
        db, new_jobs, dry_run,
        category_of=lambda meta: "Пракси и работа",
    )

    # Refresh again, since the jobs above may have just been committed.
    known = existing_source_urls(db)
    konkursi_urls = discover_konkursi_urls(max_pages=max_pages)
    new_konkursi = [u for u in konkursi_urls if u not in known]
    print(f"МОН конкурси: најдов {len(konkursi_urls)} огласи, {len(new_konkursi)} се нови.")
    added += _import_urls(
        db, new_konkursi, dry_run,
        # Filter out K-12 postings (textbooks, pupil dormitories, gymnasium
        # programs) - only postings relevant to public/private faculty or
        # university students belong in this app's feed. See
        # mon_konkursi.is_relevant_to_students for the keyword logic.
        category_of=lambda meta: "Конкурси" if is_relevant_to_students(meta["title"]) else None,
        source_name="МОН",
    )

    # Refresh again, since the MON konkursi above may have just been committed.
    known = existing_source_urls(db)
    stipendii_urls = discover_stipendii_urls(max_pages=max_pages)
    new_stipendii = [u for u in stipendii_urls if u not in known]
    print(f"МОН стипендии: најдов {len(stipendii_urls)} огласи, {len(new_stipendii)} се нови.")
    added += _import_urls(
        db, new_stipendii, dry_run,
        category_of=lambda meta: "Конкурси" if is_relevant_to_students(meta["title"]) else None,
        source_name="МОН",
    )

    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync new FINKI posts into the Blog/Ресурси feed")
    parser.add_argument(
        "--max-pages", type=int, default=2,
        help="How many list pages to scan per source for new posts (default 2)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be added without writing to the database",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        added = sync(db, max_pages=args.max_pages, dry_run=args.dry_run)
        suffix = "би биле додадени (--dry-run)" if args.dry_run else "додадени"
        print(f"Готово - {added} нови статии {suffix}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
