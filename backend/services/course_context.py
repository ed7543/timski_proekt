"""Builds a course-context block for the AI tutor prompts, the same
"build a context string, inject it into the prompt" shape as
backend.web_search.search.format_search_context - a second, composable source
of context alongside live web search results.

NOTE: Course.description is a synthesized metadata blurb (code, semester,
credits, professors, prerequisite, tags), not a real syllabus - FINKI doesn't
publish full syllabi anywhere public (see backend/services/ingestion/
predmeti_scraper.py docstring). The recording topics list and materials list
below are the closest thing to real course content this data source can
offer, since they reflect actual lecture titles and linked resources rather
than official curriculum text.
"""
from typing import Optional

from backend.database.models import Course


def format_course_context(course: Optional[Course]) -> str:
    """Format a Course (with its metadata, recording topics, and materials)
    into a context block for the AI. Returns "" if no course was given."""
    if not course:
        return ""

    lines = [f"## Course Context: {course.name}\n"]
    if course.code:
        lines.append(f"Course code: {course.code}")
    if course.semester:
        lines.append(f"Semester: {course.semester}")
    if course.description:
        lines.append(f"\n{course.description}")

    # Recording topics double as a lecture/topic outline for the course - the
    # closest thing to a syllabus this data source can offer.
    topics = sorted({r.topic for r in course.recordings if r.category and "предавањ" in r.category.lower()})
    if not topics:
        topics = sorted({r.topic for r in course.recordings})
    if topics:
        lines.append("\nTopics covered in lectures/recordings for this course:")
        for topic in topics[:40]:
            lines.append(f"- {topic}")

    # Supplementary materials (exercise solutions, example exam problems,
    # notes, external repos) - real, already-ingested data that wasn't being
    # surfaced to the AI at all before. Include the URL so the tutor can
    # actually point the student at it, same as it does for web search hits.
    if course.materials:
        lines.append("\nAdditional materials for this course:")
        for m in course.materials[:20]:
            label = f"- {m.title}"
            if m.category:
                label += f" ({m.category})"
            label += f": {m.url}"
            lines.append(label)

    if course.source_url:
        lines.append(f"\nSource: {course.source_url}")

    return "\n".join(lines)
