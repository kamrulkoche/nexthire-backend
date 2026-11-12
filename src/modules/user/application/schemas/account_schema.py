"""Self-service account schemas — what a signed-in user may change about
themselves.

Deliberately narrower than ``UserUpdateSchema``: nobody edits their own role or
status (that is an admin's call on the Users screen), and the sign-in email is
fixed, as it is there.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .user_schema import _check_password


class AccountUpdateSchema(BaseModel):
    """A partial update of the caller's own profile. Omitted keys are left alone."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=40)

    @field_validator("phone")
    @classmethod
    def blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        """An emptied field means "remove the number"."""
        return value or None


class PasswordChangeSchema(BaseModel):
    """
    The caller changing their own password.

    The CURRENT password is required even though the request is already
    authenticated: a session left open on a shared office machine must not be
    enough to take the account over. Not stripped — whitespace is part of a
    password.
    """

    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., description="At least 12 characters")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        """Apply the same length rules an admin's reset does."""
        return _check_password(value)


class PasswordChangeResponseSchema(BaseModel):
    """Acknowledgement. Existing sessions stay valid until they expire."""

    message: str = Field(default="Password changed.")
