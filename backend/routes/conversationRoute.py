import json as json_lib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.database.models import Conversation, User
from backend.middleware.auth import get_current_user
from backend.models.conversationRequest import (
    ConversationCreate,
    ConversationUpdate,
    ConversationOut,
    ConversationDetailOut,
    MessageOut,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _to_out(conv: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        subject=conv.subject,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=len(conv.messages),
    )


def _get_owned_conversation(db: Session, conversation_id: int, user: User) -> Conversation:
    """Fetch a conversation and make sure it belongs to the current user.
    Returns 404 (not 403) for someone else's conversation so we don't leak
    which conversation IDs exist."""
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = Conversation(
        user_id=current_user.id,
        title=request.title or "New conversation",
        subject=request.subject,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return _to_out(conv)


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    search: Optional[str] = Query(None, description="Filter by title substring"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Conversation).filter(Conversation.user_id == current_user.id)
    if search:
        q = q.filter(Conversation.title.ilike(f"%{search}%"))
    convs = q.order_by(Conversation.updated_at.desc()).all()
    return [_to_out(c) for c in convs]


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = _get_owned_conversation(db, conversation_id, current_user)
    return ConversationDetailOut(
        id=conv.id,
        title=conv.title,
        subject=conv.subject,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[MessageOut.model_validate(m) for m in conv.messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: int,
    request: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = _get_owned_conversation(db, conversation_id, current_user)
    conv.title = request.title
    db.commit()
    db.refresh(conv)
    return _to_out(conv)


@router.get("/{conversation_id}/export")
async def export_conversation(
    conversation_id: int,
    format: str = Query("markdown", pattern="^(markdown|json)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a conversation as a standalone .json or .md file."""
    conv = _get_owned_conversation(db, conversation_id, current_user)

    if format == "json":
        payload = {
            "id": conv.id,
            "title": conv.title,
            "subject": conv.subject,
            "created_at": conv.created_at.isoformat(),
            "messages": [
                {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
                for m in conv.messages
            ],
        }
        content = json_lib.dumps(payload, indent=2)
        media_type = "application/json"
        filename = f"conversation-{conv.id}.json"
    else:
        lines = [f"# {conv.title}", ""]
        if conv.subject:
            lines.append(f"_Subject: {conv.subject}_")
            lines.append("")
        for m in conv.messages:
            speaker = "You" if m.role == "user" else "LearnWise"
            lines.append(f"**{speaker}:**")
            lines.append(m.content)
            lines.append("")
        content = "\n".join(lines)
        media_type = "text/markdown"
        filename = f"conversation-{conv.id}.md"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = _get_owned_conversation(db, conversation_id, current_user)
    db.delete(conv)
    db.commit()
    return None
