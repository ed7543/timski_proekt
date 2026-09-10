from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base
from backend.utils.time import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="student", nullable=False)  # "student" | "admin"
    # True once a Stripe checkout for the "submit courses" subscription has
    # completed (see routes/billingRoute.py). Any user with is_premium=True
    # (of any role) can submit a course for admin review - this is
    # deliberately independent of `role`, which is about platform
    # permissions, not billing status.
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Set from the Stripe Checkout session's `customer`/`subscription` ids
    # when the submission-subscription webhook fires (see
    # routes/billingRoute.py::_handle_submission_subscription). Needed so
    # POST /api/billing/cancel knows which Stripe subscription to actually
    # cancel - null until the user has subscribed at least once.
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    verification_tokens: Mapped[list["VerificationToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    quiz_attempts: Mapped[list["QuizAttempt"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class VerificationToken(Base):
    __tablename__ = "verification_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)  # "verify_email" | "reset_password"
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="verification_tokens")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New conversation")
    subject: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )
    members: Mapped[list["ConversationMember"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    invites: Mapped[list["ConversationInvite"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Who typed this "user"-role message, for a group conversation with more
    # than one member - null for every "assistant"-role message, and null for
    # historical "user"-role messages saved before this column existed
    # (there's no way to backfill who typed something in the past; the
    # frontend simply omits the sender label when this is null). Every NEW
    # "user"-role message must set this (see chat_service.py::save_user_message) -
    # it's nullable at the schema level only for the historical/assistant cases.
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    author: Mapped["User | None"] = relationship()

    @property
    def author_name(self) -> str | None:
        """None for assistant messages and historical user messages with no
        author_user_id - same pattern as Course.submitted_by_name."""
        if self.author is None:
            return None
        return self.author.full_name or self.author.email


class ConversationMember(Base):
    """A non-owner participant in a group conversation (up to 2 more, for a
    3-person cap total including the owner). The owner is deliberately NOT
    given a row here - membership is checked as
    `conv.user_id == user.id OR a ConversationMember row exists`
    (see routes/conversationRoute.py::_get_member_conversation), so there's
    exactly one source of truth for "is this person the owner"
    (Conversation.user_id) and no risk of the owner being removed from their
    own conversation via the member-removal endpoint."""

    __tablename__ = "conversation_members"
    __table_args__ = (UniqueConstraint("conversation_id", "user_id", name="uq_conversation_members_conv_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()


class ConversationInvite(Base):
    """A shareable join link for a conversation. Multi-use until the
    conversation hits its 3-member cap (owner + 2) or the invite expires/is
    revoked - simpler than a single-use-per-invitee token for a small group."""

    __tablename__ = "conversation_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="invites")


class CachedSearch(Base):
    """A cached Tavily search result, shared across all users/conversations (not owned
    by anyone) so a repeated or near-duplicate question can be answered without another
    live API call. Matched on a normalized query, exact first then pg_trgm similarity."""

    __tablename__ = "cached_searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    normalized_query: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    raw_query: Mapped[str] = mapped_column(String(500), nullable=False)
    results: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Course(Base):
    """A FINKI course/subject, ingested from the public finki-hub.com community
    sites (predmeti.finki-hub.com / snimki.finki-hub.com). Not user-owned - shared
    read-only catalog data used to give the AI tutor course-specific context."""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    semester: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)  # e.g. "semester-1"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Moderation workflow: courses ingested by the scraper pipeline are
    # auto-approved (status defaults to "approved"); courses submitted by a
    # professor through the API start as "pending" and are hidden from the
    # public catalog (see courseRoute.list_courses) until an admin approves
    # or rejects them (see routes/adminRoute.py).
    status: Mapped[str] = mapped_column(String(20), default="approved", nullable=False)  # "pending" | "approved" | "rejected"
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 0 = free. Set by the submitter (see CourseSubmitRequest.price). Only
    # meaningful for user-submitted (submitted_by_id is not null) courses -
    # scraped FINKI courses stay 0/free. Stored in cents (int) rather than a
    # float to avoid rounding issues, same convention Stripe itself uses for
    # amounts. When > 0, materials/recordings are locked behind a
    # CoursePurchase (see routes/courseRoute.py::_has_course_access) unless
    # the viewer is the submitter or an admin.
    price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    materials: Mapped[list["CourseMaterial"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    recordings: Mapped[list["Recording"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    lessons: Mapped[list["Lesson"]] = relationship(
        back_populates="course", cascade="all, delete-orphan", order_by="Lesson.order_index"
    )
    sources: Mapped[list["CourseSource"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    purchases: Mapped[list["CoursePurchase"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    notes: Mapped[list["CourseNote"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    # Who submitted this course (None for the scraped FINKI catalog).
    # foreign_keys needed since there are two FKs to users.id on this table
    # (submitted_by_id and reviewed_by_id) - otherwise SQLAlchemy can't tell
    # which one this relationship should join on.
    submitted_by_user: Mapped["User | None"] = relationship(foreign_keys=[submitted_by_id], viewonly=True)

    @property
    def submitted_by_name(self) -> str | None:
        """Display name for whoever submitted this course (None for the
        scraped FINKI catalog, and for user-submitted courses if somehow the
        submitting account no longer exists). Read by CourseOut/
        CourseDetailOut/AdminCourseOut via from_attributes - not a real
        column, just a convenience computed from submitted_by_user."""
        user = self.submitted_by_user
        if user is None:
            return None
        return user.full_name or user.email


class CourseMaterial(Base):
    """A non-recording resource for a course (e.g. "Дополнителна содржина"/"Белешки"
    entries from snimki.finki-hub.com - source code repos, external exercise sites,
    notes) - anything that isn't itself a lecture recording."""

    __tablename__ = "course_materials"
    __table_args__ = (UniqueConstraint("course_id", "url", name="uq_course_materials_course_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Marketplace-only AI study guide - mirrors Lesson's documentation/quiz/
    # quiz_hard split exactly (migration 9d4c1a2f7e6b), generated on demand
    # from the material's own URL (services/material_study_guide.py) rather
    # than a curated textbook source. `quiz` is the default/"Medium" tier,
    # `quiz_hard` a second, independent tier - both share
    # gemini_generator.generate_quiz(difficulty=...), same as Lessons.
    documentation: Mapped[str | None] = mapped_column(Text, nullable=True)
    quiz: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    quiz_hard: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    documentation_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quiz_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quiz_hard_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    course: Mapped["Course"] = relationship(back_populates="materials")


class Recording(Base):
    """A lecture/exercise recording link for a course, scraped from
    snimki.finki-hub.com (e.g. under "Предавања" / "Аудиториски вежби" groups
    such as "Стефан Андонов, 2021")."""

    __tablename__ = "recordings"
    __table_args__ = (
        UniqueConstraint("course_id", "video_url", "topic", name="uq_recordings_course_url_topic"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    presenter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="предавања")
    video_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_page_url: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    course: Mapped["Course"] = relationship(back_populates="recordings")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    answered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="quiz_attempts")


class Lesson(Base):
    """A curriculum topic within a course, sourced from courses_db.json / the
    "LearnWise - база извори" spreadsheet (a curated, license-checked open
    textbook per course) - NOT the same thing as Recording, which is a scraped
    lecture-video link. Holds the Gemini-generated documentation + quiz for the
    topic (backend/services/ingestion/gemini_generator.py). Regeneration
    overwrites documentation/quiz in place - no version history is kept.

    Deliberately FKs into the existing `courses` table (all 67 FINKI courses
    already exist there, ingested from finki-hub.com) rather than introducing a
    second, parallel "course" concept."""

    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    topic_title: Mapped[str] = mapped_column(Text, nullable=False)
    documentation: Mapped[str | None] = mapped_column(Text, nullable=True)
    quiz: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Second, independent difficulty tier - see migration f7a2c9d14e6b. `quiz`
    # above is the original/default tier (displayed as "Medium"); this one is
    # generated separately, on demand, only when a student asks for Hard.
    quiz_hard: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Tracks how `documentation` was produced: "source" (default - grounded
    # in a real courses_db.json textbook/material excerpt, see
    # gemini_generator.generate_documentation) or "general_knowledge" (the
    # model's own general knowledge, no source excerpt at all - see
    # generate_no_source_documentation, only reachable via seed_lessons.py's
    # explicit --generate-without-source / --force-general-knowledge flags).
    # Added (migration d8f3a1c9b274) so this distinction is queryable/exposed
    # over the API - not just a markdown disclaimer sentence inside
    # `documentation` itself, which a future edit could drop unnoticed.
    # Existing rows and any not-yet-generated topic-only row default to
    # "source" - see lesson_upsert.upsert_lesson for when this actually gets
    # (re)written.
    generation_method: Mapped[str] = mapped_column(String(20), nullable=False, default="source", server_default="source")
    documentation_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quiz_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quiz_hard_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    course: Mapped["Course"] = relationship(back_populates="lessons")


class CourseSource(Base):
    """A source backing a course's Gemini-generated lesson content - either the
    single primary source (is_primary=True, mirrors courses_db.json's "source")
    or one of the supplementary sources listed under "additional_sources" for
    that course (is_primary=False). Kept separate from Lesson because a source
    is shared context for the whole course, not tied to one topic."""

    __tablename__ = "course_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    license: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    course: Mapped["Course"] = relationship(back_populates="sources")


class CoursePurchase(Base):
    """Records that a user paid the one-time price for a course (see
    Course.price_cents). Existence of a row = access granted; there's no
    "amount paid" mutability concern since prices aren't retroactively
    changed for people who already bought in. Created from the Stripe
    webhook (see routes/billingRoute.py) once checkout.session.completed
    fires for a course-purchase session."""

    __tablename__ = "course_purchases"
    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_course_purchases_user_course"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped["User"] = relationship()
    course: Mapped["Course"] = relationship(back_populates="purchases")


class CourseNote(Base):
    """A community-contributed study note (an uploaded file or a pasted
    external link) for a course - open to any logged-in user, unlike
    CourseMaterial (which only the course's own submitter controls at
    submission time). Always free to view regardless of Course.price_cents -
    see routes/courseRoute.py::list_course_notes, which deliberately never
    calls _has_course_access. Deletable by its own uploader or an admin."""

    __tablename__ = "course_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    course: Mapped["Course"] = relationship(back_populates="notes")
    uploaded_by_user: Mapped["User"] = relationship()

    @property
    def course_name(self) -> str:
        """Used by AdminCourseNoteOut (routes/adminRoute.py) so an admin
        browsing notes across every course doesn't have to cross-reference
        course_id manually."""
        return self.course.name

    @property
    def uploaded_by_name(self) -> str | None:
        """Display name for whoever uploaded this note, or None if that
        account has since been deleted - same pattern as
        Course.submitted_by_name."""
        user = self.uploaded_by_user
        if user is None:
            return None
        return user.full_name or user.email
