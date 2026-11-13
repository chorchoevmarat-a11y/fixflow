import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class _Clock:
    """Application clock.

    Production always reads the real UTC time. The deterministic seed and the test suite
    may pin the clock to replay a history (for example "Friday 17:30") through the real
    code paths. A pinned clock still ticks by one microsecond per read so that events
    written in one step keep a strict order.
    """

    def __init__(self) -> None:
        self._pinned: datetime | None = None

    def now(self) -> datetime:
        if self._pinned is None:
            return datetime.now(UTC)
        self._pinned += timedelta(microseconds=1)
        return self._pinned

    def pin(self, instant: datetime) -> None:
        self._pinned = instant.astimezone(UTC)

    def release(self) -> None:
        self._pinned = None


clock = _Clock()


def utcnow() -> datetime:
    return clock.now()


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )
