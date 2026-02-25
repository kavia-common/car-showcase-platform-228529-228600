from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class PageMeta(BaseModel):
    limit: int = Field(..., ge=1, le=100, description="Page size used for this response.")
    offset: int = Field(..., ge=0, description="Offset used for this response.")
    total: int = Field(..., ge=0, description="Total number of matching records.")


class CarImageOut(BaseModel):
    id: int = Field(..., description="Image ID.")
    car_id: int = Field(..., description="Associated car ID.")
    trim_id: Optional[int] = Field(None, description="Associated trim ID (optional).")
    url: str = Field(..., description="Public image URL.")
    alt_text: Optional[str] = Field(None, description="Alt text for accessibility.")
    kind: str = Field(..., description="Image kind (e.g., gallery, hero).")
    sort_order: int = Field(..., description="Sorting hint for display order.")
    is_primary: bool = Field(..., description="Whether this is the primary image for the car.")


class TrimSpecOut(BaseModel):
    id: int
    trim_id: int
    category: str
    name: str
    value: str
    unit: Optional[str] = None
    sort_order: int


class TrimFeatureOut(BaseModel):
    id: int
    trim_id: int
    feature_group: str
    description: str
    sort_order: int


class TrimOut(BaseModel):
    id: int = Field(..., description="Trim ID.")
    car_id: int = Field(..., description="Car ID.")
    name: str = Field(..., description="Trim name.")
    msrp_cents: int = Field(..., ge=0, description="Trim MSRP in cents.")
    is_default: bool = Field(..., description="Whether this trim is the default for its car.")


class CarOut(BaseModel):
    id: int = Field(..., description="Car ID.")
    make: str = Field(..., description="Manufacturer.")
    model: str = Field(..., description="Model name.")
    year: int = Field(..., ge=1886, le=2100, description="Model year.")
    body_type: str = Field(..., description="Body type (SUV, Sedan, etc.).")
    msrp_base_cents: int = Field(..., ge=0, description="Base MSRP in cents.")
    description: Optional[str] = Field(None, description="Marketing description.")
    is_active: bool = Field(..., description="Whether the car is visible in the public catalog.")
    created_at: datetime
    updated_at: datetime


class CarListItem(BaseModel):
    id: int
    make: str
    model: str
    year: int
    body_type: str
    msrp_base_cents: int
    description: Optional[str] = None
    primary_image_url: Optional[str] = Field(None, description="Primary image URL if present.")


class CarListResponse(BaseModel):
    meta: PageMeta
    items: list[CarListItem]


class CarDetailResponse(BaseModel):
    car: CarOut
    images: list[CarImageOut] = Field(default_factory=list)
    trims: list[TrimOut] = Field(default_factory=list)
    default_trim_id: Optional[int] = Field(None, description="ID of the default trim if set.")
    specs_by_trim: dict[str, list[TrimSpecOut]] = Field(
        default_factory=dict,
        description="Map trim_id (string) -> specs for that trim.",
    )
    features_by_trim: dict[str, list[TrimFeatureOut]] = Field(
        default_factory=dict,
        description="Map trim_id (string) -> features for that trim.",
    )


class CompareRequest(BaseModel):
    car_ids: list[int] = Field(..., min_length=2, max_length=4, description="2-4 car IDs to compare.")


class CompareResponse(BaseModel):
    cars: list[CarDetailResponse] = Field(..., description="Details for each car in the comparison set.")


class LeadCreateRequest(BaseModel):
    car_id: Optional[int] = Field(None, description="Optional car of interest.")
    trim_id: Optional[int] = Field(None, description="Optional trim of interest.")
    full_name: str = Field(..., min_length=2, max_length=200, description="Lead full name.")
    email: EmailStr = Field(..., description="Lead email.")
    phone: Optional[str] = Field(None, max_length=50, description="Lead phone (optional).")
    message: Optional[str] = Field(None, max_length=2000, description="Message (optional).")
    preferred_contact_method: Optional[Literal["email", "phone"]] = Field(
        None, description="Preferred contact method."
    )
    source: Optional[str] = Field(None, max_length=100, description="Submission source (optional).")


