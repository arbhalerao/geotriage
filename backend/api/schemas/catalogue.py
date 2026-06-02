from pydantic import BaseModel


class BandResponse(BaseModel):
    normalized_name: str
    asset_key: str
    description: str
    scale: float
    offset: float


class CollectionResponse(BaseModel):
    slug: str
    display_name: str
    description: str
    processing_level: str
    sensor_type: str
    resolution_m: float
    cloud_cover_property: str | None
    bands: list[BandResponse]
    provider_slug: str
    provider_name: str


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
    primary_score: str
    required_bands: list[str]
    derived_rasters: list[str]
    max_cloud_cover: float | None
    score_outputs: dict[str, ScoreOutputResponse]
    compatible_collections: dict[str, CompatibilityResponse]
    default_thresholds: dict[str, ThresholdBandResponse]


class ProviderResponse(BaseModel):
    slug: str
    name: str
    stac_api_url: str
    collections: list[CollectionResponse]
