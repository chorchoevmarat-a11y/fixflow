"""SQLAlchemy models for FixFlow.

Conventions
-----------
* Every tenant-owned table carries ``org_id``. Relations between tenant tables use
  composite foreign keys ``(org_id, x_id) -> parent(org_id, id)`` so the database itself
  refuses to link records that belong to different organizations (DATA-02).
* Enumerations are stored as text guarded by CHECK constraints.
* Money is stored as integer minor units (tyiyn); quantities are whole units.
* All timestamps are timezone-aware UTC instants.
"""

import uuid
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, utcnow

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Role(StrEnum):
    REQUESTER = "REQUESTER"
    DISPATCHER = "DISPATCHER"
    ADMIN = "ADMIN"
    TECHNICIAN = "TECHNICIAN"


class RequestStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    TRIAGED = "TRIAGED"
    SCHEDULED = "SCHEDULED"
    ACCEPTED = "ACCEPTED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    REOPENED = "REOPENED"
    CLOSED = "CLOSED"
    CANCELED = "CANCELED"


OPEN_STATUSES = (
    RequestStatus.SUBMITTED,
    RequestStatus.TRIAGED,
    RequestStatus.SCHEDULED,
    RequestStatus.ACCEPTED,
    RequestStatus.IN_PROGRESS,
    RequestStatus.BLOCKED,
    RequestStatus.REOPENED,
)
RESERVING_STATUSES = (
    RequestStatus.SCHEDULED,
    RequestStatus.ACCEPTED,
    RequestStatus.IN_PROGRESS,
    RequestStatus.BLOCKED,
)
TERMINAL_STATUSES = (RequestStatus.CLOSED, RequestStatus.CANCELED)


class Priority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class AssetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"
    RETIRED = "RETIRED"


class AssignmentStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    UNASSIGNED = "UNASSIGNED"
    RESCHEDULED = "RESCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"


class EstimateStatus(StrEnum):
    DRAFT = "DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class Recurrence(StrEnum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class NoteVisibility(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"


class EvidenceKind(StrEnum):
    INTAKE = "INTAKE"
    NOTE = "NOTE"
    COMPLETION = "COMPLETION"


class SlaState(StrEnum):
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    OVERDUE = "OVERDUE"


class StockMovementKind(StrEnum):
    ADDITION = "ADDITION"
    CONSUMPTION = "CONSUMPTION"


class NotificationType(StrEnum):
    ASSIGNMENT_NEW = "ASSIGNMENT_NEW"
    ASSIGNMENT_CHANGED = "ASSIGNMENT_CHANGED"
    ASSIGNMENT_DECLINED = "ASSIGNMENT_DECLINED"
    ESTIMATE_SUBMITTED = "ESTIMATE_SUBMITTED"
    ESTIMATE_DECISION = "ESTIMATE_DECISION"
    JOB_COMPLETED = "JOB_COMPLETED"
    REWORK_REQUESTED = "REWORK_REQUESTED"
    SLA_OVERDUE = "SLA_OVERDUE"


# Foreign keys are checked at COMMIT. Rows of one transaction may therefore be written
# in any order, while a transaction that would leave a dangling or cross-organization
# reference still cannot commit.
DEFERRED: dict[str, Any] = {"deferrable": True, "initially": "DEFERRED"}


def _enum_check(column: str, enum_cls: type[StrEnum]) -> CheckConstraint:
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return CheckConstraint(f"{column} IN ({values})", name=f"{column}_valid")


def _org_fk(
    column: str, table: str, *, ondelete: str = "RESTRICT", name: str | None = None
) -> ForeignKeyConstraint:
    """Composite FK that pins the child and the parent to the same organization."""
    return ForeignKeyConstraint(
        ["org_id", column],
        [f"{table}.org_id", f"{table}.id"],
        ondelete=ondelete,
        name=name,
        **DEFERRED,
    )


