# Security Guide

Comprehensive security guide for Weatherbot development and deployment.

## Security Overview

Weatherbot implements enterprise-grade security practices including automated vulnerability scanning, secure coding standards, and continuous security monitoring.

## Security Scanning

### Automated Security Tools

#### Bandit - Python Security Linter
**Purpose**: Identifies common security issues in Python code

**What it scans for**:
- Hardcoded passwords and API keys
- SQL injection vulnerabilities
- Command injection risks
- Insecure cryptographic functions
- Unsafe deserialization
- Path traversal vulnerabilities
- Insecure random number generation
- Deprecated security functions

**Usage**:
```bash
# Scan entire codebase
bandit -r src/weatherbot

# Generate JSON report
bandit -r src/weatherbot -f json -o bandit-report.json

# Scan specific files
bandit src/weatherbot/cache.py src/weatherbot/ai_map_analyzer.py
```

#### Safety - Dependency Vulnerability Scanner
**Purpose**: Checks dependencies for known security vulnerabilities

**What it checks**:
- CVE (Common Vulnerabilities and Exposures) database
- Known security advisories
- Outdated packages with security fixes
- License compliance issues
- Dependency conflicts

**Usage**:
```bash
# Check all dependencies
safety check

# Generate JSON report
safety check --json --output safety-report.json

# Check and suggest upgrades
safety check --upgrade
```

### CI/CD Integration

Security scans run automatically in GitHub Actions:

```yaml
# .github/workflows/ci.yml
- name: Security scan with bandit
  run: |
    bandit -r src/weatherbot -f json -o bandit-report.json || true
    bandit -r src/weatherbot

- name: Check dependencies for vulnerabilities
  run: |
    safety check --json --output safety-report.json || true
    safety check
```

**Benefits**:
- **Early Detection**: Catch issues before they reach production
- **Automated Monitoring**: Continuous security assessment
- **Pull Request Blocking**: Prevent insecure code from merging
- **Security Reports**: Detailed vulnerability documentation

## Current Security Issues

Based on the latest security scan (13 issues found):

### 🔴 High Priority Issues (4 found)

#### MD5 Hash Usage
**Issue**: Code uses MD5 hashing algorithm for cache keys
**Files**: `cache.py`, `ai_map_analyzer.py`
**Risk Level**: High
**CVE**: Not applicable (design issue)

**Problem**:
```python
# Insecure MD5 usage
import hashlib
cache_key = hashlib.md5(data.encode()).hexdigest()
```

**Solutions**:

1. **Add usedforsecurity=False** (if MD5 is only for non-security purposes):
```python
import hashlib
cache_key = hashlib.md5(data.encode(), usedforsecurity=False).hexdigest()
```

2. **Use SHA-256** (recommended for new code):
```python
import hashlib
cache_key = hashlib.sha256(data.encode()).hexdigest()
```

3. **Use hashlib.blake2b** (fastest secure option):
```python
import hashlib
cache_key = hashlib.blake2b(data.encode(), digest_size=16).hexdigest()
```

### 🟡 Medium Priority Issues (1 found)

#### Insecure tempfile.mktemp()
**Issue**: Using deprecated `tempfile.mktemp()` function
**Risk Level**: Medium
**Vulnerability**: Race condition attack

**Problem**:
```python
import tempfile
temp_path = tempfile.mktemp()  # Vulnerable to race conditions
```

**Solution**:
```python
import tempfile
import os

# Secure alternative
with tempfile.NamedTemporaryFile(delete=False) as tmp:
    temp_path = tmp.name
    # Use temp_path
# Clean up when done
os.unlink(temp_path)

# Or for automatic cleanup
with tempfile.NamedTemporaryFile() as tmp:
    # File automatically deleted when context exits
    pass
```

### 🟢 Low Priority Issues (8 found)

#### Assert Statements in Production
**Issue**: Using `assert` statements for validation
**Risk Level**: Low
**Note**: Acceptable for development, but can be disabled in production

**Current Usage**:
```python
assert isinstance(lat, float), "Latitude must be float"
```

**Production-Safe Alternative**:
```python
if not isinstance(lat, float):
    raise TypeError("Latitude must be float")
```

#### Generic Exception Handling
**Issue**: Some try/except blocks catch all exceptions
**Risk Level**: Low
**Impact**: May hide security-relevant errors

**Current Pattern**:
```python
try:
    process_data()
except Exception:
    pass  # Too broad
```

**Better Pattern**:
```python
try:
    process_data()
except (ValueError, TypeError) as e:
    logger.error(f"Data processing error: {e}")
    raise
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise
```

### 📦 Dependency Vulnerabilities (1 found)

#### Outdated pip (version 24.0)
**Issue**: pip version has known security vulnerability
**CVE**: CVE-2024-XXXX (example)
**Risk Level**: Medium
**Fix**: Upgrade to pip 25.0+

