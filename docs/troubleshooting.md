# Troubleshooting Guide

Comprehensive troubleshooting guide for common Weatherbot issues.

## Quick Diagnostics

### Health Check Commands

Run these commands to quickly diagnose issues:

```bash
# 1. Check installation
weatherbot --help

# 2. Validate configuration
weatherbot check-coverage

# 3. Test notifications
weatherbot test-alert

# 4. Run with verbose logging
weatherbot run --once --verbose

# 5. Check current state
weatherbot state show
```

### Log Analysis

Check logs for detailed error information:

```bash
# View recent logs
tail -f logs/weatherbot.log

# Search for errors
grep -i error logs/weatherbot.log

# Search for specific issues
grep -i "connection\|timeout\|failed" logs/weatherbot.log
```

## Installation Issues

### Python Version Errors

**Error**:
```
Error: Python 3.11+ required, found 3.9.7
```

**Solutions**:

1. **Update Python**:
   ```bash
   # Windows - Download from python.org
   # Linux
   sudo apt update && sudo apt install python3.11
   # macOS
   brew install python@3.11
   ```

2. **Use pyenv** (recommended):
   ```bash
   # Install pyenv
   curl https://pyenv.run | bash
   
   # Install Python 3.11
   pyenv install 3.11.0
   pyenv local 3.11.0
   ```

3. **Use conda**:
   ```bash
   conda create -n weatherbot python=3.11
   conda activate weatherbot
   ```

### Package Installation Errors

**Error**:
```
ERROR: Could not install packages due to an EnvironmentError
```

**Solutions**:

1. **Update pip**:
   ```bash
   python -m pip install --upgrade pip
   ```

2. **Use virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -e .
   ```

3. **Install with user flag**:
   ```bash
   pip install -e . --user
   ```

4. **Clear pip cache**:
   ```bash
   pip cache purge
   pip install -e . --no-cache-dir
   ```

### Permission Errors

**Error**:
```
PermissionError: [Errno 13] Permission denied
```

**Solutions**:

1. **Windows - Run as Administrator**:
   - Right-click Command Prompt → "Run as administrator"
   - Or use PowerShell as administrator

2. **Linux/macOS - Check permissions**:
   ```bash
   # Fix directory permissions
   chmod 755 /path/to/weatherbot
   
   # Fix file permissions
   chmod 644 /path/to/weatherbot/.env
   ```

3. **Use virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -e .
   ```

## Configuration Issues

### Missing Configuration File

**Error**:
```
FileNotFoundError: .env file not found
```

**Solutions**:

1. **Create .env file**:
   ```bash
   # Windows
   copy env.example .env
   
   # Linux/macOS
   cp env.example .env
   ```

2. **Verify file location**:
   ```bash
   # Should be in project root
   ls -la .env
   ```

3. **Check file permissions**:
   ```bash
   chmod 644 .env
   ```

### Invalid Coordinates

**Error**:
```
ValueError: Latitude must be between -90 and 90 degrees
```

**Solutions**:

1. **Check coordinate format**:
   ```env
   # Correct format (decimal degrees)
   HOME_LAT=25.7617
   HOME_LON=-80.1918
   
   # Incorrect formats
   HOME_LAT=25°45'42"N  # Don't use degrees/minutes/seconds
   HOME_LAT=25.7617N    # Don't use cardinal directions
   ```

2. **Validate coordinate ranges**:
   - Latitude: -90 to 90
   - Longitude: -180 to 180
   - Western Hemisphere: negative longitude

3. **Find correct coordinates**:
   ```bash
   # Use Google Maps
   # Right-click location → Copy coordinates
   # Format: 25.7617, -80.1918
   ```

### API Key Issues

**Error**:
```
AuthenticationError: Invalid API key provided
```

**Solutions**:

1. **Verify API key format**:
   ```env
   # Correct format
   OPENAI_API_KEY=sk-1234567890abcdef1234567890abcdef
   
   # Check for extra spaces or characters
   ```

2. **Check API key status**:
   - Log into OpenAI dashboard
   - Verify key is active
   - Check usage limits and billing

