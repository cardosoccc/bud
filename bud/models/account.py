import uuid
import enum
from typing import Optional

from sqlalchemy import String, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bud.database import Base


class AccountType(str, enum.Enum):
    credit = "credit"
    debit = "debit"
    nil = "nil"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False, default=AccountType.debit)

    projects: Mapped[list["Project"]] = relationship("Project", secondary="project_accounts", back_populates="accounts")  # noqa: F821

    outgoing_transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        "Transaction",
        foreign_keys="Transaction.source_account_id",
        back_populates="source_account",
    )
    incoming_transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        "Transaction",
        foreign_keys="Transaction.destination_account_id",
        back_populates="destination_account",
    )
