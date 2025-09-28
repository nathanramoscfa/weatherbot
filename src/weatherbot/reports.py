# src/weatherbot/reports.py
"""Report generation for weatherbot analysis."""

import logging
from datetime import datetime
from pathlib import Path

import requests

from .alert_levels import AlertInfo, AlertLevel
from .config import WeatherbotConfig

logger = logging.getLogger(__name__)


def get_location_name(latitude: float, longitude: float, openai_api_key: str | None = None) -> str:
    """Get location name from coordinates using multiple strategies.

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        openai_api_key: Optional OpenAI API key for AI-powered location naming

    Returns:
        Location name string
    """
    try:
        # Use OpenStreetMap Nominatim for reverse geocoding
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            'lat': latitude,
            'lon': longitude,
            'format': 'json',
            'addressdetails': 1,
            'zoom': 10
        }
        headers = {'User-Agent': 'weatherbot/1.0'}

        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            address = data.get('address', {})

            # Build location name from components
            city = address.get('city') or address.get('town') or address.get('village')
            county = address.get('county')
            state = address.get('state') or address.get('province')
            country = address.get('country')

            # Handle different location granularities
            if city and state:
                return f"{city}, {state}"
            if county and state:
                # If we have county but no city, use county name
                # Remove "County" suffix if present for cleaner display
                county_clean = county.replace(" County", "").replace(" Parish", "")
                return f"{county_clean}, {state}"
            if city and country:
                return f"{city}, {country}"
            if state and country:
                return f"{state}, {country}"
            if country:
                return country

    except Exception as e:
        logger.debug(f"Reverse geocoding failed: {e}")

    # Strategy 2: AI-powered location naming (if API key available)
    if openai_api_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_api_key)

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",  # Fast, low-cost model
                messages=[
                    {
                        "role": "user",
                        "content": f"What is the name of the location at coordinates {latitude:.4f}°N, {longitude:.4f}°W? Provide just the city/area name and state/country in format 'City, State' or 'City, Country'. Be concise."
                    }
                ],
                max_tokens=50,
                temperature=0
            )

            ai_location = response.choices[0].message.content.strip()
            if ai_location and len(ai_location) < 100:  # Sanity check
                logger.info(f"AI location naming: {ai_location}")
                return ai_location

        except Exception as e:
            logger.debug(f"AI location naming failed: {e}")

    # Strategy 3: Generic coordinate-based fallback
    return f"Location {latitude:.4f}°N, {longitude:.4f}°W"


