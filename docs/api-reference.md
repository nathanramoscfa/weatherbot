# API Reference

Complete API documentation for Weatherbot's Python modules and classes.

## Core Modules

### weatherbot.config

Configuration management using Pydantic settings.

#### WeatherbotConfig

```python
class WeatherbotConfig(BaseSettings):
    """Main configuration class for Weatherbot."""
```

**Fields:**
- `home_lat: float` - Home latitude in decimal degrees (-90 to 90)
- `home_lon: float` - Home longitude in decimal degrees (-180 to 180)
- `use_county_intersect: bool` - Use county-level intersection (default: False)
- `county_geojson_path: Optional[str]` - Path to county GeoJSON file
- `toast_enabled: bool` - Enable Windows toast notifications (default: True)
- `alert_cooldown_minutes: int` - Cooldown between alerts (default: 0)
- `openai_api_key: Optional[str]` - OpenAI API key for AI features
- `log_level: str` - Logging level (default: "INFO")

**Methods:**

```python
def validate_coverage(self) -> dict:
    """Validate coordinate coverage for NOAA data sources."""
```

```python
def get_county_geojson_path(self) -> Path:
    """Get the area coverage GeoJSON file path."""
```

```python
def get_alert_icon_path(self) -> Path:
    """Get the alert icon file path."""
```

**Usage:**
```python
from weatherbot.config import load_config

config = load_config()
print(f"Location: {config.home_lat}, {config.home_lon}")
```

### weatherbot.alert_levels

5-level alert system with evacuation guidance.

#### AlertLevel

```python
class AlertLevel(Enum):
    """5-Level Storm Alert System."""
    
    ALL_CLEAR = 1
    TROPICAL_STORM_THREAT = 2
    TROPICAL_STORM_WATCH_HURRICANE_THREAT = 3
    TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION = 4
    HURRICANE_WARNING = 5
```

#### AlertInfo

```python
class AlertInfo:
    """Alert information and guidance."""
    
    def __init__(
        self,
        level: AlertLevel,
        icon: str,
        color: str,
        sound_pattern: str,
        title_prefix: str,
        guidance: str,
    ) -> None:
```

**Functions:**

```python
def get_alert_level(
    in_disturbance_cone: bool,
    in_hurricane_cone: bool,
    has_hurricane_watch: bool,
    has_hurricane_warning: bool,
    has_tropical_storm_watch: bool = False,
    has_tropical_storm_warning: bool = False,
    has_evacuation_order: bool = False,
    storm_type: str = "unknown",
    days_until_impact: int = 7,
) -> AlertLevel:
    """Determine alert level based on current conditions."""
```

```python
def get_alert_info(level: AlertLevel, location_name: str = "your location") -> AlertInfo:
    """Get alert information for a given level."""
```

```python
def format_alert_message(
    level: AlertLevel,
    storm_names: list,
    location_name: str = "your location",
    storm_details: list = None,
) -> Tuple[str, str]:
    """Format alert title and message for a given level."""
```

### weatherbot.nhc

National Hurricane Center data integration.

#### NHCClient

```python
class NHCClient:
    """Client for NHC MapServer API."""
```

**Methods:**

```python
def get_layers_info(self) -> List[Dict]:
    """Get information about available map layers."""
```

```python
def discover_cone_layer(self) -> Optional[int]:
    """Discover the forecast cone layer ID."""
```

```python
def fetch_active_cones(self) -> List[StormCone]:
    """Fetch active hurricane forecast cones."""
```

**Functions:**

```python
def get_active_cones() -> Tuple[List[StormCone], List[Polygon]]:
    """Get active hurricane forecast cones and geometries."""
```

#### StormCone

```python
@dataclass
class StormCone:
    """Hurricane forecast cone data."""
    
    storm_id: Optional[str]
    storm_name: Optional[str]
    storm_type: Optional[str]
    advisory_num: Optional[str]
    geometry: Optional[Polygon]
    current_position: Optional[Tuple[float, float]]
    max_winds: Optional[int]
    min_pressure: Optional[int]
    movement: Optional[str]
```

### weatherbot.nws

National Weather Service alerts integration.

#### NWSAlert

```python
@dataclass
class NWSAlert:
    """NWS weather alert."""
    
    id: str
    event: str
    headline: str
    description: str
    severity: str
    certainty: str
    urgency: str
    areas: List[str]
    effective: Optional[datetime]
    expires: Optional[datetime]
```

