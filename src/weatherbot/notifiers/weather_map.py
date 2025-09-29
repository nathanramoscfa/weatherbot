# src/weatherbot/notifiers/weather_map.py
"""Interactive weather map GUI with hurricane cone visualization."""

import logging
import tempfile
import threading
import webbrowser
from pathlib import Path

import folium
from folium import plugins

logger = logging.getLogger(__name__)


class WeatherMapGUI:
    """Interactive weather map showing hurricane cones and alerts."""

    def __init__(
        self,
        home_lat: float,
        home_lon: float,
    ) -> None:
        """Initialize weather map GUI.

        Args:
            home_lat: Home latitude
            home_lon: Home longitude
        """
        self.home_lat = home_lat
        self.home_lon = home_lon
        self._map_file: Path | None = None

    def show_weather_map(
        self,
        alert_level: str,
        alert_title: str,
        alert_message: str,
        cone_geometries: list | None = None,
        storm_info: list | None = None,
        auto_dismiss_seconds: int | None = None,
    ) -> None:
        """Show interactive weather map with alert information.

        Args:
            alert_level: Alert level (CONE, WATCH, WARNING, or INFO)
            alert_title: Alert title
            alert_message: Alert message
            cone_geometries: List of hurricane cone geometries
            storm_info: List of storm information
            auto_dismiss_seconds: Auto-dismiss after N seconds
        """
        logger.info(f"Showing weather map for alert: {alert_level}")

        try:
            # Create the map
            weather_map = self._create_weather_map(
                alert_level, alert_title, alert_message, cone_geometries, storm_info
            )

            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
                self._map_file = Path(tmp.name)
            weather_map.save(str(self._map_file))

            # Open in browser
            file_url = f"file://{self._map_file}"
            webbrowser.open(file_url)

            # Auto-dismiss if configured
            if auto_dismiss_seconds:
                threading.Timer(auto_dismiss_seconds, self._cleanup_map).start()

            logger.info("Weather map displayed successfully")

        except Exception as e:
            logger.error(f"Failed to show weather map: {e}")

    def _create_weather_map(
        self,
        alert_level: str,
        alert_title: str,
        alert_message: str,
        cone_geometries: list | None = None,
        storm_info: list | None = None,
    ) -> folium.Map:
        """Create the interactive weather map.

        Args:
            alert_level: Alert level
            alert_title: Alert title
            alert_message: Alert message
            cone_geometries: Hurricane cone geometries
            storm_info: Storm information

        Returns:
            Folium map object
        """
        # Create base map centered on Atlantic basin
        # Center between home location and Atlantic hurricane region
        atlantic_center_lat = (self.home_lat + 35.0) / 2  # Midpoint to Atlantic
        atlantic_center_lon = (self.home_lon - 20.0) / 2  # Shift east to Atlantic

        weather_map = folium.Map(
            location=[atlantic_center_lat, atlantic_center_lon],
            zoom_start=5,  # Zoom in one increment as requested
            tiles="OpenStreetMap",
        )

        # Add additional tile layers
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            name="Satellite",
            overlay=False,
            control=True,
        ).add_to(weather_map)

        # Add weather radar overlay
        folium.TileLayer(
            tiles="https://mapservices.weather.noaa.gov/tropical/rest/services/"
            "tropical/NHC_tropical_weather/MapServer/tile/{z}/{y}/{x}",
            attr="NOAA NHC",
            name="Hurricane Data",
            overlay=True,
            control=True,
            opacity=0.7,
        ).add_to(weather_map)

        # Add home location marker
        home_icon_color = self._get_folium_icon_color(alert_level)
        folium.Marker(
            location=[self.home_lat, self.home_lon],
            popup=folium.Popup(
                f"<b>🏠 Home Location</b><br>"
                f"<b>Alert Level:</b> {alert_level}<br>"
                f"<b>Status:</b> {alert_title}",
                max_width=300,
            ),
            tooltip="Home Location",
            icon=folium.Icon(color=home_icon_color, icon="home", prefix="fa"),
        ).add_to(weather_map)

        # Add hurricane cones and storm positions if provided
        if cone_geometries:
            self._add_hurricane_cones(weather_map, cone_geometries, storm_info)
            self._add_storm_positions(weather_map, storm_info)

        # Add alert information panel
        self._add_alert_panel(weather_map, alert_level, alert_title, alert_message)

        # Add layer control
        folium.LayerControl().add_to(weather_map)

        # Add fullscreen button
        plugins.Fullscreen().add_to(weather_map)

        # Add measure tool
        plugins.MeasureControl().add_to(weather_map)

        return weather_map

    def _add_hurricane_cones(
        self,
        weather_map: folium.Map,
        cone_geometries: list,
        storm_info: list | None = None,
    ) -> None:
        """Add hurricane forecast cones to the map.

        Args:
            weather_map: Folium map object
            cone_geometries: List of cone geometries
            storm_info: Storm information
        """
        for i, geometry in enumerate(cone_geometries):
            try:
                # Convert Shapely geometry to GeoJSON-like coordinates
                if hasattr(geometry, "exterior"):
                    # Polygon
                    coords = list(geometry.exterior.coords)
                    # Convert from (lon, lat) to (lat, lon) for Folium
                    folium_coords = [[lat, lon] for lon, lat in coords]

                    # Get storm info if available
                    storm_name = "Unknown Storm"
                    storm_details = ""
                    tooltip_text = ""

                    if storm_info and i < len(storm_info):
                        storm = storm_info[i]
                        storm_name = storm.storm_name or storm.storm_id or f"Storm {i+1}"
                        storm_details = storm.get_storm_info_html()

                        # Build detailed tooltip
                        tooltip_parts = [storm_name]
                        if storm.storm_type:
                            tooltip_parts.append(f"({storm.storm_type})")
                        if storm.max_winds:
                            tooltip_parts.append(f"- {storm.max_winds} mph")
                        tooltip_text = " ".join(tooltip_parts)

                    # Determine cone type and color
                    is_development = "development" in storm_name.lower() or "disturbance" in storm_name.lower()
                    cone_color = "orange" if is_development else "red"
                    cone_icon = "🌪️" if is_development else "🌀"
                    cone_type = "Development Area" if is_development else "Forecast Cone"

                    # Add cone polygon with enhanced information
                    folium.Polygon(
                        locations=folium_coords,
                        popup=folium.Popup(
                            storm_details if storm_details else f"<b>{cone_icon} {storm_name}</b><br><b>{cone_type}</b><br>{'Potential development area' if is_development else 'Probability of storm center passing through this area'}",
                            max_width=350,
                        ),
                        tooltip=tooltip_text if tooltip_text else f"{cone_type} - {storm_name}",
                        color=cone_color,
                        weight=2,
                        fillColor=cone_color,
                        fillOpacity=0.3 if is_development else 0.2,
                    ).add_to(weather_map)

            except Exception as e:
                logger.warning(f"Failed to add cone geometry {i}: {e}")

    def _add_storm_positions(
        self,
        weather_map: folium.Map,
        storm_info: list | None = None,
    ) -> None:
        """Add current storm position markers to the map.

        Args:
            weather_map: Folium map object
            storm_info: Storm information
        """
        if not storm_info:
            return

        for storm in storm_info:
            # Try to get position from storm data or estimate from cone center
            position = storm.current_position
            if not position and hasattr(storm, 'geometry'):
                try:
                    # Estimate position from cone centroid
                    centroid = storm.geometry.centroid
                    position = (centroid.y, centroid.x)
                    logger.debug(f"Using cone centroid for {storm.storm_name}: {position}")
                except Exception as e:
                    logger.debug(f"Failed to get centroid for {storm.storm_name}: {e}")
                    continue

            if not position:
                continue

            try:
                lat, lon = position
                storm_name = storm.storm_name or "Unknown Storm"
                storm_type = storm.storm_type or "Unknown"

                # Create custom HTML icon based on storm type (like NHC map)
                if "hurricane" in storm_type.lower() or storm_type.upper() == "HU":
                    # Hurricane icon - red circle with H
                    icon_html = """
                    <div style="
                        width: 24px; height: 24px;
                        background-color: #FF0000;
                        border: 2px solid #FFFFFF;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-weight: bold;
                        color: white;
                        font-size: 14px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                    ">H</div>
                    """
                    icon = folium.DivIcon(html=icon_html, icon_size=(24, 24), icon_anchor=(12, 12))

                elif "tropical storm" in storm_type.lower() or "storm" in storm_type.lower() or storm_type.upper() == "TS":
                    # Tropical Storm icon - orange circle with S
                    icon_html = """
                    <div style="
                        width: 20px; height: 20px;
                        background-color: #FF8C00;
                        border: 2px solid #FFFFFF;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-weight: bold;
                        color: white;
                        font-size: 12px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                    ">S</div>
                    """
                    icon = folium.DivIcon(html=icon_html, icon_size=(20, 20), icon_anchor=(10, 10))

                else:
                    # Disturbance icon - red X like NHC map
                    icon_html = """
                    <div style="
                        width: 20px; height: 20px;
                        background-color: transparent;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-weight: bold;
                        color: #FF0000;
                        font-size: 18px;
                        text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
                    ">✕</div>
                    """
                    icon = folium.DivIcon(html=icon_html, icon_size=(20, 20), icon_anchor=(10, 10))

                # Add storm center marker with enhanced icon
                folium.Marker(
                    location=[lat, lon],
                    popup=folium.Popup(
                        storm.get_storm_info_html(),
                        max_width=350,
                    ),
                    tooltip=f"Current Position - {storm_name}",
                    icon=icon,
                ).add_to(weather_map)

            except Exception as e:
                logger.warning(f"Failed to add storm position for {storm.storm_name}: {e}")

    def _add_alert_panel(
        self,
        weather_map: folium.Map,
        alert_level: str,
        alert_title: str,
        alert_message: str,
    ) -> None:
        """Add alert information panel to the map.

        Args:
            weather_map: Folium map object
            alert_level: Alert level
            alert_title: Alert title
            alert_message: Alert message
        """
        # Get alert level info for better styling
        from ..alert_levels import AlertLevel, get_alert_info

        # Determine alert level enum from string
        alert_level_enum = AlertLevel.ALL_CLEAR
        if "LEVEL_1" in alert_level.upper():
            alert_level_enum = AlertLevel.ALL_CLEAR
        elif "LEVEL_2" in alert_level.upper():
            alert_level_enum = AlertLevel.TROPICAL_STORM_THREAT
        elif "LEVEL_3" in alert_level.upper():
            alert_level_enum = AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT
        elif "LEVEL_4" in alert_level.upper():
            alert_level_enum = AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION
        elif "LEVEL_5" in alert_level.upper():
            alert_level_enum = AlertLevel.HURRICANE_WARNING

        alert_info = get_alert_info(alert_level_enum)

        # Create HTML for alert panel with improved styling
        alert_html = f"""
        <div style="position: fixed;
                    top: 10px; left: 10px; width: 380px; height: auto;
                    background-color: white; border: 3px solid {alert_info.color};
                    border-radius: 12px; padding: 15px; z-index: 9999;
                    box-shadow: 0 6px 12px rgba(0,0,0,0.4);
                    font-family: 'Segoe UI', Arial, sans-serif;">
            <div style="background-color: white; color: black;
                        padding: 8px; margin: -15px -15px 15px -15px;
                        border-radius: 9px 9px 0 0; font-weight: bold;
                        font-size: 16px; border-bottom: 2px solid {alert_info.color};">
                {alert_info.icon} WEATHERBOT ALERT
            </div>
            <h3 style="margin: 0 0 12px 0; color: {alert_info.color}; font-size: 16px;">
                {alert_title}
            </h3>
            <div style="margin: 0 0 12px 0; font-size: 13px; line-height: 1.5; color: #333;">
                {alert_message.replace(chr(10), '<br>')}
            </div>
            <div style="margin-top: 12px; padding-top: 8px; border-top: 1px solid #eee;
                        font-size: 11px; color: #666;">
                <strong>Your Location:</strong> {self.home_lat:.4f}°N, {self.home_lon:.4f}°W
            </div>
        </div>
        """

        # Add HTML to map
        weather_map.get_root().html.add_child(folium.Element(alert_html))

    def _get_alert_color(self, alert_level: str) -> str:
        """Get color for alert level.

        Args:
            alert_level: Alert level

        Returns:
            Color string
        """
        color_map = {
            "WARNING": "#FF0000",  # Red
            "WATCH": "#FF8C00",    # Dark Orange
            "CONE": "#FFD700",     # Gold
            "INFO": "#4169E1",     # Royal Blue
        }
        return color_map.get(alert_level.upper(), "#808080")  # Gray default

    def _get_folium_icon_color(self, alert_level: str) -> str:
        """Get Folium-compatible icon color for alert level.

        Args:
            alert_level: Alert level

        Returns:
            Folium icon color string
        """
        color_map = {
            "WARNING": "red",
            "WATCH": "orange",
            "CONE": "lightgreen",
            "INFO": "blue",
        }
        return color_map.get(alert_level.upper(), "gray")


    def _cleanup_map(self) -> None:
        """Clean up temporary map file."""
        try:
            if self._map_file and self._map_file.exists():
                self._map_file.unlink()
                logger.debug("Cleaned up temporary map file")
        except Exception as e:
            logger.warning(f"Failed to cleanup map file: {e}")


def create_weather_map_gui(
    home_lat: float,
    home_lon: float,
) -> WeatherMapGUI:
    """Create a weather map GUI instance.

    Args:
        home_lat: Home latitude
        home_lon: Home longitude

    Returns:
        WeatherMapGUI instance
    """
    return WeatherMapGUI(home_lat, home_lon)
