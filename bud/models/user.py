import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bud.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    projects: Mapped[list["Project"]] = relationship("Project", back_populates="user", cascade="all, delete-orphan")  # noqa: F821
    categories: Mapped[list["Category"]] = relationship("Category", back_populates="user", cascade="all, delete-orphan")  # noqa: F821