def _org_column() -> Mapped[uuid.UUID]:
    return mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )


TZDateTime = DateTime(timezone=True)

# ---------------------------------------------------------------------------
# Identity and organizations
# ---------------------------------------------------------------------------


class Organization(Base, IdMixin, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Bishkek")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KGS")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_request_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (CheckConstraint("currency = 'KGS'", name="currency_kgs"),)


class BusinessHours(Base, IdMixin):
    """One opening interval on one weekday (0 = Monday). No rows for a day = closed."""

    __tablename__ = "business_hours"

    org_id: Mapped[uuid.UUID] = _org_column()
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    opens_at: Mapped[time] = mapped_column(Time, nullable=False)
    closes_at: Mapped[time] = mapped_column(Time, nullable=False)

    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("closes_at > opens_at", name="interval_positive"),
        UniqueConstraint("org_id", "weekday", "opens_at"),
    )


class Holiday(Base, IdMixin):
    __tablename__ = "holidays"

    org_id: Mapped[uuid.UUID] = _org_column()
    day: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (UniqueConstraint("org_id", "day"),)


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)


class OrganizationMembership(Base, IdMixin, TimestampMixin):
    __tablename__ = "organization_memberships"

    org_id: Mapped[uuid.UUID] = _org_column()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        _enum_check("role", Role),
        UniqueConstraint("org_id", "user_id"),
        UniqueConstraint("org_id", "id"),
        Index("ix_memberships_user", "user_id"),
        Index("ix_memberships_org_role", "org_id", "role"),
    )


class AuthSession(Base, IdMixin):
    """Server-side session. Only a SHA-256 digest of the bearer token is stored."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE", **DEFERRED), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (Index("ix_auth_sessions_user", "user_id"),)


class LoginAttempt(Base, IdMixin):
    """Database-backed record used to rate limit sign-in across API workers."""

    __tablename__ = "login_attempts"

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_login_attempts_email_created", "email", "created_at"),
        Index("ix_login_attempts_ip_created", "ip_address", "created_at"),
    )


# ---------------------------------------------------------------------------
# Skills, technicians, categories
# ---------------------------------------------------------------------------


class Skill(Base, IdMixin, TimestampMixin):
    __tablename__ = "skills"

    org_id: Mapped[uuid.UUID] = _org_column()
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    __table_args__ = (UniqueConstraint("org_id", "name"), UniqueConstraint("org_id", "id"))


class TechnicianProfile(Base, IdMixin, TimestampMixin):
    __tablename__ = "technician_profiles"

    org_id: Mapped[uuid.UUID] = _org_column()
    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )
    # Compact numeric identity used by the schedule exclusion constraint.
    technician_no: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    title: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))

    __table_args__ = (
        _org_fk("membership_id", "organization_memberships"),
        UniqueConstraint("membership_id"),
        UniqueConstraint("org_id", "id"),
        UniqueConstraint("id", "technician_no"),
        Index("ix_technician_profiles_org_user", "org_id", "user_id"),
    )


class TechnicianSkill(Base):
    __tablename__ = "technician_skills"

    org_id: Mapped[uuid.UUID] = _org_column()
    technician_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)

    __table_args__ = (
        _org_fk("technician_id", "technician_profiles", ondelete="CASCADE"),
        _org_fk("skill_id", "skills", ondelete="CASCADE"),
    )


class TechnicianAvailability(Base, IdMixin):
    """Weekly working interval in the organization's local time (0 = Monday)."""

    __tablename__ = "technician_availability"

    org_id: Mapped[uuid.UUID] = _org_column()
    technician_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    starts_at: Mapped[time] = mapped_column(Time, nullable=False)
    ends_at: Mapped[time] = mapped_column(Time, nullable=False)

    __table_args__ = (
        _org_fk("technician_id", "technician_profiles", ondelete="CASCADE"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("ends_at > starts_at", name="interval_positive"),
        UniqueConstraint("technician_id", "weekday", "starts_at"),
    )


class TechnicianTimeOff(Base, IdMixin):
    __tablename__ = "technician_time_off"

    org_id: Mapped[uuid.UUID] = _org_column()
    technician_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    start_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        _org_fk("technician_id", "technician_profiles", ondelete="CASCADE"),
        CheckConstraint("end_at > start_at", name="interval_positive"),
        Index("ix_time_off_technician_start", "technician_id", "start_at"),
    )


