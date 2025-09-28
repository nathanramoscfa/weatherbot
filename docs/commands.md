# Command Reference

Complete reference for all Weatherbot CLI commands.

## Main Commands

### weatherbot run

Run the main monitoring cycle.

```bash
weatherbot run [OPTIONS]
```

**Options**:
- `--once`: Run once and exit (useful for scheduled tasks)
- `--verbose, -v`: Enable verbose logging

**Examples**:
```bash
# Continuous monitoring
weatherbot run

# Run once and exit
weatherbot run --once

# Verbose monitoring
weatherbot run --verbose

# One-time verbose check
weatherbot run --once --verbose
```

**Behavior**:
- Loads configuration from `.env` file
- Validates coordinates and coverage
- Checks NHC forecast cones
- Monitors NWS alerts
- Triggers notifications for threats
- Uses AI analysis if API key configured
- Saves state to prevent duplicate alerts

### weatherbot ai-analysis

Get AI-powered threat analysis.

```bash
weatherbot ai-analysis
```

**Requirements**:
- OpenAI API key configured in `.env`

**Behavior**:
- For NOAA coverage areas: Analyzes official NOAA maps
- For global locations: Uses AI web search
- Provides detailed threat assessment
- Generates HTML report
- Displays formatted analysis in terminal

**Example Output**:
```
🚨 WEATHERBOT AI THREAT ANALYSIS - LEVEL 3
📍 Miami, FL (25.7617°N, 80.1918°W)
🗺️ DATA SOURCE: Official NOAA Atlantic Maps + Geometric Analysis

🛑 TROPICAL STORM WATCH OR HURRICANE THREAT
Tropical disturbance shows potential Florida trajectory...
```

### weatherbot test-alert

Test notification systems.

```bash
weatherbot test-alert
```

**What it tests**:
- Windows toast notifications
- Alert sounds
- Notification formatting
- System permissions

**Expected behavior**:
- Toast notification appears
- Alert sound plays
- Success message displayed
- No errors in console

### weatherbot check-coverage

Validate coordinate coverage.

```bash
weatherbot check-coverage
```

**Output**:
- NOAA coverage status
- Service availability
- Recommendations for improvement
- Coverage area details

**Example Output**:
```
📊 NOAA COVERAGE ANALYSIS
📍 Location: 25.7617°N, 80.1918°W

✅ COVERAGE STATUS: FULL COVERAGE
All NOAA data sources are available for this location.

🔍 SERVICE COVERAGE:
  ✅ NHC Hurricane Forecasts: COVERED
  ✅ NWS Weather Alerts: COVERED
  ✅ Caribbean/Gulf Priority: COVERED
```

### weatherbot show-map

Open official NOAA hurricane map.

```bash
weatherbot show-map [OPTIONS]
```

**Options**:
- `--force`: Force show map even if no alerts

**Behavior**:
- Determines appropriate basin based on location
- Opens NOAA tropical weather outlook map
- Uses same map that AI analyzes
- Opens in default web browser

**Map URLs**:
- **Atlantic**: 7-day tropical weather outlook
- **Eastern Pacific**: 7-day tropical weather outlook
- **Central Pacific**: 7-day tropical weather outlook

## State Commands

### weatherbot state show

Display current system state.

```bash
weatherbot state show
```

**Output**: JSON formatted state information including:
- Last alert timestamps
- Storm advisory tracking
- In-cone status
- Processed alert IDs

**Example Output**:
```json
{
  "last_alert": "2024-09-15T14:30:00Z",
  "was_in_cone": true,
  "cone_advisories": {
    "AL092024": "15A"
  },
  "processed_alert_ids": [
    "urn:oid:2.49.0.1.840.0.123456789"
  ],
  "updated": "2024-09-15T14:30:00Z"
}
```

### weatherbot state clear

Clear all saved state.

```bash
weatherbot state clear
```

**Effect**:
- Removes state file
- Resets alert tracking
- Allows duplicate alerts
- Useful for testing or troubleshooting

## Debug Commands

