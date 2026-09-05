"""Loads courses_db.json - the curated lesson-topic/source list this whole
lesson-content pipeline is driven by. Lives OUTSIDE this repo (in the team's
shared Downloads folder as of this writing), so its path is always passed in
explicitly (--courses-db-path), never hardcoded.
"""
import json
from pathlib import Path
from typing import Any, Dict, List

# Courses in either of these two statuses have no usable source yet - handled
# as "topic titles only, no generation" by seed_lessons.py.
NO_SOURCE_STATUSES = ("deferred_user_will_provide_materials", "pending_source")

# Courses whose source.url is None - the source exists only as a file the
# user holds locally (not yet wired into this pipeline - see chat: Оперативни
# системи / КМиБ / Е-трговија / Шаблони / Вовед во науката за податоци).
# Excluded from generation for now; NOT auto-detected by seed_lessons.py so
# this list stays an explicit, reviewed decision rather than silently
# skipping anything with url=None (a future course could legitimately have a
# different reason for that).
LOCAL_FILE_ONLY_CODES = {
    "F23L2W014",  # Компјутерски мрежи и безбедност (KMiB Skripta)
    "F23L2W167",  # Шаблони за дизајн на кориснички интерфејси
    "F23L2S017",  # Оперативни системи (tHe OSkripta)
    "F23L3W008",  # Вовед во науката за податоци
    "F23L3S025",  # Електронска и мобилна трговија (E-Commerce 2023, 17th ed.)
}


def load_courses(courses_db_path: Path) -> List[Dict[str, Any]]:
    data = json.loads(courses_db_path.read_text(encoding="utf-8"))
    return data["courses"]


def get_courses_by_codes(courses: List[Dict[str, Any]], course_codes: List[str]) -> List[Dict[str, Any]]:
    by_code = {c["course_code"]: c for c in courses}
    missing = [code for code in course_codes if code not in by_code]
    if missing:
        raise ValueError(f"course_code(s) not found in courses_db.json: {missing}")
    return [by_code[code] for code in course_codes]


def has_fetchable_source(course: Dict[str, Any]) -> bool:
    """True if this course has a source with a real URL seed_lessons.py can
    fetch from. False for the 12 no-source courses AND the 5 local-file-only
    ones (see LOCAL_FILE_ONLY_CODES)."""
    if course.get("status") in NO_SOURCE_STATUSES:
        return False
    if course["course_code"] in LOCAL_FILE_ONLY_CODES:
        return False
    source = course.get("source")
    return bool(source and source.get("url"))
