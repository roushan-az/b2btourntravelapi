import uuid
import enum

from sqlalchemy import Column, String, Boolean, ForeignKey, Integer, Enum, JSON, DateTime, func, Numeric
from sqlalchemy.orm import relationship, declarative_base, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime

Base = declarative_base()

class UserRole(enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    AGENT = "AGENT"

class QuotationStatus(enum.Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    CONFIRMED = "CONFIRMED"
    PENDING = "PENDING"

class Season(enum.Enum):
    PEAK = "PEAK"
    SUMMER = "SUMMER"
    WINTER = "WINTER"
    NEW_YEAR = "NEW_YEAR"
    LONG_WEEKEND = "LONG_WEEKEND"
    OFF_SEASON = "OFF_SEASON"

class MealPlanCode(enum.Enum):
    EP = "EP"
    CP = "CP"
    MAP = "MAP"
    AP = "AP"

# ── User Models ──────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(Enum(UserRole), default=UserRole.AGENT)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    agent_profile = relationship("Agent", back_populates="user", uselist=False)

class Agent(Base):
    __tablename__ = "agents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    agency_name = Column(String)
    is_approved = Column(Boolean, default=False)
    user = relationship("User", back_populates="agent_profile")

# ── Catalog Models ───────────────────────────────────────────────────────────
class Destination(Base):
    __tablename__ = "destinations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True)
    region = Column(String)
    image_url = Column(String)
    image_blob_name = Column(String)
    highlights = Column(JSON) # List of strings
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

class Hotel(Base):
    __tablename__ = "hotels"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    destination_id = Column(UUID(as_uuid=True), ForeignKey("destinations.id"))
    category = Column(String)
    stars = Column(Integer)
    image_url = Column(String)
    image_blob_name = Column(String)
    description = Column(String)
    amenities = Column(JSON)
    rating = Column(Numeric)
    review_count = Column(Integer)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    destination_rel = relationship("Destination")
    room_types = relationship("RoomType", back_populates="hotel")

class RoomType(Base):
    __tablename__ = "room_types"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hotel_id = Column(UUID(as_uuid=True), ForeignKey("hotels.id"))
    name = Column(String)
    max_occupancy = Column(Integer)
    extra_bed_rate = Column(Numeric)
    hotel = relationship("Hotel", back_populates="room_types")
    meal_plan_rates = relationship("MealPlanRate", back_populates="room_type")
    seasonal_rates = relationship("HotelSeasonalRate", back_populates="room_type")

class MealPlanRate(Base):
    __tablename__ = "meal_plan_rates"
    id = Column(Integer, primary_key=True)
    room_type_id = Column(UUID(as_uuid=True), ForeignKey("room_types.id"))
    meal_plan = Column(Enum(MealPlanCode))
    rate_per_night = Column(Numeric)
    room_type = relationship("RoomType", back_populates="meal_plan_rates")

class HotelSeasonalRate(Base):
    __tablename__ = "hotel_seasonal_rates"
    id = Column(Integer, primary_key=True)
    room_type_id = Column(UUID(as_uuid=True), ForeignKey("room_types.id"))
    season = Column(Enum(Season))
    meal_plan = Column(Enum(MealPlanCode))
    rate_per_night = Column(Numeric)
    room_type = relationship("RoomType", back_populates="seasonal_rates")

# ── Itinerary & Activity Models ──────────────────────────────────────────────
class ItineraryBlock(Base):
    __tablename__ = "itinerary_blocks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(String)
    day_number = Column(Integer)
    departs_from = Column(String)
    overnight_destination_id = Column(UUID(as_uuid=True), ForeignKey("destinations.id"), nullable=True)
    overnight_slug = Column(String)
    highlights = Column(JSON)
    duration_label = Column(String)
    icon = Column(String)
    image_url = Column(String)
    image_blob_name = Column(String)
    tags = Column(JSON)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

class Activity(Base):
    __tablename__ = "activities"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    destination_id = Column(UUID(as_uuid=True), ForeignKey("destinations.id"), nullable=True)
    name = Column(String, nullable=False)
    category = Column(String)
    base_price = Column(Numeric)
    child_price = Column(Numeric, nullable=True)
    duration_label = Column(String)
    image_url = Column(String)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

# ── Vehicle Models ──────────────────────────────────────────────────────────
class Vehicle(Base):
    __tablename__ = "vehicles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_type = Column(String)
    models = Column(String)
    capacity_pax = Column(Integer)
    luggage_capacity = Column(String)
    icon_emoji = Column(String)
    per_day_rate = Column(Numeric)
    per_km_rate = Column(Numeric)
    airport_transfer_rate = Column(Numeric)
    suitable_for = Column(JSON)
    image_url = Column(String)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    seasonal_rates = relationship("VehicleSeasonalRate", back_populates="vehicle")

class VehicleSeasonalRate(Base):
    __tablename__ = "vehicle_seasonal_rates"
    id = Column(Integer, primary_key=True)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"))
    season = Column(Enum(Season))
    surcharge_per_day = Column(Numeric)
    vehicle = relationship("Vehicle", back_populates="seasonal_rates")

# ── Quotation Models ─────────────────────────────────────────────────────────
class Quotation(Base):
    __tablename__ = "quotations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quote_number = Column(String, unique=True, index=True)
    agent_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    client_name = Column(String)
    client_email = Column(String)
    client_phone = Column(String)
    package_label = Column(String)
    travel_date = Column(String, nullable=True) # <--- Real database column
    base_cost = Column(Numeric)
    markup_amount = Column(Numeric)
    gst_amount = Column(Numeric)
    total_cost = Column(Numeric)
    gst_rate = Column(Numeric)
    status = Column(Enum(QuotationStatus), default=QuotationStatus.DRAFT)
    valid_until = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    full_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now())
    items = relationship("QuotationItem", back_populates="quotation")
    activities = relationship("QuotationActivity", back_populates="quotation", cascade="all, delete-orphan")
    agent_user = relationship("User")

class QuotationItem(Base):
    __tablename__ = "quotation_items"
    id = Column(Integer, primary_key=True)
    quotation_id = Column(UUID(as_uuid=True), ForeignKey("quotations.id"))
    description = Column(String)
    detail = Column(String)
    quantity = Column(Integer)
    unit_price = Column(Numeric)
    total_price = Column(Numeric)
    quotation = relationship("Quotation", back_populates="items")

class QuotationActivity(Base):
    __tablename__ = "quotation_activities"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quotation_id = Column(UUID(as_uuid=True), ForeignKey("quotations.id"), nullable=False)
    name = Column(String)
    quantity = Column(Integer)
    unit_price = Column(Numeric)
    total_price = Column(Numeric)
    quotation = relationship("Quotation", back_populates="activities")

class SeasonalPricingRule(Base):
    __tablename__ = "seasonal_pricing_rules"
    id = Column(Integer, primary_key=True)
    season = Column(Enum(Season))
    label = Column(String)
    multiplier = Column(Numeric)
    date_from = Column(String, nullable=True)
    date_to = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)


# ══════════════════════════════════════════════════════════════════════════════
# Password Reset OTP Tokens
# ══════════════════════════════════════════════════════════════════════════════

class PasswordResetOTP(Base):
    __tablename__ = "password_reset_otps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    otp_code: Mapped[str] = mapped_column(String(8), nullable=False)
    # Hashed OTP stored — never store plain OTP in DB
    otp_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship("User")