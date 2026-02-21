import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, DateTime, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bud.database import Base


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", "user_id", name="uq_categories_name_user"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="categories")  # noqa: F821
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="category")  # noqa: F821
    forecasts: Mapped[list["Forecast"]] = relationship("Forecast", back_populates="category")  # noqa: F821