**Solution**:
```bash
pip install --upgrade pip
```

## Security Best Practices

### Code Security

#### Input Validation
```python
def validate_coordinates(lat: float, lon: float) -> None:
    """Validate coordinates with proper error handling."""
    if not isinstance(lat, (int, float)):
        raise TypeError(f"Latitude must be numeric, got {type(lat)}")
    
    if not isinstance(lon, (int, float)):
        raise TypeError(f"Longitude must be numeric, got {type(lon)}")
    
    if not -90 <= lat <= 90:
        raise ValueError(f"Latitude {lat} out of range [-90, 90]")
    
    if not -180 <= lon <= 180:
        raise ValueError(f"Longitude {lon} out of range [-180, 180]")
```

#### Secure Configuration
```python
from pydantic import Field, validator
from pydantic_settings import BaseSettings

class SecureConfig(BaseSettings):
    """Secure configuration with validation."""
    
    api_key: str = Field(..., min_length=32, description="API key")
    
    @validator('api_key')
    def validate_api_key(cls, v):
        if not v.startswith(('sk-', 'api-')):
            raise ValueError("Invalid API key format")
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = True
```

#### Secure Logging
```python
import logging
import re

def sanitize_log_message(message: str) -> str:
    """Remove sensitive data from log messages."""
    # Remove API keys
    message = re.sub(r'sk-[a-zA-Z0-9]{32,}', 'sk-***', message)
    # Remove coordinates (if considered sensitive)
    message = re.sub(r'\d+\.\d+°[NS],\s*\d+\.\d+°[EW]', '***coordinates***', message)
    return message

logger = logging.getLogger(__name__)

def log_safely(message: str) -> None:
    """Log message with sensitive data removed."""
    safe_message = sanitize_log_message(message)
    logger.info(safe_message)
```

### API Security

#### Secure HTTP Requests
```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def create_secure_session() -> requests.Session:
    """Create secure HTTP session with proper configuration."""
    session = requests.Session()
    
    # Configure retries
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Set secure headers
    session.headers.update({
        'User-Agent': 'Weatherbot/1.0.0',
        'Accept': 'application/json',
    })
    
    # Set timeout
    session.timeout = 30
    
    return session
```

#### Rate Limiting
```python
import time
from functools import wraps

def rate_limit(calls_per_minute: int):
    """Rate limiting decorator."""
    min_interval = 60.0 / calls_per_minute
    last_called = [0.0]
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator

@rate_limit(calls_per_minute=60)
def api_call():
    """API call with rate limiting."""
    pass
```

### File Security

#### Secure File Operations
```python
import os
import stat
from pathlib import Path

def create_secure_file(file_path: Path, content: str) -> None:
    """Create file with secure permissions."""
    # Create file
    file_path.write_text(content, encoding='utf-8')
    
    # Set secure permissions (owner read/write only)
    os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)

def validate_file_path(file_path: Path, allowed_dir: Path) -> None:
    """Validate file path to prevent directory traversal."""
    try:
        resolved_path = file_path.resolve()
        allowed_resolved = allowed_dir.resolve()
        
        # Check if path is within allowed directory
        resolved_path.relative_to(allowed_resolved)
    except ValueError:
        raise SecurityError(f"Path {file_path} outside allowed directory")
```

## Security Maintenance

### Regular Security Tasks

#### Weekly Tasks
- [ ] Run `make security` on development branches
- [ ] Review security scan results
- [ ] Update dependencies with security fixes

#### Monthly Tasks
- [ ] Full security audit with `bandit` and `safety`
- [ ] Review and rotate API keys
- [ ] Update security documentation
- [ ] Check for new CVEs affecting dependencies

#### Release Tasks
- [ ] Complete security scan with zero high/critical issues
- [ ] Dependency vulnerability check
- [ ] Security-focused code review
- [ ] Update security changelog

### Security Monitoring

#### Automated Monitoring
```bash
# Add to CI/CD pipeline
name: Security Monitoring
on:
  schedule:
    - cron: '0 2 * * 1'  # Weekly Monday 2 AM
  
jobs:
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Security Scan
        run: |
          pip install bandit safety
          bandit -r src/weatherbot
          safety check
```

#### Manual Monitoring
```bash
# Create security monitoring script
#!/bin/bash
echo "Running security checks..."

echo "1. Bandit scan:"
bandit -r src/weatherbot

echo "2. Safety check:"
safety check

echo "3. Outdated packages:"
pip list --outdated

echo "4. File permissions check:"
find . -name "*.py" -perm /022 -ls

echo "Security check complete."
```

## Incident Response

### Security Incident Procedure

1. **Immediate Response**:
   - Stop affected services
   - Assess scope of vulnerability
   - Document incident details

2. **Investigation**:
   - Identify root cause
   - Determine impact scope
   - Check for exploitation signs

3. **Remediation**:
   - Apply security fixes
   - Update dependencies
   - Patch vulnerabilities

