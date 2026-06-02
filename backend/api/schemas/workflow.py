import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


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
    time_mode: str = Field(pattern="^(historical|fixed_future)$")
    time_start: datetime
    time_end: datetime
    aoi_filter_mode: str = Field(default="intersects", pattern="^(intersects|enclosed)$")
    poll_interval_minutes: int | None = None
    collection_slugs: list[str] = Field(min_length=1)
    models: list[ModelConfigInput] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def check_poll_interval(self) -> "WorkflowCreate":
        if self.poll_interval_minutes is not None and self.time_mode != "fixed_future":
            raise ValueError("poll_interval_minutes is only valid for fixed_future workflows")
        if self.poll_interval_minutes is not None and self.poll_interval_minutes < 1:
            raise ValueError("poll_interval_minutes must be at least 1")
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