def generate_html_report(
    alert_level: int,
    alert_enum: AlertLevel,
    alert_info: AlertInfo,
    title: str,
    message: str,
    config: WeatherbotConfig,
    location_name: str,
    storm_cone_data: list | None = None,
) -> str:
    """Generate comprehensive HTML report.

    Args:
        alert_level: Numeric alert level
        alert_enum: Alert level enum
        alert_info: Alert information
        title: Alert title
        message: Alert message
        config: Configuration
        location_name: Dynamic location name
        storm_cone_data: Optional list of individual storm cone data with URLs and metadata

    Returns:
        Path to generated HTML file
    """
    import base64

    # Create reports directory
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"hurricane_threat_analysis_{timestamp}.html"
    filepath = reports_dir / filename

    # Check if coordinates are outside NOAA coverage
    coverage_result = config.validate_coverage()
    is_outside_coverage = coverage_result.get("is_outside", False)

    if is_outside_coverage:
        # Generate AI-only report for out-of-coverage locations
        logger.info("Generating AI-only HTML report for out-of-coverage location")
        html_content = _get_ai_only_html_template(
            alert_level=alert_level,
            alert_info=alert_info,
            location_name=location_name,
            config=config,
            title=title,
            message=message,
            timestamp=timestamp
        )
    else:
        # Generate full NOAA report for in-coverage locations
        logger.info("Generating full NOAA HTML report for in-coverage location")

        # Determine the correct basin and get appropriate map URLs
        basin = coverage_result.get("basin", "atlantic")
        basin_urls = _get_basin_urls(basin)
        map_url = basin_urls["7day"]
        basin_display = basin_urls["display_name"]

        # Download NOAA map image for the correct basin
        map_image_b64 = None
        try:
            response = requests.get(map_url, timeout=30)
            if response.status_code == 200:
                map_image_b64 = base64.b64encode(response.content).decode('utf-8')
        except Exception as e:
            logger.warning(f"Failed to download NOAA {basin_display} map: {e}")

        # Download individual storm cone images
        storm_cone_images = []
        logger.info(f"Processing {len(storm_cone_data) if storm_cone_data else 0} storm cone data entries for HTML report")
        if storm_cone_data:
            logger.info(f"Storm cone data: {storm_cone_data}")
        else:
            logger.warning("No storm cone data provided to HTML report generation")

        if storm_cone_data:
            for i, storm_data in enumerate(storm_cone_data):
                try:
                    cone_url = storm_data.get('url')
                    if cone_url:
                        response = requests.get(cone_url, timeout=30)
                        if response.status_code == 200:
                            cone_image_b64 = base64.b64encode(response.content).decode('utf-8')
                            storm_cone_images.append({
                                'index': i + 1,
                                'name': storm_data.get('name', 'Unknown Storm'),
                                'storm_id': storm_data.get('storm_id', ''),
                                'url': cone_url,
                                'page_url': storm_data.get('page_url', ''),
                                'image_b64': cone_image_b64
                            })
                            logger.info(f"Downloaded cone image for {storm_data.get('name', f'Storm {i + 1}')}")
                except Exception as e:
                    logger.warning(f"Failed to download cone image for {storm_data.get('name', f'Storm {i + 1}')}: {e}")

        # Get alert level color
        level_colors = {
            1: "#4CAF50",  # Green
            2: "#FF9800",  # Orange
            3: "#FF5722",  # Deep Orange
            4: "#F44336",  # Red
            5: "#B71C1C"   # Dark Red
        }
        alert_color = level_colors.get(alert_level, "#757575")

        # Generate HTML content using full template
        html_content = _get_html_template(
            alert_level=alert_level,
            alert_info=alert_info,
            alert_color=alert_color,
            location_name=location_name,
            config=config,
            title=title,
            message=message,
            map_image_b64=map_image_b64,
            storm_cone_images=storm_cone_images,
            timestamp=timestamp,
            basin_display=basin_display,
            map_url=map_url
        )

    # Write to file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return str(filepath)


def _get_basin_urls(basin: str) -> dict:
    """Get basin-specific URLs and display names.

    Args:
        basin: Basin name ('atlantic', 'eastern_pacific', 'central_pacific')

    Returns:
        Dictionary with URLs and display name for the basin
    """
    basin_configs = {
        "atlantic": {
            "7day": "https://www.nhc.noaa.gov/xgtwo/two_atl_7d0.png",
            "2day": "https://www.nhc.noaa.gov/xgtwo/two_atl_2d0.png",
            "text": "https://www.nhc.noaa.gov/gtwo.php?basin=atlc&fdays=7",
            "display_name": "Atlantic"
        },
        "eastern_pacific": {
            "7day": "https://www.nhc.noaa.gov/xgtwo/two_epac_7d0.png",
            "2day": "https://www.nhc.noaa.gov/xgtwo/two_epac_2d0.png",
            "text": "https://www.nhc.noaa.gov/gtwo.php?basin=epac&fdays=7",
            "display_name": "Eastern Pacific"
        },
        "central_pacific": {
            "7day": "https://www.nhc.noaa.gov/xgtwo/two_cpac_7d0.png",
            "2day": "https://www.nhc.noaa.gov/xgtwo/two_cpac_2d0.png",
            "text": "https://www.nhc.noaa.gov/gtwo.php?basin=cpac&fdays=7",
            "display_name": "Central Pacific"
        }
    }

    return basin_configs.get(basin, basin_configs["atlantic"])


def _get_html_template(
    alert_level: int,
    alert_info: AlertInfo,
    alert_color: str,
    location_name: str,
    config: WeatherbotConfig,
    title: str,
    message: str,
    map_image_b64: str | None,
    storm_cone_images: list,
    timestamp: str,
    basin_display: str = "Atlantic",
    map_url: str = "https://www.nhc.noaa.gov/xgtwo/two_atl_7d0.png"
) -> str:
    """Generate HTML template with provided data.

    Args:
        alert_level: Numeric alert level
        alert_info: Alert information
        alert_color: Alert color hex code
        location_name: Location name
        config: Configuration
        title: Alert title
        message: Alert message
        map_image_b64: Base64 encoded map image
        timestamp: Report timestamp

    Returns:
        Complete HTML content
    """
    # Generate HTML content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚨 Hurricane Threat Analysis - Level {alert_level}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, {alert_color}, {alert_color}aa);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .alert-badge {{
            background: rgba(255,255,255,0.2);
            border-radius: 25px;
            padding: 10px 20px;
            display: inline-block;
            margin-bottom: 15px;
            font-size: 18px;
            font-weight: bold;
        }}
        .content {{
            padding: 30px;
        }}
        .section {{
            margin-bottom: 30px;
            border-left: 4px solid {alert_color};
            padding-left: 20px;
        }}
        .section h2 {{
            color: {alert_color};
            margin-top: 0;
        }}
        .map-container {{
            text-align: center;
            margin: 20px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
        }}
        .map-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .actions-box {{
            background: {alert_color}15;
            border: 2px solid {alert_color};
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
        }}
        .actions-box h3 {{
            color: {alert_color};
            margin-top: 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: {alert_color};
            color: white;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            border-top: 1px solid #eee;
        }}
        ul {{
            padding-left: 20px;
        }}
        li {{
            margin: 8px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="alert-badge">{alert_info.icon} ALERT LEVEL {alert_level}</div>
            <h1>🚨 Hurricane Threat Analysis Report</h1>
            <p><strong>Location:</strong> {location_name}<br>
            <strong>Coordinates:</strong> {config.home_lat:.4f}°N, {config.home_lon:.4f}°W<br>
            <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>

        <div class="content">
            <div class="section">
                <h2>{alert_info.icon} Current Alert Status</h2>
                <h3>Alert Level {alert_level}: {alert_info.title_prefix}</h3>
                <p><strong>Situation:</strong> {title.replace('**', '')}</p>
            </div>

            <div class="section">
                <h2>📊 Official NOAA Hurricane Map</h2>
                <p><em>7-Day {basin_display} Tropical Weather Outlook</em></p>
                <div class="map-container">"""

    if map_image_b64:
        html_content += f'<img src="data:image/png;base64,{map_image_b64}" alt="NOAA 7-Day {basin_display} Tropical Weather Outlook">'
    else:
        html_content += f'<img src="{map_url}" alt="NOAA 7-Day {basin_display} Tropical Weather Outlook">'

    html_content += f"""
                </div>
                <p><em>Source: <a href="{map_url}" target="_blank">National Hurricane Center</a></em></p>
            </div>"""

    # Add individual storm cone images if available
    if storm_cone_images:
        html_content += """

            <div class="section">
                <h2>🌀 Individual Storm Forecast Cones</h2>
                <p><em>Detailed forecast cones from individual storm tracking pages</em></p>"""

        for storm_image in storm_cone_images:
            storm_name = storm_image.get('name', f"Storm {storm_image['index']}")
            storm_id = storm_image.get('storm_id', '')
            page_url = storm_image.get('page_url', '')

            html_content += f"""
                <div class="map-container">
                    <h3>🌀 {storm_name}</h3>
                    {f'<p><strong>Storm ID:</strong> {storm_id}</p>' if storm_id else ''}
                    <img src="data:image/png;base64,{storm_image['image_b64']}" alt="{storm_name} Forecast Cone" style="width: 100%; max-width: 800px; height: auto; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <p><em>Cone Image Source: <a href="{storm_image['url']}" target="_blank">Direct PNG Link</a></em></p>
                    {f'<p><em>Storm Page: <a href="{page_url}" target="_blank">NHC Individual Storm Page</a></em></p>' if page_url else ''}
                </div>"""

        html_content += """
            </div>"""

    html_content += """

            <div class="section">
                <h2>📋 Detailed Threat Assessment</h2>"""

    # Parse and format the detailed assessment
    clean_message = message.replace("**", "").strip()
    sections = clean_message.split('\n')

    html_content += "<ul>\n"

    for line in sections:
        line = line.strip()
        if not line:
            continue

        # Remove bullet point prefixes
        if line.startswith(('• ', '- ')):
            line = line[2:].strip()

        # Check if this is a section header (ends with colon and contains key phrases)
        if (line.endswith(':') and
            ('Affecting the Area' in line or 'Analysis' in line or 'Watches/Warnings' in line or
             'Actions Based on' in line or 'Next Steps' in line or 'Guidance' in line or 'Details' in line)):
            # Close previous list and start new section
            html_content += "</ul>\n"
            html_content += f"<h3>{line}</h3>\n<ul>\n"
        else:
            # Regular bullet point
            html_content += f"<li>{line}</li>\n"

    html_content += "</ul>\n"

    html_content += f"""
            </div>

            <div class="actions-box">
                <h3>🚨 Immediate Actions Required</h3>
                <h4>Alert Level {alert_level} Actions:</h4>
                <div>{alert_info.guidance.replace(chr(10), '<br>')}</div>
            </div>

            <div class="section">
                <h2>📞 Emergency Contacts & Resources</h2>
                <h3>Official Weather Services</h3>
                <ul>
                    <li><strong>National Hurricane Center:</strong> <a href="https://www.nhc.noaa.gov/" target="_blank">https://www.nhc.noaa.gov/</a></li>
                    <li><strong>Local Weather Service:</strong> Monitor local radio and TV</li>
                    <li><strong>Emergency Management:</strong> Follow local authorities</li>
                </ul>

                <h3>Transportation</h3>
                <ul>
                    <li><strong>Primary Airport:</strong> Monitor flight status</li>
                    <li><strong>Airlines:</strong> Check available routes to safe destinations</li>
                    <li><strong>Ground Transportation:</strong> Pre-arrange airport transportation</li>
                </ul>

                <h3>Evacuation Destinations</h3>
                <ul>
                    <li><strong>Nearest Major City:</strong> Primary evacuation destination</li>
                    <li><strong>Alternative Locations:</strong> Secondary evacuation options</li>
                    <li><strong>Inland Areas:</strong> Away from coastal storm surge</li>
                </ul>
            </div>

            <div class="section">
                <h2>⚠️ 5-Level Storm Alert System</h2>
                <table>
                    <tr>
                        <th>Level</th>
                        <th>Icon</th>
                        <th>Status</th>
                        <th>Trigger</th>
                        <th>Action</th>
                    </tr>
                    <tr>
                        <td><strong>1</strong></td>
                        <td>✅</td>
                        <td>All Clear</td>
                        <td>No active disturbances</td>
                        <td>Normal activities</td>
                    </tr>
                    <tr>
                        <td><strong>2</strong></td>
                        <td>🌪️</td>
                        <td>Tropical Storm Threat</td>
                        <td>Disturbance within 5-7 days</td>
                        <td>Monitor & review plans</td>
                    </tr>
                    <tr>
                        <td><strong>3</strong></td>
                        <td>🛑</td>
                        <td>TS Watch/Hurricane Threat</td>
                        <td>TS Watch or Hurricane within 3-5 days</td>
                        <td>Stock supplies & pack</td>
                    </tr>
                    <tr>
                        <td><strong>4</strong></td>
                        <td>🚨</td>
                        <td>TS Warning/Hurricane Watch</td>
                        <td>TS Warning or Hurricane Watch</td>
                        <td><strong>EVACUATE NOW</strong></td>
                    </tr>
                    <tr>
                        <td><strong>5</strong></td>
                        <td>🌀</td>
                        <td>Hurricane Warning</td>
                        <td>Hurricane conditions within 36h</td>
                        <td>Shelter in place if trapped</td>
                    </tr>
                </table>
            </div>

            <div class="section">
                <h2>📍 Location Information</h2>
                <p><strong>{location_name}</strong></p>
                <ul>
                    <li><strong>Coordinates:</strong> {config.home_lat:.4f}°N, {config.home_lon:.4f}°W</li>
                    <li><strong>Elevation:</strong> Variable (check local conditions for storm surge risk)</li>
                    <li><strong>Location Type:</strong> Monitor local geography for evacuation requirements</li>
                    <li><strong>Emergency Planning:</strong> Identify nearest safe evacuation routes and destinations</li>
                </ul>
            </div>
        </div>

        <div class="footer">
            <p><em>This report was generated automatically by Weatherbot AI using official National Hurricane Center data.<br>
            Always follow official emergency management guidance and evacuation orders.</em></p>
            <p><strong>Report ID:</strong> {timestamp} | <strong>System Version:</strong> Weatherbot v1.0.0 | <strong>Data Source:</strong> NOAA National Hurricane Center</p>
        </div>
    </div>
</body>
</html>"""

    return html_content


def _get_ai_only_html_template(
    alert_level: int,
    alert_info: AlertInfo,
    location_name: str,
    config: WeatherbotConfig,
    title: str,
    message: str,
    timestamp: str
) -> str:
    """Generate AI-only HTML template for out-of-coverage locations.

    Args:
        alert_level: Numeric alert level
        alert_info: Alert information
        location_name: Location name
        config: Configuration
        title: Alert title
        message: Alert message
        timestamp: Report timestamp

    Returns:
        Complete HTML content for AI-only report
    """
    # Get alert level color
    level_colors = {
        1: "#4CAF50",  # Green
        2: "#FF9800",  # Orange
        3: "#FF5722",  # Deep Orange
        4: "#F44336",  # Red
        5: "#B71C1C"   # Dark Red
    }
    alert_color = level_colors.get(alert_level, "#757575")

    # Generate HTML content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌍 AI Weather Analysis - Level {alert_level}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, {alert_color}, {alert_color}aa);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .alert-badge {{
            background: rgba(255,255,255,0.2);
            border-radius: 25px;
            padding: 10px 20px;
            display: inline-block;
            margin-bottom: 15px;
            font-size: 18px;
            font-weight: bold;
        }}
        .coverage-notice {{
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
            color: #856404;
        }}
        .content {{
            padding: 30px;
        }}
        .section {{
            margin-bottom: 30px;
            border-left: 4px solid {alert_color};
            padding-left: 20px;
        }}
        .section h2 {{
            color: {alert_color};
            margin-top: 0;
        }}
        .ai-analysis {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            border-left: 4px solid #007bff;
        }}
        .actions-box {{
            background: {alert_color}15;
            border: 2px solid {alert_color};
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
        }}
        .actions-box h3 {{
            color: {alert_color};
            margin-top: 0;
        }}
        .data-source {{
            background: #e3f2fd;
            border: 1px solid #bbdefb;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
            color: #1565c0;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            border-top: 1px solid #eee;
        }}
        ul {{
            padding-left: 20px;
        }}
        li {{
            margin: 8px 0;
        }}
        .warning {{
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 4px;
            padding: 10px;
            margin: 10px 0;
            color: #856404;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="alert-badge">{alert_info.icon} ALERT LEVEL {alert_level}</div>
            <h1>🌍 AI Weather Analysis Report</h1>
            <p><strong>Location:</strong> {location_name}<br>
            <strong>Coordinates:</strong> {config.home_lat:.4f}°N, {config.home_lon:.4f}°W<br>
            <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>

        <div class="content">
            <div class="coverage-notice">
                <h3>⚠️ Coverage Notice</h3>
                <p><strong>This location is outside NOAA coverage areas.</strong> This analysis is based on AI web search of local meteorological services and weather data sources. For the most accurate and up-to-date information, please consult your local meteorological service or national weather agency.</p>
            </div>

            <div class="section">
                <h2>{alert_info.icon} Current Alert Status</h2>
                <h3>Alert Level {alert_level}: {alert_info.title_prefix}</h3>
                <p><strong>Situation:</strong> {title.replace('**', '')}</p>
            </div>

            <div class="ai-analysis">
                <h2>🤖 AI Weather Analysis</h2>
                <p><em>Based on web search of local weather services and meteorological data</em></p>
                <div class="section">
                    <h3>📋 Detailed Assessment</h3>"""

    # Parse and format the detailed assessment
    clean_message = message.replace("**", "").strip()
    sections = clean_message.split('\n')

    html_content += "<ul>\n"

    for line in sections:
        line = line.strip()
        if not line:
            continue

        # Remove bullet point prefixes
        if line.startswith(('• ', '- ')):
            line = line[2:].strip()

        # Check if this is a section header (ends with colon and contains key phrases)
        if (line.endswith(':') and
            ('Affecting the Area' in line or 'Analysis' in line or 'Warnings' in line or
             'Actions Based on' in line or 'Next Steps' in line or 'Guidance' in line or 'Details' in line or
             'Status' in line or 'Assessment' in line or 'Timeline' in line or 'Sources' in line)):
            # Close previous list and start new section
            html_content += "</ul>\n"
            html_content += f"<h4>{line}</h4>\n<ul>\n"
        else:
            # Regular bullet point
            html_content += f"<li>{line}</li>\n"

    html_content += "</ul>\n"

    html_content += f"""
                </div>
            </div>

            <div class="actions-box">
                <h3>🚨 Immediate Actions Required</h3>
                <h4>Alert Level {alert_level} Actions:</h4>
                <div>{alert_info.guidance.replace(chr(10), '<br>')}</div>
            </div>

            <div class="data-source">
                <h3>📊 Data Sources & Limitations</h3>
                <ul>
                    <li><strong>Primary Source:</strong> AI web search of local meteorological services</li>
                    <li><strong>Coverage Area:</strong> Outside NOAA Atlantic Basin (0-60°N, 100°W-0°E)</li>
                    <li><strong>Accuracy:</strong> May be less accurate than NOAA-sourced data</li>
                    <li><strong>Update Frequency:</strong> Based on available web data at time of analysis</li>
                    <li><strong>Recommendation:</strong> Always verify with local weather services</li>
                </ul>
            </div>

            <div class="section">
                <h2>🌍 Regional Weather Services</h2>
                <p><em>Recommended local weather information sources for your region:</em></p>
                <ul>
                    <li><strong>Local Meteorological Service:</strong> Check your country's national weather service</li>
                    <li><strong>Regional Weather Centers:</strong> Look for regional meteorological organizations</li>
                    <li><strong>International Services:</strong> World Meteorological Organization (WMO) member services</li>
                    <li><strong>Emergency Services:</strong> Local emergency management and civil defense</li>
                </ul>
            </div>

            <div class="section">
                <h2>⚠️ 5-Level Weather Alert System</h2>
                <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
                    <tr style="background-color: {alert_color}; color: white;">
                        <th style="border: 1px solid #ddd; padding: 12px; text-align: left;">Level</th>
                        <th style="border: 1px solid #ddd; padding: 12px; text-align: left;">Icon</th>
                        <th style="border: 1px solid #ddd; padding: 12px; text-align: left;">Status</th>
                        <th style="border: 1px solid #ddd; padding: 12px; text-align: left;">Trigger</th>
                        <th style="border: 1px solid #ddd; padding: 12px; text-align: left;">Action</th>
                    </tr>
                    <tr>
                        <td style="border: 1px solid #ddd; padding: 12px;"><strong>1</strong></td>
                        <td style="border: 1px solid #ddd; padding: 12px;">✅</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">All Clear</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">No active weather threats</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">Normal activities</td>
                    </tr>
                    <tr>
                        <td style="border: 1px solid #ddd; padding: 12px;"><strong>2</strong></td>
                        <td style="border: 1px solid #ddd; padding: 12px;">🌪️</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">Weather Watch</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">Potential severe weather within 24-48 hours</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">Monitor conditions</td>
                    </tr>
                    <tr>
                        <td style="border: 1px solid #ddd; padding: 12px;"><strong>3</strong></td>
                        <td style="border: 1px solid #ddd; padding: 12px;">⚠️</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">Weather Warning</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">Severe weather within 12-24 hours</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">Prepare for impacts</td>
                    </tr>
                    <tr>
                        <td style="border: 1px solid #ddd; padding: 12px;"><strong>4</strong></td>
                        <td style="border: 1px solid #ddd; padding: 12px;">🚨</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">Severe Weather Alert</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">Dangerous weather within 6-12 hours</td>
                        <td style="border: 1px solid #ddd; padding: 12px;"><strong>Take immediate precautions</strong></td>
                    </tr>
                    <tr>
                        <td style="border: 1px solid #ddd; padding: 12px;"><strong>5</strong></td>
                        <td style="border: 1px solid #ddd; padding: 12px;">🛑</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">Emergency Warning</td>
                        <td style="border: 1px solid #ddd; padding: 12px;">Life-threatening weather imminent</td>
                        <td style="border: 1px solid #ddd; padding: 12px;"><strong>Seek immediate shelter</strong></td>
                    </tr>
                </table>
            </div>

            <div class="section">
                <h2>📍 Location Information</h2>
                <p><strong>{location_name}</strong></p>
                <ul>
                    <li><strong>Coordinates:</strong> {config.home_lat:.4f}°N, {config.home_lon:.4f}°W</li>
                    <li><strong>Coverage Status:</strong> Outside NOAA Atlantic Basin</li>
                    <li><strong>Data Source:</strong> AI web search of local meteorological services</li>
                    <li><strong>Emergency Planning:</strong> Consult local emergency management services</li>
                </ul>
            </div>

            <div class="warning">
                <h3>⚠️ Important Disclaimer</h3>
                <p>This analysis is generated using AI web search and may not reflect the most current weather conditions. Always consult official local meteorological services and emergency management authorities for the most accurate and up-to-date weather information and safety guidance.</p>
            </div>
        </div>

        <div class="footer">
            <p><em>This report was generated automatically by Weatherbot AI using web search data.<br>
            This location is outside NOAA coverage areas. Always follow official local weather guidance.</em></p>
            <p><strong>Report ID:</strong> {timestamp} | <strong>System Version:</strong> Weatherbot v1.0.0 | <strong>Data Source:</strong> AI Web Search</p>
        </div>
    </div>
</body>
</html>"""

    return html_content
