"""Idempotent upserts for ingested course/material/recording data - re-running
ingestion must never create duplicates, only refresh timestamps/content."""
from datetime import datetime
from typing import Optional

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.database.models import Course, CourseMaterial, Recording
from backend.services.ingestion.predmeti_scraper import PredmetiCourse
from backend.services.ingestion.snimki_scraper import CourseScrapeResult, MaterialItem, RecordingItem


def upsert_course_from_snimki(db: Session, scraped: CourseScrapeResult) -> int:
    """Upsert a Course row keyed on its unique `slug`, from a snimki scrape result.
    Returns the course id."""
    now = datetime.utcnow()
    stmt = insert(Course).values(
        slug=scraped.slug,
        name=scraped.name,
        semester=scraped.semester,
        source_url=scraped.source_url,
        created_at=now,
        updated_at=now,
        last_scraped_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Course.slug],
        set_={
            "name": stmt.excluded.name,
            "semester": stmt.excluded.semester,
            "source_url": stmt.excluded.source_url,
            "updated_at": now,
            "last_scraped_at": now,
        },
    ).returning(Course.id)
    result = db.execute(stmt)
    course_id = result.scalar_one()
    db.commit()
    return course_id


def upsert_course_metadata_from_predmeti(db: Session, course_id: int, predmeti: PredmetiCourse) -> None:
    """Enrich an existing Course row with predmeti metadata (code/semester/
    description) without touching its slug/name/source_url (snimki-owned)."""
    course = db.get(Course, course_id)
    if not course:
        return
    if predmeti.code:
        course.code = predmeti.code
    if predmeti.semester and not course.semester:
        course.semester = predmeti.semester
    course.description = predmeti.to_description()
    course.updated_at = datetime.utcnow()
    course.last_scraped_at = datetime.utcnow()
    db.commit()


def create_course_from_predmeti(db: Session, slug: str, predmeti: PredmetiCourse) -> int:
    """Create a brand-new Course row for a predmeti-only course (no snimki page),
    keyed on a synthesized slug. Idempotent on that slug like the snimki path."""
    now = datetime.utcnow()
    stmt = insert(Course).values(
        slug=slug,
        name=predmeti.name,
        code=predmeti.code,
        semester=predmeti.semester,
        description=predmeti.to_description(),
        source_url=None,
        created_at=now,
        updated_at=now,
        last_scraped_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Course.slug],
        set_={
            "code": stmt.excluded.code,
            "semester": stmt.excluded.semester,
            "description": stmt.excluded.description,
            "updated_at": now,
            "last_scraped_at": now,
        },
    ).returning(Course.id)
    result = db.execute(stmt)
    course_id = result.scalar_one()
    db.commit()
    return course_id


def find_course_by_name(db: Session, name: str) -> Optional[Course]:
    return db.query(Course).filter(Course.name == name).first()


def upsert_recordings_for_course(
    db: Session, course_id: int, recordings: list[RecordingItem], source_page_url: str
) -> int:
    now = datetime.utcnow()
    count = 0
    for item in recordings:
        stmt = insert(Recording).values(
            course_id=course_id,
            topic=item.topic,
            presenter=item.presenter,
            year=item.year,
            category=item.category,
            video_url=item.video_url,
            source_page_url=source_page_url,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Recording.course_id, Recording.video_url, Recording.topic],
            set_={
                "presenter": stmt.excluded.presenter,
                "year": stmt.excluded.year,
                "category": stmt.excluded.category,
                "source_page_url": stmt.excluded.source_page_url,
                "updated_at": now,
            },
        )
        db.execute(stmt)
        count += 1
    db.commit()
    return count


def upsert_materials_for_course(db: Session, course_id: int, materials: list[MaterialItem]) -> int:
    now = datetime.utcnow()
    count = 0
    for item in materials:
        stmt = insert(CourseMaterial).values(
            course_id=course_id,
            title=item.title,
            category=item.category,
            url=item.url,
            description=item.description,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[CourseMaterial.course_id, CourseMaterial.url],
            set_={
                "title": stmt.excluded.title,
                "category": stmt.excluded.category,
                "description": stmt.excluded.description,
                "updated_at": now,
            },
        )
        db.execute(stmt)
        count += 1
    db.commit()
    return count
