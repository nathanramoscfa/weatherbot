# src/weatherbot/sources/markup.py
"""The one way a source parses XML from the network: ``defusedxml``, with no DTD at all.

KML, RSS, and WMS capabilities arrive from the network, so no client parses them with the
standard library's parsers. ``parse_xml`` refuses a document that declares a DTD (and so
any entity, internal or external) or is not well formed, as a ``SourceSchemaError``.
``XmlElement`` is the part of an element tree the clients read; the standard library's
element satisfies it, and naming it here keeps every client free of ``xml.etree``.
"""

from collections.abc import Iterator
from typing import Final, Protocol

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from weatherbot.models import SourceId
from weatherbot.sources.errors import SourceSchemaError

_NAMESPACE_END: Final = "}"


class XmlElement(Protocol):
    """An element of a parsed document: its tag, text, attributes, and children."""

    @property
    def tag(self) -> str:
        """``{namespace}local`` or ``local``."""
        ...

    @property
    def text(self) -> str | None:
        """The text before the first child."""
        ...

    def get(self, key: str, default: None = None) -> str | None:
        """Return an attribute's value."""
        ...

    def iter(self, tag: str | None = None) -> Iterator["XmlElement"]:
        """Iterate this element and its descendants, in document order."""
        ...

    def __iter__(self) -> Iterator["XmlElement"]:
        """Iterate the direct children."""
        ...


def parse_xml(body: bytes, source_id: SourceId, what: str) -> XmlElement:
    """Parse an XML payload with ``defusedxml``, refusing any DTD.

    Args:
        body: The payload.
        source_id: The register id, for the error.
        what: What the payload is, for the error.

    Returns:
        The root element.

    Raises:
        SourceSchemaError: The payload declares a DTD or an entity, or is not well formed.
    """
    try:
        return fromstring(body, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as error:
        message = f"{what} declares a DTD or an entity, which no client parses ({error!r})"
        raise SourceSchemaError(source_id, message) from None
    except ParseError as error:
        message = f"{what} is not well-formed XML (line {error.position[0]})"
        raise SourceSchemaError(source_id, message) from None


def local_name(element: XmlElement) -> str:
    """Return an element's tag without its namespace.

    Args:
        element: The element.

    Returns:
        ``Placemark`` for ``{http://www.opengis.net/kml/2.2}Placemark``.
    """
    return element.tag.rpartition(_NAMESPACE_END)[2]


def namespace_of(element: XmlElement) -> str | None:
    """Return an element's namespace URI.

    Args:
        element: The element.

    Returns:
        The URI, or ``None`` for an element in no namespace.
    """
    if element.tag.startswith("{"):
        return element.tag[1:].partition(_NAMESPACE_END)[0]
    return None


def children(element: XmlElement, name: str, namespace: str | None = None) -> list[XmlElement]:
    """Return the direct children with this local name in this namespace.

    Args:
        element: The parent.
        name: The local name.
        namespace: The namespace URI, or ``None`` for no namespace.

    Returns:
        The children, in document order.
    """
    return [
        child for child in element if local_name(child) == name and namespace_of(child) == namespace
    ]


def text_of(element: XmlElement) -> str:
    """Return an element's text, stripped; an empty element gives an empty string.

    Args:
        element: The element.

    Returns:
        The text.
    """
    return (element.text or "").strip()