### weatherbot debug layers

Show NHC MapServer layer information.

```bash
weatherbot debug layers
```

**Output**: Table showing available NHC map layers:
- Layer ID and name
- Layer type and description
- Forecast cone layer identification

### weatherbot debug storm-data

Display detailed storm information.

```bash
weatherbot debug storm-data
```

**Output**: Table with active storm data:
- Storm names and types
- Advisory numbers
- Current positions
- Wind speeds and pressures
- Enhanced with AI data when available

### weatherbot debug current-storms

Test CurrentStorms.json API directly.

```bash
weatherbot debug current-storms
```

**Purpose**: Direct test of NHC CurrentStorms.json endpoint
**Output**: Raw storm position and intensity data

### weatherbot debug discover-storms

Discover individual storm tracking pages.

```bash
weatherbot debug discover-storms
```

**Purpose**: Test storm page discovery mechanism
**Output**: List of discovered storm pages and cone URLs

### weatherbot debug test-ai

Test AI storm position detection.

```bash
weatherbot debug test-ai
```

**Requirements**: OpenAI API key configured
**Output**: AI-detected storm positions and probabilities
**Purpose**: Verify AI integration and analysis capabilities

### weatherbot debug clear-cache

Clear API response cache.

```bash
weatherbot debug clear-cache
```

**Effect**:
- Removes all cached API responses
- Forces fresh data retrieval on next run
- Useful for troubleshooting stale data

## Command Options

### Global Options

Available for all commands:

- `--help`: Show help message and exit
- `--version`: Show version information

### Verbose Logging

Enable detailed logging output:

```bash
weatherbot run --verbose
```

**Effect**:
- Sets log level to DEBUG
- Shows detailed processing steps
- Displays API requests and responses
- Useful for troubleshooting

### Environment Variables

Override configuration via environment variables:

```bash
# Temporary coordinate override
HOME_LAT=26.1224 HOME_LON=-80.1373 weatherbot run --once

# Temporary log level override
LOG_LEVEL=DEBUG weatherbot ai-analysis
```

## Exit Codes

Weatherbot uses standard exit codes:

- `0`: Success
- `1`: General error
- `2`: Configuration error
- `3`: Network error

**Usage in scripts**:
```bash
#!/bin/bash
weatherbot run --once
if [ $? -eq 0 ]; then
    echo "Weatherbot completed successfully"
else
    echo "Weatherbot failed with exit code $?"
    exit 1
fi
```

## Automation Examples

### Windows Task Scheduler

Create scheduled task using PowerShell:

```powershell
# Register daily task
$action = New-ScheduledTaskAction -Execute "weatherbot" -Argument "run --once"
$trigger = New-ScheduledTaskTrigger -Daily -At "06:00"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries
Register-ScheduledTask -TaskName "WeatherbotMonitor" -Action $action -Trigger $trigger -Settings $settings
```

### Linux Cron

Add to crontab for regular monitoring:

```bash
# Edit crontab
crontab -e

# Add entries
# Every 4 hours during hurricane season (June-November)
0 */4 * 6-11 * /path/to/venv/bin/weatherbot run --once

# Daily check during off-season
0 6 * 1-5,12 * /path/to/venv/bin/weatherbot run --once
```

### Batch Scripts

Windows batch script for automation:

```batch
@echo off
cd /d "%~dp0"
call "venv\Scripts\activate.bat"
weatherbot run --once
if %errorlevel% neq 0 (
    echo Weatherbot failed with error %errorlevel%
    exit /b %errorlevel%
)
echo Weatherbot completed successfully
```

Shell script for Linux/macOS:

```bash
#!/bin/bash
set -e

cd /path/to/weatherbot
source venv/bin/activate
weatherbot run --once

if [ $? -eq 0 ]; then
    echo "$(date): Weatherbot completed successfully" >> /var/log/weatherbot.log
else
    echo "$(date): Weatherbot failed with exit code $?" >> /var/log/weatherbot.log
    exit 1
fi
```

## Integration Examples

### Home Assistant

