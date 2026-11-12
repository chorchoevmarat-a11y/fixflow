"""
SQLAlchemy models for FixFlow Field Service Operations Platform.
All models registered here so Alembic picks them up.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RequestStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    TRIAGED = "triaged"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    PENDING_PARTS = "pending_parts"
    PENDING_ESTIMATE = "pending_estimate"
    ESTIMATE_APPROVED = "estimate_approved"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    CLOSED = "closed"


class RequestPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class AssetStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNDER_MAINTENANCE = "under_maintenance"
    DECOMMISSIONED = "decommissioned"
    LOST = "lost"


class EstimateStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class AssignmentStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EN_ROUTE = "en_route"
    ON_SITE = "on_site"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RecurrenceRule(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"
    ANNUAL = "annual"


class NoteVisibility(str, enum.Enum):
    INTERNAL = "internal"
    CLIENT = "client"
    TECHNICIAN = "technician"
    ALL = "all"


class MemberRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    DISPATCHER = "dispatcher"
    TECHNICIAN = "technician"
    CLIENT = "client"
    VIEWER = "viewer"


class InventoryTransactionType(str, enum.Enum):
    RESTOCK = "restock"
    CONSUMPTION = "consumption"
    ADJUSTMENT = "adjustment"
    TRANSFER = "transfer"
    RETURN = "return"


class AuditAction(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    STATUS_CHANGE = "status_change"
    LOGIN = "login"
    LOGOUT = "logout"
    FILE_UPLOAD = "file_upload"
    ASSIGN = "assign"
    UNASSIGN = "unassign"
    NOTE_ADD = "note_add"
    ESTIMATE_SUBMIT = "estimate_submit"
    ESTIMATE_APPROVE = "estimate_approve"
    ESTIMATE_REJECT = "estimate_reject"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    memberships: Mapped[list["OrganizationMembership"]] = relationship(back_populates="user")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="actor")


class Organization(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    logo_url: Mapped[str | None] = mapped_column(String(1024))
    address: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC", nullable=False)
    business_hours: Mapped[dict | None] = mapped_column(JSON)  # {mon: {open: "08:00", close: "17:00"}, ...}
    sla_policy: Mapped[dict | None] = mapped_column(JSON)  # {high: 4, urgent: 1, ...} hours
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    memberships: Mapped[list["OrganizationMembership"]] = relationship(back_populates="organization")
    properties: Mapped[list["Property"]] = relationship(back_populates="organization")
    service_requests: Mapped[list["ServiceRequest"]] = relationship(back_populates="organization")
    inventory_items: Mapped[list["InventoryItem"]] = relationship(back_populates="organization")
    maintenance_plans: Mapped[list["MaintenancePlan"]] = relationship(back_populates="organization")
    holidays: Mapped[list["Holiday"]] = relationship(back_populates="organization")
    categories: Mapped[list["ServiceCategory"]] = relationship(back_populates="organization")


class OrganizationMembership(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_membership"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[MemberRole] = mapped_column(Enum(MemberRole), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    hourly_rate: Mapped[float | None] = mapped_column(Numeric(10, 2))
    skills: Mapped[list | None] = mapped_column(JSON)  # ["plumbing", "electrical"]

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships", foreign_keys=[user_id])
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="technician_membership")


class Holiday(Base, UUIDMixin):
    __tablename__ = "holidays"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="holidays")


class ServiceCategory(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "service_categories"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_category_name_per_org"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(20))  # hex color
    icon: Mapped[str | None] = mapped_column(String(100))
    sla_hours: Mapped[float | None] = mapped_column(Float)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_categories.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="categories")
    parent: Mapped["ServiceCategory | None"] = relationship(remote_side="ServiceCategory.id")
    service_requests: Mapped[list["ServiceRequest"]] = relationship(back_populates="category")


class Property(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "properties"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(10), default="US", nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    access_notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)

    organization: Mapped["Organization"] = relationship(back_populates="properties")
    assets: Mapped[list["Asset"]] = relationship(back_populates="property")
    service_requests: Mapped[list["ServiceRequest"]] = relationship(back_populates="property")


class Asset(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "assets"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_tag: Mapped[str | None] = mapped_column(String(100), index=True)
    make: Mapped[str | None] = mapped_column(String(255))
    model: Mapped[str | None] = mapped_column(String(255))
    serial_number: Mapped[str | None] = mapped_column(String(255))
    year: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus), default=AssetStatus.ACTIVE, nullable=False)
    purchase_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    warranty_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location_description: Mapped[str | None] = mapped_column(Text)
    specifications: Mapped[dict | None] = mapped_column(JSON)
    image_url: Mapped[str | None] = mapped_column(String(1024))
    qr_code: Mapped[str | None] = mapped_column(String(255))

    property: Mapped["Property"] = relationship(back_populates="assets")
    service_requests: Mapped[list["ServiceRequest"]] = relationship(back_populates="asset")
    maintenance_plans: Mapped[list["MaintenancePlan"]] = relationship(back_populates="asset")
    asset_history: Mapped[list["AssetHistory"]] = relationship(back_populates="asset")


class AssetHistory(Base, UUIDMixin):
    __tablename__ = "asset_history"

    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped["Asset"] = relationship(back_populates="asset_history")


class ServiceRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "service_requests"
    __table_args__ = (
        Index("ix_sr_org_status", "org_id", "status"),
        Index("ix_sr_org_requester", "org_id", "requester_id"),
        Index("ix_sr_org_created", "org_id", "created_at"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    requester_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id", ondelete="SET NULL"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assets.id", ondelete="SET NULL"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_categories.id", ondelete="SET NULL"))
    request_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RequestStatus] = mapped_column(Enum(RequestStatus), default=RequestStatus.SUBMITTED, nullable=False)
    priority: Mapped[RequestPriority] = mapped_column(Enum(RequestPriority), default=RequestPriority.MEDIUM, nullable=False)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_breached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(50), default="web", nullable=False)  # web, mobile, api, pm
    external_ref: Mapped[str | None] = mapped_column(String(255))  # for maintenance-generated
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)

    organization: Mapped["Organization"] = relationship(back_populates="service_requests")
    property: Mapped["Property | None"] = relationship(back_populates="service_requests")
    asset: Mapped["Asset | None"] = relationship(back_populates="service_requests")
    category: Mapped["ServiceCategory | None"] = relationship(back_populates="service_requests")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="service_request")
    estimates: Mapped[list["Estimate"]] = relationship(back_populates="service_request")
    work_notes: Mapped[list["WorkNote"]] = relationship(back_populates="service_request")
    file_attachments: Mapped[list["FileAttachment"]] = relationship(back_populates="service_request")
    material_usages: Mapped[list["MaterialUsage"]] = relationship(back_populates="service_request")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="service_request")


class Assignment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "assignments"
    __table_args__ = (
        Index("ix_assignment_tech_time", "technician_id", "start_at", "end_at"),
    )

    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    technician_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organization_memberships.id", ondelete="CASCADE"), nullable=False)
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[AssignmentStatus] = mapped_column(Enum(AssignmentStatus), default=AssignmentStatus.PENDING, nullable=False)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    en_route_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    on_site_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    travel_minutes: Mapped[int | None] = mapped_column(Integer)
    work_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    service_request: Mapped["ServiceRequest"] = relationship(back_populates="assignments")
    technician_membership: Mapped["OrganizationMembership"] = relationship(back_populates="assignments")


class Estimate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "estimates"

    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[EstimateStatus] = mapped_column(Enum(EstimateStatus), default=EstimateStatus.DRAFT, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    labor_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    materials_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    other_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0, nullable=False)
    total_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    line_items: Mapped[list | None] = mapped_column(JSON)  # [{description, qty, unit_price, total}]

    service_request: Mapped["ServiceRequest"] = relationship(back_populates="estimates")


class WorkNote(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "work_notes"
    __table_args__ = (
        UniqueConstraint("client_command_id", name="uq_work_note_command"),
    )

    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[NoteVisibility] = mapped_column(Enum(NoteVisibility), default=NoteVisibility.INTERNAL, nullable=False)
    client_command_id: Mapped[str | None] = mapped_column(String(255), unique=True)  # idempotency key
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)

    service_request: Mapped["ServiceRequest"] = relationship(back_populates="work_notes")
    file_attachments: Mapped[list["FileAttachment"]] = relationship(back_populates="work_note")


class FileAttachment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "file_attachments"

    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    service_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"))
    work_note_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("work_notes.id", ondelete="CASCADE"))
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    service_request: Mapped["ServiceRequest | None"] = relationship(back_populates="file_attachments")
    work_note: Mapped["WorkNote | None"] = relationship(back_populates="file_attachments")


class InventoryItem(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "sku", name="uq_inventory_sku_per_org"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sku: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[str] = mapped_column(String(50), default="each", nullable=False)
    unit_cost: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    stock_quantity: Mapped[float] = mapped_column(Numeric(12, 3), default=0, nullable=False)
    min_stock_level: Mapped[float | None] = mapped_column(Numeric(12, 3))
    max_stock_level: Mapped[float | None] = mapped_column(Numeric(12, 3))
    location: Mapped[str | None] = mapped_column(String(255))
    supplier: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="inventory_items")
    transactions: Mapped[list["InventoryTransaction"]] = relationship(back_populates="item")
    material_usages: Mapped[list["MaterialUsage"]] = relationship(back_populates="item")


class InventoryTransaction(Base, UUIDMixin):
    __tablename__ = "inventory_transactions"

    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_type: Mapped[InventoryTransactionType] = mapped_column(Enum(InventoryTransactionType), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(10, 2))
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # service_request or other ref
    notes: Mapped[str | None] = mapped_column(Text)
    performed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    transacted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped["InventoryItem"] = relationship(back_populates="transactions")


class MaterialUsage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "material_usages"
    __table_args__ = (
        UniqueConstraint("client_command_id", name="uq_material_usage_command"),
    )

    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total_cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    client_command_id: Mapped[str | None] = mapped_column(String(255), unique=True)  # idempotency key
    notes: Mapped[str | None] = mapped_column(Text)

    service_request: Mapped["ServiceRequest"] = relationship(back_populates="material_usages")
    item: Mapped["InventoryItem"] = relationship(back_populates="material_usages")


class MaintenancePlan(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "maintenance_plans"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assets.id", ondelete="SET NULL"))
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id", ondelete="SET NULL"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_categories.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    recurrence: Mapped[RecurrenceRule] = mapped_column(Enum(RecurrenceRule), nullable=False)
    next_occurrence: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    advance_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)  # generate SR X days before
    priority: Mapped[RequestPriority] = mapped_column(Enum(RequestPriority), default=RequestPriority.MEDIUM, nullable=False)
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped["Organization"] = relationship(back_populates="maintenance_plans")
    asset: Mapped["Asset | None"] = relationship(back_populates="maintenance_plans")
    occurrences: Mapped[list["MaintenancePlanOccurrence"]] = relationship(back_populates="plan")


class MaintenancePlanOccurrence(Base, UUIDMixin):
    __tablename__ = "maintenance_plan_occurrences"
    __table_args__ = (
        UniqueConstraint("plan_id", "occurrence_date", name="uq_plan_occurrence_date"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("maintenance_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    service_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="SET NULL"))
    occurrence_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    plan: Mapped["MaintenancePlan"] = relationship(back_populates="occurrences")


class Notification(Base, UUIDMixin):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(100), nullable=False)  # assignment, sla_breach, etc.
    reference_type: Mapped[str | None] = mapped_column(String(100))
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="notifications")


class AuditEvent(Base, UUIDMixin):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_org_created", "org_id", "created_at"),
        Index("ix_audit_sr", "service_request_id", "created_at"),
    )

    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    service_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="SET NULL"))
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    old_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    actor: Mapped["User | None"] = relationship(back_populates="audit_events")
    service_request: Mapped["ServiceRequest | None"] = relationship(back_populates="audit_events")