**Methods:**

```python
def get_severity_prefix(self) -> str:
    """Get severity prefix for display."""
```

**Functions:**

```python
def get_hurricane_alerts(latitude: float, longitude: float) -> List[NWSAlert]:
    """Get hurricane-related alerts for a location."""
```

### weatherbot.geometry

Geometric operations for spatial analysis.

**Functions:**

```python
def validate_coordinates(longitude: float, latitude: float) -> None:
    """Validate coordinate ranges."""
```

```python
def point_in_any(geometries: List[Polygon], point: Tuple[float, float]) -> bool:
    """Check if point is in any of the geometries."""
```

```python
def polygon_intersects_any(geometries: List[Polygon], polygon: Polygon) -> bool:
    """Check if polygon intersects any of the geometries."""
```

```python
def load_county_polygon(geojson_path: Path) -> Polygon:
    """Load county polygon from GeoJSON file."""
```

### weatherbot.ai_map_analyzer

AI-powered analysis of NOAA hurricane maps.

#### AIMapAnalyzer

```python
class AIMapAnalyzer:
    """AI-powered analysis of NOAA hurricane maps."""
    
    def __init__(self, api_key: str) -> None:
```

**Methods:**

```python
def analyze_threat_for_location(
    self,
    latitude: float,
    longitude: float,
    location_name: str,
    basin: str = "atlantic",
    geometric_results: Optional[Dict] = None,
) -> Tuple[int, str, str]:
    """Analyze hurricane threat for a specific location."""
```

**Functions:**

```python
def analyze_hurricane_threat_with_ai(
    latitude: float,
    longitude: float,
    location_name: str,
    api_key: str,
    basin: str = "atlantic",
    geometric_results: Optional[Dict] = None,
) -> Tuple[int, str, str]:
    """Analyze hurricane threat using AI with geometric results."""
```

### weatherbot.ai_web_search

AI web search for global weather alerts.

**Functions:**

```python
def analyze_weather_threat_web_search(
    latitude: float,
    longitude: float,
    location_name: str,
    api_key: str,
) -> Tuple[int, str, str]:
    """Analyze weather threats using AI web search for global coverage."""
```

### weatherbot.enhanced_cone_analyzer

Enhanced geometric analysis of hurricane threats.

#### ThreatAnalysis

```python
@dataclass
class ThreatAnalysis:
    """Threat analysis for a single storm."""
    
    cone: StormCone
    is_in_cone: bool
    distance_km: float
    threat_level: AlertLevel
    days_until_impact: int
```

**Functions:**

```python
def analyze_location_threat_enhanced(
    latitude: float,
    longitude: float,
    use_county_intersect: bool = False,
    county_geojson_path: Optional[str] = None,
) -> Dict:
    """Enhanced threat analysis combining multiple data sources."""
```

### weatherbot.alerting

Alert management and notification system.

#### AlertManager

```python
class AlertManager:
    """Manages weather alerts and notifications."""
    
    def __init__(self, config: WeatherbotConfig) -> None:
```

**Methods:**

```python
def raise_alert(
    self,
    alert_type: str,
    title: str,
    message: str,
    cone_geometries: Optional[List] = None,
    storm_info: Optional[List] = None,
) -> None:
    """Raise a weather alert."""
```

```python
def test_notifications(self) -> None:
    """Test notification systems."""
```

**Functions:**

```python
def create_alert_manager(config: WeatherbotConfig) -> AlertManager:
    """Create alert manager with configured notifiers."""
```

### weatherbot.state

State management for persistent data.

#### WeatherbotState

```python
class WeatherbotState:
    """Persistent state for Weatherbot."""
    
    def __init__(self) -> None:
```

**Methods:**

```python
def set_in_cone_status(self, in_cone: bool) -> None:
    """Set current in-cone status."""
```

```python
def is_new_cone_advisory(self, storm_id: str, advisory_num: str) -> bool:
    """Check if this is a new cone advisory."""
```

```python
def update_cone_advisory(self, storm_id: str, advisory_num: str) -> None:
    """Update cone advisory tracking."""
```

```python
def is_new_alert(self, alert_id: str) -> bool:
    """Check if this is a new alert."""
```

```python
def add_alert_id(self, alert_id: str) -> None:
    """Add alert ID to processed list."""
```

#### StateManager

```python
class StateManager:
    """Manages persistent state storage."""
    
    def __init__(self, state_file: Optional[Path] = None) -> None:
```

**Methods:**

```python
def load_state(self) -> WeatherbotState:
    """Load state from file."""
```

```python
def save_state(self, state: WeatherbotState) -> None:
    """Save state to file."""
```

```python
def clear_state(self) -> None:
    """Clear state file."""
```

```python
def show_state(self) -> Dict:
    """Show current state as dictionary."""
```

### weatherbot.reports

HTML report generation.

**Functions:**

```python
def generate_html_report(
    alert_level: int,
    alert_enum: AlertLevel,
    alert_info: any,
    title: str,
    message: str,
    config: WeatherbotConfig,
    location_name: str,
    storm_cone_data: List[dict],
) -> str:
    """Generate comprehensive HTML threat analysis report."""
```

```python
def get_location_name(
    latitude: float,
    longitude: float,
    openai_api_key: Optional[str] = None,
) -> str:
    """Get human-readable location name from coordinates."""
```

### weatherbot.coverage_validator

NOAA coverage validation.

#### CoverageValidator

```python
class CoverageValidator:
    """Validates coordinate coverage for NOAA data sources."""
    
    def validate_coordinates(self, latitude: float, longitude: float) -> Dict:
        """Validate coordinates against NOAA coverage areas."""
```

```python
def get_coverage_recommendations(
    self, latitude: float, longitude: float
) -> List[str]:
    """Get recommendations for improving coverage."""
```

**Functions:**

```python
def validate_coordinate_coverage(latitude: float, longitude: float) -> Dict:
    """Validate coordinate coverage (convenience function)."""
```

### weatherbot.cache

API response caching.

#### APICache

```python
class APICache:
    """Simple file-based cache for API responses."""
    
    def get(self, key: str) -> Optional[Dict]:
        """Get cached response."""
```

```python
def set(self, key: str, data: Dict, ttl_minutes: int = 30) -> None:
    """Cache response with TTL."""
```

```python
def clear(self) -> None:
    """Clear all cached data."""
```

## CLI Interface

### Main Commands

```bash
weatherbot run [--once] [--verbose]
weatherbot ai-analysis
weatherbot test-alert
weatherbot check-coverage
weatherbot show-map [--force]
```

### State Commands

```bash
weatherbot state show
weatherbot state clear
```

### Debug Commands

```bash
weatherbot debug layers
weatherbot debug storm-data
weatherbot debug current-storms
weatherbot debug discover-storms
weatherbot debug test-ai
weatherbot debug clear-cache
```

## Error Handling

### Common Exceptions

- `ValueError`: Invalid coordinates or configuration
- `ConnectionError`: Network connectivity issues
- `FileNotFoundError`: Missing configuration or data files
- `PermissionError`: File system access issues

### Error Codes

CLI commands return standard exit codes:
- `0`: Success
- `1`: General error
- `2`: Configuration error
- `3`: Network error

## Usage Examples

### Basic Monitoring

```python
from weatherbot.config import load_config
from weatherbot.enhanced_cone_analyzer import analyze_location_threat_enhanced

config = load_config()
threat_analysis = analyze_location_threat_enhanced(
    latitude=config.home_lat,
    longitude=config.home_lon,
)

print(f"Alert Level: {threat_analysis['alert_level']}")
print(f"Storms: {len(threat_analysis['storm_threats'])}")
```

### AI Analysis

```python
from weatherbot.ai_map_analyzer import analyze_hurricane_threat_with_ai

alert_level, title, message = analyze_hurricane_threat_with_ai(
    latitude=25.7617,
    longitude=-80.1918,
    location_name="Miami, FL",
    api_key="your_openai_key",
)

print(f"Level {alert_level}: {title}")
```

### Custom Notifications

```python
from weatherbot.alerting import AlertManager
from weatherbot.config import load_config

config = load_config()
alert_manager = AlertManager(config)

alert_manager.raise_alert(
    alert_type="HURRICANE_WARNING",
    title="Hurricane Warning",
    message="Hurricane conditions expected within 36 hours.",
)
```

## Type Hints

Weatherbot uses comprehensive type hints. Import types:

```python
from typing import Dict, List, Optional, Tuple
from weatherbot.alert_levels import AlertLevel, AlertInfo
from weatherbot.nhc import StormCone
from weatherbot.nws import NWSAlert
```
