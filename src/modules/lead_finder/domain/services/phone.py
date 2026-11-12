"""Phone number normalization for duplicate detection.

Google returns a business's number twice: ``nationalPhoneNumber``
("01712-345678", "02-55012345") and ``internationalPhoneNumber``
("+880 1712-345678"). Both are kept for display. This module derives a third,
E.164 form ("+8801712345678") so the same number written two ways is
recognized as one.

It NEVER invents a number. No input, or input without enough digits to be a
phone number, normalizes to None.
"""

import re
from typing import Optional

#: Bangladesh's country calling code.
BD_COUNTRY_CODE = "880"

#: E.164 allows at most 15 digits after the "+". Fewer than 7 digits is not a
#: reachable number in any plan Google returns.
_MIN_DIGITS = 7
_MAX_DIGITS = 15


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def normalize_phone(
    national: Optional[str], international: Optional[str] = None
) -> Optional[str]:
    """The E.164 form of a business's number, or None.

    The international form is preferred, because it carries its own country
    code. A national number is assumed to be Bangladeshi (every search here
    is), so its trunk ``0`` is replaced with ``+880``.

    Args:
        national: Google's national format, e.g. "01712-345678"
        international: Google's international format, e.g. "+880 1712-345678"

    Returns:
        "+8801712345678", or None when there is no usable number
    """
    if international and international.strip().startswith("+"):
        digits = _digits(international)
        if _MIN_DIGITS <= len(digits) <= _MAX_DIGITS:
            return f"+{digits}"

    if not national:
        return None
    digits = _digits(national)
    if national.strip().startswith("+") or digits.startswith(BD_COUNTRY_CODE):
        candidate = digits
    elif digits.startswith("0"):
        candidate = BD_COUNTRY_CODE + digits[1:]
    else:
        candidate = BD_COUNTRY_CODE + digits
    if not _MIN_DIGITS <= len(candidate) <= _MAX_DIGITS:
        return None
    return f"+{candidate}"
