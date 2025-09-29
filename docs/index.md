# Weatherbot Documentation

Welcome to the complete documentation for Weatherbot - a local hurricane alert system with NHC cone tracking, NWS alerts, and AI-powered threat analysis.

## ⚠️ CRITICAL SAFETY DISCLAIMER

**READ THIS BEFORE USING WEATHERBOT**

**THIS SOFTWARE IS FOR INFORMATIONAL PURPOSES ONLY AND MUST NOT BE USED AS THE SOLE SOURCE FOR LIFE-SAFETY DECISIONS.**

### Key Limitations and Risks

- **🚫 NOT OFFICIAL**: Weatherbot is not an official weather service and is not endorsed by NOAA, NHC, or NWS
- **🤖 AI UNCERTAINTY**: AI analysis may produce incorrect threat assessments, false positives, or false negatives
- **⚡ TECHNICAL FAILURES**: Software bugs, network issues, or data source problems may cause missed alerts or incorrect information
- **🕐 TIMING DELAYS**: Information may be delayed compared to official sources during rapidly changing conditions
- **🎯 ACCURACY LIMITS**: Geographic precision and alert level determinations may be inaccurate

### Your Responsibilities

- **✅ VERIFY INDEPENDENTLY**: Always cross-check information with official sources
- **📻 MONITOR OFFICIAL SOURCES**: Continuously monitor NHC, NWS, and local emergency management
- **🚨 FOLLOW EVACUATION ORDERS**: Always comply with official evacuation orders regardless of Weatherbot's assessment
- **⚖️ ASSUME ALL RISK**: You assume full responsibility for decisions made using this software

