from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Sender(BaseModel):
    platform_id: str = Field(description="Sender platform user id")
    display_name: Optional[str] = Field(default=None, description="Sender display name")


class ReplyTo(BaseModel):
    id: str = Field(description="Replied message id")
    content: Optional[str] = Field(default=None, description="Replied message content")
    author_name: Optional[str] = Field(
        default=None, description="Replied message author display name"
    )


class ChatRequest(BaseModel):
    message_id: str
    channel: str
    account_id: str
    sender: Sender
    chat_type: Literal["private", "group"]
    message_type: Literal["text", "image", "voice", "video", "file", "reference"]
    content: str
    media_url: Optional[str] = None
    reply_to: Optional[ReplyTo] = None
    group_id: Optional[str] = None
    timestamp: int
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_group_chat(self) -> "ChatRequest":
        if self.chat_type == "group" and not self.group_id:
            raise ValueError("group_id is required for group chat")
        return self


class ChatAcceptedResponse(BaseModel):
    status: Literal["accepted"]
    request_message_id: str
    input_message_id: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    message_id: Optional[str] = None
    account_id: Optional[str] = None
