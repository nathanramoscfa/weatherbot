# AI Integration Guide

Comprehensive guide to Weatherbot's AI-powered features using OpenAI.

## Overview

Weatherbot integrates with OpenAI's GPT models to provide intelligent weather threat analysis. The AI system enhances traditional geometric analysis with sophisticated interpretation of weather maps and global weather data.

## Features

### NOAA Map Analysis

For locations within NOAA coverage areas, AI analyzes official tropical weather outlook maps:

- **Atlantic Basin**: 7-day tropical weather outlook
- **Eastern Pacific**: 7-day tropical weather outlook  
- **Central Pacific**: 7-day tropical weather outlook

**Capabilities**:
- Interprets weather disturbances and development areas
- Analyzes storm trajectories and intensification potential
- Provides location-specific threat assessments
- Combines with geometric cone analysis for enhanced accuracy

### Global Weather Search

For locations outside NOAA coverage, AI performs web searches to find:

- Local meteorological service alerts
- Regional weather warnings
- Storm tracking from international sources
- Location-specific weather threats

**Coverage**:
- Europe (UK Met Office, ECMWF, national services)
- Asia-Pacific (JMA, BOM, PAGASA, etc.)
- Other regions with established weather services

### Enhanced Analysis

AI provides:
- **Intelligent Interpretation**: Beyond simple geometric analysis
- **Context Awareness**: Considers local geography and climate
- **Threat Evolution**: Predicts how threats may develop
- **Personalized Guidance**: Location-specific recommendations

## Setup

### OpenAI Account