class ServiceCategory(Base, IdMixin, TimestampMixin):
    __tablename__ = "service_categories"

    org_id: Mapped[uuid.UUID] = _org_column()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    default_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("org_id", "name"),
        UniqueConstraint("org_id", "id"),
        CheckConstraint("default_duration_minutes >= 30", name="duration_min"),
    )


class CategorySkill(Base):
    __tablename__ = "category_skills"

    org_id: Mapped[uuid.UUID] = _org_column()
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)

    __table_args__ = (
        _org_fk("category_id", "service_categories", ondelete="CASCADE"),
        _org_fk("skill_id", "skills", ondelete="CASCADE"),
    )


# ---------------------------------------------------------------------------
# Properties and assets
# ---------------------------------------------------------------------------


class Property(Base, IdMixin, TimestampMixin):
    __tablename__ = "properties"

    org_id: Mapped[uuid.UUID] = _org_column()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    contact_instructions: Mapped[str | None] = mapped_column(Text)
    # When false only requesters listed in property_requesters may file requests here.
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("org_id", "id"),
        UniqueConstraint("org_id", "name"),
    )


class PropertyRequester(Base):
    __tablename__ = "property_requesters"

    org_id: Mapped[uuid.UUID] = _org_column()
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)

    __table_args__ = (
        _org_fk("property_id", "properties", ondelete="CASCADE"),
        _org_fk("membership_id", "organization_memberships", ondelete="CASCADE"),
    )


class Asset(Base, IdMixin, TimestampMixin):
    __tablename__ = "assets"

    org_id: Mapped[uuid.UUID] = _org_column()
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(100), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(120))
    installed_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=AssetStatus.ACTIVE)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        _org_fk("property_id", "properties"),
        _enum_check("status", AssetStatus),
        UniqueConstraint("org_id", "code"),
        UniqueConstraint("org_id", "id"),
        Index("ix_assets_org_property", "org_id", "property_id"),
    )


# ---------------------------------------------------------------------------
# Service requests
# ---------------------------------------------------------------------------


class MaintenancePlan(Base, IdMixin, TimestampMixin):
    __tablename__ = "maintenance_plans"

    org_id: Mapped[uuid.UUID] = _org_column()
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default=Priority.NORMAL)
    first_date: Mapped[date] = mapped_column(Date, nullable=False)
    recurrence: Mapped[str] = mapped_column(String(10), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )

    __table_args__ = (
        _org_fk("asset_id", "assets"),
        _org_fk("category_id", "service_categories"),
        _enum_check("priority", Priority),
        _enum_check("recurrence", Recurrence),
        UniqueConstraint("org_id", "id"),
        Index("ix_maintenance_plans_org_asset", "org_id", "asset_id"),
    )


