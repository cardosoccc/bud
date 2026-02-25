import uuid
from datetime import date, datetime
from typing import Optional
from decimal import Decimal

from sqlalchemy import String, Numeric, ForeignKey, Date, DateTime, Uuid, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bud.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    value: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["Account"] = relationship(  # noqa: F821
        "Account", foreign_keys=[account_id], back_populates="transactions"
    )
    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="transactions")  # noqa: F821
    project: Mapped["Project"] = relationship("Project", back_populates="transactions")  # noqa: F821