### Official Sources (Use These for Life-Safety Decisions)
- **National Hurricane Center**: [nhc.noaa.gov](https://nhc.noaa.gov)
- **National Weather Service**: [weather.gov](https://weather.gov)
- **Local Emergency Management**: Your county/city emergency services
- **Emergency Broadcasts**: NOAA Weather Radio, Emergency Alert System

**📋 COMPLETE LEGAL TERMS**: Review the full [Legal Disclaimer](../DISCLAIMER.md) for comprehensive liability information.

## Quick Navigation

### 🚀 Getting Started
- **[Installation Guide](installation.md)** - Complete setup instructions
- **[Configuration Reference](configuration.md)** - All configuration options
- **[User Guide](user-guide.md)** - How to use Weatherbot effectively

### 📖 User Documentation
- **[Command Reference](commands.md)** - Complete CLI command guide
- **[Alert System Guide](alerts.md)** - Understanding the 5-level alert system
- **[AI Integration Guide](ai-integration.md)** - OpenAI features and setup
- **[Troubleshooting Guide](troubleshooting.md)** - Common issues and solutions

### 🔧 Developer Documentation
- **[API Reference](api-reference.md)** - Complete API documentation
- **[Development Guide](development.md)** - Contributing and development setup
- **[Architecture Overview](#architecture)** - System design and components

### 📋 Project Information
- **[Changelog](../CHANGELOG.md)** - Version history and changes
- **[Contributing Guide](../CONTRIBUTING.md)** - How to contribute
- **[License](../LICENSE)** - MIT License details

## What is Weatherbot?

Weatherbot is a comprehensive hurricane monitoring and alerting system designed to provide real-time notifications for tropical weather threats. It combines data from multiple sources to deliver precise, location-specific threat assessments.

### Key Features

- **🌀 Real-time Hurricane Tracking**: Monitors active NHC forecast cones
- **📡 NWS Alert Integration**: Processes official weather service alerts
- **🤖 AI-Enhanced Analysis**: Optional OpenAI integration for intelligent threat assessment
- **🔔 Multi-level Alert System**: 5-tier system from "All Clear" to "Hurricane Warning"
- **💻 Toast Notifications**: Windows native notifications with sounds
- **🎯 Geometric Precision**: Point-in-polygon and county-level intersection analysis
- **📊 Comprehensive Reporting**: HTML reports with interactive storm tracking maps
- **🌍 Global Coverage**: AI web search fallback for locations outside NOAA coverage

## Quick Start

### 1. Installation
```bash
git clone https://github.com/nathanramoscfa/weatherbot.git
cd weatherbot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
```

### 2. Configuration
```bash
cp env.example .env
# Edit .env with your coordinates:
# HOME_LAT=25.7617
# HOME_LON=-80.1918
```

### 3. First Run
```bash
weatherbot check-coverage  # Validate setup
weatherbot test-alert      # Test notifications
weatherbot run --once      # Run analysis
```

### 4. AI Enhancement (Optional)
```bash
# Add to .env:
# OPENAI_API_KEY=your_key_here
weatherbot ai-analysis     # AI-powered analysis
```

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Weatherbot Architecture                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │     CLI     │    │   Config    │    │   Logging   │     │
│  │   (Typer)   │    │ (Pydantic)  │    │   Setup     │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                Data Sources Layer                       │ │
│  ├─────────────┬─────────────┬─────────────┬─────────────┤ │
│  │     NHC     │     NWS     │  AI Maps    │  AI Search  │ │
│  │  MapServer  │   Alerts    │  Analyzer   │   Global    │ │
│  └─────────────┴─────────────┴─────────────┴─────────────┘ │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                Analysis Layer                           │ │
│  ├─────────────┬─────────────┬─────────────┬─────────────┤ │
│  │  Enhanced   │  Geometry   │    Alert    │    State    │ │
│  │    Cone     │  Analysis   │   Levels    │ Management  │ │
│  │  Analyzer   │             │             │             │ │
│  └─────────────┴─────────────┴─────────────┴─────────────┘ │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Notification Layer                         │ │
│  ├─────────────┬─────────────┬─────────────┬─────────────┤ │
│  │   Alert     │    Toast    │    HTML     │   Console   │ │
│  │  Manager    │ Notifications│  Reports   │   Output    │ │
│  └─────────────┴─────────────┴─────────────┴─────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Configuration Loading**: Load settings from `.env` file
2. **Coverage Validation**: Check NOAA coverage for coordinates
3. **Data Retrieval**: Fetch storm data from NHC, NWS, and AI sources
4. **Geometric Analysis**: Analyze forecast cone intersections
5. **Threat Assessment**: Determine alert level using 5-tier system
6. **AI Enhancement**: Optional AI analysis of weather maps
7. **Alert Generation**: Create notifications and reports
8. **State Management**: Track alerts to prevent duplicates

## Coverage Areas

### NOAA Coverage (Full Support)
- **Atlantic Basin**: 0-60°N, 100°W-0°E
- **Eastern Pacific**: 0-60°N, 180°W-100°W
- **Central Pacific**: 0-60°N, 180°W-140°W

### Optimal Coverage (Recommended)
- **US East Coast**: Florida to Maine
- **Gulf of Mexico**: Texas to Florida
- **Caribbean**: All major islands
- **Bermuda**: Atlantic coverage

### Global Coverage (AI Fallback)
- **Europe**: UK, Ireland, Mediterranean
- **Asia-Pacific**: Japan, Philippines, Australia
- **Other**: Any location with internet weather services

## Alert System Overview

### 5-Level Alert System

| Level | Icon | Status | Condition | Action Required |
|-------|------|--------|-----------|-----------------|
| 1 | ✅ | All Clear | No threats | Normal activities |
| 2 | 🌪️ | Tropical Storm Threat | 5-7 day potential | Monitor and prepare |
| 3 | 🛑 | TS Watch/Hurricane Threat | 3-5 day threat | Stock supplies, plan |
| 4 | 🚨 | Evacuation Zone | TS Warning/Hurricane Watch | Evacuate if ordered |
| 5 | 🌀 | Hurricane Warning | Hurricane imminent | Take shelter |

## Technology Stack

### Core Technologies
- **Python 3.11+**: Primary programming language
- **Typer**: Command-line interface framework
- **Pydantic**: Configuration and data validation
- **Shapely**: Geometric operations and spatial analysis
- **Requests**: HTTP client for API interactions

### Data Processing
- **OpenAI**: AI-powered analysis and global coverage
- **Folium**: Interactive map generation
- **Pandas**: Data manipulation and analysis
- **BeautifulSoup**: HTML parsing for web scraping

### Notifications
- **win11toast**: Windows toast notifications
- **Rich**: Terminal formatting and display
- **Pillow**: Image processing for maps

### Development Tools
- **pytest**: Testing framework
- **Black**: Code formatting
- **Ruff**: Linting and import sorting
- **MyPy**: Type checking
- **Bandit**: Security vulnerability scanner
- **Safety**: Dependency vulnerability checker
- **pre-commit**: Git hooks for quality assurance

## Use Cases

### Personal Hurricane Monitoring
- **Residents**: Monitor threats to home location
- **Travelers**: Check destination weather conditions
- **Property Owners**: Multiple location monitoring

### Emergency Management
- **Local Agencies**: Automated threat assessment
- **Emergency Responders**: Real-time situational awareness
- **Community Groups**: Neighborhood alert systems

### Business Applications
- **Maritime Operations**: Storm avoidance planning
- **Aviation**: Flight planning and safety
- **Construction**: Weather-sensitive operations
- **Tourism**: Guest safety and planning

### Research and Education
- **Meteorology Students**: Real-time storm analysis
- **Researchers**: Historical storm tracking
- **Weather Enthusiasts**: Advanced storm monitoring

## Integration Possibilities

### Home Automation
- **Home Assistant**: Sensor integration
- **SmartThings**: Device automation
- **IFTTT/Zapier**: Workflow automation

### Communication Platforms
- **Slack**: Team notifications
- **Discord**: Community alerts
- **Email**: Automated reports
- **SMS**: Critical alerts

### Monitoring Systems
- **Grafana**: Metrics visualization
- **Prometheus**: Performance monitoring
- **Nagios**: System health checks

## Performance Characteristics

### System Requirements
- **RAM**: 512MB minimum, 1GB recommended
- **Storage**: 100MB installation, 500MB for cache/logs
- **Network**: Broadband internet connection
- **CPU**: Modern multi-core processor

### Typical Performance
- **Startup Time**: < 5 seconds
- **Analysis Time**: 10-30 seconds per cycle
- **Memory Usage**: 50-100MB during operation
- **Network Usage**: 1-5MB per analysis cycle

## Security Considerations

### Security Scanning
- **Bandit**: Python security vulnerability scanner
- **Safety**: Dependency vulnerability checker
- **CI/CD Integration**: Automated security checks on every commit
- **Continuous Monitoring**: Regular security assessments

### Data Protection
- **API Keys**: Stored in environment variables
- **Location Data**: Geographic coordinates only
- **No Personal Data**: No sensitive information collected
- **Secure Communications**: HTTPS for all API calls

### Access Control
- **File Permissions**: Restricted configuration file access
- **API Rate Limiting**: Built-in request throttling
- **Error Handling**: Graceful failure without data exposure
- **Secure Defaults**: Production-ready security configuration

## Support and Community

### Getting Help
- **Documentation**: Comprehensive guides in `docs/`
- **GitHub Issues**: Bug reports and feature requests
- **Discussions**: Community Q&A and sharing
- **Troubleshooting**: Step-by-step problem resolution

### Contributing
- **Code Contributions**: Features, bug fixes, improvements
- **Documentation**: Guides, examples, translations
- **Testing**: Bug reports, test cases, validation
- **Community**: Support other users, share experiences

### Roadmap
- **v1.1**: Docker support, web dashboard, mobile notifications
- **v1.2**: Enhanced AI models, better global coverage, performance optimizations
- **v2.0**: Multi-hazard monitoring, commercial features, enterprise support

## License and Legal

### Open Source License
Weatherbot is released under the MIT License, allowing:
- **Commercial Use**: Use in commercial applications
- **Modification**: Customize and extend functionality
- **Distribution**: Share and redistribute
- **Private Use**: Use for personal projects

### Data Sources
- **NOAA/NHC**: Public domain weather data
- **National Weather Service**: Official government alerts
- **OpenAI**: Commercial API service (requires subscription)

### Legal Disclaimer and Liability Limitations

**WEATHERBOT IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.**

#### No Warranties
- No warranty of merchantability, fitness for a particular purpose, or non-infringement
- No guarantee of accuracy, completeness, or timeliness of weather information
- No assurance that the software will be error-free or uninterrupted

#### Limitation of Liability
- Authors and contributors shall not be liable for any direct, indirect, incidental, special, or consequential damages
- This includes but is not limited to: property damage, personal injury, loss of life, business interruption, or lost profits
- Liability limitations apply even if advised of the possibility of such damages
- Some jurisdictions may not allow limitation of liability for personal injury or death

#### Indemnification
By using Weatherbot, you agree to indemnify and hold harmless the authors and contributors from any claims, damages, or expenses arising from your use of the software.

#### Governing Law
This disclaimer is governed by the laws of the jurisdiction where the software is developed and distributed.

**REMEMBER**: Weather emergencies can be life-threatening. This software is a supplementary tool only and should never be the sole source for emergency decisions. Always follow official emergency guidance and evacuation orders from local authorities.

---

## Next Steps

1. **[Install Weatherbot](installation.md)** - Get started with setup
2. **[Configure Your Location](configuration.md)** - Set up coordinates and preferences
3. **[Learn the Commands](commands.md)** - Master the CLI interface
4. **[Understand Alerts](alerts.md)** - Learn the alert system
5. **[Enable AI Features](ai-integration.md)** - Set up OpenAI integration
6. **[Join the Community](../CONTRIBUTING.md)** - Contribute and get support

Welcome to Weatherbot - your intelligent hurricane monitoring companion! 🌀
