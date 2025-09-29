# Weatherbot

A local hurricane alert system with NHC cone tracking, NWS alerts, and AI-powered threat analysis.

## ⚠️ IMPORTANT DISCLAIMER

**THIS SOFTWARE IS PROVIDED FOR INFORMATIONAL PURPOSES ONLY AND SHOULD NOT BE USED AS THE SOLE SOURCE FOR LIFE-SAFETY DECISIONS.**

- **NOT AN OFFICIAL SOURCE**: Weatherbot is not affiliated with or endorsed by NOAA, NHC, NWS, or any official weather service
- **NO WARRANTY**: This software is provided "AS IS" without warranty of any kind, express or implied
- **AI LIMITATIONS**: AI-powered analysis may produce incorrect assessments and should never replace official meteorological guidance
- **USER RESPONSIBILITY**: Users must independently verify all weather information through official sources
- **EMERGENCY GUIDANCE**: Always follow official evacuation orders and emergency guidance from local authorities
- **NO LIABILITY**: The authors and contributors assume no responsibility for decisions made based on this software

**For official weather information and emergency guidance, always consult:**
- National Hurricane Center (nhc.noaa.gov)
- National Weather Service (weather.gov)
- Local emergency management authorities
- Official evacuation orders and emergency broadcasts

**📋 FULL LEGAL DISCLAIMER**: See [DISCLAIMER.md](DISCLAIMER.md) for complete liability terms and conditions.

## Overview

Weatherbot is a comprehensive hurricane monitoring and alerting system designed to provide real-time notifications for tropical weather threats. It combines data from the National Hurricane Center (NHC) forecast cones, National Weather Service (NWS) alerts, and optional AI-powered analysis of official NOAA weather maps to deliver precise, location-specific threat assessments.

### Key Features

- **Real-time Hurricane Tracking**: Monitors active NHC forecast cones and determines if your location is at risk
- **NWS Alert Integration**: Receives and processes official hurricane watches and warnings
- **AI-Enhanced Analysis**: Optional OpenAI integration for intelligent threat assessment using official NOAA maps
- **Multi-level Alert System**: 5-tier alert system from "All Clear" to "Hurricane Warning"
- **Multiple Notification Methods**: Toast notifications
- **Geometric Precision**: Point-in-polygon and county-level intersection analysis
- **Comprehensive Reporting**: Generates detailed HTML reports with storm tracking maps
- **Flexible Configuration**: Supports both point-based and county-based threat detection

## Installation

### Prerequisites

- Python 3.11 or higher
- Windows 10/11 (for toast notifications)

### Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/nathanramoscfa/weatherbot.git
   cd weatherbot
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate
   
   # Linux/macOS
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install the package**:
   ```bash
   pip install -e .
   ```

4. **Install development dependencies** (optional):
   ```bash
   pip install -e .[dev]
   ```

5. **Configure environment variables**:
   Copy `env.example` to `.env` and configure your settings:
   ```bash
   copy env.example .env
   ```

   Edit `.env` with your location and preferences:
   ```env
   # Required: Your home coordinates
   HOME_LAT=25.7617
   HOME_LON=-80.1918

   # Optional: OpenAI API key for AI analysis
   OPENAI_API_KEY=your_api_key_here

   # Optional: County-based intersection (requires GeoJSON file)
   USE_COUNTY_INTERSECT=false
   COUNTY_GEOJSON_PATH=src/weatherbot/data/default_area.geojson

   # Alert settings
   ALERT_COOLDOWN_MINUTES=60
   TOAST_ENABLED=true
   ```

## How to Run

### Basic Monitoring

Run the main monitoring cycle:
```bash
weatherbot run
```

Run once and exit (useful for scheduled tasks):
```bash
weatherbot run --once
```

Run with verbose logging:
```bash
weatherbot run --verbose
```

### AI-Powered Analysis

Get AI analysis of current hurricane threats:
```bash
weatherbot ai-analysis
```

**🌍 Global Coverage**: For locations outside NOAA coverage areas, weatherbot automatically uses AI web search to find weather alerts and warnings from local meteorological services, providing worldwide weather threat analysis.

### Testing Notifications

Test your notification systems:
```bash
weatherbot test-alert
```

### Check Coverage

Validate if your coordinates are within NOAA coverage areas:
```bash
weatherbot check-coverage
```

### View Official Maps

Open the official NOAA hurricane map:
```bash
weatherbot show-map
```

### State Management

View current state:
```bash
weatherbot state show
```

Clear state file:
```bash
weatherbot state clear
```

### Debug Commands

