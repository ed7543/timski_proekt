import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from google.genai import errors as genai_errors
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from backend.database.models import Course, CourseMaterial, CourseNote, CoursePurchase, Lesson, Recording, User
from backend.database.session import get_db
from backend.middleware.auth import get_current_paying_user, get_current_user, get_current_user_optional
from backend.middleware.rate_limit import limiter
from backend.models.courseNoteRequest import CourseNoteCreate
from backend.models.courseResponse import (
    AdminCourseOut,
    CourseDetailOut,
    CourseMaterialOut,
    CourseNoteOut,
    CourseOut,
    LessonDetailOut,
    LessonOut,
    MaterialStudyGuideOut,
    RecordingOut,
)
from backend.models.courseSubmitRequest import CourseSubmitRequest
from backend.services import material_study_guide
from backend.services.ingestion import gemini_generator
from backend.utils.slugify import slugify
from backend.utils.time import utcnow

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _unique_slug(db: Session, name: str, requested: Optional[str]) -> str:
    """Slugs are generated from the course name so submitters never have to
    think about URLs - if `requested` is given (currently unused by the
    frontend form) it's respected as-is instead. Falls back to "-2", "-3"...
    on collision, and to the literal string "course" if the name has no
    sluggable characters at all (e.g. a name that's pure punctuation)."""
    if requested:
        return requested
    base = slugify(name) or "course"
    candidate = base
    suffix = 2
    while db.query(Course).filter(Course.slug == candidate).first() is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _can_view_unapproved(course: Course, viewer: Optional[User]) -> bool:
    """A pending/rejected course is only visible to the person who submitted
    it (so they can see its status/rejection reason) or an admin - everyone
    else gets a 404, same as if it didn't exist."""
    if viewer is None:
        return False
    return viewer.role == "admin" or viewer.id == course.submitted_by_id


def _get_visible_course_or_404(db: Session, course_id: int, viewer: Optional[User]) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.status != "approved" and not _can_view_unapproved(course, viewer):
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _has_course_access(db: Session, course: Course, viewer: Optional[User]) -> bool:
    """Whether `viewer` can see this course's materials/recordings. Free
    courses (price_cents == 0) are open to anyone. Priced courses require
    being the submitter, an admin, or having a CoursePurchase row (see
    routes/billingRoute.py, which creates one on a successful Stripe
    checkout)."""
    if course.price_cents <= 0:
        return True
    if viewer is None:
        return False
    if viewer.role == "admin" or viewer.id == course.submitted_by_id:
        return True
    return (
        db.query(CoursePurchase)
        .filter(CoursePurchase.user_id == viewer.id, CoursePurchase.course_id == course.id)
        .first()
        is not None
    )


def _get_course_or_404(db: Session, course_id: int) -> Course:
    """Bare existence check (no pending/rejected visibility gating) - used by
    the public, no-auth lesson endpoints below. Lessons only ever exist for
    ingested official-catalog courses (see Lesson's docstring in
    database/models.py), so the stricter submitter/admin visibility rules in
    _get_visible_course_or_404 don't apply here."""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _get_note_or_404(db: Session, course_id: int, note_id: int) -> CourseNote:
    note = (
        db.query(CourseNote)
        .filter(CourseNote.id == note_id, CourseNote.course_id == course_id)
        .first()
    )
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


