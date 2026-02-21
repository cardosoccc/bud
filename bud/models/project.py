import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, ForeignKey, Table, Column, DateTime, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bud.database import Base

project_accounts = Table(
    "project_accounts",
    Base.metadata,
    Column("project_id", Uuid, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("account_id", Uuid, ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True),
)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("name", "user_id", name="uq_projects_name_user"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="projects")  # noqa: F821
    accounts: Mapped[list["Account"]] = relationship("Account", secondary=project_accounts, back_populates="projects")  # noqa: F821
    budgets: Mapped[list["Budget"]] = relationship("Budget", back_populates="project", cascade="all, delete-orphan")  # noqa: F821
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="project", cascade="all, delete-orphan")  # noqa: F821
