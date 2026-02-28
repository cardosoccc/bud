import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Integer, Numeric, ForeignKey, DateTime, Uuid, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bud.database import Base


class Recurrence(Base):
    __tablename__ = "recurrences"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    start: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    end: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # YYYY-MM
    installments: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    base_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    value: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship("Project")  # noqa: F821
    category: Mapped[Optional["Category"]] = relationship("Category")  # noqa: F821
    forecasts: Mapped[list["Forecast"]] = relationship(  # noqa: F821
        "Forecast", back_populates="recurrence", foreign_keys="[Forecast.recurrence_id]"
    )
