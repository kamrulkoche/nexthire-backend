"""What the use cases need from a Places provider.

``GooglePlacesClient`` implements it; the integration suite swaps in a fake
through ``get_places_gateway_factory``, so no test calls Google.
"""

from typing import List, Optional, Protocol, Tuple

from ..value_objects.place_record import PlaceRecord


class PlacesGateway(Protocol):
    """Text Search + Place Details, counting the requests it makes."""

    requests_made: int

    @property
    def is_configured(self) -> bool:
        """Whether a key is present."""
        ...

    async def text_search(
        self, query: str, page_token: Optional[str] = None
    ) -> Tuple[List[PlaceRecord], Optional[str]]:
        """One page of results and the next page's token."""
        ...

    async def place_details(self, place_id: str) -> Optional[PlaceRecord]:
        """One place re-read, or None if Google no longer has it."""
        ...
