import uuid
from datetime import datetime

from pydantic import BaseModel


class ModelScoreResponse(BaseModel):
    score_name: str
    score_value: float
    is_primary: bool
    severity: str


class ModelRunResponse(BaseModel):
    id: uuid.UUID
    model_slug: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    scores: list[ModelScoreResponse]


class ReviewResponse(BaseModel):
    id: uuid.UUID
    review_status: str
    notes: str | None
    reviewed_at: datetime | None
    updated_at: datetime


class StacItemResponse(BaseModel):
    id: str
    collection: str
    datetime: datetime
    bbox: list[float] | None
    properties: dict
    assets: dict


class WorkflowItemSummary(BaseModel):
    id: uuid.UUID
    collection_slug: str
    stac_item_id: str
    scene_datetime: datetime
    status: str
    overall_severity: str | None
    discovered_at: datetime
    processed_at: datetime | None
    is_bookmarked: bool
    bbox: list[float] | None


class WorkflowItemPage(BaseModel):
    items: list[WorkflowItemSummary]
    total: int
    page: int
    page_size: int
    pages: int


class WorkflowItemDetail(BaseModel):
    id: uuid.UUID
    collection_slug: str
    stac_item_id: str
    scene_datetime: datetime
    status: str
    overall_severity: str | None
    discovered_at: datetime
    processed_at: datetime | None
    is_bookmarked: bool
    stac_item: StacItemResponse
    model_runs: list[ModelRunResponse]
    review: ReviewResponse | None


class ReviewCreate(BaseModel):
    review_status: str
    notes: str | None = None


class BookmarkResponse(BaseModel):
    id: uuid.UUID
    workflow_item_id: uuid.UUID
    notes: str | None
    created_at: datetime


class TimeseriesPoint(BaseModel):
    item_id: uuid.UUID
    stac_item_id: str
    scene_datetime: datetime
    score_name: str
    score_value: float
    severity: str


class TimeseriesResponse(BaseModel):
    available_scores: list[str]
    points: list[TimeseriesPoint]
