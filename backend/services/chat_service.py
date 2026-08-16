import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend.database.models import ChatMessage, Conversation, User
from backend.database.session import SessionLocal
from backend.models.chatRequest import ChatRequest
from backend.routes.conversationRoute import _get_owned_conversation

logger = logging.getLogger(__name__)


def resolve_conversation(db: Session, request: ChatRequest, current_user: User, latest_user_msg: str) -> Conversation:
    """Fetch the conversation this exchange belongs to, or create a new one."""
    if request.conversation_id:
        return _get_owned_conversation(db, request.conversation_id, current_user)

    conversation = Conversation(
        user_id=current_user.id,
        title=(latest_user_msg[:48] or "New conversation"),
        subject=request.subject,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def save_user_message(db: Session, conversation: Conversation, content: str) -> None:
    db.add(ChatMessage(conversation_id=conversation.id, role="user", content=content))
    conversation.updated_at = datetime.utcnow()
    db.commit()


def save_assistant_reply(conversation_id: int, content: str) -> None:
    """Called from inside the SSE generator, after the request-scoped `db` session
    (from Depends(get_db)) has already closed - opens its own session, and rolls
    back + logs instead of letting a failed commit propagate into the stream."""
    save_db = SessionLocal()
    try:
        save_db.add(ChatMessage(conversation_id=conversation_id, role="assistant", content=content))
        conv = save_db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conv:
            conv.updated_at = datetime.utcnow()
        save_db.commit()
    except Exception:
        save_db.rollback()
        logger.exception("Failed to save assistant reply for conversation %s", conversation_id)
    finally:
        save_db.close()
