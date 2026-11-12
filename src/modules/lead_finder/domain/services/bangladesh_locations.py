"""Bangladesh's administrative hierarchy, and turning a selection into searches.

Country → Division → District → Upazila → Area.

The 8 divisions, all 64 districts and their upazilas are listed here. City
corporations (Dhaka North / South, Chattogram, Gazipur, Khulna, Rajshahi) are
listed at upazila level because that is how people search a city. "Area" is not
an administrative unit with an authoritative list, so it is free text, with a
few common suggestions under the busiest upazilas.

This file is the ONE copy of the hierarchy: the frontend's location picker
reads it from `GET /lead/locations` rather than keeping its own.

A selection is resolved into SEARCH TARGETS, one Places Text Search query each:
nothing selected (all of Bangladesh) fans out to every district; a division to
its districts; a district, upazila or area is one target.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

#: Division → district → upazilas.
DIVISIONS: Dict[str, Dict[str, List[str]]] = {
    "Barishal": {
        "Barguna": [
            "Amtali",
            "Bamna",
            "Barguna Sadar",
            "Betagi",
            "Patharghata",
            "Taltali",
        ],
        "Barishal": [
            "Agailjhara",
            "Babuganj",
            "Bakerganj",
            "Banaripara",
            "Barishal Sadar",
            "Gournadi",
            "Hizla",
            "Mehendiganj",
            "Muladi",
            "Wazirpur",
        ],
        "Bhola": [
            "Bhola Sadar",
            "Burhanuddin",
            "Char Fasson",
            "Daulatkhan",
            "Lalmohan",
            "Manpura",
            "Tazumuddin",
        ],
        "Jhalokati": ["Jhalokati Sadar", "Kathalia", "Nalchity", "Rajapur"],
        "Patuakhali": [
            "Bauphal",
            "Dashmina",
            "Dumki",
            "Galachipa",
            "Kalapara",
            "Mirzaganj",
            "Patuakhali Sadar",
            "Rangabali",
        ],
        "Pirojpur": [
            "Bhandaria",
            "Indurkani",
            "Kawkhali",
            "Mathbaria",
            "Nazirpur",
            "Nesarabad",
            "Pirojpur Sadar",
        ],
    },
    "Chattogram": {
        "Bandarban": [
            "Ali Kadam",
            "Bandarban Sadar",
            "Lama",
            "Naikhongchhari",
            "Rowangchhari",
            "Ruma",
            "Thanchi",
        ],
        "Brahmanbaria": [
            "Akhaura",
            "Ashuganj",
            "Bancharampur",
            "Bijoynagar",
            "Brahmanbaria Sadar",
            "Kasba",
            "Nabinagar",
            "Nasirnagar",
            "Sarail",
        ],
        "Chandpur": [
            "Chandpur Sadar",
            "Faridganj",
            "Haimchar",
            "Haziganj",
            "Kachua",
            "Matlab Dakshin",
            "Matlab Uttar",
            "Shahrasti",
        ],
        "Chattogram": [
            "Chattogram City",
            "Anwara",
            "Banshkhali",
            "Boalkhali",
            "Chandanaish",
            "Fatikchhari",
            "Hathazari",
            "Karnaphuli",
            "Lohagara",
            "Mirsharai",
            "Patiya",
            "Rangunia",
            "Raozan",
            "Sandwip",
            "Satkania",
            "Sitakunda",
        ],
        "Cox's Bazar": [
            "Chakaria",
            "Cox's Bazar Sadar",
            "Eidgaon",
            "Kutubdia",
            "Maheshkhali",
            "Pekua",
            "Ramu",
            "Teknaf",
            "Ukhia",
        ],
        "Cumilla": [
            "Barura",
            "Brahmanpara",
            "Burichang",
            "Chandina",
            "Chauddagram",
            "Cumilla Adarsha Sadar",
            "Cumilla Sadar Dakshin",
            "Daudkandi",
            "Debidwar",
            "Homna",
            "Laksam",
            "Lalmai",
            "Meghna",
            "Monohargonj",
            "Muradnagar",
            "Nangalkot",
            "Titas",
        ],
        "Feni": [
            "Chhagalnaiya",
            "Daganbhuiyan",
            "Feni Sadar",
            "Fulgazi",
            "Parshuram",
            "Sonagazi",
        ],
        "Khagrachhari": [
            "Dighinala",
            "Guimara",
            "Khagrachhari Sadar",
            "Lakshmichhari",
            "Mahalchhari",
            "Manikchhari",
            "Matiranga",
            "Panchhari",
            "Ramgarh",
        ],
        "Lakshmipur": [
            "Kamalnagar",
            "Lakshmipur Sadar",
            "Raipur",
            "Ramganj",
            "Ramgati",
        ],
        "Noakhali": [
            "Begumganj",
            "Chatkhil",
            "Companiganj",
            "Hatiya",
            "Kabirhat",
            "Noakhali Sadar",
            "Senbagh",
            "Sonaimuri",
            "Subarnachar",
        ],
        "Rangamati": [
            "Baghaichhari",
            "Barkal",
            "Belaichhari",
            "Juraichhari",
            "Kaptai",
            "Kawkhali",
            "Langadu",
            "Naniarchar",
            "Rajasthali",
            "Rangamati Sadar",
        ],
    },
    "Dhaka": {
        "Dhaka": [
            "Dhaka North City",
            "Dhaka South City",
            "Dhamrai",
            "Dohar",
            "Keraniganj",
            "Nawabganj",
            "Savar",
        ],
        "Faridpur": [
            "Alfadanga",
            "Bhanga",
            "Boalmari",
            "Charbhadrasan",
            "Faridpur Sadar",
            "Madhukhali",
            "Nagarkanda",
            "Sadarpur",
            "Saltha",
        ],
        "Gazipur": [
            "Gazipur City",
            "Gazipur Sadar",
            "Kaliakair",
            "Kaliganj",
            "Kapasia",
            "Sreepur",
        ],
        "Gopalganj": [
            "Gopalganj Sadar",
            "Kashiani",
            "Kotalipara",
            "Muksudpur",
            "Tungipara",
        ],
        "Kishoreganj": [
            "Austagram",
            "Bajitpur",
            "Bhairab",
            "Hossainpur",
            "Itna",
            "Karimganj",
            "Katiadi",
            "Kishoreganj Sadar",
            "Kuliarchar",
            "Mithamain",
            "Nikli",
            "Pakundia",
            "Tarail",
        ],
        "Madaripur": ["Dasar", "Kalkini", "Madaripur Sadar", "Rajoir", "Shibchar"],
        "Manikganj": [
            "Daulatpur",
            "Ghior",
            "Harirampur",
            "Manikganj Sadar",
            "Saturia",
            "Shibalaya",
            "Singair",
        ],
        "Munshiganj": [
            "Gazaria",
            "Lohajang",
            "Munshiganj Sadar",
            "Sirajdikhan",
            "Sreenagar",
            "Tongibari",
        ],
        "Narayanganj": [
            "Araihazar",
            "Bandar",
            "Narayanganj Sadar",
            "Rupganj",
            "Sonargaon",
        ],
        "Narsingdi": [
            "Belabo",
            "Monohardi",
            "Narsingdi Sadar",
            "Palash",
            "Raipura",
            "Shibpur",
        ],
        "Rajbari": ["Baliakandi", "Goalanda", "Kalukhali", "Pangsha", "Rajbari Sadar"],
        "Shariatpur": [
            "Bhedarganj",
            "Damudya",
            "Gosairhat",
            "Naria",
            "Shariatpur Sadar",
            "Zajira",
        ],
        "Tangail": [
            "Basail",
            "Bhuapur",
            "Delduar",
            "Dhanbari",
            "Ghatail",
            "Gopalpur",
            "Kalihati",
            "Madhupur",
            "Mirzapur",
            "Nagarpur",
            "Sakhipur",
            "Tangail Sadar",
        ],
    },
    "Khulna": {
        "Bagerhat": [
            "Bagerhat Sadar",
            "Chitalmari",
            "Fakirhat",
            "Kachua",
            "Mollahat",
            "Mongla",
            "Morrelganj",
            "Rampal",
            "Sarankhola",
        ],
        "Chuadanga": ["Alamdanga", "Chuadanga Sadar", "Damurhuda", "Jibannagar"],
        "Jashore": [
            "Abhaynagar",
            "Bagherpara",
            "Chaugachha",
            "Jashore Sadar",
            "Jhikargachha",
            "Keshabpur",
            "Manirampur",
            "Sharsha",
        ],
        "Jhenaidah": [
            "Harinakunda",
            "Jhenaidah Sadar",
            "Kaliganj",
            "Kotchandpur",
            "Maheshpur",
            "Shailkupa",
        ],
        "Khulna": [
            "Khulna City",
            "Batiaghata",
            "Dacope",
            "Dighalia",
            "Dumuria",
            "Koyra",
            "Paikgachha",
            "Phultala",
            "Rupsha",
            "Terokhada",
        ],
        "Kushtia": [
            "Bheramara",
            "Daulatpur",
            "Khoksa",
            "Kumarkhali",
            "Kushtia Sadar",
            "Mirpur",
        ],
        "Magura": ["Magura Sadar", "Mohammadpur", "Shalikha", "Sreepur"],
        "Meherpur": ["Gangni", "Meherpur Sadar", "Mujibnagar"],
        "Narail": ["Kalia", "Lohagara", "Narail Sadar"],
        "Satkhira": [
            "Assasuni",
            "Debhata",
            "Kalaroa",
            "Kaliganj",
            "Satkhira Sadar",
            "Shyamnagar",
            "Tala",
        ],
    },
    "Mymensingh": {
        "Jamalpur": [
            "Bakshiganj",
            "Dewanganj",
            "Islampur",
            "Jamalpur Sadar",
            "Madarganj",
            "Melandaha",
            "Sarishabari",
        ],
        "Mymensingh": [
            "Bhaluka",
            "Dhobaura",
            "Fulbaria",
            "Gafargaon",
            "Gauripur",
            "Haluaghat",
            "Ishwarganj",
            "Muktagachha",
            "Mymensingh Sadar",
            "Nandail",
            "Phulpur",
            "Tarakanda",
            "Trishal",
        ],
        "Netrokona": [
            "Atpara",
            "Barhatta",
            "Durgapur",
            "Kalmakanda",
            "Kendua",
            "Khaliajuri",
            "Madan",
            "Mohanganj",
            "Netrokona Sadar",
            "Purbadhala",
        ],
        "Sherpur": ["Jhenaigati", "Nakla", "Nalitabari", "Sherpur Sadar", "Sreebardi"],
    },
    "Rajshahi": {
        "Bogura": [
            "Adamdighi",
            "Bogura Sadar",
            "Dhunat",
            "Dhupchanchia",
            "Gabtali",
            "Kahaloo",
            "Nandigram",
            "Sariakandi",
            "Shajahanpur",
            "Sherpur",
            "Shibganj",
            "Sonatala",
        ],
        "Chapainawabganj": [
            "Bholahat",
            "Chapainawabganj Sadar",
            "Gomastapur",
            "Nachole",
            "Shibganj",
        ],
        "Joypurhat": ["Akkelpur", "Joypurhat Sadar", "Kalai", "Khetlal", "Panchbibi"],
        "Naogaon": [
            "Atrai",
            "Badalgachhi",
            "Dhamoirhat",
            "Mahadebpur",
            "Manda",
            "Naogaon Sadar",
            "Niamatpur",
            "Patnitala",
            "Porsha",
            "Raninagar",
            "Sapahar",
        ],
        "Natore": [
            "Bagatipara",
            "Baraigram",
            "Gurudaspur",
            "Lalpur",
            "Naldanga",
            "Natore Sadar",
            "Singra",
        ],
        "Pabna": [
            "Atgharia",
            "Bera",
            "Bhangura",
            "Chatmohar",
            "Faridpur",
            "Ishwardi",
            "Pabna Sadar",
            "Santhia",
            "Sujanagar",
        ],
        "Rajshahi": [
            "Rajshahi City",
            "Bagha",
            "Bagmara",
            "Charghat",
            "Durgapur",
            "Godagari",
            "Mohanpur",
            "Paba",
            "Puthia",
            "Tanore",
        ],
        "Sirajganj": [
            "Belkuchi",
            "Chauhali",
            "Kamarkhanda",
            "Kazipur",
            "Raiganj",
            "Shahjadpur",
            "Sirajganj Sadar",
            "Tarash",
            "Ullahpara",
        ],
    },
    "Rangpur": {
        "Dinajpur": [
            "Birampur",
            "Birganj",
            "Biral",
            "Bochaganj",
            "Chirirbandar",
            "Dinajpur Sadar",
            "Ghoraghat",
            "Hakimpur",
            "Kaharole",
            "Khansama",
            "Nawabganj",
            "Parbatipur",
            "Phulbari",
        ],
        "Gaibandha": [
            "Fulchhari",
            "Gaibandha Sadar",
            "Gobindaganj",
            "Palashbari",
            "Sadullapur",
            "Saghata",
            "Sundarganj",
        ],
        "Kurigram": [
            "Bhurungamari",
            "Char Rajibpur",
            "Chilmari",
            "Kurigram Sadar",
            "Nageshwari",
            "Phulbari",
            "Rajarhat",
            "Raumari",
            "Ulipur",
        ],
        "Lalmonirhat": [
            "Aditmari",
            "Hatibandha",
            "Kaliganj",
            "Lalmonirhat Sadar",
            "Patgram",
        ],
        "Nilphamari": [
            "Dimla",
            "Domar",
            "Jaldhaka",
            "Kishoreganj",
            "Nilphamari Sadar",
            "Saidpur",
        ],
        "Panchagarh": ["Atwari", "Boda", "Debiganj", "Panchagarh Sadar", "Tetulia"],
        "Rangpur": [
            "Badarganj",
            "Gangachara",
            "Kaunia",
            "Mithapukur",
            "Pirgachha",
            "Pirganj",
            "Rangpur Sadar",
            "Taraganj",
        ],
        "Thakurgaon": [
            "Baliadangi",
            "Haripur",
            "Pirganj",
            "Ranisankail",
            "Thakurgaon Sadar",
        ],
    },
    "Sylhet": {
        "Habiganj": [
            "Ajmiriganj",
            "Bahubal",
            "Baniyachong",
            "Chunarughat",
            "Habiganj Sadar",
            "Lakhai",
            "Madhabpur",
            "Nabiganj",
            "Shayestaganj",
        ],
        "Moulvibazar": [
            "Barlekha",
            "Juri",
            "Kamalganj",
            "Kulaura",
            "Moulvibazar Sadar",
            "Rajnagar",
            "Sreemangal",
        ],
        "Sunamganj": [
            "Bishwamvarpur",
            "Chhatak",
            "Derai",
            "Dharampasha",
            "Dowarabazar",
            "Jagannathpur",
            "Jamalganj",
            "Madhyanagar",
            "Shalla",
            "Shantiganj",
            "Sunamganj Sadar",
            "Tahirpur",
        ],
        "Sylhet": [
            "Balaganj",
            "Beanibazar",
            "Bishwanath",
            "Companiganj",
            "Dakshin Surma",
            "Fenchuganj",
            "Golapganj",
            "Gowainghat",
            "Jaintiapur",
            "Kanaighat",
            "Osmani Nagar",
            "Sylhet Sadar",
            "Zakiganj",
        ],
    },
}

#: Common areas under the busiest upazilas, offered as suggestions. Keyed by
#: (district, upazila). Any other area can be typed.
AREA_SUGGESTIONS: Dict[tuple[str, str], List[str]] = {
    ("Dhaka", "Dhaka North City"): [
        "Gulshan",
        "Banani",
        "Baridhara",
        "Uttara",
        "Mirpur",
        "Pallabi",
        "Mohakhali",
        "Mohammadpur",
        "Badda",
        "Tejgaon",
        "Kafrul",
        "Khilkhet",
        "Bashundhara",
    ],
    ("Dhaka", "Dhaka South City"): [
        "Dhanmondi",
        "Motijheel",
        "Ramna",
        "Shahbagh",
        "Lalbagh",
        "Old Dhaka",
        "Jatrabari",
        "Khilgaon",
        "Hazaribagh",
        "Kamrangirchar",
        "Wari",
    ],
    ("Dhaka", "Savar"): [
        "Ashulia",
        "Hemayetpur",
        "Savar Bazar",
        "Birulia",
        "Nabinagar",
    ],
    ("Dhaka", "Keraniganj"): ["Jinjira", "Hasnabad", "Kalindi"],
    ("Chattogram", "Chattogram City"): [
        "Agrabad",
        "GEC",
        "Nasirabad",
        "Panchlaish",
        "Halishahar",
        "Chawkbazar",
        "Bahaddarhat",
        "Patenga",
        "Khulshi",
    ],
    ("Gazipur", "Gazipur City"): ["Tongi", "Board Bazar", "Konabari", "Chandra"],
    ("Narayanganj", "Narayanganj Sadar"): ["Chashara", "Fatullah", "Siddhirganj"],
    ("Sylhet", "Sylhet Sadar"): [
        "Zindabazar",
        "Amberkhana",
        "Shahjalal Upashahar",
        "Uposhohor",
    ],
    ("Khulna", "Khulna City"): ["Sonadanga", "Khalishpur", "Boyra", "Daulatpur"],
    ("Rajshahi", "Rajshahi City"): ["Shaheb Bazar", "Uposhohor", "Kazla", "Motihar"],
    ("Cox's Bazar", "Cox's Bazar Sadar"): ["Kolatoli", "Sugandha", "Laboni"],
}

#: Most characters a typed area may have.
MAX_AREA_LENGTH = 80


def slugify(value: str) -> str:
    """A stable, URL-safe code for a place name ("Cox's Bazar" -> "coxs-bazar")."""
    value = value.lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


# Lookups by slug, built once.
_DIVISION_BY_SLUG: Dict[str, str] = {slugify(d): d for d in DIVISIONS}
_DISTRICT_BY_SLUG: Dict[str, Dict[str, str]] = {
    division: {slugify(district): district for district in districts}
    for division, districts in DIVISIONS.items()
}
_UPAZILA_BY_SLUG: Dict[tuple[str, str], Dict[str, str]] = {
    (division, district): {slugify(u): u for u in upazilas}
    for division, districts in DIVISIONS.items()
    for district, upazilas in districts.items()
}


@dataclass(frozen=True)
class SearchTarget:
    """One place to run the search in — one Places Text Search query."""

    division: Optional[str]
    district: Optional[str]
    upazila: Optional[str]
    area: Optional[str]

    @property
    def key(self) -> str:
        """Identity, so a selection naming the same place twice searches once."""
        return "/".join(
            slugify(part)
            for part in (self.division, self.district, self.upazila, self.area)
            if part
        )

    @property
    def label(self) -> str:
        """Most specific first: "Ashulia, Savar, Dhaka"."""
        parts = [self.area, self.upazila, self.district]
        if not self.district and self.division:
            parts.append(f"{self.division} Division")
        return ", ".join(p for p in parts if p) or "Bangladesh"

    def query(self, keyword: str) -> str:
        """The Text Search query for a keyword here.

        "Sadar" upazilas are named with their district already ("Savar" is
        not, so the district is always appended), and "Bangladesh" anchors
        same-named places elsewhere.
        """
        if self.area or self.upazila:
            place = self.label
        elif self.district:
            place = f"{self.district} District"
        elif self.division:
            place = f"{self.division} Division"
        else:
            place = ""
        where = f"{place}, Bangladesh" if place else "Bangladesh"
        return f"{keyword} in {where}"


class UnknownLocationError(ValueError):
    """A selection named a division, district or upazila that does not exist."""


@dataclass(frozen=True)
class LocationSelection:
    """What the picker sends for one selected place. Slugs, except ``area``."""

    division: Optional[str] = None
    district: Optional[str] = None
    upazila: Optional[str] = None
    area: Optional[str] = None


def _resolve_one(selection: LocationSelection) -> List[SearchTarget]:
    """Turn one selected place into its targets.

    Raises:
        UnknownLocationError: An unknown slug, or a level given without its
            parent (an upazila needs its district and division)
    """
    if not selection.division:
        if selection.district or selection.upazila or selection.area:
            raise UnknownLocationError("Choose a division before a district.")
        return all_district_targets()

    division = _DIVISION_BY_SLUG.get(selection.division)
    if division is None:
        raise UnknownLocationError(f"Unknown division: {selection.division}")

    if not selection.district:
        if selection.upazila or selection.area:
            raise UnknownLocationError("Choose a district before an upazila.")
        return [
            SearchTarget(division, district, None, None)
            for district in DIVISIONS[division]
        ]

    district = _DISTRICT_BY_SLUG[division].get(selection.district)
    if district is None:
        raise UnknownLocationError(
            f"Unknown district in {division}: {selection.district}"
        )

    upazila: Optional[str] = None
    if selection.upazila:
        upazila = _UPAZILA_BY_SLUG[(division, district)].get(selection.upazila)
        if upazila is None:
            raise UnknownLocationError(
                f"Unknown upazila in {district}: {selection.upazila}"
            )

    area = clean_area(selection.area)
    if area and not upazila:
        raise UnknownLocationError("Choose an upazila before an area.")

    return [SearchTarget(division, district, upazila, area)]


def clean_area(value: Optional[str]) -> Optional[str]:
    """A typed area, trimmed and limited to letters, digits and simple marks.

    It ends up inside a search query, so it is reduced to what a place name
    needs. Empty means none.
    """
    if value is None:
        return None
    cleaned = re.sub(r"[^\w\s,.'()-]", " ", value, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()[:MAX_AREA_LENGTH]
    return cleaned or None


def all_district_targets() -> List[SearchTarget]:
    """All 64 districts — "all of Bangladesh"."""
    return [
        SearchTarget(division, district, None, None)
        for division, districts in DIVISIONS.items()
        for district in districts
    ]


def resolve_targets(selections: Sequence[LocationSelection]) -> List[SearchTarget]:
    """Every distinct target a whole selection covers, in a stable order.

    An empty selection means all of Bangladesh.

    Raises:
        UnknownLocationError: If any selected place is unknown
    """
    if not selections:
        return all_district_targets()
    seen: Dict[str, SearchTarget] = {}
    for selection in selections:
        for target in _resolve_one(selection):
            seen.setdefault(target.key, target)
    return list(seen.values())


def describe_selection(selections: Sequence[LocationSelection]) -> List[dict]:
    """The selection as stored on the search: code, label and level per place."""
    described = []
    for selection in selections:
        targets = _resolve_one(selection)
        # Kept verbatim so a re-run resolves exactly the same places.
        raw = {
            "division": selection.division,
            "district": selection.district,
            "upazila": selection.upazila,
            "area": clean_area(selection.area),
        }
        if selection.district:
            target = targets[0]
            level = (
                "area" if target.area else "upazila" if target.upazila else "district"
            )
            described.append(
                {
                    "code": target.key,
                    "label": target.label,
                    "level": level,
                    "selection": raw,
                }
            )
        else:
            division = _DIVISION_BY_SLUG.get(selection.division or "")
            described.append(
                {
                    "code": slugify(division) if division else "bangladesh",
                    "label": f"{division} Division" if division else "All Bangladesh",
                    "level": "division" if division else "country",
                    "selection": raw,
                }
            )
    return described


def selections_from_stored(stored: Sequence[dict]) -> List[LocationSelection]:
    """Rebuild the selections a search was started with (for a re-run)."""
    selections = []
    for item in stored:
        raw = item.get("selection") or {}
        selections.append(
            LocationSelection(
                division=raw.get("division"),
                district=raw.get("district"),
                upazila=raw.get("upazila"),
                area=raw.get("area"),
            )
        )
    return selections


def summarize_selection(described: Sequence[dict]) -> str:
    """One line for lists: "Savar, Dhaka +2 more", or "All Bangladesh"."""
    if not described:
        return "All Bangladesh"
    first = str(described[0]["label"])
    rest = len(described) - 1
    return f"{first} +{rest} more" if rest else first


def location_tree() -> List[dict]:
    """The hierarchy as the picker reads it."""
    return [
        {
            "code": slugify(division),
            "name": division,
            "districts": [
                {
                    "code": slugify(district),
                    "name": district,
                    "upazilas": [
                        {
                            "code": slugify(upazila),
                            "name": upazila,
                            "areas": AREA_SUGGESTIONS.get((district, upazila), []),
                        }
                        for upazila in upazilas
                    ],
                }
                for district, upazilas in districts.items()
            ],
        }
        for division, districts in DIVISIONS.items()
    ]


def district_count() -> int:
    """How many districts the hierarchy holds (64)."""
    return sum(len(districts) for districts in DIVISIONS.values())
