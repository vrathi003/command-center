"""Home inventory API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HomeItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    category: str = "other"
    brand: str | None = None
    model: str | None = None
    serial_number: str | None = None
    room_location: str | None = None
    purchase_date: str | None = None
    purchase_price_paise: int | None = None
    retailer: str | None = None
    warranty_end_date: str | None = None
    extended_warranty: bool = False
    condition_status: str = "good"
    notes: str | None = None


class HomeItemPut(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    category: str = "other"
    brand: str | None = None
    model: str | None = None
    serial_number: str | None = None
    room_location: str | None = None
    purchase_date: str | None = None
    purchase_price_paise: int | None = None
    retailer: str | None = None
    warranty_end_date: str | None = None
    extended_warranty: bool = False
    condition_status: str = "good"
    notes: str | None = None


class HomeItemOut(BaseModel):
    id: int
    name: str
    category: str
    brand: str | None
    model: str | None
    serial_number: str | None
    room_location: str | None
    purchase_date: str | None
    purchase_price_paise: int | None
    retailer: str | None
    warranty_end_date: str | None
    extended_warranty: bool
    condition_status: str
    notes: str | None
    created_at: str
    updated_at: str


class HomeItemSummaryOut(BaseModel):
    """List row + aggregates for detail header."""

    id: int
    name: str
    category: str
    brand: str | None
    model: str | None
    room_location: str | None
    purchase_date: str | None
    purchase_price_paise: int | None
    warranty_end_date: str | None
    condition_status: str
    service_event_count: int
    total_service_spend_paise: int


class HomeItemServiceEventCreate(BaseModel):
    service_date: str = Field(min_length=10, max_length=10)
    event_type: str = "other"
    vendor: str | None = None
    description: str | None = None
    cost_paise: int | None = None
    next_service_due: str | None = None
    notes: str | None = None


class HomeItemServiceEventPut(BaseModel):
    service_date: str = Field(min_length=10, max_length=10)
    event_type: str = "other"
    vendor: str | None = None
    description: str | None = None
    cost_paise: int | None = None
    next_service_due: str | None = None
    notes: str | None = None


class HomeItemServiceEventOut(BaseModel):
    id: int
    home_item_id: int
    service_date: str
    event_type: str
    vendor: str | None
    description: str | None
    cost_paise: int | None
    next_service_due: str | None
    notes: str | None
    created_at: str
    updated_at: str


class HomeInventorySummaryOut(BaseModel):
    item_count: int
    purchase_value_total_paise: int
    service_spend_total_paise: int
    count_by_category: dict[str, int]
    warranty_expiring_within_90_days: int
