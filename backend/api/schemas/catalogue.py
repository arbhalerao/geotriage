from pydantic import BaseModel


class CollectionResponse(BaseModel):
    slug: str
    display_name: str
    processing_level: str
    resolution_m: float


class CompatibilityResponse(BaseModel):
    level: str
    reasons: list[str]


class ScoreOutputResponse(BaseModel):
    description: str
    unit: str
    value_range: tuple[float, float]


class ThresholdBandResponse(BaseModel):
    green: tuple[float, float]
    yellow: tuple[float, float]


class ModelResponse(BaseModel):
    slug: str
    name: str
    description: str
    required_bands: list[str]
    derived_rasters: list[str]
    max_cloud_cover: float | None
    score_outputs: dict[str, ScoreOutputResponse]
    compatible_collections: dict[str, CompatibilityResponse]
    default_thresholds: dict[str, ThresholdBandResponse]
