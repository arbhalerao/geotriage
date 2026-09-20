import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from api.schemas.workflow import ModelConfigInput, WorkflowCreate


class EstimateCreate(BaseModel):

    geometry: dict[str, Any]
    time_mode: str
    time_start: datetime | None = None
    time_end: datetime
    poll_interval_minutes: int | None = None
    collection_slugs: list[str] = Field(min_length=1)
    models: list[ModelConfigInput] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def valid_as_a_workflow(self) -> "EstimateCreate":
        WorkflowCreate(name="estimate", **self.model_dump())
        return self

    def as_draft(self) -> dict:
        return self.model_dump(mode="json")


class EstimateResponse(BaseModel):
    id: uuid.UUID
    status: str
    result: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime
