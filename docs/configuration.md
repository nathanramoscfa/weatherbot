# Configuration Reference

Complete reference for all Weatherbot configuration options.

## Configuration File

Weatherbot uses a `.env` file for configuration. Copy `env.example` to `.env` and customize:

```bash
# Windows
copy env.example .env

# Linux/macOS
cp env.example .env
```

## Required Settings

### Location Coordinates

```env
# Your home coordinates (required)
HOME_LAT=25.7617
HOME_LON=-80.1918
```

**Format**: Decimal degrees
- **Latitude**: -90 to 90 (positive = North, negative = South)
- **Longitude**: -180 to 180 (positive = East, negative = West)

**Examples**:
```env
# Miami, Florida
HOME_LAT=25.7617
HOME_LON=-80.1918

# New York City
HOME_LAT=40.7128
HOME_LON=-74.0060

# London, UK (outside NOAA coverage)
HOME_LAT=51.5074
HOME_LON=-0.1278
```

**Finding Coordinates**:
1. **Google Maps**: Right-click location → copy coordinates
2. **GPS Device**: Use decimal degree format
3. **Online Tools**: Search "lat lon finder"

## Optional Settings

### County-Level Detection

```env
# Use county polygon instead of point detection
USE_COUNTY_INTERSECT=false
COUNTY_GEOJSON_PATH=src/weatherbot/data/default_area.geojson
```

**USE_COUNTY_INTERSECT**:
- `true`: Use county/area polygon for threat detection
- `false`: Use point-based detection (default)

**COUNTY_GEOJSON_PATH**:
- Path to GeoJSON file containing county/area boundaries
- Leave empty to use default area
- Supports absolute or relative paths

**When to Use**:
- Coastal areas with complex geography
- Large metropolitan areas
- Custom threat zones

### AI Enhancement

```env
# OpenAI API key for AI analysis
OPENAI_API_KEY=your_openai_api_key_here
```

**Features Enabled**:
- Enhanced threat analysis using NOAA maps
- Global weather alert search (outside NOAA coverage)
- Intelligent storm position detection
- Location-specific recommendations

**Getting API Key**:
1. Sign up at [OpenAI](https://openai.com)
2. Navigate to API section
3. Generate new API key
4. Add to `.env` file

**Cost Considerations**:
- Typical usage: $0.01-0.10 per analysis
- Monitor usage in OpenAI dashboard
- Set usage limits if needed

### Notification Settings

```env
# Toast notification settings
TOAST_ENABLED=true
```

**TOAST_ENABLED**:
- `true`: Enable Windows toast notifications (default)
- `false`: Disable toast notifications

**Platform Support**:
- **Windows 10/11**: Full toast support with sounds
- **Linux/macOS**: Limited notification support

### Alert Behavior

```env
# Alert cooldown period
ALERT_COOLDOWN_MINUTES=60
```

**ALERT_COOLDOWN_MINUTES**:
- `0`: No cooldown (immediate alerts)
- `60`: 1-hour cooldown (recommended)
- `240`: 4-hour cooldown (for frequent monitoring)

**Purpose**:
- Prevents alert spam
- Reduces notification fatigue
- Configurable based on monitoring frequency

### Logging Configuration

```env
# Logging level
LOG_LEVEL=INFO
```

**LOG_LEVEL Options**:
- `DEBUG`: Detailed debugging information
- `INFO`: General information (default)
- `WARNING`: Warning messages only
- `ERROR`: Error messages only
- `CRITICAL`: Critical errors only

**Log Files**:
- Location: `logs/weatherbot.log`
- Rotation: Automatic when file gets large
- Format: Timestamp, level, module, message

## Advanced Configuration

### Custom Data Paths

```env
# Custom paths (advanced users)
COUNTY_GEOJSON_PATH=/path/to/custom/area.geojson
```

**Custom GeoJSON Requirements**:
- Valid GeoJSON format
- Polygon or MultiPolygon geometry
- Coordinate system: WGS84 (EPSG:4326)

**Example GeoJSON Structure**:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [-80.2, 25.7],
          [-80.1, 25.7],
          [-80.1, 25.8],
          [-80.2, 25.8],
          [-80.2, 25.7]
        ]]
      },
      "properties": {
        "name": "Custom Area"
      }
    }
  ]
}
```

### Environment Variable Override

All settings can be overridden with environment variables:

```bash
# Windows PowerShell
$env:HOME_LAT="26.1224"
$env:HOME_LON="-80.1373"
weatherbot run --once