Command line sensor configuration:

```yaml
# configuration.yaml
command_line:
  - sensor:
      name: "Hurricane Alert Level"
      command: "weatherbot ai-analysis --json"
      value_template: "{{ value_json.alert_level }}"
      json_attributes:
        - title
        - message
        - location
      scan_interval: 3600
      
  - binary_sensor:
      name: "Hurricane Threat"
      command: "weatherbot run --once --json"
      value_template: "{{ value_json.alert_level >= 2 }}"
      device_class: safety
```

### Monitoring Scripts

Python script for custom monitoring:

```python
#!/usr/bin/env python3
import subprocess
import json
import sys
from datetime import datetime

def run_weatherbot():
    """Run weatherbot and return results."""
    try:
        result = subprocess.run(
            ["weatherbot", "ai-analysis", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Weatherbot failed: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Failed to parse output: {e}")
        return None

def send_notification(alert_level, title, message):
    """Send notification based on alert level."""
    if alert_level >= 4:
        # High priority notification
        subprocess.run(["notify-send", "--urgency=critical", title, message])
    elif alert_level >= 2:
        # Normal notification
        subprocess.run(["notify-send", title, message])

if __name__ == "__main__":
    print(f"{datetime.now()}: Running weatherbot analysis...")
    
    results = run_weatherbot()
    if results:
        alert_level = results.get("alert_level", 1)
        title = results.get("title", "Weather Update")
        message = results.get("message", "No threats detected")
        
        print(f"Alert Level: {alert_level}")
        print(f"Title: {title}")
        
        if alert_level >= 2:
            send_notification(alert_level, title, message)
            
        sys.exit(0)
    else:
        print("Failed to get weatherbot results")
        sys.exit(1)
```

## Command Chaining

Combine commands for comprehensive monitoring:

```bash
# Full monitoring sequence
weatherbot check-coverage && \
weatherbot test-alert && \
weatherbot run --once --verbose && \
weatherbot state show
```

```bash
# Conditional AI analysis
weatherbot run --once || weatherbot ai-analysis
```

```bash
# Clear state and run fresh analysis
weatherbot state clear && \
weatherbot debug clear-cache && \
weatherbot run --once --verbose
```

## Performance Considerations

### Command Execution Time

Typical execution times:
- `weatherbot run --once`: 10-30 seconds
- `weatherbot ai-analysis`: 15-45 seconds
- `weatherbot check-coverage`: 2-5 seconds
- `weatherbot test-alert`: 1-3 seconds

### Resource Usage

- **Memory**: 50-100MB during execution
- **Network**: 1-5MB per analysis cycle
- **CPU**: Low usage, brief spikes during analysis
- **Disk**: Minimal, mainly for logs and cache

### Optimization Tips

1. **Use appropriate cooldown periods** to reduce API calls
2. **Cache results** when running frequent checks
3. **Monitor during active threats** only
4. **Use `--once` flag** for scheduled tasks
5. **Clear cache periodically** to prevent stale data

## Troubleshooting Commands

### Diagnostic Sequence

Run this sequence to diagnose issues:

```bash
# 1. Check basic functionality
weatherbot --help

# 2. Validate configuration
weatherbot check-coverage

# 3. Test notifications
weatherbot test-alert

# 4. Run with verbose logging
weatherbot run --once --verbose

# 5. Check current state
weatherbot state show

# 6. Clear cache if needed
weatherbot debug clear-cache
```

### Error Investigation

For detailed error investigation:

```bash
# Enable debug logging
LOG_LEVEL=DEBUG weatherbot run --once --verbose 2>&1 | tee debug.log

# Check specific components
weatherbot debug layers
weatherbot debug storm-data
weatherbot debug current-storms

# Test AI if configured
weatherbot debug test-ai
```

### Recovery Commands

If Weatherbot is not working properly:

```bash
# Clear all cached data
weatherbot debug clear-cache

# Reset state
weatherbot state clear

# Verify configuration
weatherbot check-coverage

# Test basic functionality
weatherbot run --once --verbose
```
