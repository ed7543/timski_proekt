from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ConversationCreate(BaseModel):
    title: Optional[str] = "New conversation"
    subject: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime
    # Both None for assistant messages and for historical user messages
    # saved before group chat existed - see database/models.py::ChatMessage.
    author_user_id: Optional[int] = None
    author_name: Optional[str] = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    subject: Optional[str] = None
    # The owner's Nth-ever conversation, stamped once at creation - stays
    # fixed even if an earlier conversation is later deleted.
    issue_no: int
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationMemberOut(BaseModel):
    """A conversation participant - built manually in conversationRoute.py
    (not from_attributes) since "is_owner" isn't a real column on either
    ConversationMember or User."""

    user_id: int
    name: str
    joined_at: datetime
    is_owner: bool = False


class ConversationDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    subject: Optional[str] = None
    issue_no: int
    created_at: datetime
    updated_at: datetime
    messages: List[MessageOut] = []
    members: List[ConversationMemberOut] = []
    # Whether the requesting viewer is this conversation's owner - computed
    # per-request in conversationRoute.py, not stored (same pattern as
    # CourseDetailOut.locked).
    is_owner: bool = True
    # Whether an assistant reply is currently streaming for this
    # conversation - lets a polling client show "someone is asking
    # something..." instead of silence. Advisory only, tracked in-memory
    # (see services/chat_state.py) - never blocks a second send.
    generating: bool = False
    # The server-side member cap (routes/conversationRoute.py::MAX_CONVERSATION_MEMBERS),
    # sent down rather than hardcoded a second time in the frontend so the
    # two can't silently drift out of sync.
    max_members: int = 3


class ConversationStatusOut(BaseModel):
    """Cheap poll target for useConversationPolling.ts - just enough to know
    whether a full GET /{id} is actually worth fetching, so a 2-3 person
    group conversation's polling clients aren't re-transferring the entire
    transcript every couple of seconds regardless of whether anything
    changed."""

    message_count: int
    generating: bool


class ConversationInviteOut(BaseModel):
    """A shareable join link - built manually in conversationRoute.py (the
    full `url` isn't a real column, it's FRONTEND_URL + the token)."""

    id: int
    token: str
    url: str
    created_at: datetime
    expires_at: Optional[datetime] = None
