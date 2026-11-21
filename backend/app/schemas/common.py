"""Common Pydantic models and response wrappers."""

from typing import Generic, TypeVar, Any
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int

    model_config = ConfigDict(from_attributes=True)


class StandardMessageResponse(BaseModel):
    success: bool
    message: str
    data: dict[str, Any] | None = None
