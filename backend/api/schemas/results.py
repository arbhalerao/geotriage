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
    stac_item: StacItemResponse
    model_runs: list[ModelRunResponse]


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