1. **Create Account**:
   - Visit [OpenAI](https://openai.com)
   - Sign up for account
   - Verify email address

2. **API Access**:
   - Navigate to API section
   - Accept terms of service
   - Set up billing (required for API access)

3. **Generate API Key**:
   - Go to API Keys section
   - Click "Create new secret key"
   - Copy key (starts with `sk-`)
   - Store securely

### Configuration

Add API key to your `.env` file:

```env
OPENAI_API_KEY=sk-1234567890abcdef1234567890abcdef1234567890abcdef
```

**Security Notes**:
- Never commit API keys to version control
- Use environment variables in production
- Rotate keys regularly
- Monitor usage and set limits

### Verification

Test AI integration:

```bash
# Test AI analysis
weatherbot debug test-ai

# Run AI-powered analysis
weatherbot ai-analysis

# Check with verbose logging
weatherbot run --once --verbose
```

## Usage

### AI Analysis Command

Get comprehensive AI threat analysis:

```bash
weatherbot ai-analysis
```

**Output Example**:
```
╔══════════════════════════════════════════════════════════════════════════════╗
║ 🚨 WEATHERBOT AI THREAT ANALYSIS - LEVEL 3                                  ║
║ 📍 Miami, FL (25.7617°N, 80.1918°W)                                         ║
║ 🕐 2024-09-15 14:30:00 UTC                                                   ║
║ 🗺️  DATA SOURCE: Official NOAA Atlantic Maps + Geometric Analysis           ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌─ 🛑 ALERT LEVEL 3: TROPICAL STORM WATCH OR HURRICANE THREAT ─┐

🎯 SITUATION: Tropical disturbance shows potential Florida trajectory

📋 DETAILED ASSESSMENT
──────────────────────────────────────────────────────────────────────────────
▶ Current Threat Level: LEVEL 3 - TROPICAL STORM WATCH OR HURRICANE THREAT
  A tropical disturbance in the Caribbean shows potential for development 
  and possible trajectory toward South Florida within 3-5 days.

▶ Specific Storms/Disturbances Affecting the Area
  • Invest 95L (Tropical Disturbance)
    ◦ Position: 18.5°N, 65.2°W (approximately 450 miles southeast)
    ◦ Development probability: 70% over next 5 days
    ◦ Movement: West-northwest at 12 mph
    ◦ Potential impact timeframe: 72-120 hours

▶ Storm Intensity Analysis
  • Environmental conditions favor gradual strengthening
  • Sea surface temperatures 28-29°C support development
  • Low wind shear conducive to organization
  • Upper-level divergence pattern favorable

┌─ 🛑 IMMEDIATE ACTIONS REQUIRED ──────────────────────────────────┐
│ • Stock up on food, water, fuel, batteries                      │
│ • Pack emergency go-bag & important documents                    │
│ • Plan evacuation route and transportation                       │
│ • Check local building notices and emergency services            │
└──────────────────────────────────────────────────────────────────┘
```

### Integrated Monitoring

AI analysis is automatically included when running with API key configured:

```bash
# Standard monitoring with AI enhancement
weatherbot run

# One-time check with AI analysis
weatherbot run --once
```

### Global Coverage

For locations outside NOAA coverage:

```bash
# AI will automatically use web search
weatherbot ai-analysis
```

**Example for London, UK**:
```
╔══════════════════════════════════════════════════════════════════════════════╗
║ 🚨 WEATHERBOT AI THREAT ANALYSIS - LEVEL 1                                  ║
║ 📍 London, UK (51.5074°N, 0.1278°W)                                         ║
║ 🕐 2024-09-15 14:30:00 UTC                                                   ║
║ 🌍  DATA SOURCE: AI Web Search (Outside NOAA Coverage)                      ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌─ ✅ ALERT LEVEL 1: ALL CLEAR ─┐

🎯 SITUATION: No significant weather threats detected for London area

📋 DETAILED ASSESSMENT
──────────────────────────────────────────────────────────────────────────────
▶ Current Weather Status: ALL CLEAR
  No severe weather warnings or tropical storm threats affecting the London 
  area. Normal weather conditions expected.

▶ UK Met Office Status
  • No weather warnings in effect for Greater London
  • No storm systems approaching from Atlantic
  • Typical autumn weather pattern for region
```

## Technical Details

### AI Models

Weatherbot uses OpenAI's latest models:

- **Primary**: GPT-4 for complex analysis
- **Fallback**: GPT-3.5-turbo for cost efficiency
- **Vision**: GPT-4V for map image analysis

### Analysis Process

#### NOAA Coverage Areas

1. **Map Retrieval**: Download current NOAA tropical weather outlook
2. **Image Analysis**: AI interprets weather patterns and disturbances
3. **Geometric Integration**: Combine with cone intersection analysis
4. **Threat Assessment**: Generate location-specific threat level
5. **Guidance Generation**: Create actionable recommendations

#### Global Coverage Areas

1. **Location Context**: Determine relevant weather services
2. **Web Search**: Query for current weather alerts and warnings
3. **Source Analysis**: Interpret meteorological service data
4. **Threat Evaluation**: Assess local weather threats
5. **Recommendation**: Provide location-appropriate guidance

### Prompt Engineering

AI analysis uses carefully crafted prompts:

#### Map Analysis Prompt
```
You are a professional meteorologist analyzing the official NOAA 7-day 
tropical weather outlook map for hurricane threats to a specific location.

Location: {location_name} ({latitude}°N, {longitude}°W)
Basin: {basin}

Analyze the attached weather map image and provide:
1. Current threat level (1-5 scale)
2. Specific disturbances affecting the area
3. Development probabilities and timeframes
4. Location-specific recommendations

Consider:
- Storm development areas and probabilities
- Trajectory analysis toward the location
- Environmental conditions for strengthening
- Timeframe for potential impacts
```

#### Web Search Prompt
```
You are a meteorologist providing weather threat analysis for a location 
outside NOAA coverage using web search results.

Location: {location_name} ({latitude}°N, {longitude}°W)

Based on the search results for current weather alerts and warnings:
1. Assess current threat level (1-5 scale)
2. Identify any active weather warnings
3. Evaluate tropical storm or severe weather threats
4. Provide location-specific guidance

Focus on official meteorological services and current conditions.
```

### Data Sources

#### Primary Sources (NOAA Coverage)
- **NOAA Maps**: https://www.nhc.noaa.gov/xgtwo/
- **NHC Advisories**: Real-time storm data
- **Geometric Analysis**: Forecast cone intersections

#### Secondary Sources (Global Coverage)
- **National Weather Services**: Country-specific meteorological services
- **International Organizations**: WMO, regional weather centers
- **Official Alerts**: Government weather warnings

### Cost Management

#### Usage Optimization

**Token Efficiency**:
- Optimized prompts to minimize token usage
- Efficient image compression for map analysis
- Caching of repeated analyses

**Cost Monitoring**:
```bash
# Monitor API usage in OpenAI dashboard
# Set usage alerts and limits
# Track costs per analysis cycle
```

**Typical Costs**:
- **Map Analysis**: $0.01-0.05 per analysis
- **Web Search**: $0.005-0.02 per analysis
- **Monthly Usage**: $1-10 for regular monitoring

#### Cost Control Strategies

1. **Cooldown Periods**:
   ```env
   ALERT_COOLDOWN_MINUTES=120  # Reduce API calls
   ```

2. **Selective Usage**:
   - Use AI only during active threats
   - Disable for routine monitoring
   - Enable for uncertain conditions

3. **Usage Limits**:
   - Set monthly limits in OpenAI dashboard
   - Monitor usage regularly
   - Use alerts for high usage

## Advanced Features

### Custom Analysis

For developers, customize AI analysis:

```python
from weatherbot.ai_map_analyzer import analyze_hurricane_threat_with_ai

# Custom analysis with specific parameters
alert_level, title, message = analyze_hurricane_threat_with_ai(
    latitude=25.7617,
    longitude=-80.1918,
    location_name="Miami, FL",
    api_key="your_key",
    basin="atlantic",
    geometric_results=threat_analysis,
)
```

### Batch Analysis

Analyze multiple locations:

```python
locations = [
    {"name": "Miami", "lat": 25.7617, "lon": -80.1918},
    {"name": "Tampa", "lat": 27.9506, "lon": -82.4572},
    {"name": "Key West", "lat": 24.5551, "lon": -81.7800},
]

for location in locations:
    alert_level, title, message = analyze_hurricane_threat_with_ai(
        latitude=location["lat"],
        longitude=location["lon"],
        location_name=location["name"],
        api_key=api_key,
    )
    print(f"{location['name']}: Level {alert_level}")
```

### Integration with Other Services

#### Home Assistant
```yaml
# configuration.yaml
command_line:
  - sensor:
      name: "AI Hurricane Analysis"
      command: "weatherbot ai-analysis --json"
      value_template: "{{ value_json.alert_level }}"
      json_attributes:
        - title
        - message
        - timestamp
      scan_interval: 3600
```

#### Custom Webhooks
```python
import requests
from weatherbot.ai_map_analyzer import analyze_hurricane_threat_with_ai

# Get AI analysis
alert_level, title, message = analyze_hurricane_threat_with_ai(...)

# Send to webhook
if alert_level >= 3:
    requests.post("https://hooks.slack.com/...", json={
        "text": f"Hurricane Alert Level {alert_level}: {title}",
        "attachments": [{"text": message}]
    })
```

## Troubleshooting

### Common Issues

#### API Key Errors

**Error**: `AuthenticationError: Invalid API key`

**Solutions**:
1. Verify key format (starts with `sk-`)
2. Check for extra spaces or characters
3. Ensure billing is set up in OpenAI account
4. Regenerate key if necessary

#### Rate Limiting

**Error**: `RateLimitError: Rate limit exceeded`

**Solutions**:
1. Increase cooldown periods
2. Check usage in OpenAI dashboard
3. Upgrade to higher rate limits
4. Implement exponential backoff

#### Analysis Timeout

**Error**: `TimeoutError: AI analysis timeout`

**Solutions**:
1. Check network connectivity
2. Verify OpenAI service status
3. Retry analysis
4. Check for large image sizes

#### Inaccurate Results

**Issue**: AI provides inconsistent analysis

**Solutions**:
1. Cross-reference with official sources
2. Check input data quality
3. Verify prompt engineering
4. Report issues for prompt improvement

### Debug Commands

```bash
# Test AI connectivity
weatherbot debug test-ai

# Verbose AI analysis
weatherbot ai-analysis --verbose

# Check AI model responses
LOG_LEVEL=DEBUG weatherbot ai-analysis
```

### Performance Optimization

#### Image Optimization
- Compress NOAA maps before analysis
- Use appropriate image formats
- Cache processed images

#### Prompt Optimization
- Minimize token usage in prompts
- Use efficient prompt structures
- Cache common analysis patterns

#### Network Optimization
- Use connection pooling
- Implement retry logic
- Handle network timeouts gracefully

## Best Practices

### Security

1. **API Key Management**:
   - Store keys securely
   - Use environment variables
   - Rotate keys regularly
   - Monitor for unauthorized usage

2. **Data Privacy**:
   - No personal data in prompts
   - Location data is geographic only
   - No sensitive information logged

### Reliability

1. **Fallback Mechanisms**:
   - Graceful degradation without AI
   - Geometric analysis as backup
   - Error handling for API failures

2. **Validation**:
   - Cross-reference AI results
   - Sanity check alert levels
   - Verify against official sources

### Cost Management

1. **Usage Monitoring**:
   - Track API costs regularly
   - Set usage alerts
   - Monitor token consumption

2. **Optimization**:
   - Use appropriate cooldown periods
   - Cache results when possible
   - Optimize prompt efficiency

### Quality Assurance

1. **Testing**:
   - Test with known scenarios
   - Validate against historical events
   - Compare with official forecasts

2. **Continuous Improvement**:
   - Monitor analysis accuracy
   - Update prompts based on performance
   - Incorporate user feedback

## Future Enhancements

### Planned Features

1. **Enhanced Models**:
   - Integration with newer OpenAI models
   - Specialized weather analysis models
   - Multi-modal analysis capabilities

2. **Advanced Analysis**:
   - Historical pattern recognition
   - Ensemble forecast analysis
   - Uncertainty quantification

3. **Global Expansion**:
   - More international weather services
   - Regional specialization
   - Multi-language support

### Research Areas

1. **Machine Learning**:
   - Custom weather prediction models
   - Pattern recognition algorithms
   - Automated threat classification

2. **Data Integration**:
   - Satellite imagery analysis
   - Radar data interpretation
   - Multi-source data fusion

3. **User Experience**:
   - Natural language queries
   - Conversational interfaces
   - Personalized recommendations