# Linux/macOS
HOME_LAT=26.1224 HOME_LON=-80.1373 weatherbot run --once
```

## Configuration Validation

### Coordinate Validation

Weatherbot validates coordinates on startup:

```bash
weatherbot check-coverage
```

**Validation Checks**:
- Coordinate range validation
- NOAA coverage assessment
- Service availability check
- Recommendation generation

### Coverage Areas

#### NOAA Coverage (Full Support)
- **Atlantic Basin**: 0-60°N, 100°W-0°E
- **Eastern Pacific**: 0-60°N, 180°W-100°W  
- **Central Pacific**: 0-60°N, 180°W-140°W

#### Optimal Coverage (Recommended)
- **US East Coast**: Florida to Maine
- **Gulf of Mexico**: Texas to Florida
- **Caribbean**: All major islands
- **Bermuda**: Atlantic coverage

#### Global Coverage (AI Fallback)
- **Europe**: UK, Ireland, Mediterranean
- **Asia-Pacific**: Japan, Philippines, Australia
- **Other**: Any location with internet weather services

### Configuration Examples

#### Standard US East Coast Setup
```env
# Miami, Florida - Full NOAA coverage
HOME_LAT=25.7617
HOME_LON=-80.1918
USE_COUNTY_INTERSECT=false
TOAST_ENABLED=true
ALERT_COOLDOWN_MINUTES=60
OPENAI_API_KEY=sk-your-key-here
LOG_LEVEL=INFO
```

#### County-Level Detection Setup
```env
# Coastal area with complex geography
HOME_LAT=25.7617
HOME_LON=-80.1918
USE_COUNTY_INTERSECT=true
COUNTY_GEOJSON_PATH=data/miami_dade_county.geojson
TOAST_ENABLED=true
ALERT_COOLDOWN_MINUTES=60
OPENAI_API_KEY=sk-your-key-here
LOG_LEVEL=INFO
```

#### Global Location Setup
```env
# London, UK - Outside NOAA coverage
HOME_LAT=51.5074
HOME_LON=-0.1278
USE_COUNTY_INTERSECT=false
TOAST_ENABLED=true
ALERT_COOLDOWN_MINUTES=120
OPENAI_API_KEY=sk-your-key-here  # Required for global coverage
LOG_LEVEL=INFO
```

#### Development/Testing Setup
```env
# Development configuration
HOME_LAT=25.7617
HOME_LON=-80.1918
USE_COUNTY_INTERSECT=false
TOAST_ENABLED=false  # Disable for testing
ALERT_COOLDOWN_MINUTES=0  # No cooldown for testing
OPENAI_API_KEY=sk-your-key-here
LOG_LEVEL=DEBUG  # Verbose logging
```

## Configuration Management

### Multiple Configurations

Use different `.env` files for different scenarios:

```bash
# Production
cp .env.production .env

# Development  
cp .env.development .env

# Testing
cp .env.testing .env
```

### Configuration Backup

Backup your configuration (without API keys):

```bash
# Create backup
cp .env .env.backup

# Restore backup
cp .env.backup .env
```

### Security Considerations

**API Key Security**:
- Never commit `.env` files to version control
- Use environment variables in production
- Rotate API keys regularly
- Monitor API usage

**File Permissions**:
```bash
# Restrict access to configuration file
chmod 600 .env
```

## Troubleshooting Configuration

### Common Issues

#### Invalid Coordinates
```
Error: Latitude must be between -90 and 90 degrees
```
**Solution**: Check coordinate format and ranges

#### Missing Configuration
```
Error: HOME_LAT is required
```
**Solution**: Ensure `.env` file exists and contains required settings

#### API Key Issues
```
Error: OpenAI API key invalid
```
**Solution**: Verify API key format and billing status

#### File Path Issues
```
Error: GeoJSON file not found
```
**Solution**: Check file path and permissions

### Validation Commands

```bash
# Check configuration
weatherbot check-coverage

# Test with verbose output
weatherbot run --once --verbose

# Validate specific settings
python -c "from weatherbot.config import load_config; print(load_config())"
```

### Debug Configuration

Enable debug mode to see configuration loading:

```env
LOG_LEVEL=DEBUG
```

```bash
weatherbot run --verbose
```

This will show:
- Configuration file loading
- Setting validation
- Coverage assessment
- Service initialization

## Best Practices

### Location Accuracy
- Use precise coordinates for your exact location
- Consider using county-level detection for coastal areas
- Validate coverage before relying on alerts

### Alert Management
- Set appropriate cooldown periods
- Test notifications before hurricane season
- Monitor log files for issues

### AI Usage
- Monitor OpenAI API costs
- Set usage limits if needed
- Use AI features during uncertain conditions

### Security
- Keep API keys secure
- Use environment variables in production
- Regular configuration backups

### Performance
- Use caching for frequent API calls
- Adjust logging levels appropriately
- Monitor system resources during continuous monitoring
