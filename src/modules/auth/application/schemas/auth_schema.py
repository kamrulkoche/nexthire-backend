"""Authentication request and response schemas."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.modules.user.application.schemas.user_schema import (
    UserResponseSchema,
    check_password,
)


class LoginRequestSchema(BaseModel):
    """
    An email + password sign-in.

    ``EmailStr`` gives shape validation for free; the deliberately vague
    credential error that protects against account enumeration is raised by the
    use case, not here. The password rule is only ``min_length=1``: enforcing a
    policy at LOGIN would tell an attacker what the policy is.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {"email": "you@example.com", "password": "your-password"}
        },
    )

    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., min_length=1, max_length=128, description="Password")


class RegisterRequestSchema(BaseModel):
    """
    A job seeker creating their own account.

    There is no ``role`` field: self-registration always creates a SEEKER, and
    because the field is not declared, a ``role`` sent in the body is dropped
    by Pydantic before the use case ever sees it.

    Limits mirror the frontend's `helpers/validation/auth.schema.ts`.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., description="At least 12 characters")

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """The same length rules every password here follows."""
        return check_password(value)


class LoginResponseSchema(BaseModel):
    """
    A successful login: the token plus the profile, so the client does not
    need a second round trip to ``/auth/me`` to render the dashboard header.
    """

    access_token: str = Field(..., description="Signed JWT access token")
    token_type: str = Field(default="bearer", description="Token scheme")
    expires_in: int = Field(..., description="Token lifetime in seconds")
    user: UserResponseSchema = Field(..., description="Authenticated user")


class LogoutResponseSchema(BaseModel):
    """
    A logout acknowledgement.

    As in hgs-backend, logout is client-side in v1: the Next.js route clears the
    httpOnly cookie and the token expires on its own. The endpoint exists so a
    future revocation store can be added without any frontend change.
    """

    message: str = Field(default="Signed out successfully.")