def _get_lesson_or_404(db: Session, course_id: int, lesson_id: int) -> Lesson:
    lesson = (
        db.query(Lesson)
        .filter(Lesson.id == lesson_id, Lesson.course_id == course_id)
        .first()
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


def _lesson_detail_out(lesson: Lesson) -> LessonDetailOut:
    return LessonDetailOut(
        id=lesson.id,
        course_id=lesson.course_id,
        order_index=lesson.order_index,
        topic_title=lesson.topic_title,
        has_documentation=bool(lesson.documentation),
        has_quiz=bool(lesson.quiz),
        has_quiz_hard=bool(lesson.quiz_hard),
        generation_method=lesson.generation_method,
        documentation=lesson.documentation,
        quiz=lesson.quiz,
        quiz_hard=lesson.quiz_hard,
    )


def _get_material_or_404(db: Session, course_id: int, material_id: int) -> CourseMaterial:
    material = (
        db.query(CourseMaterial)
        .filter(CourseMaterial.id == material_id, CourseMaterial.course_id == course_id)
        .first()
    )
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    return material


def _material_study_guide_out(material: CourseMaterial) -> MaterialStudyGuideOut:
    return MaterialStudyGuideOut(
        material_id=material.id,
        has_documentation=bool(material.documentation),
        has_quiz=bool(material.quiz),
        has_quiz_hard=bool(material.quiz_hard),
        documentation=material.documentation,
        quiz=material.quiz,
        quiz_hard=material.quiz_hard,
    )


@router.get("", response_model=list[CourseOut])
async def list_courses(
    semester: Optional[str] = Query(None, description="Filter by semester, e.g. 'semester-1'"),
    search: Optional[str] = Query(None, description="Filter by course name substring"),
    source: str = Query(
        "official",
        description=(
            "'official' (default) = scraped FINKI catalog (submitted_by_id is null); "
            "'community' = approved user-submitted courses; 'all' = both"
        ),
    ),
    price_filter: Optional[str] = Query(
        None,
        description=(
            "'free' = only price_cents == 0 courses; 'purchased' = only priced "
            "courses the current viewer already has access to (submitted by "
            "them, or bought - see CoursePurchase). 'purchased' requires being "
            "logged in. Omit for no price filtering."
        ),
    ),
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    """List courses. Read-only (though price_filter="purchased" needs a
    logged-in viewer). Only status="approved" courses are shown here -
    pending/rejected submissions stay invisible until an admin approves them
    (see routes/adminRoute.py). `source` keeps the scraped FINKI catalog and
    user-submitted "community" courses in separate tabs on the frontend
    rather than mixed into one list. Priced community courses still show up
    here (with their price_cents) - only the materials/recordings underneath
    are locked, see _has_course_access. `price_filter` powers the Marketplace
    page's "Free" / "My purchases" filter buttons."""
    q = db.query(Course).filter(Course.status == "approved")
    if source == "official":
        q = q.filter(Course.submitted_by_id.is_(None))
    elif source == "community":
        q = q.filter(Course.submitted_by_id.isnot(None))
    elif source != "all":
        raise HTTPException(status_code=400, detail="source must be one of: official, community, all")
    if semester:
        q = q.filter(Course.semester == semester)
    if search:
        q = q.filter(Course.name.ilike(f"%{search}%"))
    if price_filter == "free":
        q = q.filter(Course.price_cents == 0)
    elif price_filter == "purchased":
        if viewer is None:
            raise HTTPException(status_code=401, detail="Log in to filter by your purchased courses")
        if viewer.role == "admin":
            q = q.filter(Course.price_cents > 0)
        else:
            owned_course_ids = db.query(CoursePurchase.course_id).filter(CoursePurchase.user_id == viewer.id)
            q = q.filter(Course.price_cents > 0).filter(
                or_(Course.submitted_by_id == viewer.id, Course.id.in_(owned_course_ids))
            )
    elif price_filter is not None:
        raise HTTPException(status_code=400, detail="price_filter must be one of: free, purchased")
    courses = q.order_by(Course.semester, Course.name).all()
    return [CourseOut.model_validate(c) for c in courses]


@router.get("/mine", response_model=list[AdminCourseOut])
async def list_my_courses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every course the current user has ever submitted, regardless of
    status - so they can track pending/approved/rejected and see the
    admin's reason if rejected (there's nowhere else in the app that
    surfaces rejection_reason - this "My courses" page is it). Reuses
    AdminCourseOut since the shape (status/rejection_reason/materials) is
    identical to what the admin queue already returns."""
    courses = (
        db.query(Course)
        .filter(Course.submitted_by_id == current_user.id)
        .order_by(Course.created_at.desc())
        .all()
    )
    return [AdminCourseOut.model_validate(c) for c in courses]


@router.delete("/{course_id}", status_code=204)
async def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permanently deletes a user-submitted course (any status), along with
    its materials and purchase records (cascade="all, delete-orphan" on
    Course.materials/Course.purchases - see database/models.py). No undo.
    Allowed for the course's own submitter (a professor cleaning up their
    own Marketplace listing) or an admin (moderation) - anyone else gets
    403. Refuses to touch the scraped FINKI catalog (submitted_by_id is
    null) regardless of who's asking - that's not this endpoint's job."""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.submitted_by_id is None:
        raise HTTPException(status_code=400, detail="Cannot delete official catalog courses here")
    is_owner = course.submitted_by_id == current_user.id
    if not is_owner and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the course's submitter or an admin can delete it")
    db.delete(course)
    db.commit()


@router.post("/submit", response_model=CourseDetailOut, status_code=201)
async def submit_course(
    payload: CourseSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_paying_user),
):
    """A paying user (is_premium, any role) proposes a new course, with its
    materials attached in the same request, and can optionally set a price
    for students (payload.price in euros, 0 = free). Course + materials are
    created together with status="pending" and are invisible to everyone
    except the submitter/an admin (see _can_view_unapproved) until an admin
    approves it via POST /api/admin/courses/{id}/approve. Note that the
    is_premium subscription (gating this endpoint) and the course's own
    price are deliberately separate: subscribing lets you submit courses at
    all; the price is what students pay to unlock this specific course's
    materials once it's approved.

    NOTE: materials can be either a pasted link or a file uploaded via
    POST /api/courses/upload-material (Supabase Storage-backed - see that route)."""
    slug = _unique_slug(db, payload.name, payload.slug)

    course = Course(
        slug=slug,
        name=payload.name,
        code=payload.code,
        semester=payload.semester,
        description=payload.description,
        source_url=payload.source_url,
        status="pending",
        submitted_by_id=current_user.id,
        price_cents=round(payload.price * 100),
    )
    db.add(course)
    db.flush()  # assigns course.id without ending the transaction, so materials below can reference it

    for m in payload.materials:
        db.add(CourseMaterial(
            course_id=course.id,
            title=m.title,
            url=m.url,
            category=m.category,
            description=m.description,
        ))

    db.commit()
    db.refresh(course)
    return CourseDetailOut(
        id=course.id,
        slug=course.slug,
        name=course.name,
        code=course.code,
        semester=course.semester,
        source_url=course.source_url,
        created_at=course.created_at,
        updated_at=course.updated_at,
        last_scraped_at=course.last_scraped_at,
        description=course.description,
        price_cents=course.price_cents,
        material_count=len(payload.materials),
        recording_count=0,
        locked=False,
        submitted_by_name=current_user.full_name or current_user.email,
    )