3. **Regenerate API key**:
   - Create new key in OpenAI dashboard
   - Update .env file
   - Test with `weatherbot debug test-ai`

## Network Issues

### Connection Timeouts

**Error**:
```
ConnectionError: HTTPSConnectionPool timeout
```

**Solutions**:

1. **Check internet connection**:
   ```bash
   # Test basic connectivity
   ping google.com
   
   # Test HTTPS connectivity
   curl -I https://www.nhc.noaa.gov
   ```

2. **Check firewall settings**:
   - Allow Python/weatherbot through firewall
   - Check corporate firewall restrictions
   - Verify HTTPS (port 443) access

3. **Use proxy settings** (if required):
   ```bash
   export HTTPS_PROXY=http://proxy.company.com:8080
   export HTTP_PROXY=http://proxy.company.com:8080
   ```

4. **Retry with backoff**:
   ```bash
   # Weatherbot has built-in retry logic
   # Check logs for retry attempts
   weatherbot run --once --verbose
   ```

### DNS Resolution Issues

**Error**:
```
gaierror: [Errno 11001] getaddrinfo failed
```

**Solutions**:

1. **Check DNS settings**:
   ```bash
   # Windows
   nslookup www.nhc.noaa.gov
   
   # Linux/macOS
   dig www.nhc.noaa.gov
   ```

2. **Use alternative DNS**:
   ```bash
   # Windows - Change DNS to 8.8.8.8, 8.8.4.4
   # Linux/macOS - Edit /etc/resolv.conf
   nameserver 8.8.8.8
   nameserver 8.8.4.4
   ```

3. **Flush DNS cache**:
   ```bash
   # Windows
   ipconfig /flushdns
   
   # Linux
   sudo systemctl restart systemd-resolved
   
   # macOS
   sudo dscacheutil -flushcache
   ```

## Data Issues

### No Storm Data

**Error**:
```
INFO: Found 0 active forecast cones
```

**Solutions**:

1. **Check hurricane season**:
   - Atlantic: June 1 - November 30
   - Pacific: May 15 - November 30
   - Outside season: Limited storm activity

2. **Verify data sources**:
   ```bash
   # Check NHC layers
   weatherbot debug layers
   
   # Check current storms
   weatherbot debug current-storms
   ```

3. **Clear cache**:
   ```bash
   weatherbot debug clear-cache
   ```

4. **Check NOAA services**:
   - Visit https://www.nhc.noaa.gov
   - Verify services are operational
   - Check for maintenance announcements

### Outdated Data

**Error**:
```
WARNING: Using cached data from 4 hours ago
```

**Solutions**:

1. **Clear cache**:
   ```bash
   weatherbot debug clear-cache
   ```

2. **Check cache settings**:
   ```python
   # Default cache TTL is 30 minutes
   # Increase if getting frequent cache misses
   ```

3. **Verify network connectivity**:
   ```bash
   weatherbot run --once --verbose
   # Check for network errors in logs
   ```

### Geometric Analysis Errors

**Error**:
```
ERROR: Failed to load county polygon
```

**Solutions**:

1. **Check GeoJSON file**:
   ```bash
   # Verify file exists
   ls -la src/weatherbot/data/default_area.geojson
   
   # Validate GeoJSON format
   python -c "import json; json.load(open('path/to/file.geojson'))"
   ```

2. **Disable county intersection**:
   ```env
   USE_COUNTY_INTERSECT=false
   ```

3. **Use default area**:
   ```env
   COUNTY_GEOJSON_PATH=src/weatherbot/data/default_area.geojson
   ```

## Notification Issues

### No Toast Notifications

**Error**: Notifications not appearing on Windows

**Solutions**:

1. **Check Windows notification settings**:
   - Settings → System → Notifications & actions
   - Ensure notifications are enabled
   - Check Focus Assist settings

2. **Test notification system**:
   ```bash
   weatherbot test-alert
   ```

3. **Check toast configuration**:
   ```env
   TOAST_ENABLED=true
   ```

