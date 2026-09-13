import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ThresholdInput(BaseModel):
    green_min: float
    green_max: float
    yellow_min: float
    yellow_max: float


class ModelConfigInput(BaseModel):
    model_slug: str
    user_label: str | None = None
    parameters: dict | None = None
    thresholds: dict[str, ThresholdInput] | None = None


class WorkflowCreate(BaseModel):
    name: str
    geometry: dict[str, Any]
    description: str | None = None
    time_mode: str = Field(pattern="^(historical|recurring)$")
    # historical only; a recurring workflow starts when it is created, so the server sets it
    time_start: datetime | None = None
    time_end: datetime
    aoi_filter_mode: str = Field(default="intersects", pattern="^(intersects|enclosed)$")
    poll_interval_minutes: int | None = None
    collection_slugs: list[str] = Field(min_length=1)
    models: list[ModelConfigInput] = Field(min_length=1, max_length=1)

    @field_validator("time_start", "time_end")
    @classmethod
    def in_utc(cls, value: datetime | None) -> datetime | None:
        # the platform runs on UTC; a time without a zone is ambiguous, so it's refused rather than guessed at
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("must include a timezone, e.g. 2026-09-01T00:00:00Z")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def check_mode(self) -> "WorkflowCreate":
        now = datetime.now(timezone.utc)
        if self.time_mode == "recurring":
            if self.poll_interval_minutes is None:
                raise ValueError("recurring workflows need a poll_interval_minutes")
            if self.poll_interval_minutes < 1:
                raise ValueError("poll_interval_minutes must be at least 1")
            # it watches for new scenes from the moment it exists, so its start is always now and not the caller's to choose
            if self.time_start is not None:
                raise ValueError("recurring workflows start when they are created; send only time_end")
            self.time_start = now
            if self.time_end <= now:
                raise ValueError("a recurring workflow has to end in the future")
        else:
            if self.time_start is None:
                raise ValueError("historical workflows need a time_start")
            if self.poll_interval_minutes is not None:
                raise ValueError("poll_interval_minutes is only valid for recurring workflows")
            # a historical workflow runs once over scenes that already exist
            if self.time_end > now:
                raise ValueError("historical workflows can't end in the future")
        return self


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ThresholdConfigResponse(BaseModel):
    score_name: str
    green_min: float
    green_max: float
    yellow_min: float
    yellow_max: float


class CollectionConfigResponse(BaseModel):
    collection_slug: str
    compatibility_level: str
    is_enabled: bool


class ModelConfigResponse(BaseModel):
    id: uuid.UUID
    model_slug: str
    user_label: str | None
    parameters: dict | None
    collection_configs: list[CollectionConfigResponse]
    threshold_configs: list[ThresholdConfigResponse]


class WorkflowResponse(BaseModel):
    id: uuid.UUID
    aoi_id: uuid.UUID
    aoi_geometry: dict[str, Any]
    name: str
    description: str | None
    time_mode: str
    time_start: datetime
    time_end: datetime
    aoi_filter_mode: str
    poll_interval_minutes: int | None
    last_checked_at: datetime | None
    next_run_at: datetime | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    collection_slugs: list[str]
    model_configs: list[ModelConfigResponse]
    total_items: int = 0
    processed_items: int = 0
    identified_items: int = 0
    failed_fetch_items: int = 0
    failed_upload_items: int = 0
    failed_score_items: int = 0
    screened_out_items: int = 0  # rejected by a model's prefilter, never fetched


class WorkflowSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    time_mode: str
    time_start: datetime
    time_end: datetime
    status: str
    created_at: datetime
    updated_at: datetime
    # the numbers a list row shows; anything more comes from GET /workflows/{id} when a row is opened
    total_items: int
    processed_items: int
    identified_items: int
    failed_items: int