class ServiceRequest(Base, IdMixin, TimestampMixin):
    __tablename__ = "service_requests"

    org_id: Mapped[uuid.UUID] = _org_column()
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    requester_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RequestStatus.SUBMITTED)
    preferred_start_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    preferred_end_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    triage_notes: Mapped[str | None] = mapped_column(Text)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    completion_note: Mapped[str | None] = mapped_column(Text)
    blocker_reason: Mapped[str | None] = mapped_column(Text)

    # Preventive maintenance provenance (PM-02 / PM-03)
    maintenance_plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    occurrence_date: Mapped[date | None] = mapped_column(Date)

    # SLA clock (business seconds). See app/services/sla.py.
    sla_budget_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    sla_consumed_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sla_running_since: Mapped[datetime | None] = mapped_column(TZDateTime)
    sla_due_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    sla_at_risk_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    sla_overdue_from: Mapped[datetime | None] = mapped_column(TZDateTime)
    sla_stopped_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    sla_final_state: Mapped[str | None] = mapped_column(String(10))
    sla_escalated_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    completed_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    canceled_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (
        _org_fk("property_id", "properties"),
        _org_fk("asset_id", "assets"),
        _org_fk("category_id", "service_categories"),
        _org_fk("maintenance_plan_id", "maintenance_plans"),
        _org_fk("duplicate_of_id", "service_requests", name="fk_service_requests_duplicate_of"),
        _enum_check("status", RequestStatus),
        _enum_check("priority", Priority),
        CheckConstraint("char_length(title) BETWEEN 5 AND 120", name="title_length"),
        CheckConstraint("char_length(description) BETWEEN 20 AND 3000", name="description_length"),
        CheckConstraint(
            "preferred_end_at IS NULL OR preferred_start_at IS NULL "
            "OR preferred_end_at > preferred_start_at",
            name="preferred_interval",
        ),
        CheckConstraint(
            "duplicate_of_id IS NULL OR duplicate_of_id <> id", name="not_self_duplicate"
        ),
        CheckConstraint(
            "(maintenance_plan_id IS NULL) = (occurrence_date IS NULL)", name="plan_occurrence_pair"
        ),
        CheckConstraint("sla_budget_seconds > 0", name="sla_budget_positive"),
        CheckConstraint("sla_consumed_seconds >= 0", name="sla_consumed_nonnegative"),
        UniqueConstraint("org_id", "id"),
        UniqueConstraint("org_id", "number"),
        UniqueConstraint(
            "maintenance_plan_id", "occurrence_date", name="uq_request_plan_occurrence"
        ),
        Index("ix_requests_org_status", "org_id", "status"),
        Index("ix_requests_org_created", "org_id", "created_at"),
        Index("ix_requests_org_requester", "org_id", "requester_id"),
        Index("ix_requests_org_priority", "org_id", "priority"),
        Index("ix_requests_org_category", "org_id", "category_id"),
        Index("ix_requests_org_property", "org_id", "property_id"),
        Index("ix_requests_org_asset", "org_id", "asset_id"),
        Index("ix_requests_org_due", "org_id", "sla_due_at"),
        Index("ix_requests_org_completed", "org_id", "completed_at"),
    )


class SlaEvent(Base, IdMixin):
    """Append-only history that lets the SLA budget be re-derived (SLA-03)."""

    __tablename__ = "sla_events"

    org_id: Mapped[uuid.UUID] = _org_column()
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    budget_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    consumed_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    detail: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        _org_fk("request_id", "service_requests", ondelete="CASCADE"),
        Index("ix_sla_events_request", "request_id", "occurred_at"),
    )


