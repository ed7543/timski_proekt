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
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    verification_tokens: Mapped[list["VerificationToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
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


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


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
    documentation_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quiz_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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