class LeadCreateResponse(BaseModel):
    id: int = Field(..., description="Inquiry ID.")
    status: str = Field(..., description="Inquiry status.")


# ---------------- Admin create/update schemas ----------------

class CarCreate(BaseModel):
    make: str = Field(..., min_length=1, max_length=100)
    model: str = Field(..., min_length=1, max_length=100)
    year: int = Field(..., ge=1886, le=2100)
    body_type: str = Field(..., min_length=1, max_length=50)
    msrp_base_cents: int = Field(..., ge=0)
    description: Optional[str] = Field(None, max_length=5000)
    is_active: bool = Field(True, description="Whether the car should be visible publicly.")


class CarUpdate(BaseModel):
    make: Optional[str] = Field(None, min_length=1, max_length=100)
    model: Optional[str] = Field(None, min_length=1, max_length=100)
    year: Optional[int] = Field(None, ge=1886, le=2100)
    body_type: Optional[str] = Field(None, min_length=1, max_length=50)
    msrp_base_cents: Optional[int] = Field(None, ge=0)
    description: Optional[str] = Field(None, max_length=5000)
    is_active: Optional[bool] = Field(None)


class TrimCreate(BaseModel):
    car_id: int = Field(..., description="Associated car ID.")
    name: str = Field(..., min_length=1, max_length=100)
    msrp_cents: int = Field(..., ge=0)
    is_default: bool = Field(False)


class TrimUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    msrp_cents: Optional[int] = Field(None, ge=0)
    is_default: Optional[bool] = Field(None)


class CarImageCreate(BaseModel):
    car_id: int
    trim_id: Optional[int] = None
    url: str = Field(..., min_length=5, max_length=2000)
    alt_text: Optional[str] = Field(None, max_length=500)
    kind: str = Field("gallery", max_length=50)
    sort_order: int = Field(0)
    is_primary: bool = Field(False)


class CarImageUpdate(BaseModel):
    trim_id: Optional[int] = None
    url: Optional[str] = Field(None, min_length=5, max_length=2000)
    alt_text: Optional[str] = Field(None, max_length=500)
    kind: Optional[str] = Field(None, max_length=50)
    sort_order: Optional[int] = None
    is_primary: Optional[bool] = None


class TrimSpecCreate(BaseModel):
    trim_id: int
    category: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1, max_length=200)
    unit: Optional[str] = Field(None, max_length=50)
    sort_order: int = 0


class TrimSpecUpdate(BaseModel):
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    value: Optional[str] = Field(None, min_length=1, max_length=200)
    unit: Optional[str] = Field(None, max_length=50)
    sort_order: Optional[int] = None


class TrimFeatureCreate(BaseModel):
    trim_id: int
    feature_group: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    sort_order: int = 0


class TrimFeatureUpdate(BaseModel):
    feature_group: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    sort_order: Optional[int] = None


class InquiryOut(BaseModel):
    id: int
    car_id: Optional[int] = None
    trim_id: Optional[int] = None
    full_name: str
    email: str
    phone: Optional[str] = None
    message: Optional[str] = None
    preferred_contact_method: Optional[str] = None
    status: str
    source: Optional[str] = None
    created_at: datetime


class InquiryUpdate(BaseModel):
    status: Optional[str] = Field(None, min_length=1, max_length=50)
    message: Optional[str] = Field(None, max_length=2000)
    preferred_contact_method: Optional[str] = Field(None, max_length=50)
    source: Optional[str] = Field(None, max_length=100)


class DeleteResponse(BaseModel):
    ok: bool = Field(True, description="Whether delete succeeded.")
    deleted_id: int = Field(..., description="ID of the deleted record.")


class AdminListResponse(BaseModel):
    meta: PageMeta
    items: list[Any]