class Assignment(Base, IdMixin, TimestampMixin):
    __tablename__ = "assignments"

    org_id: Mapped[uuid.UUID] = _org_column()
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    technician_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    technician_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    start_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AssignmentStatus.SCHEDULED
    )
    # True while the request holds the technician's time (SCHED-03).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    assigned_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    ended_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        _org_fk("request_id", "service_requests"),
        _org_fk("technician_id", "technician_profiles"),
        ForeignKeyConstraint(
            ["technician_id", "technician_no"],
            ["technician_profiles.id", "technician_profiles.technician_no"],
            name="fk_assignments_technician_no",
            **DEFERRED,
        ),
        _enum_check("status", AssignmentStatus),
        CheckConstraint("end_at >= start_at + interval '30 minutes'", name="min_duration"),
        CheckConstraint(
            "is_active = (status IN ('SCHEDULED', 'ACCEPTED'))", name="active_matches_status"
        ),
        UniqueConstraint("org_id", "id"),
        # SCHED-03 / SCHED-04: no two active reservations of one technician may overlap.
        # Half-open ranges make back-to-back appointments legal. Range operators are
        # native to GiST, so no extension is required.
        ExcludeConstraint(
            (text("int8range(technician_no, technician_no, '[]')"), "&&"),
            (text("tstzrange(start_at, end_at, '[)')"), "&&"),
            where=text("is_active"),
            using="gist",
            name="ex_assignments_no_overlap",
        ),
        Index(
            "uq_assignments_one_active_per_request",
            "request_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        Index("ix_assignments_org_technician_start", "org_id", "technician_id", "start_at"),
        Index("ix_assignments_request", "request_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Estimates
# ---------------------------------------------------------------------------


class Estimate(Base, IdMixin, TimestampMixin):
    __tablename__ = "estimates"

    org_id: Mapped[uuid.UUID] = _org_column()
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=EstimateStatus.DRAFT)
    labor_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    labor_rate_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    labor_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    materials_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KGS")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED)
    )
    decided_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED)
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        _org_fk("request_id", "service_requests"),
        _org_fk("previous_version_id", "estimates", name="fk_estimates_previous_version"),
        _enum_check("status", EstimateStatus),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("labor_minutes >= 0", name="labor_minutes_nonnegative"),
        CheckConstraint("labor_rate_minor >= 0", name="labor_rate_nonnegative"),
        CheckConstraint(
            "labor_total_minor >= 0 AND materials_total_minor >= 0 "
            "AND total_minor = labor_total_minor + materials_total_minor",
            name="totals_consistent",
        ),
        CheckConstraint("currency = 'KGS'", name="currency_kgs"),
        UniqueConstraint("org_id", "id"),
        UniqueConstraint("request_id", "version"),
        Index(
            "uq_estimates_one_draft_per_request",
            "request_id",
            unique=True,
            postgresql_where=text("status = 'DRAFT'"),
        ),
        Index(
            "uq_estimates_one_current_per_request",
            "request_id",
            unique=True,
            postgresql_where=text("status IN ('AWAITING_APPROVAL', 'APPROVED', 'REJECTED')"),
        ),
        Index("ix_estimates_org_status", "org_id", "status"),
    )


class EstimateLine(Base, IdMixin):
    __tablename__ = "estimate_lines"

    org_id: Mapped[uuid.UUID] = _org_column()
    estimate_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        _org_fk("estimate_id", "estimates", ondelete="CASCADE"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price_minor >= 0", name="unit_price_nonnegative"),
        CheckConstraint(
            "line_total_minor = quantity * unit_price_minor", name="line_total_consistent"
        ),
        UniqueConstraint("estimate_id", "position"),
    )


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class InventoryItem(Base, IdMixin, TimestampMixin):
    __tablename__ = "inventory_items"

    org_id: Mapped[uuid.UUID] = _org_column()
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reorder_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("stock_quantity >= 0", name="stock_nonnegative"),
        CheckConstraint("reorder_threshold >= 0", name="threshold_nonnegative"),
        CheckConstraint("unit_price_minor >= 0", name="unit_price_nonnegative"),
        UniqueConstraint("org_id", "code"),
        UniqueConstraint("org_id", "id"),
    )


class StockMovement(Base, IdMixin):
    __tablename__ = "stock_movements"

    org_id: Mapped[uuid.UUID] = _org_column()
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        _org_fk("item_id", "inventory_items"),
        _enum_check("kind", StockMovementKind),
        CheckConstraint("quantity_delta <> 0", name="delta_nonzero"),
        CheckConstraint("balance_after >= 0", name="balance_nonnegative"),
        Index("ix_stock_movements_item", "item_id", "created_at"),
    )


