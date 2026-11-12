"""Preset business categories for the search form.

A preset is a label and the keyword sent to Text Search. Any other keyword can
be typed; the preset key is only stored so history can show the category.
"""

from typing import Dict, List

#: key -> (label, keyword sent to Google)
CATEGORIES: Dict[str, tuple[str, str]] = {
    "hospital": ("Hospital", "Hospital"),
    "clinic": ("Clinic", "Clinic"),
    "diagnostic_center": ("Diagnostic Center", "Diagnostic Center"),
    "pharmacy": ("Pharmacy", "Pharmacy"),
    "dental_clinic": ("Dental Clinic", "Dental Clinic"),
    "restaurant": ("Restaurant", "Restaurant"),
    "cafe": ("Cafe", "Cafe"),
    "hotel": ("Hotel", "Hotel"),
    "resort": ("Resort", "Resort"),
    "school": ("School", "School"),
    "college": ("College", "College"),
    "university": ("University", "University"),
    "coaching_center": ("Coaching Center", "Coaching Center"),
    "real_estate": ("Real Estate", "Real Estate Agency"),
    "it_company": ("IT Company", "IT Company"),
    "shopping_mall": ("Shopping Mall", "Shopping Mall"),
    "supermarket": ("Supermarket", "Supermarket"),
    "beauty_salon": ("Beauty Salon / Parlour", "Beauty Parlour"),
    "gym": ("Gym / Fitness", "Gym"),
    "car_dealer": ("Car Dealer", "Car Showroom"),
    "travel_agency": ("Travel Agency", "Travel Agency"),
    "furniture_store": ("Furniture Store", "Furniture Shop"),
    "electronics_store": ("Electronics Store", "Electronics Shop"),
    "garment_factory": ("Garment Factory", "Garment Factory"),
    "law_firm": ("Law Firm", "Law Firm"),
    "accounting_firm": ("Accounting Firm", "Chartered Accountant Firm"),
    "event_management": ("Event Management", "Event Management Company"),
    "printing_press": ("Printing Press", "Printing Press"),
}


def category_list() -> List[dict]:
    """The presets, in display order, for the catalog endpoint."""
    return [
        {"key": key, "label": label, "keyword": keyword}
        for key, (label, keyword) in CATEGORIES.items()
    ]


def is_known_category(key: str) -> bool:
    """Whether a preset key exists."""
    return key in CATEGORIES