View NHC MapServer layers:
```bash
weatherbot debug layers
```

Show detailed storm data:
```bash
weatherbot debug storm-data
```

Test AI storm detection:
```bash
weatherbot debug test-ai
```

Clear API cache:
```bash
weatherbot debug clear-cache
```

## How to Test

### Running Tests

Run all tests:
```bash
pytest
```

Run tests with verbose output:
```bash
pytest -v
```

Run specific test files:
```bash
pytest tests/test_smoke.py
pytest tests/test_geometry.py
```

Run tests with coverage:
```bash
pytest --cov=weatherbot
```

### Test Categories

- **Smoke Tests** (`test_smoke.py`): Basic import and configuration tests
- **Geometry Tests** (`test_geometry.py`): Coordinate validation and geometric operations
- **Integration Tests**: End-to-end functionality testing

### Development Setup

1. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

2. **Run code formatting**:
   ```bash
   black src/ tests/
   ```

3. **Run linting**:
   ```bash
   ruff check src/ tests/
   ```

4. **Run type checking**:
   ```bash
   mypy src/weatherbot
   ```

5. **Run security scans**:
   ```bash
   make security
   ```

## Configuration

### Required Settings

- `HOME_LAT`: Your latitude (decimal degrees)
- `HOME_LON`: Your longitude (decimal degrees, negative for Western Hemisphere)

**⚠️ Important**: 
- **NOAA Coverage**: Atlantic Basin (0-60°N, 100°W-0°E), Eastern Pacific Basin (0-60°N, 180°W-100°W), Central Pacific Basin (0-60°N, 180°W-140°W)
- **Global Coverage**: Locations outside NOAA coverage automatically use AI web search fallback
- **Recommended**: US East Coast, Caribbean, Gulf of Mexico for most accurate results

Use `weatherbot check-coverage` to validate your coordinates before running the system.

### Optional Settings

- `OPENAI_API_KEY`: Enable AI-powered threat analysis
- `USE_COUNTY_INTERSECT`: Use county polygon instead of point-based detection
- `COUNTY_GEOJSON_PATH`: Path to county boundary GeoJSON file
- `ALERT_COOLDOWN_MINUTES`: Minimum time between alerts (default: 60)
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)

### Notification Settings

- `TOAST_ENABLED`: Enable Windows toast notifications

## Alert Levels

1. **Level 1 - All Clear**: No threats detected
2. **Level 2 - Tropical Storm Threat**: Tropical storm conditions possible
3. **Level 3 - Hurricane Threat**: Hurricane conditions possible, tropical storm watch/warning may be in effect
4. **Level 4 - Evacuation Zone**: Hurricane watch in effect, evacuation may be recommended
5. **Level 5 - Hurricane Warning**: Hurricane warning in effect, immediate action required

## Architecture

### Core Components

- **CLI Interface** (`cli.py`): Typer-based command-line interface
- **Configuration** (`config.py`): Pydantic-based settings management
- **NHC Integration** (`nhc.py`, `nhc_storm_tracker.py`): Hurricane cone data retrieval
- **NWS Integration** (`nws.py`): Weather alert processing
- **AI Analysis** (`ai_map_analyzer.py`, `ai_enhancer.py`): OpenAI-powered threat assessment
- **Geometry Engine** (`geometry.py`): Spatial analysis and intersection detection
- **Alert System** (`alerting.py`, `alert_levels.py`): Multi-tier notification system
- **State Management** (`state.py`): Persistent state tracking
- **Reporting** (`reports.py`): HTML report generation

### Data Sources

- **NHC MapServer**: Real-time hurricane forecast cones
- **NWS API**: Official weather alerts and warnings
- **NOAA Maps**: Official tropical weather outlook imagery
- **CurrentStorms.json**: Active storm position data

## License and Liability

MIT License - see [LICENSE](LICENSE) file for details.

### Additional Liability Disclaimer

**WEATHERBOT IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND.** The MIT License includes important liability limitations, but we want to emphasize:

- **NO WARRANTIES**: No express or implied warranties regarding accuracy, reliability, or fitness for any particular purpose
- **NO LIABILITY**: Authors and contributors shall not be liable for any damages arising from use of this software
- **WEATHER RISKS**: Weather prediction and alerting involves inherent uncertainties and risks
- **USER ASSUMES RISK**: Users assume all risks associated with relying on this software for weather-related decisions

**CRITICAL**: This software may produce false positives, false negatives, or incorrect threat assessments. Never rely solely on Weatherbot for life-safety decisions.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## Support

For issues and questions, please use the GitHub issue tracker.