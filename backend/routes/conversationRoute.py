import json as json_lib
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, or_, update
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.database.models import ChatMessage, Conversation, ConversationInvite, ConversationMember, User
from backend.middleware.auth import get_current_user
from backend.models.conversationRequest import (
    ConversationCreate,
    ConversationUpdate,
    ConversationOut,
    ConversationDetailOut,
    ConversationInviteOut,
    ConversationMemberOut,
    ConversationStatusOut,
    MessageOut,
)
from backend.services.chat_state import is_generating
from backend.utils.time import utcnow
from config import FRONTEND_URL

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

MAX_CONVERSATION_MEMBERS = 3  # owner + up to 2 invited members
INVITE_DEFAULT_LIFETIME_DAYS = 7


def _is_member(db: Session, conv: Conversation, user: User) -> bool:
    if conv.user_id == user.id:
        return True
    return (
        db.query(ConversationMember)
        .filter(ConversationMember.conversation_id == conv.id, ConversationMember.user_id == user.id)
        .first()
        is not None
    )


def _to_out(conv: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        subject=conv.subject,
        issue_no=conv.issue_no,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=len(conv.messages),
    )


def _member_out(member: ConversationMember) -> ConversationMemberOut:
    return ConversationMemberOut(
        user_id=member.user_id,
        name=member.user.full_name or member.user.email,
        joined_at=member.joined_at,
        is_owner=False,
    )


def _all_members_out(conv: Conversation) -> list[ConversationMemberOut]:
    """Owner + every ConversationMember, in one list - used everywhere the
    frontend needs a full roster (both list_members and get_conversation's
    `members` field), so "how many people are in this conversation" is
    always conv.members-plus-owner, never just conv.members alone."""
    owner = ConversationMemberOut(
        user_id=conv.user_id,
        name=conv.user.full_name or conv.user.email,
        joined_at=conv.created_at,
        is_owner=True,
    )
    return [owner] + [_member_out(m) for m in conv.members]


def _get_member_conversation(db: Session, conversation_id: int, user: User) -> Conversation:
    """Fetch a conversation and make sure the current user can see it -
    either they're the owner (Conversation.user_id) or a ConversationMember
    of it. Returns 404 (not 403) for anyone else so we don't leak which
    conversation IDs exist. Used by every read/write below except the
    owner-only actions (see _get_owned_conversation_or_404)."""
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv or not _is_member(db, conv, user):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


