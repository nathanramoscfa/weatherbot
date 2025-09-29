# src/weatherbot/nhc_storm_tracker.py
"""Automated tracking of individual NHC storm pages and cone graphics."""

import logging
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from shapely.geometry import Polygon
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .cache import api_cache
from .nhc import NHCCone

logger = logging.getLogger(__name__)

# NHC URLs
NHC_BASE = "https://www.nhc.noaa.gov/"
CURRENT_STORMS_JSON = "https://www.nhc.noaa.gov/CurrentStorms.json"
NHC_MAPSERVER_BASE = (
    "https://mapservices.weather.noaa.gov/tropical/rest/services/"
    "tropical/NHC_tropical_weather/MapServer"
)

REQUEST_TIMEOUT = 30


class NHCStormTracker:
    """Automated tracker for individual NHC storm pages and cone graphics."""

    def __init__(self, timeout: int = REQUEST_TIMEOUT) -> None:
        """Initialize storm tracker.

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
    def _make_request(self, url: str) -> requests.Response:
        """Make HTTP request with retry logic.

        Args:
            url: Request URL

        Returns:
            Response object
        """
        logger.debug(f"Making request to: {url}")
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response

    def discover_active_storm_pages(self) -> list[dict[str, str]]:
        """Discover all active individual storm tracking pages.

        Returns:
            List of storm page information dictionaries
        """
        storm_pages = []

        try:
            # First, get active storms from CurrentStorms.json
            current_storms = self._get_current_storms_metadata()

            for storm in current_storms:
                # Try to find the individual storm page
                storm_page = self._find_storm_page(storm)
                if storm_page:
                    # Add position data from the storm metadata
                    if isinstance(storm, dict):
                        # Extract position from dictionary
                        lat = storm.get('latitudeNumeric') or storm.get('lat') or storm.get('latitude')
                        lon = storm.get('longitudeNumeric') or storm.get('lon') or storm.get('longitude')
                        if lat is not None and lon is not None:
                            storm_page['latitude'] = float(lat)
                            storm_page['longitude'] = float(lon)
                    elif hasattr(storm, 'current_position') and storm.current_position:
                        # Extract from NHCCone object
                        storm_page['latitude'] = storm.current_position[0]
                        storm_page['longitude'] = storm.current_position[1]
                    storm_pages.append(storm_page)

            # Also scan the main NHC page for any storm links we might have missed
            additional_pages = self._scan_nhc_main_page()
            for page in additional_pages:
                # Avoid duplicates
                if not any(p['storm_id'] == page['storm_id'] for p in storm_pages):
                    storm_pages.append(page)

            logger.info(f"Discovered {len(storm_pages)} active storm pages")
            return storm_pages

        except Exception as e:
            logger.error(f"Failed to discover storm pages: {e}")
            return []

    def _get_current_storms_metadata(self) -> list[dict]:
        """Get current storms metadata from NHC API.

        Returns:
            List of storm metadata dictionaries
        """
        try:
            import hashlib
            cache_key = hashlib.md5(CURRENT_STORMS_JSON.encode(), usedforsecurity=False).hexdigest()

            # Try cache first
            cached_data = api_cache.get(cache_key)
            if cached_data is not None:
                logger.debug("Using cached CurrentStorms.json data")
                return cached_data.get("activeStorms", [])

            response = self._make_request(CURRENT_STORMS_JSON)
            data = response.json()

            # Cache the response
            api_cache.set(cache_key, data)

            return data.get("activeStorms", [])

        except Exception as e:
            logger.warning(f"Failed to get current storms metadata: {e}")
            return []

    def _find_storm_page(self, storm: dict) -> dict[str, str] | None:
        """Find the individual tracking page for a storm.

        Args:
            storm: Storm metadata dictionary

        Returns:
            Storm page information or None
        """
        try:
            # Extract storm identifiers
            storm_name = storm.get("name") or storm.get("tcName", "")
            storm_id = storm.get("id") or storm.get("tcid") or storm.get("stormNumber", "")
            basin = storm.get("basin") or storm.get("basinId", "")

            # Build potential URLs based on NHC naming conventions
            potential_urls = self._generate_storm_urls(storm_name, storm_id, basin)

            for url in potential_urls:
                try:
                    response = self._make_request(url)
                    if response.status_code == 200:
                        # Verify this is actually a storm page
                        if self._verify_storm_page(response.text, storm_name):
                            logger.info(f"Found storm page for {storm_name}: {url}")
                            return {
                                "storm_name": storm_name,
                                "storm_id": storm_id,
                                "basin": basin,
                                "page_url": url,
                                "cone_url": self._extract_cone_url(url, response.text)
                            }
                except requests.RequestException:
                    continue  # Try next URL

            logger.warning(f"Could not find storm page for {storm_name}")
            return None

        except Exception as e:
            logger.debug(f"Error finding storm page: {e}")
            return None

    def _generate_storm_urls(
        self,
        storm_name: str,
        storm_id: str,
        basin: str
    ) -> list[str]:
        """Generate potential URLs for a storm's tracking page.

        Args:
            storm_name: Storm name
            storm_id: Storm ID
            basin: Basin identifier

        Returns:
            List of potential URLs
        """
        urls = []
        base_url = NHC_BASE

        # The NHC URL pattern doesn't directly correspond to storm ID numbers
        # We need to try multiple possibilities since storms can be on different pages

        if basin.upper() == "AL" or not basin:  # Atlantic (basin might be None)
            # Try all possible Atlantic storm page numbers (1-5)
            for storm_num in range(1, 6):
                # Try both regular pages and refresh pages with cone parameter
                urls.append(f"{base_url}graphics_at{storm_num}.shtml")
                urls.append(f"{base_url}graphics_at{storm_num}.shtml?start#contents")

                # Add the specific refresh cone pages that you found
                import datetime
                now = datetime.datetime.now()
                timestamp = now.strftime("%d%H%M")  # Current day, hour, minute
                urls.append(f"{base_url}refresh/graphics_at{storm_num}+shtml/{timestamp}.shtml?cone#contents")

                # Also try some common timestamp patterns
                for ts_pattern in ["250251", "250250", "242034"]:
                    urls.append(f"{base_url}refresh/graphics_at{storm_num}+shtml/{ts_pattern}.shtml?cone#contents")

        elif basin.upper() == "EP":  # Eastern Pacific
            # Try all possible Eastern Pacific storm page numbers (1-5)
            for storm_num in range(1, 6):
                urls.append(f"{base_url}graphics_ep{storm_num}.shtml")
                urls.append(f"{base_url}graphics_ep{storm_num}.shtml?start#contents")

                # Add refresh cone pages for Eastern Pacific
                import datetime
                now = datetime.datetime.now()
                timestamp = now.strftime("%d%H%M")
                urls.append(f"{base_url}refresh/graphics_ep{storm_num}+shtml/{timestamp}.shtml?cone#contents")

                for ts_pattern in ["250251", "250250", "242034"]:
                    urls.append(f"{base_url}refresh/graphics_ep{storm_num}+shtml/{ts_pattern}.shtml?cone#contents")

        # Also try with storm name if available
        if storm_name:
            clean_name = storm_name.lower().replace(" ", "")
            urls.append(f"{base_url}graphics_{clean_name}.shtml")

        return urls

    def _verify_storm_page(self, html_content: str, storm_name: str) -> bool:
        """Verify that an HTML page is actually a storm tracking page.

        Args:
            html_content: HTML content to check
            storm_name: Expected storm name

        Returns:
            True if this appears to be a valid storm page
        """
        try:
            # Check for storm name in the content (case insensitive)
            content_upper = html_content.upper()
            storm_name_upper = storm_name.upper()

            # Must contain the storm name
            if storm_name_upper not in content_upper:
                return False

            # Must contain storm-specific indicators
            storm_indicators = [
                'TROPICAL STORM',
                'HURRICANE',
                'FORECAST CONE',
                'CONE GRAPHIC',
                'ADVISORY',
                'WARNING',
                'WATCH'
            ]

            indicator_count = sum(1 for indicator in storm_indicators if indicator in content_upper)

            # Must have at least 2 storm indicators to be considered a valid storm page
            return indicator_count >= 2

        except Exception as e:
            logger.debug(f"Error verifying storm page: {e}")
            return False

    def _extract_cone_url(self, page_url: str, html_content: str) -> str | None:
        """Extract the cone graphic URL from a storm page.

        Args:
            page_url: Storm page URL
            html_content: HTML content of the page

        Returns:
            Cone graphic URL or None
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # Look for cone graphic images with multiple strategies
            cone_urls = []

            # Strategy 1: Look for images with cone-related src attributes
            # Prioritize the specific cone images from refresh pages
            cone_patterns = [
                r'.*5day_cone_no_line_and_wind.*\.png',  # Highest priority - your specific pattern
                r'.*cone.*\.png',
                r'.*5day.*cone.*\.png',
                r'.*forecast.*cone.*\.png',
                r'storm_graphics.*\.png'
            ]

            for img in soup.find_all('img'):
                src = img.get('src', '')
                alt = img.get('alt', '')

                # Prioritize images with "Warnings and 5-Day Cone" alt text (from your examples)
                if 'warnings and 5-day cone' in alt.lower() or '5day_cone_no_line_and_wind' in src.lower():
                    if src.startswith('/'):
                        full_url = urljoin(NHC_BASE, src)
                    elif src.startswith('http'):
                        full_url = src
                    else:
                        full_url = urljoin(page_url, src)

                    # Convert small version to full-size version
                    if '_sm+png/' in full_url and '_sm.png' in full_url:
                        # Convert from: /storm_graphics/AT08/refresh/AL082025_5day_cone_no_line_and_wind_sm+png/250251_5day_cone_no_line_and_wind_sm.png
                        # To: /storm_graphics/AT08/refresh/AL082025_5day_cone_no_line_and_wind+png/250251_5day_cone_no_line_and_wind.png
                        full_size_url = full_url.replace('_sm+png/', '+png/').replace('_sm.png', '.png')
                        cone_urls.insert(0, full_size_url)  # Insert full-size at beginning for priority
                        logger.info(f"Found priority cone image (full-size): {full_size_url}")
                    else:
                        cone_urls.insert(0, full_url)  # Insert at beginning for priority
                        logger.info(f"Found priority cone image: {full_url}")
                    continue

                # Check other patterns
                for pattern in cone_patterns:
                    if re.search(pattern, src, re.IGNORECASE):
                        # Convert relative URL to absolute
                        if src.startswith('/'):
                            full_url = urljoin(NHC_BASE, src)
                        elif src.startswith('http'):
                            full_url = src
                        else:
                            full_url = urljoin(page_url, src)
                        cone_urls.append(full_url)

            # Strategy 2: Look for cone graphic links in the HTML content
            # Pattern like: storm_graphics/AT08/refresh/AL082025_5day_cone_no_line_and_wind+png/242034.png
            # Also look for the specific pattern from your examples
            cone_link_patterns = [
                r'/storm_graphics/[A-Z]{2}\d+/refresh/[A-Z]{2}\d+2025_5day_cone_no_line_and_wind_sm\+png/\d+_5day_cone_no_line_and_wind_sm\.png',  # Your exact pattern
                r'storm_graphics/[A-Z]{2}\d+/refresh/[A-Z]{2}\d+2025_5day_cone[^"\']*\.png',
                r'storm_graphics/[A-Z]{2}\d+/[^"\']*cone[^"\']*\.png',
                r'/refresh/[A-Z]{2}\d+2025[^"\']*cone[^"\']*\.png'
            ]

            for pattern in cone_link_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                for match in matches:
                    if not match.startswith('http'):
                        full_url = urljoin(NHC_BASE, match)
                    else:
                        full_url = match
                    cone_urls.append(full_url)

            # Strategy 3: Extract storm ID and construct expected cone URL
            storm_id_match = re.search(r'(AL|EP)(\d{2})2025', html_content)
            if storm_id_match:
                basin = storm_id_match.group(1)
                storm_num = storm_id_match.group(2)
                storm_id = f"{basin}{storm_num}2025"

                # Try common cone URL patterns - prioritize the actual cone images
                potential_urls = [
                    f"https://www.nhc.noaa.gov/storm_graphics/{basin}{storm_num}/refresh/{storm_id}_5day_cone_no_line_and_wind+png/",
                    f"https://www.nhc.noaa.gov/storm_graphics/{basin}{storm_num}/refresh/{storm_id}_5day_cone_no_line_and_wind_sm+png/",
                    f"https://www.nhc.noaa.gov/storm_graphics/{basin}{storm_num}/refresh/{storm_id}_cone+png/",
                    f"https://www.nhc.noaa.gov/storm_graphics/{basin}{storm_num}/{storm_id}_5day_cone_no_line_and_wind.png"
                ]

                for base_url in potential_urls:
                    if base_url.endswith('/'):
                        # Try to find the actual PNG file in the directory
                        try:
                            response = self._make_request(base_url)
                            if response.status_code == 200:
                                # Look for PNG files in the directory listing, prioritizing cone images
                                png_matches = re.findall(r'href="([^"]*\.png)"', response.text)

                                # Filter and prioritize cone images over wind probability images
                                cone_images = []
                                other_images = []

                                for png_file in png_matches:
                                    if 'cone' in png_file.lower() and 'wind_probs' not in png_file.lower():
                                        cone_images.append(png_file)
                                    elif 'wind_probs' not in png_file.lower():
                                        other_images.append(png_file)

                                # Use cone images first, then other images
                                preferred_images = cone_images + other_images
                                if preferred_images:
                                    cone_urls.append(urljoin(base_url, preferred_images[0]))
                                    logger.debug(f"Found cone image: {preferred_images[0]}")
                        except:
                            pass
                    else:
                        cone_urls.append(base_url)

            # Remove duplicates and return the first valid URL
            cone_urls = list(dict.fromkeys(cone_urls))  # Remove duplicates while preserving order

            # Test each URL to find a working one
            for url in cone_urls:
                try:
                    response = self._make_request(url)
                    if response.status_code == 200 and 'image' in response.headers.get('content-type', ''):
                        logger.info(f"Found working cone URL: {url}")
                        return url
                except:
                    continue

            # If no URLs worked, try to construct the specific cone URL pattern you provided
            if storm_id_match:
                basin = storm_id_match.group(1)
                storm_num = storm_id_match.group(2)
                storm_id = f"{basin}{storm_num}2025"

                # Try to find the latest cone image using a timestamp pattern
                import datetime
                now = datetime.datetime.now()

                # Try recent timestamps (current day and previous day)
                for days_back in range(2):
                    date = now - datetime.timedelta(days=days_back)

                    # Try different time formats that NHC uses
                    timestamp_patterns = [
                        "242034",  # Your specific example
                        date.strftime("%d%H%M"),  # DDHHM format
                        date.strftime("%d%H%S"),  # DDHHS format
                        date.strftime("%d%H34"),  # Common pattern
                        date.strftime("%d%H04"),  # Common pattern
                        date.strftime("%d2034"),  # Pattern from your example
                    ]

                    for timestamp in timestamp_patterns:
                        constructed_url = f"https://www.nhc.noaa.gov/storm_graphics/{basin}{storm_num}/refresh/{storm_id}_5day_cone_no_line_and_wind+png/{timestamp}.png"
                        try:
                            response = self._make_request(constructed_url)
                            if response.status_code == 200 and 'image' in response.headers.get('content-type', ''):
                                logger.info(f"Found constructed cone URL: {constructed_url}")
                                return constructed_url
                        except:
                            continue

            # If no working URL found, return the first one anyway
            if cone_urls:
                logger.debug(f"Using first cone URL (untested): {cone_urls[0]}")
                return cone_urls[0]

            return None

        except Exception as e:
            logger.debug(f"Error extracting cone URL: {e}")
            return None

    def _scan_nhc_main_page(self) -> list[dict[str, str]]:
        """Scan the main NHC page for storm links.

        Returns:
            List of storm page information
        """
        storm_pages = []

        try:
            response = self._make_request(NHC_BASE)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for links to storm graphics pages
            for link in soup.find_all('a', href=True):
                href = link['href']

                # Match graphics_at{number}.shtml or graphics_ep{number}.shtml
                match = re.match(r'graphics_(at|ep)(\d+)\.shtml', href)
                if match:
                    basin_code = match.group(1).upper()
                    storm_num = match.group(2)

                    # Try to extract storm name from link text
                    storm_name = link.get_text().strip()
                    if not storm_name or len(storm_name) > 50:
                        storm_name = f"Storm {storm_num}"

                    full_url = urljoin(NHC_BASE, href)

                    storm_pages.append({
                        "storm_name": storm_name,
                        "storm_id": f"{basin_code}{storm_num.zfill(2)}2025",  # Assume current year
                        "basin": basin_code,
                        "page_url": full_url,
                        "cone_url": None  # Will be filled in later
                    })

            logger.debug(f"Found {len(storm_pages)} storm links on main page")
            return storm_pages

        except Exception as e:
            logger.warning(f"Failed to scan main NHC page: {e}")
            return []

    def get_storm_cone_geometry(self, storm_page: dict[str, str]) -> NHCCone | None:
        """Get the forecast cone geometry for a specific storm.

        Args:
            storm_page: Storm page information dictionary

        Returns:
            NHCCone object with geometry or None
        """
        try:
            # Determine which page number this storm is on
            page_url = storm_page.get("page_url", "")
            storm_page_num = self._extract_page_number(page_url)

            if not storm_page_num:
                logger.warning(f"Could not determine page number for {storm_page.get('storm_name')}")
                return None

            # Determine basin prefix
            storm_id = storm_page.get("storm_id", "")
            if storm_id.upper().startswith("AL"):
                basin_prefix = "AT"
            elif storm_id.upper().startswith("EP"):
                basin_prefix = "EP"
            else:
                basin_prefix = "AT"  # Default to Atlantic

            # Get cone geometry from MapServer
            cone_geometry = self._get_mapserver_cone(storm_page_num, basin_prefix)

            if cone_geometry:
                return NHCCone(
                    geometry=cone_geometry,
                    storm_id=storm_id,
                    storm_name=storm_page.get("storm_name"),
                    storm_type="Named Storm",  # Will be refined later
                    advisory_num="Current"
                )

            return None

        except Exception as e:
            logger.error(f"Failed to get cone geometry for {storm_page.get('storm_name')}: {e}")
            return None

    def _extract_page_number(self, page_url: str) -> int | None:
        """Extract the page number from a storm page URL.

        Args:
            page_url: Storm page URL

        Returns:
            Page number (1-5) or None
        """
        try:
            # Extract from URLs like graphics_at3.shtml or graphics_ep2.shtml
            match = re.search(r'graphics_(at|ep)(\d+)\.shtml', page_url)
            if match:
                return int(match.group(2))
            return None
        except Exception as e:
            logger.debug(f"Error extracting page number from {page_url}: {e}")
            return None

    def _get_mapserver_cone(self, storm_num: int, basin_prefix: str) -> Polygon | None:
        """Get cone geometry from NHC MapServer.

        Args:
            storm_num: Storm number (1-5)
            basin_prefix: Basin prefix (AT, EP, etc.)

        Returns:
            Cone polygon geometry or None
        """
        try:
            # Calculate layer ID based on storm number and basin
            # AT1=8, AT2=34, AT3=60, AT4=86, AT5=112
            # EP1=138, EP2=164, EP3=190, EP4=216, EP5=242
            if basin_prefix == "AT":
                base_layer_ids = {1: 8, 2: 34, 3: 60, 4: 86, 5: 112}
            elif basin_prefix == "EP":
                base_layer_ids = {1: 138, 2: 164, 3: 190, 4: 216, 5: 242}
            else:
                logger.warning(f"Unknown basin prefix: {basin_prefix}")
                return None

            if storm_num not in base_layer_ids:
                logger.warning(f"Invalid storm number: {storm_num}")
                return None

            layer_id = base_layer_ids[storm_num]

            # Query the MapServer for this layer
            query_url = f"{NHC_MAPSERVER_BASE}/{layer_id}/query"
            params = {
                "where": "1=1",
                "outFields": "*",
                "geometryType": "esriGeometryPolygon",
                "spatialRel": "esriSpatialRelIntersects",
                "f": "json",
                "returnGeometry": "true"
            }

            response = requests.get(query_url, params=params, timeout=self.timeout)
            response.raise_for_status()

            try:
                data = response.json()
            except ValueError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.debug(f"Response content: {response.text[:500]}")
                return None

            features = data.get("features", [])
            if not features:
                logger.debug(f"No features found for layer {layer_id}")
                return None

            # Use the first feature (should be the cone)
            feature = features[0]
            geometry_data = feature.get("geometry")

            if not geometry_data:
                logger.warning(f"No geometry in feature for layer {layer_id}")
                return None

            # Convert ESRI geometry to Shapely polygon
            try:
                # ESRI geometry format uses 'rings' instead of GeoJSON format
                if 'rings' in geometry_data:
                    rings = geometry_data['rings']
                    if rings and len(rings) > 0:
                        # Use the first ring (exterior ring)
                        exterior_ring = rings[0]

                        # Create Shapely polygon from coordinates
                        from shapely.geometry import Polygon
                        geometry = Polygon(exterior_ring)

                        logger.info(f"Successfully retrieved cone geometry for layer {layer_id}")
                        return geometry
                    logger.warning(f"No rings in geometry data for layer {layer_id}")
                    return None
                # Try standard GeoJSON format as fallback
                from shapely.geometry import shape
                geometry = shape(geometry_data)

                if isinstance(geometry, Polygon):
                    logger.info(f"Successfully retrieved cone geometry for layer {layer_id}")
                    return geometry
                logger.warning(f"Unexpected geometry type: {type(geometry)}")
                return None

            except Exception as e:
                logger.error(f"Failed to convert geometry: {e}")
                logger.debug(f"Geometry data keys: {list(geometry_data.keys()) if geometry_data else 'None'}")
                return None

        except Exception as e:
            logger.error(f"Failed to get MapServer cone for {basin_prefix}{storm_num}: {e}")
            return None


def get_all_active_storm_cones() -> list[NHCCone]:
    """Get forecast cones for all active named storms.

    Returns:
        List of NHCCone objects for all active storms
    """
    tracker = NHCStormTracker()

    try:
        # Discover all active storm pages
        storm_pages = tracker.discover_active_storm_pages()

        cones = []
        for storm_page in storm_pages:
            cone = tracker.get_storm_cone_geometry(storm_page)
            if cone:
                cones.append(cone)
                logger.info(f"Retrieved cone for {storm_page['storm_name']}")
            else:
                logger.warning(f"Could not get cone for {storm_page['storm_name']}")

        logger.info(f"Retrieved {len(cones)} storm cones from individual pages")
        return cones

    except Exception as e:
        logger.error(f"Failed to get active storm cones: {e}")
        return []


def discover_new_storms() -> list[dict[str, str]]:
    """Discover any new storms that have individual tracking pages.

    Returns:
        List of newly discovered storm page information
    """
    tracker = NHCStormTracker()
    return tracker.discover_active_storm_pages()
