from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ImageRegister(BaseModel):
    image: str = Field(min_length=1, description="A container image reference, e.g. acme/ships:1.2")


class AdmissionCheck(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class RegisteredResponse(BaseModel):
    id: str
    slug: str
    name: str
    image: str
    is_enabled: bool
    descriptor: dict[str, Any]
    registered_at: datetime
    admission: dict[str, Any] | None = None  # the checks it passed, and why it didn't


class AdmissionResponse(BaseModel):
    """
    what the gate decided, and why
    returned on both success and rejection so the author sees which checks ran
    """

    admitted: bool
    checks: list[AdmissionCheck]
    problems: list[str] = []
    registered: RegisteredResponse | None = None
