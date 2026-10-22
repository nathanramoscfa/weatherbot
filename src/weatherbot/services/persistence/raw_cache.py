# src/weatherbot/services/persistence/raw_cache.py
"""The raw-response cache: every answer as received, and the persistent validator store.

``RawResponseCache`` implements ``weatherbot.sources.http.ValidatorStore`` on the
``raw_responses`` and ``response_bodies`` tables, so the ETag and Last-Modified of an
answer recorded in one run make the next run's request conditional, and a 304 is served
from the stored body. A body is stored once per SHA-256, zlib-compressed.

Only allowlisted response headers are kept (``HEADER_ALLOWLIST``); no request header is
ever stored. A URL can carry a location's coordinates: it stays in this local database,
and no record above DEBUG names it.
"""

import logging
import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from weatherbot.models import SourceId
from weatherbot.services.persistence.database import writing_session
from weatherbot.services.persistence.tables import RawResponseRow, ResponseBodyRow
from weatherbot.sources.http import (
    HEADER_ALLOWLIST,
    HTTP_NOT_MODIFIED,
    HTTP_OK,
    FetchResult,
    StoredResponse,
)

LOGGER: Final = logging.getLogger("weatherbot.services.persistence")
_VALIDATED_STATUSES: Final = (HTTP_OK, HTTP_NOT_MODIFIED)


class CorruptBodyError(Exception):
    """A stored body does not decompress to its recorded size and SHA-256."""


@dataclass(frozen=True)
class CachedFetch:
    """An answer to record, with the product it carried.

    ``product_key`` names the product within its source (a layer, a storm's file, a zone),
    and ``issued_at`` is the product's own issuance when it states one.
    """

    result: FetchResult
    product_key: str
    issued_at: datetime | None = None


def _kept(headers: dict[str, str] | object) -> dict[str, str]:
    if not isinstance(headers, dict):
        return {}
    return {
        str(name).lower(): str(value)
        for name, value in sorted(headers.items())  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType] - a JSON object
        if str(name).lower() in HEADER_ALLOWLIST
    }


def store_body(session: Session, sha256: str, body: bytes) -> None:
    """Store a body once per SHA-256, zlib-compressed.

    Args:
        session: The open session.
        sha256: The body's SHA-256, as received.
        body: The body.
    """
    if session.get(ResponseBodyRow, sha256) is None:
        session.add(ResponseBodyRow(sha256=sha256, size=len(body), body=zlib.compress(body)))
        session.flush()


def read_body(row: ResponseBodyRow) -> bytes:
    """Decompress a stored body, refusing one that is not what was stored.

    Args:
        row: The stored body.

    Returns:
        The body.

    Raises:
        CorruptBodyError: It decompresses to another size.
    """
    inflater = zlib.decompressobj()
    body = inflater.decompress(row.body, row.size + 1)
    if len(body) != row.size or not inflater.eof:
        message = f"the stored body {row.sha256[:12]} is corrupt"
        raise CorruptBodyError(message)
    return body


def record_fetch(
    session: Session, result: FetchResult, product_key: str, issued_at: datetime | None
) -> RawResponseRow:
    """Record one answer in an open session, deduplicated by source, product, and body.

    An answer whose source, product, issuance, and SHA-256 are already stored refreshes
    that row: its fetch time, its validators, and its headers. A 304 refreshes the row of
    the body it confirmed.

    Args:
        session: The open session.
        result: The answer.
        product_key: The product within its source.
        issued_at: The product's issuance, when it states one.

    Returns:
        The stored row.
    """
    store_body(session, result.sha256, result.body)
    headers = _kept(dict(result.headers))
    existing = session.scalars(
        select(RawResponseRow).where(
            RawResponseRow.source_id == result.source_id,
            RawResponseRow.product_key == product_key,
            RawResponseRow.issued_at.is_not_distinct_from(issued_at),
            RawResponseRow.sha256 == result.sha256,
        )
    ).first()
    if existing is None:
        row = RawResponseRow(
            source_id=result.source_id,
            product_key=product_key,
            issued_at=issued_at,
            url=result.url,
            status=result.status,
            fetched_at=result.fetched_at,
            sha256=result.sha256,
            headers=headers,
            etag=headers.get("etag"),
            last_modified=headers.get("last-modified"),
        )
        session.add(row)
        session.flush()
        return row
    if result.fetched_at >= existing.fetched_at:
        existing.url = result.url
        existing.fetched_at = result.fetched_at
        existing.headers = {**_kept(existing.headers), **headers}
        existing.etag = headers.get("etag", existing.etag)
        existing.last_modified = headers.get("last-modified", existing.last_modified)
        session.flush()
    return existing


class RawResponseCache:
    """The persistent ``ValidatorStore``, and the recorder of every answer.

    A 200 the fetcher saves is kept for the rest of the run, and becomes durable when
    ``save_fetch`` (or ``SnapshotRepository.save``) records it; the next run's ``load``
    finds it in the database.
    """

    def __init__(self, engine: Engine) -> None:
        """Create a cache on an open database.

        Args:
            engine: The database.
        """
        self._engine = engine
        self._pending: dict[str, StoredResponse] = {}

    def load(self, url: str) -> StoredResponse | None:
        """Return the newest validated answer for ``url``: this run's, else a stored one.

        Args:
            url: The request URL.

        Returns:
            The validators and the body they cover, or ``None``.
        """
        pending = self._pending.get(url)
        if pending is not None:
            return pending
        with Session(self._engine) as session:
            found = session.execute(
                select(RawResponseRow, ResponseBodyRow)
                .join(ResponseBodyRow, ResponseBodyRow.sha256 == RawResponseRow.sha256)
                .where(
                    RawResponseRow.url == url,
                    RawResponseRow.status.in_(_VALIDATED_STATUSES),
                    (RawResponseRow.etag.is_not(None))
                    | (RawResponseRow.last_modified.is_not(None)),
                )
                .order_by(RawResponseRow.fetched_at.desc(), RawResponseRow.id.desc())
                .limit(1)
            ).first()
            if found is None:
                return None
            row, body = found
            LOGGER.debug("validators for %s from the raw-response cache", url)
            return StoredResponse(
                etag=row.etag,
                last_modified=row.last_modified,
                body=read_body(body),
                sha256=row.sha256,
                headers=_kept(row.headers),
            )

    def save(self, url: str, stored: StoredResponse) -> None:
        """Keep a validated answer for the rest of the run.

        Args:
            url: The request URL.
            stored: The validators and the body.
        """
        self._pending[url] = stored

    def save_fetch(
        self,
        result: FetchResult,
        source_id: SourceId,
        product_key: str,
        issued_at: datetime | None = None,
    ) -> int:
        """Record one answer durably, in its own transaction.

        Args:
            result: The answer.
            source_id: Its register id, which must be the answer's own.
            product_key: The product within its source.
            issued_at: The product's issuance, when it states one.

        Returns:
            The stored row's id.

        Raises:
            ValueError: ``source_id`` is not the answer's.
        """
        if source_id != result.source_id:
            message = "a fetch result is recorded under its own source id"
            raise ValueError(message)
        with writing_session(self._engine) as session:
            return record_fetch(session, result, product_key, issued_at).id
