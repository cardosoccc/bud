import uuid
import enum
from typing import Optional

from sqlalchemy import String, Enum, Uuid, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bud.database import Base


class AccountType(str, enum.Enum):
    credit = "credit"
    debit = "debit"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False, default=AccountType.debit)
    initial_balance: Mapped[float] = mapped_column(Numeric(precision=18, scale=2), nullable=False, default=0)
    current_balance: Mapped[float] = mapped_column(Numeric(precision=18, scale=2), nullable=False, default=0)

    projects: Mapped[list["Project"]] = relationship("Project", secondary="project_accounts", back_populates="accounts")  # noqa: F821

    transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        "Transaction",
        foreign_keys="Transaction.account_id",
        back_populates="account",
    )