class MaterialUsage(Base, IdMixin):
    __tablename__ = "material_usages"

    org_id: Mapped[uuid.UUID] = _org_column()
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    technician_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_command_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        _org_fk("request_id", "service_requests"),
        _org_fk("item_id", "inventory_items"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("total_minor = quantity * unit_price_minor", name="total_consistent"),
        UniqueConstraint("org_id", "client_command_id", name="uq_material_usage_command"),
        Index("ix_material_usages_request", "request_id", "created_at"),
        Index("ix_material_usages_org_created", "org_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Notes, evidence, notifications, feedback
# ---------------------------------------------------------------------------


class WorkNote(Base, IdMixin):
    """Immutable note. There is deliberately no update path."""

    __tablename__ = "work_notes"

    org_id: Mapped[uuid.UUID] = _org_column()
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )
    author_role: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(10), nullable=False)
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    client_command_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        _org_fk("request_id", "service_requests"),
        _org_fk("assignment_id", "assignments"),
        _enum_check("visibility", NoteVisibility),
        CheckConstraint("char_length(body) BETWEEN 1 AND 4000", name="body_length"),
        UniqueConstraint("org_id", "id"),
        UniqueConstraint("org_id", "client_command_id", name="uq_work_note_command"),
        Index("ix_work_notes_request", "request_id", "created_at"),
    )


class EvidenceFile(Base, IdMixin):
    __tablename__ = "evidence_files"

    org_id: Mapped[uuid.UUID] = _org_column()
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    note_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    uploader_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(10), nullable=False, default=NoteVisibility.PUBLIC
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    client_command_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        _org_fk("request_id", "service_requests"),
        _org_fk("note_id", "work_notes"),
        _org_fk("assignment_id", "assignments"),
        _enum_check("kind", EvidenceKind),
        _enum_check("visibility", NoteVisibility),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="size_bounds"),
        CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp')", name="content_type_valid"
        ),
        UniqueConstraint("org_id", "client_command_id", name="uq_evidence_command"),
        Index("ix_evidence_request", "request_id", "created_at"),
    )


class Notification(Base, IdMixin):
    __tablename__ = "notifications"

    org_id: Mapped[uuid.UUID] = _org_column()
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE", **DEFERRED), nullable=False
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (
        _org_fk("request_id", "service_requests", ondelete="CASCADE"),
        _enum_check("type", NotificationType),
        Index("ix_notifications_recipient", "org_id", "recipient_id", "created_at"),
        Index(
            "ix_notifications_unread",
            "org_id",
            "recipient_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )


class Feedback(Base, IdMixin):
    __tablename__ = "feedback"

    org_id: Mapped[uuid.UUID] = _org_column()
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    requester_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        _org_fk("request_id", "service_requests"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        UniqueConstraint("request_id"),
    )


class AssetServiceHistory(Base, IdMixin):
    """One row per completed job on an asset; details hang off the request."""

    __tablename__ = "asset_service_history"

    org_id: Mapped[uuid.UUID] = _org_column()
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    technician_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED), nullable=False
    )
    serviced_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        _org_fk("asset_id", "assets"),
        _org_fk("request_id", "service_requests"),
        Index("ix_asset_history_asset", "asset_id", "serviced_at"),
    )


# ---------------------------------------------------------------------------
# Audit and idempotency
# ---------------------------------------------------------------------------


class AuditEvent(Base, IdMixin):
    """Append-only. A database trigger rejects UPDATE and DELETE (see migration)."""

    __tablename__ = "audit_events"

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="RESTRICT", **DEFERRED)
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT", **DEFERRED)
    )
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # False for internal-only entries that requesters must not see in a timeline.
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_audit_org_created", "org_id", "created_at"),
        Index("ix_audit_request_created", "request_id", "created_at"),
        Index("ix_audit_org_action", "org_id", "action"),
    )


class IdempotencyKey(Base, IdMixin):
    """Persistent replay record for retryable commands (API-03)."""

    __tablename__ = "idempotency_keys"

    org_id: Mapped[uuid.UUID] = _org_column()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE", **DEFERRED), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(60), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("org_id", "user_id", "scope", "key"),)