def _get_owned_conversation_or_404(db: Session, conversation_id: int, user: User) -> Conversation:
    """Stricter than _get_member_conversation - only the conversation's
    owner passes. Used for actions no other member should be able to do:
    deleting the whole conversation, managing invites, or removing a
    different member."""
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
    # Atomic increment-and-read (UPDATE ... RETURNING) rather than reading
    # current_user.conversation_seq and adding 1 in Python - two concurrent
    # creates for the same user would otherwise both read the same starting
    # value and hand out the same issue_no. The row-level lock the UPDATE
    # takes makes this safe under concurrency.
    next_seq = db.execute(
        update(User)
        .where(User.id == current_user.id)
        .values(conversation_seq=User.conversation_seq + 1)
        .returning(User.conversation_seq)
    ).scalar_one()
    conv = Conversation(
        user_id=current_user.id,
        title=request.title or "New conversation",
        subject=request.subject,
        issue_no=next_seq,
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
    member_conv_ids = db.query(ConversationMember.conversation_id).filter(
        ConversationMember.user_id == current_user.id
    )
    q = db.query(Conversation).filter(
        or_(Conversation.user_id == current_user.id, Conversation.id.in_(member_conv_ids))
    )
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
    conv = _get_member_conversation(db, conversation_id, current_user)
    return ConversationDetailOut(
        id=conv.id,
        title=conv.title,
        subject=conv.subject,
        issue_no=conv.issue_no,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[MessageOut.model_validate(m) for m in conv.messages],
        members=_all_members_out(conv),
        is_owner=conv.user_id == current_user.id,
        generating=is_generating(conv.id),
        max_members=MAX_CONVERSATION_MEMBERS,
    )


@router.get("/{conversation_id}/status", response_model=ConversationStatusOut)
async def get_conversation_status(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cheap poll target - a COUNT query and an in-memory flag check, not the
    full message/member payload GET /{conversation_id} returns. See
    frontend/src/hooks/useConversationPolling.ts: it hits this every tick and
    only fetches the full conversation when message_count has actually
    changed, instead of re-transferring the entire transcript every time."""
    conv = _get_member_conversation(db, conversation_id, current_user)
    message_count = db.query(func.count(ChatMessage.id)).filter(
        ChatMessage.conversation_id == conv.id
    ).scalar()
    return ConversationStatusOut(message_count=message_count or 0, generating=is_generating(conv.id))


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: int,
    request: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Any member can rename - low-stakes and collaborative, unlike delete
    or invite management which stay owner-only (see _get_owned_conversation_or_404)."""
    conv = _get_member_conversation(db, conversation_id, current_user)
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
    conv = _get_member_conversation(db, conversation_id, current_user)

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
    """Owner-only, unlike every other action above - a member who no longer
    wants to be here uses DELETE /{id}/members/{their own user_id} (leave)
    instead; only the owner can destroy the conversation for everyone."""
    conv = _get_owned_conversation_or_404(db, conversation_id, current_user)
    db.delete(conv)
    db.commit()
    return None


# ------------------------------------------------------------------- invites ----

@router.post("/{conversation_id}/invites", response_model=ConversationInviteOut, status_code=status.HTTP_201_CREATED)
async def create_invite(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Owner-only. Multi-use until the conversation hits MAX_CONVERSATION_MEMBERS
    or this invite expires/is revoked - see accept_invite below."""
    _get_owned_conversation_or_404(db, conversation_id, current_user)
    invite = ConversationInvite(
        conversation_id=conversation_id,
        token=secrets.token_urlsafe(32),
        created_by_id=current_user.id,
        expires_at=utcnow() + timedelta(days=INVITE_DEFAULT_LIFETIME_DAYS),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return ConversationInviteOut(
        id=invite.id,
        token=invite.token,
        url=f"{FRONTEND_URL}/chat/join/{invite.token}",
        created_at=invite.created_at,
        expires_at=invite.expires_at,
    )


@router.delete("/{conversation_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    conversation_id: int,
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Owner-only. Doesn't remove anyone already invited through this link -
    only stops it from being usable again."""
    _get_owned_conversation_or_404(db, conversation_id, current_user)
    invite = (
        db.query(ConversationInvite)
        .filter(ConversationInvite.id == invite_id, ConversationInvite.conversation_id == conversation_id)
        .first()
    )
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    invite.revoked_at = utcnow()
    db.commit()
    return None


@router.post("/invites/{token}/accept", response_model=ConversationOut)
async def accept_invite(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Any logged-in user - joins the conversation this invite points to, as
    long as the invite is still valid and the conversation hasn't already
    hit MAX_CONVERSATION_MEMBERS. A no-op (still 200) if the caller is
    already the owner or a member - clicking the same link twice shouldn't
    error.

    The membership-check-then-insert below is made atomic with
    with_for_update(): without it, two accept requests for the same
    conversation (two tabs on the same link, or two different invites when
    only one slot is free) can both read "not a member yet"/"under the cap"
    before either commits, then both insert - either a UniqueConstraint
    violation surfacing as a raw 500 instead of the documented no-op, or two
    different users landing the conversation one member over the cap.
    Locking the conversation row serializes any concurrent accept aimed at
    it, so the second request only proceeds once it can see the first
    request's committed result."""
    invite = db.query(ConversationInvite).filter(ConversationInvite.token == token).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.revoked_at is not None or (invite.expires_at is not None and invite.expires_at < utcnow()):
        raise HTTPException(status_code=410, detail="This invite link has expired or been revoked")

    conv = (
        db.query(Conversation)
        .filter(Conversation.id == invite.conversation_id)
        .with_for_update()
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if _is_member(db, conv, current_user):
        return _to_out(conv)

    member_count = 1 + db.query(ConversationMember).filter(ConversationMember.conversation_id == conv.id).count()
    if member_count >= MAX_CONVERSATION_MEMBERS:
        raise HTTPException(status_code=409, detail=f"This conversation already has {MAX_CONVERSATION_MEMBERS} members")

    db.add(ConversationMember(conversation_id=conv.id, user_id=current_user.id))
    db.commit()
    db.refresh(conv)
    return _to_out(conv)


# ------------------------------------------------------------------- members ----

@router.get("/{conversation_id}/members", response_model=list[ConversationMemberOut])
async def list_members(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = _get_member_conversation(db, conversation_id, current_user)
    return _all_members_out(conv)


@router.delete("/{conversation_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    conversation_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Removing yourself ("leave") is allowed for any member on their own
    user_id. Removing someone else ("kick") requires being the owner. The
    owner can't be removed at all, by anyone, including themselves - they
    delete the whole conversation instead (DELETE /{conversation_id})."""
    conv = _get_member_conversation(db, conversation_id, current_user)
    if user_id == conv.user_id:
        raise HTTPException(status_code=400, detail="The owner can't be removed - delete the conversation instead")
    if user_id != current_user.id and current_user.id != conv.user_id:
        raise HTTPException(status_code=403, detail="Only the owner can remove another member")

    member = (
        db.query(ConversationMember)
        .filter(ConversationMember.conversation_id == conversation_id, ConversationMember.user_id == user_id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(member)
    db.commit()
    return None
