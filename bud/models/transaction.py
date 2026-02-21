import uuid
from datetime import date, datetime
from typing import Optional
from decimal import Decimal

from sqlalchemy import String, Numeric, ForeignKey, Date, DateTime, func, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bud.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    value: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_counterpart: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    source_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    destination_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    counterpart_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source_account: Mapped["Account"] = relationship(  # noqa: F821
        "Account", foreign_keys=[source_account_id], back_populates="outgoing_transactions"
    )
    destination_account: Mapped["Account"] = relationship(  # noqa: F821
        "Account", foreign_keys=[destination_account_id], back_populates="incoming_transactions"
    )
    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="transactions")  # noqa: F821
    project: Mapped["Project"] = relationship("Project", back_populates="transactions")  # noqa: F821
    counterpart: Mapped[Optional["Transaction"]] = relationship(
        "Transaction", foreign_keys=[counterpart_id], remote_side="Transaction.id"
    )
