"""User role enum for role-based access control."""

from enum import Enum


class UserRole(str, Enum):
    """
    Role enumeration for RBAC.

    hgs-backend ships one member (ADMIN) and notes that adding a second is "a
    new member plus a migration, not a refactor". Homesprit added AGENT; NextHire
    adds SEEKER instead — `hasAccess(roles=[...])` is unchanged.

    - ADMIN: manages job sources, watches collection runs, moderates jobs and
      users. Can also use every seeker screen.
    - SEEKER: searches jobs and manages their OWN saved jobs, applications,
      preferences, matches and notifications. Ownership is enforced in the
      repositories by filtering on the caller's id, not here.

    - LEAD_FINDER: the Business Lead Finder product. Searches Google Places
      for businesses and works its OWN searches, saved leads and exports. It
      is deliberately NOT in ``SIGNED_IN``: a lead finder cannot reach a single
      seeker or admin endpoint, and signs in through its own endpoint
      (``/auth/lead-finder/login``) into its own session.

    Self-registration on ``/auth/register`` always creates a SEEKER; the lead
    finder registration endpoint always creates a LEAD_FINDER, and only while
    an admin has it switched on.
    """

    ADMIN = "admin"
    SEEKER = "seeker"
    LEAD_FINDER = "lead_finder"

    @classmethod
    def all_roles(cls) -> list[str]:
        """Return all valid role values."""
        return [role.value for role in cls]
