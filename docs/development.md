# Development Guide

Comprehensive guide for contributing to and developing Weatherbot.

## Table of Contents

- [Development Setup](#development-setup)
- [Code Standards](#code-standards)
- [Architecture Overview](#architecture-overview)
- [Testing](#testing)
- [Contributing Workflow](#contributing-workflow)
- [Release Process](#release-process)

## Development Setup

### Prerequisites

- **Python 3.11+** (required)
- **Git** for version control
- **Virtual environment** (recommended)
- **Code editor** with Python support

### Environment Setup

1. **Fork and clone**:
   ```bash
   git clone https://github.com/nathanramoscfa/weatherbot.git
   cd weatherbot
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install development dependencies**:
   ```bash
   pip install -e .[dev]
   ```

4. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

5. **Verify setup**:
   ```bash
   pytest
   make lint
   make security
   ```

### Development Dependencies

The `[dev]` extra includes:
- **pytest**: Testing framework
- **pytest-cov**: Coverage reporting
- **black**: Code formatting
- **ruff**: Linting and import sorting
- **mypy**: Type checking
- **pre-commit**: Git hooks
- **bandit**: Security vulnerability scanner
- **safety**: Dependency vulnerability checker

## Code Standards

### PEP 8 Compliance

All code must follow PEP 8 with these specific requirements:

- **Line length**: 80 characters maximum
- **Docstrings**: Google style, max 72 characters per line
- **File headers**: Include relative filepath as first line
- **No trailing whitespace**

### Type Hints

- **Required**: All functions must have type hints
- **Return types**: Always specify return types
- **Optional types**: Use `Optional[T]` for nullable values
- **Imports**: Import types from `typing` module

Example:
```python
# src/weatherbot/example.py
"""Example module demonstrating code standards."""

from typing import Optional, Tuple


def process_coordinates(
    latitude: float, 
    longitude: float
) -> Tuple[bool, Optional[str]]:
    """Process and validate coordinates.
    
    Args:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not -90 <= latitude <= 90:
        return False, "Invalid latitude range"
    
    if not -180 <= longitude <= 180:
        return False, "Invalid longitude range"
    
    return True, None
```

### Docstring Standards

Use Google-style docstrings:

```python
def example_function(param1: str, param2: int = 0) -> bool:
    """Brief description of function.
    
    Longer description if needed. Keep lines under 72 characters.
    
    Args:
        param1: Description of first parameter
        param2: Description of second parameter with default
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: When param1 is empty
        ConnectionError: When network is unavailable
        
    Example:
        >>> result = example_function("test", 42)
        >>> print(result)
        True
    """
```

### Code Organization

#### File Structure
```
src/weatherbot/
├── __init__.py          # Package initialization
├── cli.py               # Command-line interface
├── config.py            # Configuration management
├── alert_levels.py      # Alert system definitions
├── nhc.py               # NHC data integration
├── nws.py               # NWS alerts integration
├── ai_map_analyzer.py   # AI analysis features
├── geometry.py          # Spatial operations
├── alerting.py          # Alert management
├── state.py             # State persistence
├── reports.py           # Report generation
├── cache.py             # API caching
├── logging_setup.py     # Logging configuration
├── coverage_validator.py # Coverage validation
├── data/                # Static data files
├── icons/               # Icon resources
└── notifiers/           # Notification modules
    ├── __init__.py
    ├── toast.py         # Toast notifications
    └── weather_map.py   # Map display
```

#### Import Organization

Use ruff for automatic import sorting:

```python
# Standard library imports
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Third-party imports
import requests
from pydantic import BaseModel
from shapely.geometry import Point

# Local imports
from .config import WeatherbotConfig
from .geometry import validate_coordinates
```

## Architecture Overview

### Core Components

#### Configuration Layer
- **config.py**: Pydantic-based settings management
- **Environment variables**: `.env` file configuration
- **Validation**: Coordinate and setting validation

#### Data Layer
- **nhc.py**: National Hurricane Center integration
- **nws.py**: National Weather Service alerts
- **ai_map_analyzer.py**: AI-powered analysis
- **cache.py**: Response caching

#### Analysis Layer
- **enhanced_cone_analyzer.py**: Geometric threat analysis
- **geometry.py**: Spatial operations
- **alert_levels.py**: 5-level alert system

#### Notification Layer
- **alerting.py**: Alert management
- **notifiers/**: Notification implementations
- **reports.py**: HTML report generation

#### Persistence Layer
- **state.py**: State management
- **cache.py**: API response caching

### Design Patterns

#### Dependency Injection
```python
# Good: Inject dependencies
def create_alert_manager(config: WeatherbotConfig) -> AlertManager:
    return AlertManager(config)

# Avoid: Hard-coded dependencies
class AlertManager:
    def __init__(self):
        self.config = load_config()  # Avoid this
```

#### Error Handling
```python
# Use specific exceptions
def validate_coordinates(lat: float, lon: float) -> None:
    if not -90 <= lat <= 90:
        raise ValueError(f"Invalid latitude: {lat}")
    
    if not -180 <= lon <= 180:
        raise ValueError(f"Invalid longitude: {lon}")
```

#### Logging
```python
import logging

logger = logging.getLogger(__name__)

def process_data():
    logger.info("Starting data processing")
    try:
        # Process data
        logger.debug("Processing step completed")
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        raise
```

## Security Scanning

### Security Tools

Weatherbot includes comprehensive security scanning to identify vulnerabilities:

#### Bandit - Python Security Linter
Scans Python code for common security issues:
- **Hardcoded passwords**: Detects embedded credentials
- **SQL injection**: Identifies unsafe database queries  
- **Command injection**: Finds unsafe system calls
- **Cryptographic issues**: Weak hashing algorithms (MD5, SHA1)
- **Insecure functions**: Deprecated or unsafe functions

#### Safety - Dependency Vulnerability Scanner
Checks dependencies for known security vulnerabilities:
- **CVE database**: Cross-references known vulnerabilities
- **Outdated packages**: Identifies packages with security updates
- **License compliance**: Checks for license issues
- **Dependency conflicts**: Identifies problematic combinations

### Running Security Scans

#### Local Development
```bash
# Run all security scans
make security

# Run individually
bandit -r src/weatherbot
safety check

# Generate detailed reports
bandit -r src/weatherbot -f json -o bandit-report.json
safety check --json --output safety-report.json
```

#### CI/CD Pipeline
Security scans run automatically on every:
- **Pull Request**: Prevents insecure code from merging
- **Push to main/develop**: Continuous security monitoring
- **Release builds**: Ensures production security

### Security Issues Found

Based on the latest security scan, the following issues were identified:

#### 🔴 High Priority Issues (4 found)
**MD5 Hash Usage**: Code uses MD5 for cache keys
- **Risk**: MD5 is cryptographically weak
- **Files**: `cache.py`, `ai_map_analyzer.py`
- **Fix**: Use SHA-256 or add `usedforsecurity=False` parameter
```python
# Instead of:
import hashlib
hash_obj = hashlib.md5(data.encode())

# Use:
hash_obj = hashlib.md5(data.encode(), usedforsecurity=False)
# Or better:
hash_obj = hashlib.sha256(data.encode())
```

#### 🟡 Medium Priority Issues (1 found)
**Insecure tempfile.mktemp()**: Using deprecated tempfile function
- **Risk**: Race condition vulnerability
- **Fix**: Use `tempfile.NamedTemporaryFile()` instead
```python
# Instead of:
import tempfile
temp_path = tempfile.mktemp()

# Use:
with tempfile.NamedTemporaryFile(delete=False) as tmp:
    temp_path = tmp.name
```

#### 🟢 Low Priority Issues (8 found)
- **Assert statements**: Used for type checking (acceptable in development)
- **Try/except patterns**: Some could be more specific (non-critical)

#### 📦 Dependency Vulnerability (1 found)
**pip version 24.0**: Has known security vulnerability
- **Fix**: Upgrade pip to version 25.0+
```bash
pip install --upgrade pip
```

### Security Best Practices

#### Code Security
1. **Input Validation**: Validate all user inputs
2. **Secure Defaults**: Use secure configuration defaults
3. **Error Handling**: Don't expose sensitive information in errors
4. **Logging**: Avoid logging sensitive data

#### Dependency Management
1. **Regular Updates**: Keep dependencies current
2. **Vulnerability Monitoring**: Run `safety check` regularly
3. **Minimal Dependencies**: Only include necessary packages
4. **Version Pinning**: Use specific versions in production

#### API Security
1. **API Key Protection**: Store in environment variables
2. **Rate Limiting**: Implement request throttling
3. **HTTPS Only**: Use secure connections
4. **Input Sanitization**: Validate API inputs

### Fixing Security Issues

#### Immediate Actions Required
```bash
# 1. Fix MD5 usage
# Update cache.py and ai_map_analyzer.py to use SHA-256

# 2. Fix tempfile usage
# Replace tempfile.mktemp() with NamedTemporaryFile()

# 3. Upgrade pip
pip install --upgrade pip

# 4. Re-run security scans
make security
```

#### Long-term Security Maintenance
1. **Regular Scans**: Run `make security` before releases
2. **Dependency Updates**: Monthly security updates
3. **Code Reviews**: Security-focused code reviews
4. **Security Training**: Keep team updated on security practices

## Testing

### Test Structure

```
tests/
├── __init__.py
├── conftest.py              # Pytest fixtures
├── test_smoke.py            # Basic import tests
├── test_geometry.py         # Geometry operations
├── test_config.py           # Configuration tests
├── test_nhc.py              # NHC integration tests
├── test_nws.py              # NWS integration tests
├── test_alert_levels.py     # Alert system tests
├── test_ai_analysis.py      # AI feature tests
└── integration/             # Integration tests
    ├── test_end_to_end.py
    └── test_cli.py
```

### Writing Tests

#### Unit Tests
```python
# tests/test_geometry.py
"""Tests for geometry operations."""

import pytest
from shapely.geometry import Point, Polygon

from weatherbot.geometry import point_in_any, validate_coordinates


def test_validate_coordinates_valid():
    """Test coordinate validation with valid values."""
    # Should not raise
    validate_coordinates(-80.1918, 25.7617)


def test_validate_coordinates_invalid_latitude():
    """Test coordinate validation with invalid latitude."""
    with pytest.raises(ValueError, match="Invalid latitude"):
        validate_coordinates(-80.1918, 95.0)


def test_point_in_polygon():
    """Test point-in-polygon detection."""
    # Create test polygon (square)
    polygon = Polygon([(-1, -1), (1, -1), (1, 1), (-1, 1)])
    
    # Test point inside
    assert point_in_any([polygon], (0, 0)) is True
    
    # Test point outside
    assert point_in_any([polygon], (2, 2)) is False
```

#### Integration Tests
```python
# tests/integration/test_cli.py
"""Integration tests for CLI commands."""

import subprocess
import sys
from pathlib import Path


def test_cli_help():
    """Test CLI help command."""
    result = subprocess.run(
        [sys.executable, "-m", "weatherbot", "--help"],
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0
    assert "weatherbot" in result.stdout


def test_cli_check_coverage(tmp_path):
    """Test coverage check command."""
    # Create temporary config
    env_file = tmp_path / ".env"
    env_file.write_text("HOME_LAT=25.7617\nHOME_LON=-80.1918\n")
    
    result = subprocess.run(
        [sys.executable, "-m", "weatherbot", "check-coverage"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0
```

#### Fixtures
```python
# tests/conftest.py
"""Pytest fixtures for testing."""

import pytest
from pathlib import Path
from weatherbot.config import WeatherbotConfig


@pytest.fixture
def sample_config():
    """Create sample configuration for testing."""
    return WeatherbotConfig(
        home_lat=25.7617,
        home_lon=-80.1918,
        toast_enabled=False,  # Disable for testing
        log_level="DEBUG",
    )


@pytest.fixture
def temp_state_dir(tmp_path):
    """Create temporary state directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=weatherbot

# Run specific test file
pytest tests/test_geometry.py

# Run with verbose output
pytest -v

# Run integration tests only
pytest tests/integration/

# Run and generate HTML coverage report
pytest --cov=weatherbot --cov-report=html
```

### Test Categories

Use pytest markers for test organization:

```python
# Mark slow tests
@pytest.mark.slow
def test_api_integration():
    """Test that requires network access."""
    pass

# Mark integration tests
@pytest.mark.integration
def test_end_to_end_workflow():
    """Test complete workflow."""
    pass
```

Run specific test categories:
```bash
# Skip slow tests
pytest -m "not slow"

# Run only integration tests
pytest -m integration
```

## Contributing Workflow

### Branch Strategy

- **main**: Stable release branch
- **develop**: Development integration branch
- **feature/**: Feature development branches
- **hotfix/**: Critical bug fixes

### Feature Development

1. **Create feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Implement feature**:
   - Write code following standards
   - Add comprehensive tests
   - Update documentation

3. **Pre-commit checks**:
   ```bash
   # Automatic via pre-commit hooks
   black src/ tests/
   ruff check src/ tests/
   mypy src/weatherbot
   make security  # Run security scans
   pytest
   ```

4. **Commit changes**:
   ```bash
   git add .
   git commit -m "feat: add new feature description"
   ```

5. **Push and create PR**:
   ```bash
   git push origin feature/your-feature-name
   ```

### Commit Message Format

Use conventional commits:

- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring
- `test:` Test additions/changes
- `chore:` Maintenance tasks
- `perf:` Performance improvements
- `ci:` CI/CD changes

Examples:
```
feat: add AI web search for global coverage
fix: handle missing storm position data
docs: update installation guide
test: add integration tests for NHC client
```

### Pull Request Process

1. **Create descriptive PR**:
   - Clear title and description
   - Link related issues
   - Include testing information

2. **Ensure CI passes**:
   - All tests pass
   - Code coverage maintained
   - Linting passes
   - Type checking passes

3. **Request review**:
   - Tag relevant reviewers
   - Address feedback promptly
   - Update documentation if needed

4. **Merge requirements**:
   - Approved by maintainer
   - All CI checks pass
   - No merge conflicts

## Release Process

### Version Management

Weatherbot uses semantic versioning (SemVer):
- **Major**: Breaking changes (1.0.0 → 2.0.0)
- **Minor**: New features (1.0.0 → 1.1.0)
- **Patch**: Bug fixes (1.0.0 → 1.0.1)

### Release Steps

1. **Update version**:
   ```python
   # src/weatherbot/__init__.py
   __version__ = "1.1.0"
   
   # pyproject.toml
   version = "1.1.0"
   ```

2. **Update changelog**:
   ```bash
   # Add to CHANGELOG.md
   ## [1.1.0] - 2024-01-15
   ### Added
   - New AI web search feature
   ### Fixed
   - Storm position parsing bug
   ```

3. **Create release commit**:
   ```bash
   git commit -m "chore: release v1.1.0"
   git tag v1.1.0
   ```

4. **Push release**:
   ```bash
   git push origin main --tags
   ```

### Quality Gates

Before release:
- [ ] All tests pass
- [ ] Code coverage ≥ 80%
- [ ] Security scans pass (no high/critical issues)
- [ ] Dependencies have no known vulnerabilities
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Version numbers updated
- [ ] Manual testing completed

## Development Tools

### Makefile Commands

```bash
# Format code
make format

# Run linting
make lint

# Run security scans
make security

# Run tests
make test

# Run tests with coverage
make test-cov

# Run all checks
make lint && make security && make test

# Clean build artifacts
make clean

# Install pre-commit hooks
make pre-commit
```

### VS Code Configuration

Recommended `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.ruffEnabled": true,
    "python.formatting.provider": "black",
    "python.formatting.blackArgs": ["--line-length", "80"],
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests/"],
    "files.trimTrailingWhitespace": true,
    "files.insertFinalNewline": true
}
```

### Pre-commit Configuration

`.pre-commit-config.yaml` includes:
- **black**: Code formatting
- **ruff**: Linting and import sorting
- **mypy**: Type checking
- **pytest**: Test execution

## Debugging

### Logging

Enable debug logging:
```bash
# Environment variable
LOG_LEVEL=DEBUG weatherbot run --verbose

# Or in .env file
LOG_LEVEL=DEBUG
```

### Common Issues

#### Import Errors
```bash
# Ensure package is installed in development mode
pip install -e .
```

#### Test Failures
```bash
# Run specific test with verbose output
pytest tests/test_specific.py -v -s

# Debug with pdb
pytest tests/test_specific.py --pdb
```

#### Type Checking Issues
```bash
# Run mypy on specific file
mypy src/weatherbot/specific_module.py

# Ignore specific errors (use sparingly)
# type: ignore[error-code]
```

## Getting Help

- **Documentation**: Read all guides in `docs/`
- **Issues**: Search existing GitHub issues
- **Discussions**: Join project discussions
- **Code Review**: Ask for feedback on PRs
- **Mentoring**: Reach out to maintainers
