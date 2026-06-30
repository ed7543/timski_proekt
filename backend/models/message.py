from pydantic import BaseModel

class Message(BaseModel):
    role: str          # "user" | "assistant"
    content: str