@router.get("/{course_id}", response_model=CourseDetailOut)
async def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    """Course metadata is always visible once approved, regardless of price -
    it's the "product page" (name/description/price/counts). The `locked`
    field tells the frontend whether GET .../materials and .../recordings
    will actually return content or a 402, so it can show a Buy button
    instead of an empty list."""
    course = _get_visible_course_or_404(db, course_id, viewer)
    material_count = db.query(func.count(CourseMaterial.id)).filter(
        CourseMaterial.course_id == course.id
    ).scalar()
    recording_count = db.query(func.count(Recording.id)).filter(
        Recording.course_id == course.id
    ).scalar()
    return CourseDetailOut(
        id=course.id,
        slug=course.slug,
        name=course.name,
        code=course.code,
        semester=course.semester,
        source_url=course.source_url,
        created_at=course.created_at,
        updated_at=course.updated_at,
        last_scraped_at=course.last_scraped_at,
        description=course.description,
        price_cents=course.price_cents,
        material_count=material_count or 0,
        recording_count=recording_count or 0,
        locked=not _has_course_access(db, course, viewer),
        submitted_by_name=course.submitted_by_name,
    )


@router.get("/{course_id}/materials", response_model=list[CourseMaterialOut])
async def list_course_materials(
    course_id: int,
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    course = _get_visible_course_or_404(db, course_id, viewer)
    if not _has_course_access(db, course, viewer):
        raise HTTPException(status_code=402, detail="This course's materials are locked - purchase required")
    materials = (
        db.query(CourseMaterial)
        .filter(CourseMaterial.course_id == course_id)
        .order_by(CourseMaterial.category, CourseMaterial.title)
        .all()
    )
    return [CourseMaterialOut.model_validate(m) for m in materials]


@router.get("/{course_id}/recordings", response_model=list[RecordingOut])
async def list_course_recordings(
    course_id: int,
    category: Optional[str] = Query(None, description="Filter by category, e.g. 'Предавања'"),
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    course = _get_visible_course_or_404(db, course_id, viewer)
    if not _has_course_access(db, course, viewer):
        raise HTTPException(status_code=402, detail="This course's recordings are locked - purchase required")
    q = db.query(Recording).filter(Recording.course_id == course_id)
    if category:
        q = q.filter(Recording.category == category)
    recordings = q.order_by(Recording.year, Recording.category, Recording.topic).all()
    return [RecordingOut.model_validate(r) for r in recordings]


@router.get("/{course_id}/notes", response_model=list[CourseNoteOut])
async def list_course_notes(
    course_id: int,
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    """Community-contributed study notes - unlike materials/recordings above,
    these are never gated by _has_course_access: even a priced course's
    notes stay free to view, since they're contributed by students
    themselves, not part of what the course's submitter is selling. Still
    hidden for a pending/rejected course the viewer isn't allowed to see,
    same as the course itself (_get_visible_course_or_404)."""
    course = _get_visible_course_or_404(db, course_id, viewer)
    notes = (
        db.query(CourseNote)
        .options(joinedload(CourseNote.uploaded_by_user))  # avoids one lazy-load per note for uploaded_by_name
        .filter(CourseNote.course_id == course.id)
        .order_by(CourseNote.created_at.desc())
        .all()
    )
    return [CourseNoteOut.model_validate(n) for n in notes]


@router.post("/{course_id}/notes", response_model=CourseNoteOut, status_code=201)
async def add_course_note(
    course_id: int,
    payload: CourseNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Any logged-in user can attach a study note - a file uploaded via
    POST /api/courses/upload-material or a pasted external link - to any
    course they can see. Deliberately NOT gated by get_current_paying_user
    (unlike submit_course): contributing a note is a free community action,
    not the premium "submit a whole course" workflow."""
    course = _get_visible_course_or_404(db, course_id, current_user)
    note = CourseNote(
        course_id=course.id,
        uploaded_by_id=current_user.id,
        title=payload.title,
        url=payload.url,
        description=payload.description,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return CourseNoteOut.model_validate(note)


@router.delete("/{course_id}/notes/{note_id}", status_code=204)
async def delete_course_note(
    course_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The note's own uploader or an admin can remove it - same permission
    shape as delete_course above. No other user can touch someone else's
    note. Checks course visibility first (_get_visible_course_or_404), same
    as list_course_notes/add_course_note - if a course becomes invisible to
    this viewer (e.g. rejected after the note was added), the note becomes
    untouchable through this endpoint too, not just unlisted."""
    _get_visible_course_or_404(db, course_id, current_user)
    note = _get_note_or_404(db, course_id, note_id)
    if note.uploaded_by_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the note's uploader or an admin can delete it")
    db.delete(note)
    db.commit()


@router.get("/{course_id}/lessons", response_model=list[LessonOut])
async def list_course_lessons(course_id: int, db: Session = Depends(get_db)):
    """Lightweight lesson list for the course page (topic titles + whether each
    already has documentation/a quiz) - read-only, no auth needed, same as
    materials/recordings above."""
    _get_course_or_404(db, course_id)
    lessons = (
        db.query(Lesson)
        .filter(Lesson.course_id == course_id)
        .order_by(Lesson.order_index)
        .all()
    )
    return [
        LessonOut(
            id=l.id,
            course_id=l.course_id,
            order_index=l.order_index,
            topic_title=l.topic_title,
            has_documentation=bool(l.documentation),
            has_quiz=bool(l.quiz),
            has_quiz_hard=bool(l.quiz_hard),
            generation_method=l.generation_method,
        )
        for l in lessons
    ]


@router.get("/{course_id}/lessons/{lesson_id}", response_model=LessonDetailOut)
async def get_course_lesson(course_id: int, lesson_id: int, db: Session = Depends(get_db)):
    """Full lesson content (documentation + quiz, if generated) - fetched when
    a student opens one specific lesson."""
    _get_course_or_404(db, course_id)
    lesson = _get_lesson_or_404(db, course_id, lesson_id)
    return _lesson_detail_out(lesson)


@router.post("/{course_id}/lessons/{lesson_id}/quiz", response_model=LessonDetailOut)
@limiter.limit("5/minute")
async def generate_lesson_quiz(
    request: Request,
    course_id: int,
    lesson_id: int,
    difficulty: str = Query("medium", description="'medium' or 'hard' - which quiz tier to (re)generate"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generates (or regenerates) the quiz for one lesson on demand, via the
    same Gemini call used by the offline ingestion pipeline
    (gemini_generator.generate_quiz), based on the lesson's already-generated
    documentation. Unlike the read-only GETs above, this requires auth - it
    triggers a real, billed Gemini API call, so it shouldn't be reachable
    anonymously. Also rate-limited (5/minute per IP, same as the auth
    endpoints) since it's a real cost per call, not just an abuse-prevention
    measure. 400s if the lesson has no documentation yet (nothing to base
    a quiz on).

    `difficulty="medium"` (default) writes to the original `quiz` column -
    same behaviour as before this parameter existed, so a bulk-generated
    Medium quiz (from the offline ingestion pipeline) is never touched by
    this unless a student explicitly regenerates it. `difficulty="hard"`
    writes to the separate `quiz_hard` column instead, leaving `quiz`
    untouched - the two tiers are independent, one Gemini call each."""
    if difficulty not in ("medium", "hard"):
        raise HTTPException(status_code=400, detail="difficulty must be 'medium' or 'hard'")
    _get_course_or_404(db, course_id)
    lesson = _get_lesson_or_404(db, course_id, lesson_id)
    if not lesson.documentation:
        raise HTTPException(
            status_code=400,
            detail="This lesson doesn't have generated documentation yet - a quiz can't be generated.",
        )
    try:
        quiz = gemini_generator.generate_quiz(lesson.topic_title, lesson.documentation, difficulty=difficulty)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except genai_errors.APIError:
        raise HTTPException(
            status_code=502,
            detail="Quiz generation failed (Gemini API error) - please try again.",
        )
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="Quiz generation returned an unexpected response - please try again.",
        )
    if difficulty == "hard":
        lesson.quiz_hard = quiz
        lesson.quiz_hard_generated_at = utcnow()
    else:
        lesson.quiz = quiz
        lesson.quiz_generated_at = utcnow()
    db.commit()
    db.refresh(lesson)
    return _lesson_detail_out(lesson)


@router.get("/{course_id}/materials/{material_id}/study-guide", response_model=MaterialStudyGuideOut)
async def get_material_study_guide(
    course_id: int,
    material_id: int,
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    """Marketplace equivalent of get_course_lesson - same locked/purchase
    gating as GET .../materials, since the study guide is derived from the
    material's own content - showing it would leak a priced course's
    materials just as much as the raw file would."""
    course = _get_visible_course_or_404(db, course_id, viewer)
    if not _has_course_access(db, course, viewer):
        raise HTTPException(status_code=402, detail="This course's materials are locked - purchase required")
    material = _get_material_or_404(db, course_id, material_id)
    return _material_study_guide_out(material)


@router.post("/{course_id}/materials/{material_id}/study-guide", response_model=MaterialStudyGuideOut)
@limiter.limit("5/minute")
async def generate_material_study_guide(
    request: Request,
    course_id: int,
    material_id: int,
    difficulty: str = Query("medium", description="'medium' or 'hard' - which quiz tier to (re)generate"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generates (once per tier) an AI study guide + quiz for a single
    Marketplace material, extracting text directly from the material's own
    URL (see services/material_study_guide.py) rather than a curated
    textbook source - the Marketplace equivalent of generate_lesson_quiz,
    reusing the exact same gemini_generator.generate_quiz(difficulty=...)
    and Medium/Hard column split (quiz / quiz_hard), just on CourseMaterial
    instead of Lesson.

    Any logged-in user may trigger this (not gated to the submitter/admin/
    premium) - but each tier is idempotent: if this material already has a
    cached quiz for the requested difficulty, that tier is returned
    immediately with no new Gemini call (documentation is generated once,
    shared by both tiers). Also rate-limited (5/minute per IP, same as the
    lessons quiz endpoint) as a baseline abuse guard."""
    if difficulty not in ("medium", "hard"):
        raise HTTPException(status_code=400, detail="difficulty must be 'medium' or 'hard'")
    course = _get_visible_course_or_404(db, course_id, current_user)
    if not _has_course_access(db, course, current_user):
        raise HTTPException(status_code=402, detail="This course's materials are locked - purchase required")
    material = _get_material_or_404(db, course_id, material_id)

    existing_quiz = material.quiz_hard if difficulty == "hard" else material.quiz
    if material.documentation and existing_quiz:
        return _material_study_guide_out(material)

    if not material_study_guide.is_generatable_category(material.category):
        raise HTTPException(
            status_code=400,
            detail="A study guide can't be generated for video materials - there's no text to work from.",
        )

    if not material.documentation:
        try:
            excerpt = material_study_guide.extract_material_text(material.url)
        except material_study_guide.UnsupportedMaterialError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=502, detail="Couldn't fetch this material's content - please try again.")

        try:
            documentation = gemini_generator.generate_documentation(
                course_name_mk=course.name,
                lesson_title=material.title,
                source_excerpt=excerpt,
                source_title=material.title,
                source_author=course.submitted_by_name or "",
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        except genai_errors.APIError:
            raise HTTPException(
                status_code=502,
                detail="Study guide generation failed (Gemini API error) - please try again.",
            )
        material.documentation = documentation
        material.documentation_generated_at = utcnow()

    try:
        quiz = gemini_generator.generate_quiz(material.title, material.documentation, difficulty=difficulty)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except genai_errors.APIError:
        raise HTTPException(
            status_code=502,
            detail="Quiz generation failed (Gemini API error) - please try again.",
        )
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="Quiz generation returned an unexpected response - please try again.",
        )

    if difficulty == "hard":
        material.quiz_hard = quiz
        material.quiz_hard_generated_at = utcnow()
    else:
        material.quiz = quiz
        material.quiz_generated_at = utcnow()
    db.commit()
    db.refresh(material)
    return _material_study_guide_out(material)
