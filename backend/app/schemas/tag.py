"""Tag schemas."""
from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")


class TagOut(BaseModel):
    id: str
    name: str
    color: str
    created_at: object

    model_config = {"from_attributes": True}