4. **Verify Windows version**:
   - Windows 10 version 1903+ required
   - Windows 11 fully supported

5. **Check Python toast library**:
   ```bash
   python -c "from win11toast import toast; toast('Test', 'Message')"
   ```

### No Sound with Notifications

**Error**: Toast appears but no sound plays

**Solutions**:

1. **Check system volume**:
   - Ensure system volume is up
   - Check notification sounds in Windows settings

2. **Check notification sound settings**:
   - Settings → System → Sound → App volume and device preferences
   - Ensure Python/weatherbot has sound enabled

3. **Test with different sound**:
   ```python
   # Modify notification sound in code if needed
   ```

## AI Analysis Issues

### OpenAI API Errors

**Error**:
```
RateLimitError: Rate limit exceeded
```

**Solutions**:

1. **Check API usage**:
   - Log into OpenAI dashboard
   - Review usage and limits
   - Check billing status

2. **Reduce API calls**:
   ```env
   # Increase cooldown period
   ALERT_COOLDOWN_MINUTES=120
   ```

3. **Monitor costs**:
   - Set usage alerts in OpenAI dashboard
   - Consider usage limits

### AI Analysis Timeout

**Error**:
```
TimeoutError: AI analysis took too long
```

**Solutions**:

1. **Check network speed**:
   ```bash
   # Test download speed
   speedtest-cli
   ```

2. **Retry analysis**:
   ```bash
   weatherbot ai-analysis
   ```

3. **Check OpenAI status**:
   - Visit https://status.openai.com
   - Check for service outages

### Inaccurate AI Analysis

**Issue**: AI provides incorrect or inconsistent analysis

**Solutions**:

1. **Verify input data**:
   ```bash
   # Check geometric analysis first
   weatherbot run --once --verbose
   ```

2. **Compare with official sources**:
   - Cross-reference with NHC advisories
   - Check NWS alerts
   - Verify storm positions

3. **Update prompts** (for developers):
   - Review AI prompt engineering
   - Adjust analysis parameters
   - Test with known scenarios

## Performance Issues

### Slow Startup

**Issue**: Weatherbot takes long time to start

**Solutions**:

1. **Check system resources**:
   ```bash
   # Monitor CPU and memory usage
   top  # Linux/macOS
   # Task Manager on Windows
   ```

2. **Optimize configuration**:
   ```env
   # Reduce logging verbosity
   LOG_LEVEL=WARNING
   
   # Disable unnecessary features during testing
   TOAST_ENABLED=false
   ```

3. **Clear cache and logs**:
   ```bash
   weatherbot debug clear-cache
   rm logs/weatherbot.log
   ```

### High Memory Usage

**Issue**: Weatherbot uses excessive memory

**Solutions**:

1. **Monitor memory usage**:
   ```bash
   # Check memory usage
   ps aux | grep weatherbot  # Linux/macOS
   ```

2. **Reduce cache size**:
   ```bash
   # Clear cache regularly
   weatherbot debug clear-cache
   ```

3. **Check for memory leaks**:
   ```bash
   # Run with memory profiling
   python -m memory_profiler weatherbot/cli.py
   ```

## State Management Issues

### Corrupted State File

**Error**:
```
JSONDecodeError: Expecting value: line 1 column 1
```

**Solutions**:

1. **Clear state file**:
   ```bash
   weatherbot state clear
   ```

2. **Manual state file removal**:
   ```bash
   rm state/weatherbot_state.json
   ```

3. **Check file permissions**:
   ```bash
   chmod 644 state/weatherbot_state.json
   ```

### Persistent Alert Issues

**Issue**: Alerts continue after threat has passed

**Solutions**:

1. **Clear state**:
   ```bash
   weatherbot state clear
   ```

2. **Check cooldown settings**:
   ```env
   # Reduce cooldown for testing
   ALERT_COOLDOWN_MINUTES=0
   ```

3. **Verify current conditions**:
   ```bash
   weatherbot run --once --verbose
   ```

## Coverage Issues

### Outside NOAA Coverage

**Warning**:
```
Location outside NOAA coverage area
```

**Solutions**:

