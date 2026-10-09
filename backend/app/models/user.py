"""用户-角色-权限 (RBAC) 模型."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Table, Column, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

user_role = Table(
    "user_role", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permission = Table(
    "role_permission", Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(64), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    roles: Mapped[list["Role"]] = relationship(secondary=user_role, lazy="selectin", back_populates="users")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)          # e.g. admin / operator / viewer
    description: Mapped[str] = mapped_column(String(255), default="")

    users: Mapped[list[User]] = relationship(secondary=user_role, lazy="noload", back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permission, lazy="selectin")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # e.g. admin / task:upload / rule:manage / report:view
    description: Mapped[str] = mapped_column(String(255), default="")
