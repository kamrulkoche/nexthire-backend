"""
User entity — a person who can sign in to NextHire AI.

The equivalent of hgs-backend's `AdminUser`, widened to two roles: the job
seekers who register themselves, and the admins who run the collection.
"""

from datetime import datetime
from typing import Optional

from pydantic import ConfigDict, Field, field_validator
from pymongo import ASCENDING, IndexModel

from src.shared.domain.entities.audited_entity import AuditedEntity

from ..enums.user_role import UserRole
from ..enums.user_status import UserStatus


class User(AuditedEntity):
    """
    An account: a job seeker or an admin.

    Called `users` rather than HGS's `admin_users` because it is no longer
    admins only.

    Inherits from AuditedEntity: id, is_active, created_at, updated_at,
    created_by, updated_by.

    Attributes:
        name: Display name
        email: Login identifier, unique and stored lowercase
        phone: Optional contact number
        password_hash: bcrypt hash — NEVER the plaintext, NEVER serialized
        role: Access level (see UserRole)
        status: Account state (see UserStatus); only ACTIVE may sign in
        last_login_at: Updated on each successful login

    Collection: users

    Security:
        - password_hash is excluded from every response schema by construction:
          no response schema declares the field, so `from_attributes`
          conversion cannot surface it.
    """

    __collection__ = "users"
    __indexes__ = [
        IndexModel([("email", ASCENDING)], unique=True, name="uq_users_email"),
        IndexModel(
            [("role", ASCENDING), ("status", ASCENDING)], name="ix_users_role_status"
        ),
        IndexModel([("is_active", ASCENDING)], name="ix_users_is_active"),
    ]

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    name: str = Field(
        max_length=120,
        description="Display name",
    )

    email: str = Field(
        max_length=255,
        description="Email address (login identifier)",
    )

    phone: Optional[str] = Field(
        default=None,
        max_length=40,
        description="Optional contact number",
    )

    password_hash: str = Field(
        max_length=255,
        description="bcrypt password hash — never exposed through the API",
    )

    # Stored by VALUE ("seeker"), see MongoDocument.to_document.
    role: UserRole = Field(default=UserRole.SEEKER, description="Role")

    status: UserStatus = Field(
        default=UserStatus.ACTIVE,
        description="Account status: active, inactive, suspended",
    )

    last_login_at: Optional[datetime] = Field(
        default=None,
        description="Last successful login timestamp",
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        """Validate email shape and normalize to lowercase."""
        if not value or "@" not in value:
            raise ValueError("Invalid email address")
        return value.lower().strip()

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Ensure the display name is not blank."""
        value = value.strip()
        if not value:
            raise ValueError("Name must not be empty")
        return value

    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(id='{self.id}', email='{self.email}', role='{self.role}')>"

    @property
    def can_authenticate(self) -> bool:
        """Whether this account is permitted to sign in.

        Both gates matter: ``status`` is the administrative decision, and
        ``is_active`` is the soft-delete flag from AuditedEntity.
        """
        return self.status == UserStatus.ACTIVE and self.is_active

    @property
    def is_admin(self) -> bool:
        """Whether this user may manage sources, runs, jobs and users."""
        return self.role == UserRole.ADMIN