1. **Enable AI web search**:
   ```env
   OPENAI_API_KEY=your_key_here
   ```

2. **Understand limitations**:
   - Reduced accuracy outside NOAA coverage
   - AI web search provides fallback
   - Consider relocating monitoring point

3. **Use nearest covered location**:
   ```bash
   weatherbot check-coverage
   # Follow recommendations for nearest coverage
   ```

### Marginal Coverage

**Warning**:
```
Location has marginal NOAA coverage
```

**Solutions**:

1. **Accept limitations**:
   - Some data sources may be unavailable
   - Reduced forecast accuracy
   - Continue with available data

2. **Consider alternative coordinates**:
   - Use coordinates closer to US/Caribbean
   - Test with `weatherbot check-coverage`

## Development Issues

### Import Errors

**Error**:
```
ModuleNotFoundError: No module named 'weatherbot'
```

**Solutions**:

1. **Install in development mode**:
   ```bash
   pip install -e .
   ```

2. **Check Python path**:
   ```bash
   python -c "import sys; print(sys.path)"
   ```

3. **Verify virtual environment**:
   ```bash
   which python
   pip list | grep weatherbot
   ```

### Test Failures

**Error**: Tests failing during development

**Solutions**:

1. **Install test dependencies**:
   ```bash
   pip install -e .[dev]
   ```

2. **Run specific tests**:
   ```bash
   pytest tests/test_specific.py -v
   ```

3. **Check test environment**:
   ```bash
   # Ensure clean test environment
   pytest --tb=short
   ```

### Security Scan Failures

**Error**: Bandit or Safety reporting security issues

**Solutions**:

1. **Run security scans locally**:
   ```bash
   make security
   # Or individually:
   bandit -r src/weatherbot
   safety check
   ```

2. **Fix high priority issues first**:
   ```bash
   # MD5 usage - add usedforsecurity=False
   hashlib.md5(data.encode(), usedforsecurity=False)
   
   # Or use SHA-256
   hashlib.sha256(data.encode())
   ```

3. **Update vulnerable dependencies**:
   ```bash
   pip install --upgrade pip
   safety check --upgrade
   ```

4. **Generate detailed reports**:
   ```bash
   bandit -r src/weatherbot -f json -o bandit-report.json
   safety check --json --output safety-report.json
   ```

## Getting Help

### Diagnostic Information

When reporting issues, include:

1. **System information**:
   ```bash
   python --version
   pip list | grep weatherbot
   uname -a  # Linux/macOS
   systeminfo  # Windows
   ```

2. **Configuration** (sanitized):
   ```bash
   # Remove API keys before sharing
   cat .env | sed 's/OPENAI_API_KEY=.*/OPENAI_API_KEY=***/'
   ```

3. **Log files**:
   ```bash
   tail -100 logs/weatherbot.log
   ```

4. **Error reproduction**:
   ```bash
   weatherbot run --once --verbose 2>&1 | tee debug_output.txt
   ```

### Support Channels

1. **Documentation**: Check all guides in `docs/`
2. **GitHub Issues**: Report bugs with diagnostic info
3. **Discussions**: Ask questions and share experiences
4. **Community**: Join project discussions

### Self-Help Checklist

Before seeking help:

- [ ] Read relevant documentation
- [ ] Check logs for error messages
- [ ] Try basic diagnostic commands
- [ ] Search existing GitHub issues
- [ ] Test with minimal configuration
- [ ] Verify system requirements
- [ ] Check network connectivity
- [ ] Clear cache and state files

### Emergency Procedures

If Weatherbot fails during active hurricane threat:

1. **Use official sources**:
   - https://www.nhc.noaa.gov
   - https://www.weather.gov
   - Local emergency services

2. **Manual monitoring**:
   - Check NHC advisories every 3-6 hours
   - Monitor local news and emergency services
   - Follow evacuation orders immediately

3. **Backup notification methods**:
   - Weather radio
   - Mobile weather apps
   - Emergency alert systems
   - Social media updates

Remember: Weatherbot is a supplementary tool. Always follow official emergency guidance and evacuation orders.
