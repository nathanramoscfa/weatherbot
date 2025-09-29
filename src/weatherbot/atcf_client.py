# src/weatherbot/atcf_client.py
"""ATCF (Automated Tropical Cyclone Forecasting) client for precise storm positions."""

import logging
import re
from datetime import UTC, datetime
from urllib.parse import urljoin

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .cache import api_cache

logger = logging.getLogger(__name__)

# ATCF FTP URLs
ATCF_BASE = "https://ftp.nhc.noaa.gov/atcf/"
ATCF_BTK = urljoin(ATCF_BASE, "btk/")

# Pattern for invest files (AL93, EP96, etc.)
INVEST_FILE_RE = re.compile(
    r"""
    b           # b-deck / best-track-in-ops
    (al|ep|cp)  # basin: Atlantic / East Pac / Central Pac
    (9\d)       # invest numbers 90-99
    (\d{4})     # year
    \.dat$
    """,
    re.IGNORECASE | re.VERBOSE,
)

REQUEST_TIMEOUT = 30


class ATCFClient:
    """Client for fetching ATCF invest track data."""

    def __init__(self, timeout: int = REQUEST_TIMEOUT) -> None:
        """Initialize ATCF client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "weatherbot (alerts@example.com)"
        })

    @retry(
        retry=retry_if_exception_type((requests.RequestException,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def _make_request(self, url: str) -> str:
        """Make HTTP request with caching.

        Args:
            url: Request URL

        Returns:
            Response text
        """
        import hashlib
        cache_key = f"atcf_{hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()}"

        # Try cache first (shorter TTL for ATCF data - updates more frequently)
        cached_data = api_cache.get(cache_key)
        if cached_data is not None:
            logger.debug(f"Using cached ATCF data for: {url}")
            return cached_data.get("text", "")

        logger.debug(f"Making ATCF request to: {url}")
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        text = response.text

        # Cache with shorter TTL (1 hour for ATCF)
        cache_data = {"text": text}
        api_cache.set(cache_key, cache_data)

        return text

    def get_invest_files(self) -> list[str]:
        """Get list of current invest file URLs.

        Returns:
            List of ATCF invest file URLs
        """
        try:
            html = self._make_request(ATCF_BTK)

            # Find invest files in directory listing
            candidates = re.findall(r'href="([^"]+\.dat)"', html, flags=re.IGNORECASE)
            urls = []

            for name in candidates:
                if INVEST_FILE_RE.search(name):
                    urls.append(urljoin(ATCF_BTK, name))

            logger.info(f"Found {len(urls)} ATCF invest files")
            return sorted(set(urls))

        except Exception as e:
            logger.error(f"Failed to get ATCF invest files: {e}")
            return []

    def parse_atcf_file(self, url: str) -> list[dict]:
        """Parse a single ATCF file.

        Args:
            url: ATCF file URL

        Returns:
            List of track points
        """
        try:
            text = self._make_request(url)
            return self._parse_atcf_text(text, url)
        except Exception as e:
            logger.warning(f"Failed to parse ATCF file {url}: {e}")
            return []

    def _parse_atcf_text(self, text: str, source_url: str) -> list[dict]:
        """Parse ATCF text format.

        Args:
            text: ATCF file content
            source_url: Source URL for reference

        Returns:
            List of parsed track points
        """
        points = []

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 10:
                continue

            try:
                basin = parts[0]
                invest_num = parts[1]
                ymdh = parts[2]  # YYYYMMDDHH
                tech = parts[4]  # BEST for best track
                tau = parts[5]   # Forecast hour (0 = current)
                lat_token = parts[6]  # e.g., '131N'
                lon_token = parts[7]  # e.g., '426W'
                wind_kt = parts[8]
                pres_mb = parts[9]
                status = parts[10] if len(parts) > 10 else ""

                # Only use BEST track entries (not forecasts)
                if tech != "BEST":
                    continue

                # Parse timestamp
                try:
                    dt = datetime.strptime(ymdh, "%Y%m%d%H").replace(tzinfo=UTC)
                    iso_time = dt.isoformat()
                except Exception:
                    continue

                # Parse coordinates (ATCF uses tenths)
                lat = self._atcf_coord_to_float(lat_token)
                lon = self._atcf_coord_to_float(lon_token)

                if lat is None or lon is None:
                    continue

                # Parse intensity
                try:
                    wind = int(wind_kt) if wind_kt and wind_kt != "-999" else None
                except (ValueError, TypeError):
                    wind = None

                try:
                    pressure = int(pres_mb) if pres_mb and pres_mb != "-999" else None
                except (ValueError, TypeError):
                    pressure = None

                invest_id = f"{basin.upper()}{invest_num}"

                points.append({
                    "invest_id": invest_id,
                    "basin": basin.upper(),
                    "timestamp": iso_time,
                    "lat": lat,
                    "lon": lon,
                    "status": status,
                    "wind_kt": wind,
                    "pressure_mb": pressure,
                    "tau": int(tau) if tau.isdigit() else 0,
                    "source": source_url,
                })

            except Exception as e:
                logger.debug(f"Failed to parse ATCF line: {line[:50]}... Error: {e}")
                continue

        return points

    def _atcf_coord_to_float(self, token: str) -> float | None:
        """Convert ATCF coordinate to float.

        Args:
            token: ATCF coordinate token (e.g., '131N', '426W')

        Returns:
            Coordinate as float or None
        """
        try:
            s = token.strip().upper().replace(" ", "")
            if not s or s == "-999":
                return None

            hemi = s[-1]
            val = s[:-1]

            # Insert decimal before last digit (ATCF uses tenths)
            if val and val.isdigit() and len(val) >= 2:
                val = val[:-1] + "." + val[-1]

            x = float(val)
            if hemi in ("S", "W"):
                x = -x
            return x

        except Exception:
            return None

    def get_current_invest_positions(self) -> dict[str, tuple[float, float]]:
        """Get current positions of all active invests.

        Returns:
            Dictionary mapping invest_id to (lat, lon)
        """
        invest_files = self.get_invest_files()
        current_positions = {}

        for url in invest_files:
            try:
                points = self.parse_atcf_file(url)
                if not points:
                    continue

                # Get the most recent position (highest timestamp, tau=0)
                current_points = [p for p in points if p["tau"] == 0]
                if current_points:
                    # Sort by timestamp and take the latest
                    latest = max(current_points, key=lambda x: x["timestamp"])
                    invest_id = latest["invest_id"]
                    position = (latest["lat"], latest["lon"])
                    current_positions[invest_id] = position

                    logger.info(f"ATCF position for {invest_id}: {position}")

            except Exception as e:
                logger.warning(f"Failed to process ATCF file {url}: {e}")
                continue

        return current_positions


def get_atcf_invest_positions() -> dict[str, tuple[float, float]]:
    """Get current ATCF invest positions.

    Returns:
        Dictionary mapping invest_id to (lat, lon)
    """
    client = ATCFClient()
    return client.get_current_invest_positions()
