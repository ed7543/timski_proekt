"""Scraper for predmeti.finki-hub.com (course/accreditation metadata).

predmeti.finki-hub.com is a client-rendered React SPA - fetching its HTML only
gets you the empty shell (`<div id="root">`), the real data is loaded client-side
from a public static JSON asset that the site's own source
(github.com/finki-hub/courses-listing, see src/data/use-courses.ts) fetches
directly:

    https://assets.finki-hub.com/courses.json

We fetch that same asset (a single request) instead of rendering/scraping the
SPA - it's the actual source of truth the site itself uses, and is far cheaper.

IMPORTANT gap: this dataset is course *metadata* (name, code, semester,
credits, professors, assistants, prerequisite, study-program applicability,
enrollment history, tags) - it does NOT include an actual syllabus/curriculum
description. Real FINKI syllabi live behind the login-gated
courses.finki.ukim.mk Moodle, which is explicitly out of scope. So
`Course.description` here is a synthesized metadata blurb, not a real
syllabus - see format_course_context()/README notes in the final report.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.services.ingestion.finki_hub_client import FinkiHubClient

logger = logging.getLogger(__name__)

COURSES_JSON_URL = "https://assets.finki-hub.com/courses.json"

# Accreditations to prefer, newest first - a course may have data for either or both.
_ACCREDITATIONS = ("2023", "2018")


@dataclass
class PredmetiCourse:
    name: str
    code: Optional[str]
    semester: Optional[str]  # normalized to "semester-N"
    professors: Optional[str]
    assistants: Optional[str]
    prerequisite: Optional[str]
    credits: Optional[str]
    tags: Optional[str]

    def to_description(self) -> str:
        """Build a short human-readable metadata blurb to use as the stand-in
        `description` (see module docstring - no real syllabus is available from
        this source)."""
        lines = []
        if self.code:
            lines.append(f"Код на предмет: {self.code}")
        if self.semester:
            lines.append(f"Семестар: {self.semester.replace('semester-', '')}")
        if self.credits:
            lines.append(f"Кредити (ЕКТС): {self.credits}")
        if self.professors:
            profs = ", ".join(p.strip() for p in self.professors.split("\n") if p.strip())
            lines.append(f"Наставници: {profs}")
        if self.assistants:
            assts = ", ".join(a.strip() for a in self.assistants.split("\n") if a.strip())
            lines.append(f"Асистенти: {assts}")
        if self.prerequisite:
            lines.append(f"Предуслов: {self.prerequisite}")
        if self.tags:
            lines.append(f"Ознаки: {self.tags}")
        return "\n".join(lines)


def _get_field(raw: Dict[str, Any], accreditation: str, field: str) -> Optional[str]:
    value = raw.get(f"{accreditation}-{field}")
    return value if value else None


def _normalize_semester(raw_semester: Optional[str]) -> Optional[str]:
    if not raw_semester:
        return None
    raw_semester = raw_semester.strip()
    if not raw_semester.isdigit():
        return None
    return f"semester-{raw_semester}"


def _parse_record(raw: Dict[str, Any]) -> Optional[PredmetiCourse]:
    name = raw.get("name")
    if not name:
        return None

    code = None
    semester = None
    for accreditation in _ACCREDITATIONS:
        if raw.get(f"{accreditation}-available") == "TRUE":
            code = code or _get_field(raw, accreditation, "code")
            semester = semester or _normalize_semester(_get_field(raw, accreditation, "semester"))

    credits = None
    for accreditation in _ACCREDITATIONS:
        credits = credits or _get_field(raw, accreditation, "credits")

    prerequisite = None
    for accreditation in _ACCREDITATIONS:
        prerequisite = prerequisite or _get_field(raw, accreditation, "prerequisite")

    return PredmetiCourse(
        name=name,
        code=code,
        semester=semester,
        professors=raw.get("professors") or None,
        assistants=raw.get("assistants") or None,
        prerequisite=prerequisite,
        credits=credits,
        tags=raw.get("tags") or None,
    )


async def fetch_predmeti_courses(client: FinkiHubClient) -> List[PredmetiCourse]:
    """Fetch and parse the full public courses.json asset (a single HTTP request)."""
    data = await client.get_json(COURSES_JSON_URL)
    if not data:
        logger.warning("Could not fetch %s", COURSES_JSON_URL)
        return []

    courses: List[PredmetiCourse] = []
    for raw in data:
        parsed = _parse_record(raw)
        if parsed:
            courses.append(parsed)
    return courses
