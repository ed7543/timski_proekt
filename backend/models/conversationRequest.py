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


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    subject: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    subject: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: List[MessageOut] = []
