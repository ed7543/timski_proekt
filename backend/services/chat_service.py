import logging

from sqlalchemy.orm import Session

from backend.database.models import ChatMessage, Conversation, User
from backend.database.session import SessionLocal
from backend.models.chatRequest import ChatRequest
from backend.models.message import Message
from backend.routes.conversationRoute import _get_member_conversation
from backend.utils.time import utcnow

logger = logging.getLogger(__name__)

# Caps how much history gets rebuilt/re-sent to Groq per call (see
# get_message_history_for_model) - without a bound, a long-running
# conversation would re-fetch and re-send its ENTIRE transcript on every
# single new message, growing DB query cost, token cost, and latency
# unboundedly, eventually risking the model's own context-window limit.
# Generous for a study conversation; the oldest messages beyond this are
# simply dropped from the prompt, not deleted from the database.
MAX_HISTORY_MESSAGES = 50


def resolve_conversation(db: Session, request: ChatRequest, current_user: User, latest_user_msg: str) -> Conversation:
    """Fetch the conversation this exchange belongs to, or create a new one.
    _get_member_conversation allows the owner or any invited member (see
    conversationRoute.py) - a group conversation's other members reach this
    same endpoint just by including its conversation_id."""
    if request.conversation_id:
        return _get_member_conversation(db, request.conversation_id, current_user)

    conversation = Conversation(
        user_id=current_user.id,
        title=(latest_user_msg[:48] or "New conversation"),
        subject=request.subject,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def save_user_message(db: Session, conversation: Conversation, content: str, author_user_id: int) -> None:
    db.add(ChatMessage(
        conversation_id=conversation.id, role="user", content=content, author_user_id=author_user_id,
    ))
    conversation.updated_at = utcnow()
    db.commit()


def get_message_history_for_model(db: Session, conversation: Conversation) -> list[Message]:
    """Rebuilds the message list to send to Groq from the database instead of
    trusting the calling browser tab's own request.messages array.

    With more than one member able to post into the same conversation at
    unpredictable times, a client's locally-accumulated transcript can
    already be stale the moment two people type near-simultaneously (this
    was already a latent gap for a single user's own two open tabs - a
    group conversation just makes it visible). Querying fresh here, right
    before the model call, means the prompt always reflects every message
    committed so far (including the one save_user_message just saved),
    regardless of which of up to 3 tabs sent it - no locking or queueing
    needed for a conversation this small.

    Ordered by (created_at, id) rather than created_at alone - two members
    posting within the same timestamp tick would otherwise have no
    guaranteed stable order, which could hand the model a prompt that
    presents them reversed from what was actually typed. Capped to the most
    recent MAX_HISTORY_MESSAGES (see that constant) - fetched newest-first
    with a LIMIT, then reversed back into chronological order, so a long
    conversation's cost doesn't grow without bound."""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(MAX_HISTORY_MESSAGES)
        .all()
    )
    messages.reverse()
    return [Message(role=m.role, content=m.content) for m in messages]


def save_assistant_reply(conversation_id: int, content: str) -> None:
    """Called from inside the SSE generator, after the request-scoped `db` session
    (from Depends(get_db)) has already closed - opens its own session, and rolls
    back + logs instead of letting a failed commit propagate into the stream."""
    save_db = SessionLocal()
    try:
        save_db.add(ChatMessage(conversation_id=conversation_id, role="assistant", content=content))
        conv = save_db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conv:
            conv.updated_at = utcnow()
        save_db.commit()
    except Exception:
        save_db.rollback()
        logger.exception("Failed to save assistant reply for conversation %s", conversation_id)
    finally:
        save_db.close()
