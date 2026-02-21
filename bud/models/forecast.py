import uuid
from datetime import date, datetime
from typing import Optional
from decimal import Decimal

from sqlalchemy import String, Numeric, ForeignKey, Date, DateTime, func, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bud.database import Base


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    min_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=15, scale=2), nullable=True)
    max_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=15, scale=2), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_recurrent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurrent_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    recurrent_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    budget: Mapped["Budget"] = relationship("Budget", back_populates="forecasts")  # noqa: F821
    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="forecasts")  # noqa: F821
