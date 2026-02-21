import uuid
from datetime import date, datetime

from sqlalchemy import String, ForeignKey, Date, DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bud.database import Base


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="budgets")  # noqa: F821
    forecasts: Mapped[list["Forecast"]] = relationship("Forecast", back_populates="budget", cascade="all, delete-orphan")  # noqa: F821
