from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Optional, List, TypeVar, Generic
from uuid import UUID

T = TypeVar("T")

# --- Pagination ---
class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int

# --- Authentication & User ---
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int

class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

class OTPRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

# --- General ---
class MessageResponse(BaseModel):
    message: str

# Ensure this is in app/schemas.py
class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: bool
    azure_storage: bool

# --- Activity Schemas ---
class ActivityBase(BaseModel):
    name: str
    category: str
    base_price: float
    child_price: Optional[float] = None
    duration_label: str
    image_url: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True

class ActivityCreate(ActivityBase):
    destination_id: Optional[UUID] = None

class ActivityUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    base_price: Optional[float] = None
    child_price: Optional[float] = None
    duration_label: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None

class ActivityResponse(ActivityBase):
    id: UUID
    destination_id: Optional[UUID] = None

# --- Destination Schemas ---
class DestinationBase(BaseModel):
    name: str
    slug: str
    region: str
    image_url: Optional[str] = None
    highlights: Optional[List[str]] = []
    sort_order: int = 0
    is_active: bool = True

class DestinationCreate(DestinationBase):
    pass

class DestinationUpdate(BaseModel):
    name: Optional[str] = None
    region: Optional[str] = None
    is_active: Optional[bool] = None

class DestinationResponse(DestinationBase):
    id: UUID
    hotel_count: int = 0
    model_config = {"from_attributes": True}


# --- Move RoomType & MealPlan Schemas ABOVE Hotel Schemas ---

class MealPlanRateSchema(BaseModel):
    meal_plan: str
    rate_per_night: float
    model_config = {"from_attributes": True}

class RoomTypeCreate(BaseModel):
    hotel_id: Optional[UUID] = None # Make this optional for hotel creation
    name: str
    max_occupancy: int
    extra_bed_rate: float
    meal_plan_rates: Optional[List[MealPlanRateSchema]] = []

class RoomTypeResponse(BaseModel):
    id: UUID
    hotel_id: UUID
    name: str
    max_occupancy: int
    extra_bed_rate: float
    meal_plan_rates: List[MealPlanRateSchema]
    model_config = {"from_attributes": True}

# --- Hotel Schemas ---

class HotelBase(BaseModel):
    name: str
    destination_id: UUID
    category: str
    stars: int
    description: Optional[str] = None
    amenities: Optional[List[str]] = []
    image_url: Optional[str] = None

class HotelCreate(HotelBase):
    room_types: Optional[List[RoomTypeCreate]] = [] # <--- Now Python knows what this is!

class HotelUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    stars: Optional[int] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None

class HotelResponse(HotelBase):
    id: UUID
    rating: Optional[float] = None
    destination_name: Optional[str] = None
    destination_slug: Optional[str] = None
    room_types: List[RoomTypeResponse] = []
    model_config = {"from_attributes": True}

# --- Itinerary Block Schemas ---

class ItineraryBlockBase(BaseModel):
    title: str
    description: Optional[str] = None
    day_number: int
    departs_from: Optional[str] = None
    overnight_slug: Optional[str] = None
    highlights: Optional[List[str]] = []
    duration_label: Optional[str] = None
    icon: Optional[str] = None
    image_url: Optional[str] = None
    tags: Optional[List[str]] = []
    sort_order: int = 0
    is_active: bool = True

class ItineraryBlockCreate(ItineraryBlockBase):
    overnight_destination_id: Optional[UUID] = None

class ItineraryBlockUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    day_number: Optional[int] = None
    is_active: Optional[bool] = None

class ItineraryBlockResponse(ItineraryBlockBase):
    id: UUID
    overnight_destination_id: Optional[UUID] = None

# --- Seasonal Pricing Schema ---

class SeasonalPricingRuleSchema(BaseModel):
    season: str
    label: str
    multiplier: float
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    is_active: bool = True

# --- Quotation/Package Pricing Schemas ---

class PackagePriceRequest(BaseModel):
    destination_id: UUID
    hotel_id: UUID
    number_of_adults: int
    number_of_children: int
    check_in_date: str  # Or use datetime.date
    meal_plan: str
    activities: Optional[List[UUID]] = []

# --- Quotation/Package Pricing Schemas ---

class PackagePriceResponse(BaseModel):
    base_price: float
    taxes: float
    discount: float
    total_price: float
    currency: str = "INR"
    breakdown: Optional[dict] = None
# --- Quotation/Package Pricing Schemas ---

class QuotationItemSchema(BaseModel):
    description: str
    detail: str
    quantity: int
    unit_price: float
    total_price: float

# Alias matching create requirements
QuotationItemCreate = QuotationItemSchema

class QuotationActivitySchema(BaseModel):
    name: str
    quantity: int
    unit_price: float
    total_price: float

# Alias matching create requirements
QuotationActivityCreate = QuotationActivitySchema

class QuotationCreate(BaseModel):
    client_name: str
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    package_label: str
    nights: int
    days: int
    num_adults: int = 2
    num_children: int = 0
    travel_date: Optional[str] = None
    items: list[QuotationItemCreate] = []
    activities: list[QuotationActivityCreate] = []
    notes: Optional[str] = None
    full_snapshot: Optional[dict] = None

# --- Quotation Response Schema ---

class QuotationResponse(BaseModel):
    id: UUID
    quote_number: str
    client_name: str
    client_email: EmailStr
    client_phone: str
    package_label: str
    travel_date: Optional[str] = None
    total_cost: float
    status: str  # Reflects QuotationStatus
    items: List[QuotationItemSchema]
    activities: List[QuotationActivitySchema]
    created_at: str # ISO format timestamp
    agent_name: Optional[str] = None
    agency_name: Optional[str] = None

    # Automatically converts datetime from SQLAlchemy into str for Pydantic
    @field_validator("created_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v):
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v) if v is not None else ""

    model_config = {"from_attributes": True}
# --- Quotation Update Schema ---

class QuotationUpdate(BaseModel):
    client_name: Optional[str] = None
    client_email: Optional[EmailStr] = None
    client_phone: Optional[str] = None
    package_label: Optional[str] = None
    total_cost: Optional[float] = None
    status: Optional[str] = None

# --- Vehicle Schemas ---

class VehicleBase(BaseModel):
    vehicle_type: str
    models: str
    capacity_pax: int
    luggage_capacity: str
    icon_emoji: Optional[str] = None
    per_day_rate: float
    per_km_rate: float
    airport_transfer_rate: float
    suitable_for: Optional[List[str]] = []
    image_url: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True

class VehicleCreate(VehicleBase):
    pass

class VehicleResponse(VehicleBase):
    id: UUID

# --- Vehicle Update Schema ---

class VehicleUpdate(BaseModel):
    vehicle_type: Optional[str] = None
    models: Optional[str] = None
    capacity_pax: Optional[int] = None
    luggage_capacity: Optional[str] = None
    per_day_rate: Optional[float] = None
    per_km_rate: Optional[float] = None
    airport_transfer_rate: Optional[float] = None
    is_active: Optional[bool] = None

# --- Vehicle Seasonal Rate Schema ---

class VehicleSeasonalRateSchema(BaseModel):
    season: str
    surcharge_per_day: float

# --- Authentication & User ---
class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    agency_name: str
    role: Optional[str] = "agent"