4. **Recovery**:
   - Test fixes thoroughly
   - Restart services
   - Monitor for issues

5. **Post-Incident**:
   - Update security procedures
   - Improve monitoring
   - Document lessons learned

### Emergency Contacts

- **Security Team**: security@weatherbot.org
- **Maintainers**: maintainers@weatherbot.org
- **CVE Reporting**: security-advisories@github.com

## Legal and Liability Considerations

### Weather Alert System Liability

**CRITICAL**: Weatherbot deals with potentially life-threatening weather information. Special legal considerations apply:

#### Liability Risks
- **False Negatives**: Missing a hurricane threat could lead to injury/death claims
- **False Positives**: Unnecessary evacuations could result in economic damage claims  
- **AI Errors**: Incorrect AI assessments may be blamed for poor decisions
- **Technical Failures**: System downtime during emergencies could be seen as negligence
- **Timing Issues**: Delayed alerts might be considered inadequate warning

#### Legal Protection Measures
1. **Prominent Disclaimers**: Clear warnings that software is not official source
2. **MIT License**: "AS IS" provision limits warranty obligations
3. **User Agreement**: Users assume responsibility for verification
4. **Official Source References**: Direct users to authoritative weather services
5. **No Emergency Service Claims**: Never claim to replace official emergency systems

#### Recommended Legal Language

**For all user-facing documentation:**
```
⚠️ DISCLAIMER: This software is for informational purposes only. 
Not affiliated with NOAA/NHC/NWS. Always verify with official sources. 
Users assume all risks. No warranty provided.
```

**For API/Developer documentation:**
```
LEGAL NOTICE: Developers integrating this software must include 
appropriate disclaimers and direct users to official weather sources. 
Integration does not transfer liability protection.
```

#### Jurisdictional Considerations
- **US Federal**: NOAA/NWS have exclusive authority for official weather warnings
- **State Laws**: Some states have specific liability rules for emergency information
- **International**: Different countries have varying standards for weather services
- **Maritime/Aviation**: Special regulations may apply for transportation-related use

### Compliance and Standards

#### Security Standards
- **OWASP Top 10**: Address common web application vulnerabilities
- **CWE/SANS Top 25**: Focus on most dangerous software errors
- **NIST Cybersecurity Framework**: Follow industry best practices

#### Weather Service Standards
- **WMO Standards**: World Meteorological Organization guidelines for weather information
- **NWS Directives**: National Weather Service operational procedures
- **Emergency Management**: FEMA and local emergency management protocols

### Compliance Checklist
- [ ] Input validation implemented
- [ ] Output encoding applied
- [ ] Authentication mechanisms secure
- [ ] Session management proper
- [ ] Error handling secure
- [ ] Logging and monitoring active
- [ ] Data protection implemented
- [ ] Communication security enforced

## Security Tools Integration

### IDE Integration

#### VS Code Security Extensions
```json
{
  "recommendations": [
    "ms-python.bandit",
    "ms-python.safety",
    "redhat.vscode-yaml",
    "github.vscode-github-actions"
  ]
}
```

#### Pre-commit Security Hooks
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/PyCQA/bandit
    rev: '1.7.5'
    hooks:
      - id: bandit
        args: ['-r', 'src/weatherbot']
        
  - repo: https://github.com/pyupio/safety
    rev: '2.3.4'
    hooks:
      - id: safety
```

### Security Reporting

#### Generate Security Report
```bash
#!/bin/bash
# security-report.sh

DATE=$(date +%Y%m%d)
REPORT_DIR="security-reports"
mkdir -p $REPORT_DIR

echo "Generating security report for $DATE..."

# Bandit scan
bandit -r src/weatherbot -f json -o "$REPORT_DIR/bandit-$DATE.json"
bandit -r src/weatherbot -f txt -o "$REPORT_DIR/bandit-$DATE.txt"

# Safety check
safety check --json --output "$REPORT_DIR/safety-$DATE.json"
safety check --output "$REPORT_DIR/safety-$DATE.txt"

# Package audit
pip-audit --format=json --output="$REPORT_DIR/pip-audit-$DATE.json"

echo "Security report generated in $REPORT_DIR/"
```

## Future Security Enhancements

### Planned Security Features
- [ ] Automated dependency updates with security focus
- [ ] Container security scanning (when Docker support added)
- [ ] SAST (Static Application Security Testing) integration
- [ ] DAST (Dynamic Application Security Testing) for web components
- [ ] Security metrics dashboard
- [ ] Automated security patch deployment
- [ ] Enhanced secret management
- [ ] Security training integration

### Security Roadmap
- **v1.1**: Enhanced security scanning with more tools
- **v1.2**: Automated security patch management
- **v2.0**: Enterprise security features and compliance reporting

---

**Remember**: Security is an ongoing process, not a one-time implementation. Regular monitoring, updates, and improvements are essential for maintaining a secure codebase.
