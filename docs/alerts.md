# Alert System Guide

Comprehensive guide to Weatherbot's 5-level hurricane alert system.

## Overview

Weatherbot uses a sophisticated 5-level alert system designed to provide clear, actionable guidance for hurricane threats. The system combines official weather service data with AI analysis to deliver precise threat assessments.

## Alert Levels

### Level 1: All Clear ✅

**Condition**: No active weather threats detected

**Indicators**:
- No tropical disturbances in forecast cones
- No NWS watches or warnings
- No storms showing trajectory toward your location

**Actions**:
- Normal activities
- No immediate preparation needed
- Stay informed during hurricane season

**Color**: Green (#4CAF50)

**Example Message**:
```
✅ ALL CLEAR
No active weather disturbances threatening your location. 
Normal activities. No immediate preparation needed.
```

### Level 2: Tropical Storm Threat 🌪️

**Condition**: Disturbance with potential 5-7 day impact

**Indicators**:
- Tropical disturbance or depression in development area
- Storm system showing potential trajectory toward location
- Early-stage threat requiring monitoring

**Actions**:
- Monitor local weather forecasts daily
- Review evacuation plan and emergency supplies
- Check local emergency services for updates
- No immediate action required

**Color**: Orange (#FF9800)

**Example Message**:
```
🌪️ TROPICAL STORM THREAT
Weather disturbance with potential to impact your location within 5–7 days.

ACTION:
• Monitor local weather forecasts daily
• Review evacuation plan and emergency supplies
• Check local emergency services for updates
• No immediate action required
```

### Level 3: Tropical Storm Watch/Hurricane Threat 🛑

**Condition**: Tropical Storm Watch issued OR Hurricane shows potential trajectory

**Indicators**:
- Tropical Storm Watch in effect (winds possible within 48 hours)
- Hurricane showing potential trajectory toward location within 3-5 days
- Escalated threat requiring preparation

**Actions**:
- Stock up on food, water, fuel, batteries
- Pack emergency go-bag and important documents
- Plan evacuation route and transportation
- Check local building notices and emergency services

**Color**: Deep Orange (#FF5722)

**Example Message**:
```
🛑 TROPICAL STORM WATCH OR HURRICANE THREAT
Tropical Storm Watch (winds possible within 48h) OR Hurricane shows 
potential trajectory toward your location within 3–5 days.

ACTION:
• Stock up on food, water, fuel, batteries
• Pack emergency go-bag & important documents
• Plan evacuation route and transportation
• Check local building notices and emergency services
```

### Level 4: Evacuation Zone 🚨

**Condition**: Tropical Storm Warning, Hurricane Watch, or Evacuation Order

**Indicators**:
- Tropical Storm Warning (winds expected within 36 hours with surge risk)
- Hurricane Watch (possible hurricane conditions within 48 hours)
- Local evacuation order issued

**Actions**:
- Evacuate vulnerable areas immediately
- Use available transportation to reach safe locations
- Follow local emergency services instructions
- Assume access routes may soon be compromised

**Color**: Red (#F44336)

**Example Message**:
```
🚨 TROPICAL STORM WARNING OR HURRICANE WATCH OR EVACUATION ORDER
Tropical Storm Warning (winds expected within 36h) OR Hurricane Watch 
(possible hurricane within 48h) OR Local evacuation order for your location.

ACTION:
• Evacuate vulnerable areas immediately
• Use available transportation to reach safe locations
• Follow local emergency services instructions
• Assume access routes may soon be compromised
```

### Level 5: Hurricane Warning 🌀

**Condition**: Hurricane conditions expected within 36 hours

**Indicators**:
- Hurricane Warning in effect
- Hurricane conditions imminent
- Highest threat level

**Actions** (if not already evacuated):
- Take shelter in safest interior room away from windows
- Expect power, water, and communication outages
- Prepare for possible flooding
- Follow local emergency services instructions

**Color**: Dark Red (#B71C1C)

**Example Message**:
```
🌀 HURRICANE WARNING
Hurricane conditions expected near your location within 36h.

ACTION (if not already evacuated):
• Take shelter in safest interior room away from windows
• Expect power, water, and communication outages
• Prepare for possible flooding
• Follow local emergency services instructions
```

## Alert Triggers

### Data Sources

Alerts are triggered by multiple data sources:

#### NHC Forecast Cones
- Real-time hurricane forecast cone data
- Geometric intersection with your location
- Storm type and intensity analysis
- Advisory updates and changes

#### NWS Watches and Warnings
- Official Hurricane Watch/Warning
- Tropical Storm Watch/Warning
- Storm Surge Watch/Warning
- Evacuation orders

#### AI Analysis
- NOAA map interpretation
- Storm development assessment
- Trajectory analysis
- Threat level evaluation

#### Storm Proximity
- Distance-based threat calculation
- Time-to-impact estimation
- Storm intensity consideration
- Movement speed analysis

### Alert Logic

The system uses sophisticated logic to determine alert levels:

```python
# Simplified alert logic
if has_hurricane_warning:
    return Level 5  # Hurricane Warning
elif has_tropical_storm_warning or has_hurricane_watch or has_evacuation_order:
    return Level 4  # Evacuation Zone
elif has_tropical_storm_watch or (in_hurricane_cone and days_until_impact <= 5):
    return Level 3  # TS Watch/Hurricane Threat
elif in_disturbance_cone or (storm_nearby and days_until_impact <= 7):
    return Level 2  # Tropical Storm Threat
else:
    return Level 1  # All Clear
```

## Notification Methods

### Toast Notifications (Windows)

**Features**:
- Native Windows 10/11 notifications
- Alert level-specific sounds
- Persistent notifications for high-level alerts
- Click-to-dismiss functionality

**Configuration**:
```env
TOAST_ENABLED=true
```

**Sound Patterns**:
- Level 1: No sound
- Level 2: Gentle notification sound
- Level 3: Moderate alert sound
- Level 4: Urgent alert sound
- Level 5: Emergency siren sound

### HTML Reports

**Features**:
- Comprehensive threat analysis
- Interactive storm tracking maps
- Detailed storm information
- Action recommendations
- Printable format

**Location**: `reports/hurricane_threat_analysis_YYYYMMDD_HHMMSS.html`

**Contents**:
- Current alert level and guidance
- Storm-by-storm analysis
- Interactive map with forecast cones
- Historical storm data
- Emergency contact information

### Console Output

**Features**:
- Formatted terminal display
- Color-coded alert levels
- Detailed threat breakdown
- Real-time status updates

**Example Output**:
```
╔══════════════════════════════════════════════════════════════════════════════╗
║ 🚨 WEATHERBOT AI THREAT ANALYSIS - LEVEL 4                                  ║
║ 📍 Miami, FL (25.7617°N, 80.1918°W)                                         ║
║ 🕐 2024-09-15 14:30:00 UTC                                                   ║
║ 🗺️  DATA SOURCE: Official NOAA Atlantic Maps + Geometric Analysis           ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌─ 🚨 ALERT LEVEL 4: TROPICAL STORM WARNING OR HURRICANE WATCH OR EVACUATION ORDER ─┐

🎯 SITUATION: Hurricane Milton approaching South Florida - Evacuation recommended

📋 DETAILED ASSESSMENT
──────────────────────────────────────────────────────────────────────────────
▶ Current Threat Level: LEVEL 4 - EVACUATION ZONE
  Your location is under Hurricane Watch with evacuation recommended for 
  vulnerable areas. Hurricane conditions are possible within 48 hours.

▶ Specific Storms/Disturbances Affecting the Area
  • Hurricane Milton (Category 3)
    ◦ Position: 26.2°N, 83.1°W (approximately 180 miles west-southwest)
    ◦ Maximum sustained winds: 120 mph
    ◦ Movement: East-northeast at 16 mph
    ◦ Expected arrival: Within 36-48 hours

┌─ 🚨 IMMEDIATE ACTIONS REQUIRED ──────────────────────────────────┐
│ • Evacuate vulnerable areas immediately                          │
│ • Use available transportation to reach safe locations           │
│ • Follow local emergency services instructions                   │
│ • Assume access routes may soon be compromised                   │
└──────────────────────────────────────────────────────────────────┘

╔══════════════════════════════╗
║ 🚨  ALERT LEVEL 4            ║
╚══════════════════════════════╝
```

## Alert Management

### Cooldown System

To prevent alert spam, Weatherbot implements a configurable cooldown system:

```env
ALERT_COOLDOWN_MINUTES=60  # Wait 60 minutes between duplicate alerts
```

**Behavior**:
- Prevents duplicate alerts for the same threat level
- Allows escalation to higher alert levels
- Resets when threat level decreases
- Configurable based on monitoring frequency

**Recommended Settings**:
- **Continuous monitoring**: 60-120 minutes
- **Scheduled checks**: 30-60 minutes
- **Testing/development**: 0 minutes (no cooldown)

### State Management

Weatherbot maintains persistent state to track:

- **Last alert time**: Prevents spam
- **Storm advisories**: Tracks new updates
- **Alert IDs**: Prevents duplicate NWS alerts
- **In-cone status**: Tracks location threat status

**State File**: `state/weatherbot_state.json`

**Management Commands**:
```bash
# View current state
weatherbot state show

# Clear state (reset all tracking)
weatherbot state clear
```

### Alert Deduplication

The system prevents duplicate alerts through:

1. **Cooldown periods**: Time-based alert limiting
2. **Advisory tracking**: Only alert on new storm advisories
3. **Alert ID tracking**: Prevent duplicate NWS alerts
4. **Threat level changes**: Only alert on escalation or new threats

## Customization

### Location-Specific Guidance

Alerts are customized based on your location:

```python
# Miami, FL example
guidance = (
    f"Hurricane Watch issued for Miami-Dade County. "
    f"Evacuation zones A and B should evacuate immediately. "
    f"Storm surge of 6-10 feet expected along Biscayne Bay."
)

# Generic example
guidance = (
    f"Hurricane Watch issued for your location. "
    f"Follow local evacuation orders if issued. "
    f"Prepare for dangerous storm surge and winds."
)
```

### AI-Enhanced Alerts

When OpenAI API key is configured, alerts include:

- **Intelligent analysis**: AI interpretation of weather maps
- **Location context**: Specific geographic considerations
- **Personalized recommendations**: Based on local conditions
- **Storm evolution**: Predicted development and changes

### County-Level Detection

For more precise alerts in complex coastal areas:

```env
USE_COUNTY_INTERSECT=true
COUNTY_GEOJSON_PATH=path/to/county.geojson
```

**Benefits**:
- More accurate threat detection for large counties
- Better handling of complex coastlines
- Reduced false positives for inland areas
- Customizable threat zones

## Testing Alerts

### Test Command

```bash
weatherbot test-alert
```

**What it tests**:
- Toast notification system
- Sound playback
- Alert formatting
- System permissions

**Expected behavior**:
- Toast notification appears
- Alert sound plays
- Success message in console
- No errors in logs

### Manual Testing

Create test scenarios by temporarily modifying coordinates:

```env
# Test with coordinates in active storm area
HOME_LAT=26.0000
HOME_LON=-80.0000
```

```bash
weatherbot run --once --verbose
```

## Troubleshooting

### Common Issues

#### No Alerts Received

**Symptoms**:
- No toast notifications
- No console alerts
- Silent operation

**Solutions**:
1. Check `weatherbot test-alert`
2. Verify coordinates with `weatherbot check-coverage`
3. Check cooldown settings (`ALERT_COOLDOWN_MINUTES`)
4. Review logs: `logs/weatherbot.log`
5. Ensure active storms in area

#### False Alerts

**Symptoms**:
- Alerts when no storms present
- Incorrect threat levels
- Outdated information

**Solutions**:
1. Verify coordinate accuracy
2. Check NOAA coverage status
3. Clear cache: `weatherbot debug clear-cache`
4. Update to latest version
5. Review state: `weatherbot state show`

#### Missing High-Level Alerts

**Symptoms**:
- No Level 4/5 alerts during major storms
- Delayed notifications
- Inconsistent alerting

**Solutions**:
1. Check NWS alert integration
2. Verify storm advisory updates
3. Review geometric intersection logic
4. Enable verbose logging
5. Check API connectivity

### Debug Commands

```bash
# Check current storm data
weatherbot debug storm-data

# View NHC layers
weatherbot debug layers

# Test AI analysis
weatherbot debug test-ai

# Clear all caches
weatherbot debug clear-cache
```

### Log Analysis

Enable debug logging for detailed information:

```env
LOG_LEVEL=DEBUG
```

```bash
weatherbot run --verbose
```

**Key log entries**:
- Configuration loading
- Storm data retrieval
- Geometric analysis results
- Alert triggering logic
- Notification delivery

## Best Practices

### Setup Recommendations

1. **Accurate coordinates**: Use precise location coordinates
2. **Test notifications**: Verify alerts work before hurricane season
3. **Appropriate cooldown**: Balance between spam prevention and timely alerts
4. **Regular updates**: Keep Weatherbot updated to latest version
5. **Backup configuration**: Save `.env` file securely

### Monitoring Strategy

1. **Hurricane season**: Run every 2-4 hours
2. **Active threats**: Run every 1-2 hours
3. **Scheduled tasks**: Use `--once` flag
4. **Manual checks**: Use `ai-analysis` command during uncertainty

### Emergency Preparedness

1. **Review evacuation routes**: Know multiple exit paths
2. **Emergency supplies**: Maintain 7-day supply kit
3. **Communication plan**: Establish family contact methods
4. **Important documents**: Keep copies in waterproof container
5. **Stay informed**: Monitor official emergency services

### AI Usage Tips

1. **API costs**: Monitor OpenAI usage and set limits
2. **Accuracy**: AI enhances but doesn't replace official alerts
3. **Global coverage**: Essential for locations outside NOAA coverage
4. **Verification**: Cross-reference AI analysis with official sources

## Integration

### Automation Scripts

Example PowerShell script for Windows Task Scheduler:

```powershell
# weatherbot_monitor.ps1
$ErrorActionPreference = "Stop"

try {
    # Activate virtual environment
    & "E:\Code\Python\venvs\weatherbot\Scripts\Activate.ps1"
    
    # Run weatherbot
    weatherbot run --once
    
    Write-Host "Weatherbot monitoring completed successfully"
}
catch {
    Write-Error "Weatherbot monitoring failed: $_"
    exit 1
}
```

### Third-Party Integration

**Home Assistant**:
```yaml
# configuration.yaml
command_line:
  - sensor:
      name: "Hurricane Alert Level"
      command: "weatherbot ai-analysis --json"
      value_template: "{{ value_json.alert_level }}"
      scan_interval: 3600
```

**IFTTT/Zapier**:
- Trigger on log file changes
- Parse alert levels from output
- Send to additional notification services

### API Integration

For custom applications, use Weatherbot as a Python library:

```python
from weatherbot.enhanced_cone_analyzer import analyze_location_threat_enhanced
from weatherbot.config import load_config

config = load_config()
threat_analysis = analyze_location_threat_enhanced(
    latitude=config.home_lat,
    longitude=config.home_lon,
)

alert_level = threat_analysis["alert_level"]
if alert_level.value >= 3:
    # Trigger custom notifications
    send_custom_alert(alert_level, threat_analysis)
```
