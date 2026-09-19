import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class BuilderMessage(BaseModel):
    role: Literal["user", "assistant"]
    # long enough for any real request, short enough that nobody pastes a novel of instructions at the model
    content: str = Field(min_length=1, max_length=2000)


class BuilderRunCreate(BaseModel):
    """the whole conversation so far, since the browser is the only place it's kept"""

    conversation: list[BuilderMessage] = Field(min_length=1, max_length=20)

    @field_validator("conversation")
    @classmethod
    def ends_with_the_user(cls, conversation: list[BuilderMessage]) -> list[BuilderMessage]:
        if conversation[-1].role != "user":
            raise ValueError("the last message has to be the user's, it's what the builder answers")
        return conversation


class BuilderRunResponse(BaseModel):
    id: uuid.UUID
    status: str
    steps: list[str]
    # {"kind": "draft" | "question" | "cannot", "message", "draft", "warnings", ...} once status is done
    outcome: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime
