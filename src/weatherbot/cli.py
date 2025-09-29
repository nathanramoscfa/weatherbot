# src/weatherbot/cli.py
"""Typer CLI interface for Weatherbot."""

import json
import logging
import sys
from datetime import UTC, datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table

from .alert_levels import (
    AlertInfo,
    AlertLevel,
    format_alert_message,
    get_alert_info,
)
from .alerting import AlertManager, create_alert_manager
from .config import WeatherbotConfig, load_config
from .enhanced_cone_analyzer import analyze_location_threat_enhanced
from .geometry import (
    load_county_polygon,
    point_in_any,
    polygon_intersects_any,
    validate_coordinates,
)
from .logging_setup import setup_logging
from .nhc import get_active_cones
from .nws import get_hurricane_alerts
from .state import StateManager, WeatherbotState

app = typer.Typer(
    name="weatherbot",
    help="Local hurricane alert system with NHC cone tracking and NWS alerts",
    no_args_is_help=True,
)

console = Console()
logger = logging.getLogger(__name__)


@app.command()
def run(
    once: bool = typer.Option(
        False,
        "--once",
        help="Run once and exit (for scheduled tasks)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Run the main weatherbot monitoring cycle."""
    try:
        # Show disclaimer on first run
        console.print("⚠️  [bold red]DISCLAIMER[/bold red]: Weatherbot is for informational purposes only. "
                     "Always verify with official sources. See DISCLAIMER.md for full terms.", 
                     style="yellow")
        
        # Load configuration
        config = load_config()

        # Setup logging
        log_level = "DEBUG" if verbose else config.log_level
        setup_logging(log_level=log_level)

        logger.info("Starting Weatherbot monitoring cycle")
        logger.info(f"Home location: ({config.home_lat}, {config.home_lon})")
        logger.info(f"County intersect mode: {config.use_county_intersect}")

        # Validate coordinates
        validate_coordinates(config.home_lon, config.home_lat)

        # Validate NOAA coverage
        _validate_noaa_coverage(config)

        # Initialize components
        state_manager = StateManager()
        alert_manager = create_alert_manager(config)

        # Run monitoring cycle with AI analysis if available
        if config.openai_api_key:
            _run_ai_monitoring_cycle(config, state_manager, alert_manager)
        else:
            _run_monitoring_cycle(config, state_manager, alert_manager)

        logger.info("Weatherbot monitoring cycle completed successfully")

    except Exception as e:
        logger.error(f"Weatherbot run failed: {e}")
        if verbose:
            logger.exception("Full traceback:")
        raise typer.Exit(code=1)


@app.command("test-alert")
def test_alert() -> None:
    """Test notification systems (toast)."""
    try:
        console.print("⚠️  [bold red]DISCLAIMER[/bold red]: For informational purposes only. "
                     "See DISCLAIMER.md for full terms.", style="yellow")
        console.print("🧪 Testing Weatherbot notification systems...")

        # Load configuration
        config = load_config()
        setup_logging(log_level=config.log_level, console=False)

        # Create alert manager and test
        alert_manager = create_alert_manager(config)
        alert_manager.test_notifications()

        console.print("✅ Notification test completed!")
        console.print("Check that you saw a toast notification and heard the siren.")

    except Exception as e:
        console.print(f"❌ Test failed: {e}", style="red")
        raise typer.Exit(code=1)


@app.command("check-coverage")
def check_coverage() -> None:
    """Check if coordinates are within NOAA coverage area."""
    try:
        console.print("🔍 Checking NOAA coverage for coordinates...")

        # Load configuration
        config = load_config()
        setup_logging(log_level=config.log_level, console=False)

        # Validate coverage
        coverage_result = config.validate_coverage()

        # Display results
        _display_coverage_results(console, config, coverage_result)

    except Exception as e:
        console.print(f"❌ Coverage check failed: {e}", style="red")
        raise typer.Exit(code=1)


@app.command("show-map")
def show_map(
    force: bool = typer.Option(
        False,
        "--force",
        help="Force show map even if no alerts",
    ),
) -> None:
    """Show official NOAA hurricane map with AI threat analysis."""
    try:
        console.print("🗺️ Opening official NOAA hurricane map...")

        import webbrowser

        from .config import load_config
        from .coverage_validator import CoverageValidator

        # Determine which basin to show
        config = load_config()
        validator = CoverageValidator()
        coverage_result = validator.validate_coordinates(config.home_lat, config.home_lon)
        basin = coverage_result.get("basin", "atlantic")

        # Get basin-specific map URL
        from .ai_map_analyzer import NOAA_MAP_URLS
        basin_urls = NOAA_MAP_URLS.get(basin, NOAA_MAP_URLS["atlantic"])
        map_url = basin_urls["7day"]

        # Open the exact NOAA map image that AI analyzes
        webbrowser.open(map_url)

        basin_names = {
            "atlantic": "Atlantic",
            "eastern_pacific": "Eastern Pacific",
            "central_pacific": "Central Pacific"
        }
        basin_display = basin_names.get(basin, "Atlantic")

        console.print(f"✅ Official NOAA 7-day {basin_display} tropical weather outlook map opened!")
        console.print("This is the exact map image that the AI analyzes for threat assessment.")

    except Exception as e:
        console.print(f"❌ Failed to open NOAA map: {e}", style="red")
        raise typer.Exit(code=1)


@app.command("ai-analysis")
def ai_analysis() -> None:
    """Get AI analysis of current hurricane threat from official NOAA map or web search fallback."""
    try:
        console.print("⚠️  [bold red]AI DISCLAIMER[/bold red]: AI analysis may be incorrect. "
                     "Never rely solely on AI for emergency decisions. See DISCLAIMER.md", 
                     style="yellow")
        console.print("[AI] Analyzing weather threats with AI...")

        # Load configuration
        config = load_config()

        # Setup logging for debug output
        setup_logging(log_level=config.log_level, console=False)

        if not config.openai_api_key:
            console.print("[ERROR] No OpenAI API key configured", style="red")
            console.print("Add OPENAI_API_KEY=your_key_here to .env file", style="yellow")
            return

        # Check NOAA coverage first
        coverage_result = config.validate_coverage()

        if coverage_result["is_outside"]:
            console.print("[INFO] Location outside NOAA coverage - using AI web search fallback", style="yellow")
            _run_web_search_analysis(config, coverage_result)
        else:
            console.print("[INFO] Location within NOAA coverage - analyzing official NOAA map", style="green")
            _run_noaa_analysis(config)

    except Exception as e:
        console.print(f"[ERROR] AI analysis failed: {e}", style="red")
        raise typer.Exit(code=1)


debug_app = typer.Typer(name="debug", help="Debug commands")
app.add_typer(debug_app, name="debug")


@debug_app.command("layers")
def debug_layers() -> None:
    """Show NHC MapServer layers information."""
    try:
        console.print("🔍 Fetching NHC MapServer layers...")

        from .nhc import NHCClient

        client = NHCClient()
        layers = client.get_layers_info()

        if not layers:
            console.print("❌ No layers found", style="red")
            return

        # Create table
        table = Table(title="NHC MapServer Layers")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Type", style="yellow")
        table.add_column("Description", style="white")

        for layer in layers:
            table.add_row(
                str(layer.get("id", "")),
                layer.get("name", ""),
                layer.get("type", ""),
                layer.get("description", "")[:50] + "..."
                if len(layer.get("description", "")) > 50
                else layer.get("description", ""),
            )

        console.print(table)

        # Highlight cone layer
        cone_layer_id = client.discover_cone_layer()
        if cone_layer_id is not None:
            console.print(f"🎯 Forecast cone layer ID: {cone_layer_id}", style="green bold")
        else:
            console.print("⚠️ No forecast cone layer found", style="yellow")

    except Exception as e:
        console.print(f"❌ Debug layers failed: {e}", style="red")
        raise typer.Exit(code=1)


state_app = typer.Typer(name="state", help="State management commands")
app.add_typer(state_app, name="state")


@state_app.command("show")
def state_show() -> None:
    """Show current state."""
    try:
        state_manager = StateManager()
        state_data = state_manager.show_state()

        console.print("📊 Current weatherbot State:")
        console.print(json.dumps(state_data, indent=2, default=str))

    except Exception as e:
        console.print(f"❌ Failed to show state: {e}", style="red")
        raise typer.Exit(code=1)


@state_app.command("clear")
def state_clear() -> None:
    """Clear state file."""
    try:
        state_manager = StateManager()
        state_manager.clear_state()
        console.print("✅ State cleared successfully", style="green")

    except Exception as e:
        console.print(f"❌ Failed to clear state: {e}", style="red")
        raise typer.Exit(code=1)


@debug_app.command("clear-cache")
def debug_clear_cache() -> None:
    """Clear API cache."""
    try:
        from .cache import api_cache
        api_cache.clear()
        console.print("✅ API cache cleared successfully", style="green")

    except Exception as e:
        console.print(f"❌ Failed to clear cache: {e}", style="red")
        raise typer.Exit(code=1)


@debug_app.command("storm-data")
def debug_storm_data() -> None:
    """Show detailed storm data from NHC."""
    try:
        console.print("🔍 Fetching detailed storm data...")

        from .nhc import NHCClient

        client = NHCClient()
        cones = client.fetch_active_cones()

        if not cones:
            console.print("❌ No active storms found", style="red")
            return

        # Create table
        table = Table(title="Active Storm Data (with AI Enhancement)")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Advisory", style="yellow")
        table.add_column("Position", style="white")
        table.add_column("Winds", style="red")
        table.add_column("Pressure", style="blue")

        for cone in cones:
            position_str = "Unknown"
            if cone.current_position:
                lat, lon = cone.current_position
                position_str = f"{lat:.1f}°N, {abs(lon):.1f}°W"

            table.add_row(
                cone.storm_name or "Unknown",
                cone.storm_type or "Unknown",
                cone.advisory_num or "Unknown",
                position_str,
                f"{cone.max_winds} mph" if cone.max_winds else "Unknown",
                f"{cone.min_pressure} mb" if cone.min_pressure else "Unknown",
            )

        console.print(table)

    except Exception as e:
        console.print(f"❌ Debug storm data failed: {e}", style="red")
        raise typer.Exit(code=1)


@debug_app.command("current-storms")
def debug_current_storms() -> None:
    """Test CurrentStorms.json API directly."""
    try:
        console.print("🔍 Testing CurrentStorms.json API...")

        from .nhc_current_storms import get_current_storms_with_positions

        storms = get_current_storms_with_positions()

        if not storms:
            console.print("❌ No storms found in CurrentStorms.json", style="red")
            return

        # Create table
        table = Table(title="CurrentStorms.json Data")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Position", style="white")
        table.add_column("Winds", style="red")
        table.add_column("Pressure", style="blue")
        table.add_column("Movement", style="yellow")

        for storm in storms:
            position_str = "Unknown"
            if storm.current_position:
                lat, lon = storm.current_position
                position_str = f"{lat:.1f}°N, {abs(lon):.1f}°W"

            table.add_row(
                storm.storm_name or "Unknown",
                storm.storm_type or "Unknown",
                position_str,
                f"{storm.max_winds} mph" if storm.max_winds else "Unknown",
                f"{storm.min_pressure} mb" if storm.min_pressure else "Unknown",
                storm.movement or "Unknown",
            )

        console.print(table)

    except Exception as e:
        console.print(f"❌ CurrentStorms.json test failed: {e}", style="red")
        raise typer.Exit(code=1)


@debug_app.command("discover-storms")
def debug_discover_storms() -> None:
    """Discover individual storm tracking pages."""
    try:
        from .nhc_storm_tracker import (
            discover_new_storms,
            get_all_active_storm_cones,
        )

        console.print("🔍 Discovering individual storm tracking pages...")

        # Discover storm pages
        storm_pages = discover_new_storms()

        if not storm_pages:
            console.print("❌ No individual storm pages found")
            return

        console.print(f"📄 Found {len(storm_pages)} individual storm pages:")

        for i, page in enumerate(storm_pages, 1):
            console.print(f"\n{i}. {page['storm_name']}")
            console.print(f"   Storm ID: {page['storm_id']}")
            console.print(f"   Basin: {page['basin']}")
            console.print(f"   Page URL: {page['page_url']}")
            if page.get('cone_url'):
                console.print(f"   Cone URL: {page['cone_url']}")

        # Try to get cone geometries
        console.print("\n🌀 Attempting to retrieve cone geometries...")
        storm_cones = get_all_active_storm_cones()

        if storm_cones:
            console.print(f"✅ Successfully retrieved {len(storm_cones)} storm cones")
            for cone in storm_cones:
                console.print(f"   - {cone.storm_name}: {cone.storm_type}")
        else:
            console.print("⚠️  No cone geometries retrieved")

    except Exception as e:
        console.print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=1)


@debug_app.command("test-ai")
def debug_test_ai() -> None:
    """Test AI-powered storm position detection."""
    try:
        console.print("🤖 Testing AI storm position detection...")

        config = load_config()
        if not config.openai_api_key:
            console.print("❌ No OpenAI API key configured", style="red")
            console.print("Add OPENAI_API_KEY=your_key_here to .env file", style="yellow")
            return

        from .ai_enhancer import AIStormEnhancer

        enhancer = AIStormEnhancer(config.openai_api_key)
        positions = enhancer.get_disturbance_positions()

        if not positions:
            console.print("❌ No positions found", style="red")
            return

        # Create table
        table = Table(title="AI-Detected Storm Positions")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Position", style="white")
        table.add_column("Probability", style="yellow")

        for pos in positions:
            lat = pos.get("latitude", 0)
            lon = pos.get("longitude", 0)
            position_str = f"{lat:.1f}°N, {abs(lon):.1f}°W"

            table.add_row(
                pos.get("name", "Unknown"),
                pos.get("type", "Unknown"),
                position_str,
                pos.get("probability", "Unknown"),
            )

        console.print(table)
        console.print("✅ AI storm position detection completed!", style="green")

    except Exception as e:
        console.print(f"❌ AI test failed: {e}", style="red")
        raise typer.Exit(code=1)


def _run_ai_monitoring_cycle(
    config: WeatherbotConfig,
    state_manager: StateManager,
    alert_manager: AlertManager,
) -> None:
    """Run AI-powered monitoring cycle using official NOAA map analysis.

    Args:
        config: Configuration
        state_manager: State manager
        alert_manager: Alert manager
    """
    # Load current state
    state = state_manager.load_state()

    # Check for cooldown
    if _is_in_cooldown(state, config.alert_cooldown_minutes):
        logger.info("In alert cooldown period, skipping AI analysis")
        return

    try:
        logger.info("Starting AI-powered hurricane threat analysis...")

        from .ai_map_analyzer import analyze_hurricane_threat_with_ai

        # Get geometric analysis first
        from .enhanced_cone_analyzer import analyze_location_threat_enhanced
        threat_analysis = analyze_location_threat_enhanced(
            latitude=config.home_lat,
            longitude=config.home_lon,
            use_county_intersect=config.use_county_intersect,
            county_geojson_path=str(config.get_county_geojson_path()) if config.use_county_intersect else None,
        )

        # Get AI analysis of official NOAA map with geometric results
        # Get dynamic location name from coordinates
        from .reports import get_location_name
        location_name = get_location_name(config.home_lat, config.home_lon, config.openai_api_key)

        # Check if API key is available before calling AI function
        if config.openai_api_key is None:
            logger.error("OpenAI API key is required for AI analysis")
            return

        alert_level, title, message = analyze_hurricane_threat_with_ai(
            latitude=config.home_lat,
            longitude=config.home_lon,
            location_name=location_name,
            api_key=config.openai_api_key,
            geometric_results=threat_analysis,
        )

        logger.info(f"AI analysis complete: Level {alert_level} - {title}")

        # Trigger alert if threat detected (Level 2 and above)
        if alert_level >= 2:
            # Create simplified alert using AI analysis
            alert_manager.raise_alert(
                f"LEVEL_{alert_level}",
                title,
                message,
                cone_geometries=None,  # No geometry needed for AI analysis
                storm_info=None,
            )

            # Update state to prevent spam
            state.set_in_cone_status(True)
        # All clear
        elif state.was_in_cone:
            logger.info("Threat level reduced - location no longer under threat")
            state.set_in_cone_status(False)

        # Save updated state
        state_manager.save_state(state)

    except Exception as e:
        logger.error(f"AI monitoring cycle failed: {e}")


def _run_monitoring_cycle(
    config: WeatherbotConfig,
    state_manager: StateManager,
    alert_manager: AlertManager,
) -> None:
    """Run a complete monitoring cycle.

    Args:
        config: Configuration
        state_manager: State manager
        alert_manager: Alert manager
    """
    # Load current state
    state = state_manager.load_state()

    # Check for cooldown
    if _is_in_cooldown(state, config.alert_cooldown_minutes):
        logger.info("In alert cooldown period, skipping checks")
        return

    # Check NHC forecast cones
    _check_forecast_cones(config, state, alert_manager)

    # Check NWS alerts
    _check_nws_alerts(config, state, alert_manager)

    # Save updated state
    state_manager.save_state(state)


def _is_in_cooldown(state: WeatherbotState, cooldown_minutes: int) -> bool:
    """Check if we're in alert cooldown period.

    Args:
        state: Current state
        cooldown_minutes: Cooldown period in minutes

    Returns:
        True if in cooldown
    """
    if cooldown_minutes <= 0:
        return False

    now = datetime.now(UTC)
    cooldown_delta = timedelta(minutes=cooldown_minutes)

    return (now - state.updated) < cooldown_delta


def _check_forecast_cones(
    config: WeatherbotConfig,
    state: WeatherbotState,
    alert_manager: AlertManager,
) -> None:
    """Check NHC forecast cones for intersections.

    Args:
        config: Configuration
        state: Current state
        alert_manager: Alert manager
    """
    logger.info("Checking NHC forecast cones...")

    try:
        cones, geometries = get_active_cones()
        logger.info(f"Found {len(cones)} active forecast cones")

        if not cones:
            # No active cones - update state if previously in cone
            if state.was_in_cone:
                state.set_in_cone_status(False)
                logger.info("No longer in any forecast cone")
            return

        # Use enhanced threat analysis for maximum accuracy
        threat_analysis = analyze_location_threat_enhanced(
            latitude=config.home_lat,
            longitude=config.home_lon,
            use_county_intersect=config.use_county_intersect,
            county_geojson_path=str(config.get_county_geojson_path()) if config.use_county_intersect else None,
        )

        current_alert_level = threat_analysis["alert_level"]
        storm_threats = threat_analysis["storm_threats"]
        is_in_any_cone = threat_analysis["is_in_any_cone"]

        # Type assertions to help the type checker
        assert isinstance(current_alert_level, AlertLevel)
        assert isinstance(storm_threats, list)
        assert isinstance(is_in_any_cone, bool)

        # Convert storm threats to affecting storms for compatibility
        affecting_storms = [threat.cone for threat in storm_threats]

        # Check for new or escalated threats (Level 2 and above)
        if is_in_any_cone and (not state.was_in_cone or current_alert_level.value >= 2):
            # Get alert information
            get_alert_info(current_alert_level)
            storm_names = [storm.storm_name or storm.storm_id or "Unknown" for storm in affecting_storms]

            # Try to generate AI-powered alert if available
            try:
                from .ai_map_analyzer import analyze_hurricane_threat_with_ai

                # Define location name for alerts
                location_name_ai = f"Location at {config.home_lat:.4f}°N, {config.home_lon:.4f}°W"

                if config.openai_api_key:
                    # Use hybrid AI analysis with geometric results
                    _ai_alert_level, ai_title, ai_message = analyze_hurricane_threat_with_ai(
                        latitude=config.home_lat,
                        longitude=config.home_lon,
                        location_name=location_name_ai,
                        api_key=config.openai_api_key,
                        geometric_results=threat_analysis,
                    )

                    # Use AI-generated content if available
                    if ai_title and ai_message:
                        title = ai_title
                        message = ai_message
                        logger.info("Using AI-enhanced alert content")
                    else:
                        # Fallback to standard alert
                        title, message = format_alert_message(
                            current_alert_level, storm_names, location_name_ai
                        )
                else:
                    # Standard alert without AI
                    title, message = format_alert_message(
                        current_alert_level, storm_names, location_name_ai
                    )
            except Exception as e:
                logger.warning(f"AI alert generation failed, using standard: {e}")
                # Standard fallback
                storm_details = []
                for storm in affecting_storms:
                    details = [f"• {storm.storm_name or 'Unknown Storm'}"]
                    if storm.storm_type:
                        details.append(f"  Type: {storm.storm_type}")
                    storm_details.append("\n".join(details))

                # Get dynamic location name
                from .reports import get_location_name
                fallback_location_name = get_location_name(config.home_lat, config.home_lon, config.openai_api_key)

                title, message = format_alert_message(
                    current_alert_level,
                    storm_names,
                    fallback_location_name,
                    storm_details
                )

            alert_manager.raise_alert(
                f"LEVEL_{current_alert_level.value}",
                title,
                message,
                cone_geometries=geometries,
                storm_info=cones,
            )

        # Update cone advisories and state
        for cone in cones:
            if cone.storm_id and cone.advisory_num:
                if state.is_new_cone_advisory(cone.storm_id, cone.advisory_num):
                    logger.info(
                        f"New advisory for {cone.storm_id}: {cone.advisory_num}"
                    )
                    state.update_cone_advisory(cone.storm_id, cone.advisory_num)

        # Update in-cone status
        state.set_in_cone_status(is_in_any_cone)

    except Exception as e:
        logger.error(f"Failed to check forecast cones: {e}")


def _analyze_threat_level(config: WeatherbotConfig, cones: list, geometries: list) -> dict:
    """Analyze threat level based on storm types and intersections.

    Args:
        config: Configuration
        cones: List of storm cones
        geometries: List of cone geometries

    Returns:
        Dictionary with threat analysis
    """
    affecting_storms = []
    is_in_any_cone = False
    highest_threat = AlertLevel.ALL_CLEAR

    # Check each storm
    for i, cone in enumerate(cones):
        if i < len(geometries):
            geometry = geometries[i]

            # Check intersection
            if config.use_county_intersect:
                try:
                    county_polygon = load_county_polygon(config.get_county_geojson_path())
                    in_cone = geometry.intersects(county_polygon)
                except Exception as e:
                    logger.warning(f"Failed to load county polygon, using point check: {e}")
                    home_point = (config.home_lon, config.home_lat)
                    in_cone = point_in_any([geometry], home_point)
            else:
                home_point = (config.home_lon, config.home_lat)
                in_cone = point_in_any([geometry], home_point)

            if in_cone:
                is_in_any_cone = True
                affecting_storms.append(cone)

                # Determine threat level for this storm using new 5-level system
                storm_type = (cone.storm_type or "").lower()
                if "hurricane" in storm_type:
                    storm_level = AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT  # Level 3
                elif "tropical storm" in storm_type or "storm" in storm_type:
                    storm_level = AlertLevel.TROPICAL_STORM_THREAT  # Level 2
                else:
                    storm_level = AlertLevel.TROPICAL_STORM_THREAT  # Level 2 for disturbances

                # Track highest threat
                if storm_level.value > highest_threat.value:
                    highest_threat = storm_level

    return {
        "alert_level": highest_threat,
        "affecting_storms": affecting_storms,
        "is_in_any_cone": is_in_any_cone,
    }


def _check_cone_intersection(
    config: WeatherbotConfig,
    geometries: list,
) -> bool:
    """Check if location intersects forecast cones.

    Args:
        config: Configuration
        geometries: List of cone geometries

    Returns:
        True if location intersects any cone
    """
    if config.use_county_intersect:
        try:
            county_polygon = load_county_polygon(config.get_county_geojson_path())
            return polygon_intersects_any(geometries, county_polygon)
        except Exception as e:
            logger.warning(f"Failed to load county polygon, using point check: {e}")

    # Fallback to point check
    home_point = (config.home_lon, config.home_lat)
    return point_in_any(geometries, home_point)


def _check_nws_alerts(
    config: WeatherbotConfig,
    state: WeatherbotState,
    alert_manager: AlertManager,
) -> None:
    """Check NWS alerts for hurricane watches/warnings.

    Args:
        config: Configuration
        state: Current state
        alert_manager: Alert manager
    """
    logger.info("Checking NWS hurricane alerts...")

    try:
        alerts = get_hurricane_alerts(config.home_lat, config.home_lon)
        logger.info(f"Found {len(alerts)} hurricane alerts")

        for alert in alerts:
            if state.is_new_alert(alert.id):
                # New alert
                logger.info(f"New hurricane alert: {alert.event} - {alert.headline}")

                title = f"{alert.get_severity_prefix()}: {alert.event}"
                message = alert.headline

                if alert.areas:
                    message += f"\n\nAreas: {', '.join(alert.areas[:3])}"

                if alert.effective:
                    message += f"\nEffective: {alert.effective.strftime('%Y-%m-%d %H:%M UTC')}"

                if alert.expires:
                    message += f"\nExpires: {alert.expires.strftime('%Y-%m-%d %H:%M UTC')}"

                alert_manager.raise_alert(alert.event.upper(), title, message)

                # Mark alert as processed
                state.add_alert_id(alert.id)

    except Exception as e:
        logger.error(f"Failed to check NWS alerts: {e}")


def _display_terminal_analysis(
    console: Console,
    alert_level: int,
    alert_enum: AlertLevel,
    alert_info: AlertInfo,
    title: str,
    message: str,
    config: WeatherbotConfig,
    location_name: str,
) -> None:
    """Display formatted analysis in terminal.

    Args:
        console: Rich console instance
        alert_level: Numeric alert level
        alert_enum: Alert level enum
        alert_info: Alert information
        title: Alert title
        message: Alert message
        config: Configuration
    """
    from datetime import datetime


    # Header with proper alignment
    console.print()
    header_width = 80
    console.print("╔" + "═" * (header_width - 2) + "╗", style="cyan")

    # Format header lines with proper padding
    level_line = f"🚨 WEATHERBOT AI THREAT ANALYSIS - LEVEL {alert_level}"
    padding1 = " " * (header_width - len(level_line) - 4)
    console.print(f"║ {level_line}{padding1}║", style="bold cyan")

    location_line = f"📍 {location_name} ({config.home_lat:.4f}°N, {config.home_lon:.4f}°W)"
    padding2 = " " * (header_width - len(location_line) - 4)
    console.print(f"║ {location_line}{padding2}║", style="cyan")

    time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
    time_line = f"🕐 {time_str}"
    padding3 = " " * (header_width - len(time_line) - 4)
    console.print(f"║ {time_line}{padding3}║", style="cyan")

    # Add data source indicator
    coverage_result = config.validate_coverage()
    if coverage_result["is_outside"]:
        source_line = "🌍  DATA SOURCE: AI Web Search (Outside NOAA Coverage)"
        padding4 = " " * (header_width - len(source_line) - 2)
        console.print(f"║ {source_line}{padding4}║", style="cyan")
    else:
        basin = coverage_result.get("basin", "atlantic")
        basin_names = {
            "atlantic": "Atlantic",
            "eastern_pacific": "Eastern Pacific",
            "central_pacific": "Central Pacific"
        }
        basin_display = basin_names.get(basin, "Atlantic")
        source_line = f"🗺️  DATA SOURCE: Official NOAA {basin_display} Maps + Geometric Analysis"
        padding4 = " " * (header_width - len(source_line) - 2)
        console.print(f"║ {source_line}{padding4}║", style="cyan")

    console.print("╚" + "═" * (header_width - 2) + "╝", style="cyan")
    console.print()

    # Alert Level Badge
    level_color = _get_alert_level_color(alert_level)
    console.print(f"┌─ {alert_info.icon} ALERT LEVEL {alert_level}: {alert_info.title_prefix} ─┐", style=f"{level_color} bold")
    console.print()

    # Title
    console.print(f"🎯 SITUATION: {title.replace('**', '')}", style="bold white")
    console.print()

    # Parse and format the detailed assessment
    console.print("📋 DETAILED ASSESSMENT", style="bold yellow")
    console.print("─" * 50, style="yellow")

    # Clean and parse the message
    clean_message = message.replace("**", "").strip()
    sections = clean_message.split('\n')


    current_section = None

    # Define specific lines that should be treated as sub-headings
    subheading_keywords = [
        "Specific Storms/Disturbances Affecting the Area",
        "Storm Intensity Analysis",
        "Storm Details (Position, Intensity, Movement)"
    ]

    for line in sections:
        line = line.strip()
        if not line:
            continue

        # Check if this is a specific sub-heading we want to format specially
        is_subheading = False
        # Check for various bullet point formats
        if line.startswith(('• ', '- ', '* ')):
            # Extract bullet text, handling different bullet formats
            if line.startswith(('• ', '- ')):
                bullet_text = line[2:].strip()
            else:  # '* '
                bullet_text = line[2:].strip()

            # Check if any of our subheading keywords are contained in this line
            for keyword in subheading_keywords:
                if keyword in bullet_text:
                    is_subheading = True
                    break

        if is_subheading:
            # Special sub-headings - display as section headers
            console.print()  # Add spacing before all subheadings
            current_section = line
            console.print(f"▶ {line[2:].strip()}", style="bold white")
        elif line.endswith(':') and not (line.startswith(('- ', '• '))):
            # Regular section headers (not bullet points that end with colon)
            if current_section:
                console.print()  # Add spacing between sections
            current_section = line
            console.print(f"▶ {line}", style="bold white")
        elif (line.startswith(('- ', '• ', '* '))) and not is_subheading:
            # Main bullet point - wrap long lines (but not if it's a subheading)
            if line.startswith(('• ', '- ')):
                bullet_text = line[2:]
            else:  # '* '
                bullet_text = line[2:]
            _print_wrapped_text(console, f"  • {bullet_text}", "white", 76)
        elif line.startswith(('  - ', '    - ', '  • ')):
            # Sub bullet point - wrap long lines (handle various indentations)
            if line.startswith('    - '):
                sub_bullet_text = line[6:]
            elif line.startswith('  - '):
                sub_bullet_text = line[4:]
            else:  # '  • '
                sub_bullet_text = line[4:]
            _print_wrapped_text(console, f"    ◦ {sub_bullet_text}", "dim white", 74)
        # Regular content - wrap long lines
        elif current_section:
            _print_wrapped_text(console, f"  {line}", "white", 76)
        else:
            _print_wrapped_text(console, f"{line}", "white", 78)

    console.print()

    # Action Summary Box with perfect alignment
    action_box_width = 64  # Fixed width for consistency
    header_text = "🚨 IMMEDIATE ACTIONS REQUIRED"

    # Calculate exact header padding
    header_line_length = len(f"┌─ {header_text} ") + len("┐") + 1
    header_padding_needed = action_box_width - header_line_length
    header_padding = "─" * max(0, header_padding_needed)

    console.print(f"┌─ {header_text} {header_padding}┐", style=f"{level_color} bold")

    action_lines = alert_info.guidance.split('\n')
    for line in action_lines:
        if line.strip():
            # Wrap long action lines within the box
            wrapped_lines = _wrap_text_to_width(line, action_box_width - 4)
            for wrapped_line in wrapped_lines:
                # Calculate exact padding for content lines
                content_length = len(f"│ {wrapped_line} │")
                padding_needed = action_box_width - content_length
                padding = " " * max(0, padding_needed)
                console.print(f"│ {wrapped_line}{padding} │", style=f"{level_color}")

    # Bottom border with exact width
    console.print("└" + "─" * (action_box_width - 2) + "┘", style=f"{level_color}")

    console.print()

    # Final alert level display with proper centering
    final_box_width = 32
    level_text = f"{alert_info.icon}  ALERT LEVEL {alert_level}"

    # Use Rich's built-in text measurement for accurate width calculation
    from rich.text import Text
    rich_text = Text(level_text)
    text_width = console.measure(rich_text).maximum

    # Calculate exact padding needed for perfect alignment
    # Account for: "║ " (2 chars) + level_text + padding + "║" (1 char) = final_box_width
    content_width = final_box_width - 3  # Subtract 3 for "║ " and "║"

    if text_width < content_width:
        padding_needed = content_width - text_width
        level_padding = " " * padding_needed
    else:
        level_padding = ""

    console.print("╔" + "═" * (final_box_width - 2) + "╗", style=f"{level_color}")
    console.print(f"║ {level_text}{level_padding}║", style=f"{level_color} bold")
    console.print("╚" + "═" * (final_box_width - 2) + "╝", style=f"{level_color}")
    console.print()


def _print_wrapped_text(console: Console, text: str, style: str, max_width: int) -> None:
    """Print text with proper wrapping to avoid overflow.

    Args:
        console: Rich console instance
        text: Text to print
        style: Text style
        max_width: Maximum width before wrapping
    """
    import textwrap
    wrapped_lines = textwrap.wrap(text, width=max_width, subsequent_indent="    ")
    for line in wrapped_lines:
        console.print(line, style=style)


def _wrap_text_to_width(text: str, max_width: int) -> list:
    """Wrap text to specified width.

    Args:
        text: Text to wrap
        max_width: Maximum width

    Returns:
        List of wrapped lines
    """
    import textwrap
    return textwrap.wrap(text, width=max_width)


def _get_alert_level_color(alert_level: int) -> str:
    """Get color for alert level.

    Args:
        alert_level: Alert level number

    Returns:
        Color string
    """
    if alert_level >= 5 or alert_level >= 4:
        return "red"
    if alert_level >= 3:
        return "yellow"
    if alert_level >= 2:
        return "cyan"
    return "green"


def _validate_noaa_coverage(config: WeatherbotConfig) -> None:
    """Validate NOAA coverage for coordinates and provide user guidance.

    Args:
        config: Weatherbot configuration
    """
    try:
        coverage_result = config.validate_coverage()

        if coverage_result["errors"]:
            for error in coverage_result["errors"]:
                logger.error(f"Coverage validation error: {error}")
            raise typer.Exit(code=1)

        if coverage_result["warnings"]:
            for warning in coverage_result["warnings"]:
                logger.warning(f"Coverage warning: {warning}")

        # Handle different coverage statuses
        if coverage_result["is_outside"]:
            _handle_outside_coverage(config, coverage_result)
        elif coverage_result["is_marginal"]:
            _handle_marginal_coverage(config, coverage_result)
        else:
            logger.info("Coordinates are within NOAA coverage area")

    except Exception as e:
        logger.error(f"Coverage validation failed: {e}")
        raise typer.Exit(code=1)


def _handle_outside_coverage(config: WeatherbotConfig, coverage_result: dict) -> None:
    """Handle coordinates outside NOAA coverage.

    Args:
        config: Weatherbot configuration
        coverage_result: Coverage validation results
    """
    from .coverage_validator import CoverageValidator

    validator = CoverageValidator()
    recommendations = validator.get_coverage_recommendations(
        config.home_lat, config.home_lon
    )

    console.print("❌ COVERAGE WARNING", style="red bold")
    console.print("=" * 50, style="red")
    console.print(f"Location ({config.home_lat:.4f}°N, {config.home_lon:.4f}°W) is outside NOAA coverage area.", style="red")
    console.print()
    console.print("⚠️  IMPACT:", style="yellow bold")
    console.print("• Hurricane forecasts may be inaccurate or unavailable")
    console.print("• NWS weather alerts will not be available")
    console.print("• AI analysis may produce unreliable results")
    console.print()
    console.print("📋 RECOMMENDATIONS:", style="cyan bold")

    for recommendation in recommendations:
        console.print(f"  {recommendation}", style="white")

    console.print()
    console.print("🤔 CONTINUE ANYWAY?", style="yellow bold")
    console.print("Type 'yes' to continue with limited functionality, or 'no' to exit and update coordinates.")

    # In non-interactive mode, just warn and continue
    if not sys.stdin.isatty():
        logger.warning("Running in non-interactive mode - continuing with limited functionality")
        return

    try:
        response = input("Continue? (yes/no): ").lower().strip()
        if response not in ['yes', 'y']:
            console.print("Exiting. Please update coordinates in .env file.", style="yellow")
            raise typer.Exit(code=1)
    except (EOFError, KeyboardInterrupt):
        console.print("\nExiting. Please update coordinates in .env file.", style="yellow")
        raise typer.Exit(code=1)


def _handle_marginal_coverage(config: WeatherbotConfig, coverage_result: dict) -> None:
    """Handle coordinates with marginal NOAA coverage.

    Args:
        config: Weatherbot configuration
        coverage_result: Coverage validation results
    """
    console.print("⚠️  MARGINAL COVERAGE", style="yellow bold")
    console.print("=" * 50, style="yellow")
    console.print(f"Location ({config.home_lat:.4f}°N, {config.home_lon:.4f}°W) has marginal NOAA coverage.", style="yellow")
    console.print()
    console.print("⚠️  IMPACT:", style="yellow")
    console.print("• Some data sources may be unavailable")
    console.print("• Forecast accuracy may be reduced")
    console.print("• Consider using coordinates closer to US/Caribbean")
    console.print()
    console.print("Continuing with available data sources...", style="dim")
    console.print()


def _run_web_search_analysis(config: WeatherbotConfig, coverage_result: dict) -> None:
    """Run AI web search analysis for out-of-coverage locations.

    Args:
        config: Weatherbot configuration
        coverage_result: Coverage validation results
    """
    try:
        from .ai_web_search import analyze_weather_threat_web_search
        from .alert_levels import get_alert_info
        from .reports import get_location_name

        # Get location name
        location_name = get_location_name(
            config.home_lat, config.home_lon, config.openai_api_key
        )

        # Check API key before calling web search analysis
        if config.openai_api_key is None:
            raise ValueError("OpenAI API key is required for web search analysis")

        # Perform web search analysis
        alert_level, title, message = analyze_weather_threat_web_search(
            latitude=config.home_lat,
            longitude=config.home_lon,
            location_name=location_name,
            api_key=config.openai_api_key,
        )

        # Map numeric level to AlertLevel enum
        alert_enum = _map_alert_level_to_enum(alert_level)
        alert_info = get_alert_info(alert_enum, location_name)

        # Display results
        _display_terminal_analysis(console, alert_level, alert_enum, alert_info, title, message, config, location_name)

        # Generate HTML report
        _generate_html_report(alert_level, alert_enum, alert_info, title, message, config, location_name, [])

    except Exception as e:
        logger.error(f"Web search analysis failed: {e}")
        console.print(f"❌ Web search analysis failed: {e}", style="red")
        raise typer.Exit(code=1)


def _run_noaa_analysis(config: WeatherbotConfig) -> None:
    """Run standard NOAA analysis for in-coverage locations.

    Args:
        config: Weatherbot configuration
    """
    try:
        from .ai_map_analyzer import analyze_hurricane_threat_with_ai
        from .alert_levels import get_alert_info
        from .coverage_validator import CoverageValidator
        from .enhanced_cone_analyzer import analyze_location_threat_enhanced
        from .reports import get_location_name

        # Determine which basin the location is in
        validator = CoverageValidator()
        coverage_result = validator.validate_coordinates(config.home_lat, config.home_lon)
        basin = coverage_result.get("basin", "atlantic")

        # Get location name
        location_name = get_location_name(
            config.home_lat, config.home_lon, config.openai_api_key
        )

        # Get geometric analysis first
        threat_analysis = analyze_location_threat_enhanced(
            latitude=config.home_lat,
            longitude=config.home_lon,
            use_county_intersect=config.use_county_intersect,
            county_geojson_path=str(config.get_county_geojson_path()) if config.use_county_intersect else None,
        )

        # Check API key before calling AI analysis
        if config.openai_api_key is None:
            raise ValueError("OpenAI API key is required for AI analysis")

        # Analyze threat for location with geometric results and basin
        alert_level, title, message = analyze_hurricane_threat_with_ai(
            latitude=config.home_lat,
            longitude=config.home_lon,
            location_name=location_name,
            api_key=config.openai_api_key,
            basin=basin,
            geometric_results=threat_analysis,
        )

        # Map numeric level to AlertLevel enum
        alert_enum = _map_alert_level_to_enum(alert_level)
        alert_info = get_alert_info(alert_enum, location_name)

        # Display results
        _display_terminal_analysis(console, alert_level, alert_enum, alert_info, title, message, config, location_name)

        # Generate HTML report with storm data
        storm_cone_data = _get_storm_cone_data_for_report(config)
        _generate_html_report(alert_level, alert_enum, alert_info, title, message, config, location_name, storm_cone_data)

    except Exception as e:
        logger.error(f"NOAA analysis failed: {e}")
        console.print(f"❌ NOAA analysis failed: {e}", style="red")
        raise typer.Exit(code=1)


def _map_alert_level_to_enum(alert_level: int) -> AlertLevel:
    """Map numeric alert level to AlertLevel enum.

    Args:
        alert_level: Numeric alert level (1-5)

    Returns:
        AlertLevel enum
    """
    if alert_level == 1:
        return AlertLevel.ALL_CLEAR
    if alert_level == 2:
        return AlertLevel.TROPICAL_STORM_THREAT
    if alert_level == 3:
        return AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT
    if alert_level == 4:
        return AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION
    if alert_level == 5:
        return AlertLevel.HURRICANE_WARNING
    return AlertLevel.ALL_CLEAR


def _get_storm_cone_data_for_report(config: WeatherbotConfig) -> list[dict]:
    """Get storm cone data for HTML report.

    Args:
        config: Weatherbot configuration

    Returns:
        List of storm cone data dictionaries
    """
    storm_cone_data = []

    try:
        from .nhc_storm_tracker import discover_new_storms

        logger.info("Starting storm discovery for HTML report...")
        storm_pages = discover_new_storms()
        logger.info(f"Discovered {len(storm_pages)} storm pages for HTML report")

        if storm_pages:
            # Apply distance filtering
            from math import asin, cos, radians, sin, sqrt

            def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
                lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                c = 2 * asin(sqrt(a))
                r = 6371  # Radius of earth in kilometers
                return c * r

            for page in storm_pages:
                if page.get('cone_url'):
                    # Check if storm is within reasonable distance
                    include_storm = True

                    # Try to get storm position
                    lat = page.get('latitude')
                    lon = page.get('longitude')

                    if lat is not None and lon is not None:
                        try:
                            lat_float = float(lat)
                            lon_float = float(lon)
                            distance = haversine_distance(
                                config.home_lat, config.home_lon, lat_float, lon_float
                            )
                        except (ValueError, TypeError):
                            # If conversion fails, include the storm (safer approach)
                            logger.warning(
                                f"Could not convert coordinates for "
                                f"{page.get('storm_name')}: lat={lat}, lon={lon}"
                            )
                            continue
                        # Use 3000km threshold for HTML report
                        if distance > 3000:
                            include_storm = False
                            logger.info(
                                f"Excluding {page.get('storm_name')} from HTML "
                                f"report: {distance:.0f}km away"
                            )

                    if include_storm:
                        storm_cone_data.append({
                            'name': page.get('storm_name', 'Unknown Storm'),
                            'storm_id': page.get('storm_id', ''),
                            'url': page.get('cone_url'),
                            'page_url': page.get('page_url', '')
                        })
                        logger.info(f"Added relevant storm to HTML report: {page.get('storm_name')}")

        logger.info(f"Total storms added to HTML report: {len(storm_cone_data)}")

    except Exception as e:
        logger.warning(f"Failed to get storm cone data: {e}")

    return storm_cone_data


def _generate_html_report(
    alert_level: int,
    alert_enum: AlertLevel,
    alert_info: AlertInfo,
    title: str,
    message: str,
    config: WeatherbotConfig,
    location_name: str,
    storm_cone_data: list[dict],
) -> None:
    """Generate HTML report.

    Args:
        alert_level: Numeric alert level
        alert_enum: Alert level enum
        alert_info: Alert information
        title: Alert title
        message: Alert message
        config: Configuration
        location_name: Location name
        storm_cone_data: Storm cone data for report
    """
    try:
        from .reports import generate_html_report

        html_file = generate_html_report(
            alert_level, alert_enum, alert_info, title, message,
            config, location_name, storm_cone_data
        )
        console.print(f"📄 Detailed report saved: {html_file}", style="dim cyan")

    except Exception as e:
        logger.warning(f"Failed to generate HTML report: {e}")
        console.print(f"⚠️ Could not generate HTML report: {e}", style="yellow")


def _display_coverage_results(console: Console, config: WeatherbotConfig, coverage_result: dict) -> None:
    """Display coverage validation results.

    Args:
        console: Rich console instance
        config: Weatherbot configuration
        coverage_result: Coverage validation results
    """
    console.print()
    console.print("📊 NOAA COVERAGE ANALYSIS", style="bold cyan")
    console.print("=" * 50, style="cyan")
    console.print(f"📍 Location: {config.home_lat:.4f}°N, {config.home_lon:.4f}°W", style="white")
    console.print()

    # Overall status
    status = coverage_result["status"]
    if status.value == "covered":
        console.print("✅ COVERAGE STATUS: FULL COVERAGE", style="green bold")
        console.print("All NOAA data sources are available for this location.", style="green")
    elif status.value == "marginal":
        console.print("⚠️  COVERAGE STATUS: MARGINAL COVERAGE", style="yellow bold")
        console.print("Some NOAA data sources may be limited for this location.", style="yellow")
    else:
        console.print("❌ COVERAGE STATUS: OUTSIDE COVERAGE", style="red bold")
        console.print("This location is outside NOAA coverage area.", style="red")

    console.print()

    # Service-specific status
    console.print("🔍 SERVICE COVERAGE:", style="bold white")

    # NHC Status
    nhc_status = coverage_result.get("nhc_status")
    if nhc_status:
        nhc_icon = "✅" if nhc_status.value == "covered" else "⚠️" if nhc_status.value == "marginal" else "❌"
        nhc_color = "green" if nhc_status.value == "covered" else "yellow" if nhc_status.value == "marginal" else "red"
        console.print(f"  {nhc_icon} NHC Hurricane Forecasts: {nhc_status.value.upper()}", style=nhc_color)

    # NWS Status
    nws_status = coverage_result.get("nws_status")
    if nws_status:
        nws_icon = "✅" if nws_status.value == "covered" else "⚠️" if nws_status.value == "marginal" else "❌"
        nws_color = "green" if nws_status.value == "covered" else "yellow" if nws_status.value == "marginal" else "red"
        console.print(f"  {nws_icon} NWS Weather Alerts: {nws_status.value.upper()}", style=nws_color)

    # Caribbean Status
    caribbean_status = coverage_result.get("caribbean_status")
    if caribbean_status:
        carib_icon = "✅" if caribbean_status.value == "covered" else "⚠️" if caribbean_status.value == "marginal" else "❌"
        carib_color = "green" if caribbean_status.value == "covered" else "yellow" if caribbean_status.value == "marginal" else "red"
        console.print(f"  {carib_icon} Caribbean/Gulf Priority: {caribbean_status.value.upper()}", style=carib_color)

    console.print()

    # Warnings
    if coverage_result["warnings"]:
        console.print("⚠️  WARNINGS:", style="yellow bold")
        for warning in coverage_result["warnings"]:
            console.print(f"  • {warning}", style="yellow")
        console.print()

    # Errors
    if coverage_result["errors"]:
        console.print("❌ ERRORS:", style="red bold")
        for error in coverage_result["errors"]:
            console.print(f"  • {error}", style="red")
        console.print()

    # Recommendations for out-of-coverage locations
    if coverage_result["is_outside"] or coverage_result["is_marginal"]:
        from .coverage_validator import CoverageValidator
        validator = CoverageValidator()
        recommendations = validator.get_coverage_recommendations(
            config.home_lat, config.home_lon
        )

        if recommendations:
            console.print("📋 RECOMMENDATIONS:", style="cyan bold")
            for recommendation in recommendations:
                console.print(f"  {recommendation}", style="white")
            console.print()

    # Usage guidance
    if coverage_result["is_covered"]:
        console.print("✅ This location is fully supported by weatherbot!", style="green bold")
    elif coverage_result["is_marginal"]:
        console.print("⚠️  This location has limited support. Consider using coordinates closer to the US/Caribbean.", style="yellow bold")
    else:
        console.print("❌ This location is not supported. Please use coordinates within NOAA coverage areas.", style="red bold")




if __name__ == "__main__":
    app()
