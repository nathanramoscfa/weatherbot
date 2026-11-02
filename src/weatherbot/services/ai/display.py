# src/weatherbot/services/ai/display.py
"""How a surface links a stored product's sources: to a public NOAA page that names no point.

A stored briefing, summary, or narration keeps its sources as records (``SourceRef``: the
key, the register source, the code, the issuer, the advisory, the issuance), never a URL,
so neither the model nor an injected advisory can put a link on a page. A surface that
shows a source may link it only to the public product page of its register source, from
this fixed table: NHC's pages and the NWS alerts portal, none of which carries a query or
a coordinate. A source whose requests name a point (an NWS point or point-alert query, a
geocode) and every source the table does not hold get no link.

The module is pure: the standard library and the models' source ids only.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from weatherbot.models import SourceId

NHC_HOME: Final = "https://www.nhc.noaa.gov/"
PUBLIC_PAGES: Final[Mapping[SourceId, str]] = MappingProxyType(
    {
        "nhc-current-storms": NHC_HOME,
        "nhc-arrival-times": "https://www.nhc.noaa.gov/gis/",
        "nhc-map-tropical-weather": NHC_HOME,
        "nhc-map-tropical-summary": NHC_HOME,
        "nhc-map-breakpoints": NHC_HOME,
        "nhc-gis-rss": "https://www.nhc.noaa.gov/gis/",
        "nhc-gis-archive": "https://www.nhc.noaa.gov/gis/",
        "nhc-text-products": NHC_HOME,
        "nhc-outlook-graphics": "https://www.nhc.noaa.gov/gtwo.php",
        "nws-alerts-zone": "https://alerts.weather.gov/",
    }
)
"""Each register source's public product page; a source absent here is never linked."""


def public_page(source_id: SourceId) -> str | None:
    """Return the public page a source may link to.

    Args:
        source_id: A stored source's register id.

    Returns:
        The page, or ``None`` for a source whose requests name a point and for every
        source the table does not hold.
    """
    return PUBLIC_PAGES.get(source_id)
