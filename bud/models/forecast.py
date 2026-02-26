import uuid
from datetime import datetime
from typing import Optional
from decimal import Decimal

from sqlalchemy import String, Integer, Numeric, ForeignKey, DateTime, Uuid, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bud.database import Base


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    value: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    installment: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    budget_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    recurrence_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("recurrences.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    budget: Mapped["Budget"] = relationship("Budget", back_populates="forecasts")  # noqa: F821
    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="forecasts")  # noqa: F821
    recurrence: Mapped[Optional["Recurrence"]] = relationship(  # noqa: F821
        "Recurrence", back_populates="forecasts", foreign_keys=[recurrence_id]
    )
