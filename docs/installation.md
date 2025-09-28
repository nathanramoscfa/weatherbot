# Installation Guide

This guide covers the complete installation process for Weatherbot.

## System Requirements

### Operating System
- **Primary**: Windows 10/11 (for toast notifications)
- **Secondary**: Linux/macOS (limited notification support)

### Python Requirements
- **Python 3.11 or higher** (required)
- Virtual environment recommended

### Hardware Requirements
- **RAM**: 512MB minimum, 1GB recommended
- **Storage**: 100MB for installation, 500MB for cache/logs
- **Network**: Internet connection for weather data

## Installation Methods

### Method 1: Standard Installation (Recommended)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/nathanramoscfa/weatherbot.git
   cd weatherbot
   ```

2. **Create virtual environment**:
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # Linux/macOS
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install Weatherbot**:
   ```bash
   pip install -e .
   ```

4. **Verify installation**:
   ```bash
   weatherbot --help
   ```

### Method 2: Development Installation

For contributors and developers:

1. **Clone and setup**:
   ```bash
   git clone https://github.com/nathanramoscfa/weatherbot.git
   cd weatherbot
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

2. **Install with development dependencies**:
   ```bash
   pip install -e .[dev]
   ```

3. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

### Method 3: Docker Installation (Future)

Docker support is planned for future releases.

## Configuration Setup

### 1. Environment File

Copy the example configuration:
```bash
# Windows
copy env.example .env

# Linux/macOS
cp env.example .env
```

### 2. Required Configuration

Edit `.env` with your location:
```env
# Required: Your coordinates
HOME_LAT=25.7617
HOME_LON=-80.1918
```

### 3. Optional Configuration

```env
# AI Enhancement
OPENAI_API_KEY=your_api_key_here

# Notifications
TOAST_ENABLED=true
ALERT_COOLDOWN_MINUTES=60

# County-based detection
USE_COUNTY_INTERSECT=false
COUNTY_GEOJSON_PATH=src/weatherbot/data/default_area.geojson

# Logging
LOG_LEVEL=INFO
```

## Coordinate Setup

### Finding Your Coordinates

1. **Google Maps**: Right-click location → coordinates
2. **GPS devices**: Use decimal degree format
3. **Online tools**: Use coordinate conversion websites

### Coordinate Format

- **Latitude**: -90 to 90 (positive = North)
- **longitude**: -180 to 180 (negative = West for Americas)
- **Format**: Decimal degrees (e.g., 25.7617, -80.1918)

### Coverage Validation

Check if your coordinates are supported:
```bash
weatherbot check-coverage
```

## Verification

### Test Installation

1. **Basic functionality**:
   ```bash
   weatherbot --help
   ```

2. **Configuration test**:
   ```bash
   weatherbot check-coverage
   ```

3. **Notification test**:
   ```bash
   weatherbot test-alert
   ```

4. **Run once**:
   ```bash
   weatherbot run --once
   ```

### Expected Output

Successful installation should show:
- ✅ Configuration loaded
- ✅ Coordinates validated
- ✅ NOAA coverage confirmed
- ✅ Notifications working

## Troubleshooting

### Common Issues

#### Python Version Error
```
Error: Python 3.11+ required
```
**Solution**: Upgrade Python or use pyenv/conda

#### Permission Errors
```
Error: Permission denied
```
**Solution**: Run as administrator or check file permissions

#### Network Errors
```
Error: Failed to fetch weather data
```
**Solution**: Check internet connection and firewall settings

#### Coordinate Errors
```
Error: Invalid coordinates
```
**Solution**: Verify coordinate format and ranges

### Getting Help

1. **Check logs**: `logs/weatherbot.log`
2. **Verbose mode**: `weatherbot run --verbose`
3. **GitHub Issues**: Report bugs with logs
4. **Documentation**: See [troubleshooting guide](troubleshooting.md)

## Next Steps

After installation:

1. **Read the [User Guide](user-guide.md)**
2. **Configure [Alert Settings](alerts.md)**
3. **Set up [Scheduled Tasks](user-guide.md#automation)**
4. **Explore [AI Features](ai-integration.md)** (optional)

## Uninstallation

To remove Weatherbot:

1. **Deactivate virtual environment**:
   ```bash
   deactivate
   ```

2. **Remove directory**:
   ```bash
   rm -rf weatherbot/  # Linux/macOS
   rmdir /s weatherbot  # Windows
   ```

3. **Remove scheduled tasks** (if configured)

## Updates

To update Weatherbot:

1. **Pull latest changes**:
   ```bash
   git pull origin main
   ```

2. **Update dependencies**:
   ```bash
   pip install -e . --upgrade
   ```

3. **Check for breaking changes** in [CHANGELOG.md](../CHANGELOG.md)
