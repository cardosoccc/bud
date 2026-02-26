import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bud.database import Base


class Recurrence(Base):
    __tablename__ = "recurrences"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    start: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    end: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # YYYY-MM
    installments: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    base_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    original_forecast_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("forecasts.id", ondelete="CASCADE", use_alter=True), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    original_forecast: Mapped["Forecast"] = relationship(  # noqa: F821
        "Forecast", foreign_keys=[original_forecast_id]
    )
    project: Mapped["Project"] = relationship("Project")  # noqa: F821
    forecasts: Mapped[list["Forecast"]] = relationship(  # noqa: F821
        "Forecast", back_populates="recurrence", foreign_keys="[Forecast.recurrence_id]"
    )
