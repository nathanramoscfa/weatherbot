# User Guide

This comprehensive guide covers everything you need to know to use Weatherbot effectively.

## Table of Contents

- [Getting Started](#getting-started)
- [Basic Usage](#basic-usage)
- [Command Reference](#command-reference)
- [Alert System](#alert-system)
- [AI Features](#ai-features)
- [Automation](#automation)
- [Advanced Features](#advanced-features)

## Getting Started

### First Run

After installation and configuration:

1. **Test your setup**:
   ```bash
   weatherbot check-coverage
   ```

2. **Test notifications**:
   ```bash
   weatherbot test-alert
   ```

3. **Run once to verify**:
   ```bash
   weatherbot run --once --verbose
   ```

### Understanding Your Location

Weatherbot works differently based on your location:

- **NOAA Coverage Areas**: Full functionality with official data
- **Outside NOAA Coverage**: AI web search fallback
- **Marginal Coverage**: Limited but functional

Use `weatherbot check-coverage` to understand your location's support level.

## Basic Usage

### Monitoring Commands

#### Continuous Monitoring
```bash
# Run continuous monitoring
weatherbot run

# Run with verbose logging
weatherbot run --verbose
```

#### One-Time Check
```bash
# Run once and exit (good for scheduled tasks)
weatherbot run --once
```

#### AI Analysis
```bash
# Get AI-powered threat analysis
weatherbot ai-analysis
```

### Information Commands

#### Coverage Check
```bash
# Check if your location is supported
weatherbot check-coverage
```

#### View Official Maps
```bash
# Open NOAA hurricane map in browser
weatherbot show-map
```

#### Current State
```bash
# Show current system state
weatherbot state show

# Clear saved state
weatherbot state clear
```

### Testing Commands

#### Test Notifications
```bash
# Test toast notifications and sounds
weatherbot test-alert
```

#### Debug Information
```bash
# Show NHC data layers
weatherbot debug layers

# Show active storm data
weatherbot debug storm-data

# Test AI storm detection
weatherbot debug test-ai

# Clear API cache
weatherbot debug clear-cache
```

## Alert System

### 5-Level Alert System

Weatherbot uses a sophisticated 5-level alert system:

#### Level 1: All Clear ✅
- **Condition**: No threats detected
- **Action**: Normal activities, no preparation needed
- **Color**: Green

#### Level 2: Tropical Storm Threat 🌪️
- **Condition**: Disturbance with 5-7 day potential impact
- **Action**: Monitor forecasts, review plans
- **Color**: Orange

#### Level 3: Tropical Storm Watch/Hurricane Threat 🛑
- **Condition**: TS Watch issued OR hurricane shows potential trajectory
- **Action**: Stock supplies, pack go-bag, plan evacuation
- **Color**: Deep Orange

#### Level 4: Evacuation Zone 🚨
- **Condition**: TS Warning, Hurricane Watch, or evacuation order
- **Action**: Evacuate vulnerable areas immediately
- **Color**: Red

#### Level 5: Hurricane Warning 🌀
- **Condition**: Hurricane conditions expected within 36 hours
- **Action**: Take shelter, expect outages
- **Color**: Dark Red

### Alert Triggers

Alerts are triggered by:
- **Forecast Cone Intersection**: Your location enters a storm's forecast cone
- **NWS Watches/Warnings**: Official weather service alerts
- **AI Analysis**: Intelligent threat assessment from NOAA maps
- **Storm Proximity**: Distance-based threat evaluation

### Alert Cooldown

To prevent spam, alerts have a configurable cooldown period:
```env
ALERT_COOLDOWN_MINUTES=60  # Wait 60 minutes between duplicate alerts
```

## AI Features

### AI Map Analysis

When OpenAI API key is configured, Weatherbot provides enhanced analysis:

#### NOAA Coverage Areas
- Analyzes official NOAA tropical weather outlook maps
- Combines geometric cone analysis with AI interpretation
- Provides detailed threat assessments and recommendations

#### Global Coverage (Outside NOAA)
- Uses AI web search to find local weather alerts
- Searches meteorological services worldwide
- Provides location-specific threat analysis

### Configuring AI

1. **Get OpenAI API Key**:
   - Sign up at [OpenAI](https://openai.com)
   - Generate API key in dashboard
   - Add to `.env` file:
     ```env
     OPENAI_API_KEY=your_api_key_here
     ```

2. **Test AI Features**:
   ```bash
   weatherbot debug test-ai
   weatherbot ai-analysis
   ```

### AI Analysis Output

AI analysis provides:
- **Threat Level**: 1-5 scale assessment
- **Situation Summary**: Current conditions
- **Detailed Assessment**: Storm-by-storm analysis
- **Action Recommendations**: Location-specific guidance
- **Storm Details**: Position, intensity, movement

## Automation

### Windows Task Scheduler

Create automated monitoring:

1. **Open Task Scheduler**
2. **Create Basic Task**:
   - Name: "Weatherbot Monitor"
   - Trigger: Daily, every 4 hours
   - Action: Start program
   - Program: `weatherbot`
   - Arguments: `run --once`

### Cron Jobs (Linux/macOS)

```bash
# Edit crontab
crontab -e

# Add entry for every 4 hours
0 */4 * * * /path/to/venv/bin/weatherbot run --once
```

### PowerShell Scripts

Use the provided scripts in `scripts/`:
- `run_once.ps1`: Single execution
- `register_task.ps1`: Register scheduled task

## Advanced Features

### County-Level Detection

For more precise threat detection:

1. **Enable county intersection**:
   ```env
   USE_COUNTY_INTERSECT=true
   COUNTY_GEOJSON_PATH=path/to/county.geojson
   ```

2. **Obtain county GeoJSON**:
   - Download from Census Bureau
   - Use provided default area
   - Create custom boundary

### Custom Notification Settings

```env
# Disable toast notifications
TOAST_ENABLED=false

# Adjust alert frequency
ALERT_COOLDOWN_MINUTES=120
```

### Logging Configuration

```env
# Set logging level
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR

# Logs are saved to logs/weatherbot.log
```

### State Management

Weatherbot maintains state to prevent duplicate alerts:

- **Location**: `state/weatherbot_state.json`
- **Contents**: Last alert times, storm advisories, alert IDs
- **Management**: Use `weatherbot state` commands

## Data Sources

### Primary Sources (NOAA Coverage)
- **NHC MapServer**: Real-time forecast cones
- **NWS API**: Official weather alerts
- **NOAA Maps**: Tropical weather outlook imagery
- **CurrentStorms.json**: Active storm positions

### Fallback Sources (Global)
- **AI Web Search**: Local meteorological services
- **OpenAI**: Intelligent analysis and recommendations

## Best Practices

### Location Setup
- Use precise coordinates for your exact location
- Verify coverage with `weatherbot check-coverage`
- Consider county-level detection for coastal areas

### Monitoring Strategy
- Run every 2-4 hours during hurricane season
- Use `--once` flag for scheduled tasks
- Enable verbose logging during active threats

### Alert Management
- Test notifications before hurricane season
- Set appropriate cooldown periods
- Review and update evacuation plans regularly

### AI Usage
- Configure OpenAI API key for enhanced analysis
- Monitor API usage and costs
- Use AI analysis during uncertain conditions

## Troubleshooting

### Common Issues

#### No Alerts Received
1. Check `weatherbot test-alert`
2. Verify coordinates with `weatherbot check-coverage`
3. Check cooldown settings
4. Review logs in `logs/weatherbot.log`

#### Inaccurate Alerts
1. Verify coordinate precision
2. Consider county-level detection
3. Check NOAA coverage status
4. Update to latest version

#### AI Analysis Fails
1. Verify OpenAI API key
2. Check API quota and billing
3. Test with `weatherbot debug test-ai`
4. Review error logs

### Getting Help

1. **Check Documentation**: Review all guides in `docs/`
2. **Enable Verbose Logging**: Use `--verbose` flag
3. **Review Logs**: Check `logs/weatherbot.log`
4. **GitHub Issues**: Report bugs with logs and configuration
5. **Community**: Join discussions and share experiences

## Next Steps

- **Explore [Alert System Guide](alerts.md)** for detailed alert information
- **Read [AI Integration Guide](ai-integration.md)** for advanced AI features
- **Check [Troubleshooting Guide](troubleshooting.md)** for common issues
- **Review [Configuration Reference](configuration.md)** for all options
