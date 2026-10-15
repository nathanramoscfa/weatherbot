# Changelog

All notable changes to Weatherbot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- The version 2 scaffold (2.0.0.dev0): a uv project on Python 3.13 with a
  `uv_build` backend and a committed `uv.lock`; the `src/weatherbot/`
  package skeleton with the `sources`, `engine`, `services`, `cli`, and
  `web` layers and a `weatherbot --version` command; import-linter layer
  contracts and a test that bans I/O libraries from the engine; strict ruff
  and pyright; pytest with a network guard and a temporary working
  directory for every test; and a CI workflow on Ubuntu and Windows whose
  aggregate `gate` job is the required check on `main`.
- `docs/DATA_SOURCES.md`, the data-source register, verified live on
  2026-10-12: a stable id, endpoint, format, fixture class, cadence, and
  terms for every source in the brief's §5; every ArcGIS layer by name,
  with its fields and the query parameters shared by the fixture recorder
  and the source clients; the per-basin answer on arrival-time,
  probabilistic-wind, and surge layers; the NWS, text-product, graphic,
  RSS, archive, overlay, and geocoding endpoints with their etiquette; the
  project User-Agent; and the sources version 2 does not use.
- `scripts/record_fixtures.py`, the fixture recorder, and `tests/fixtures/recorded/`: a
  capture of every `required` source in the register, taken live on 2026-10-12 with the
  project User-Agent and stored with a checksummed `manifest.json` per directory; the six
  seven-day Atlantic outlook maps recovered from the 2025 version 1 reports; a notice of the
  third-party terms; and contract tests that keep the register, the recorder, and the
  recorded service catalogs in agreement and hold the fixtures to a 25 MiB budget.

- A checksum-pinned NHC replay corpus for Irma, Dorian, Ian, and Milton, with
  deterministic compressed advisory geometry, explicit native CRS provenance, an
  ignored cache for original forecast, wind-probability, and arrival-time archives,
  offline and full-cache tests, and a twice-weekly cache-verification workflow.

### Changed
- Version 1 is retired; it remains installable with
  `pip install weatherbot==1.0.0`, and its source is preserved at the
  `v1.0.0` tag. Version 2 is a from-scratch rewrite specified in
  [the v2 brief](docs/brief/weatherbot-v2-brief.md).
- `README.md`, `CONTRIBUTING.md`, and `AGENTS.md` describe version 2.

### Removed
- Version 1's code, tests, documentation, scripts, and packaging
  (setuptools metadata, Makefile, and v1's CI workflow, including its
  Safety scan and the `SAFETY_API_KEY` secret). The v1 default coverage
  polygon and `env.example` leave the tree with them.

## [1.0.0] - 2025-09-29

### Added
- Comprehensive documentation suite
- API reference documentation
- Development guide for contributors
- Configuration reference guide
- User guide with examples
- **Security scanning implementation**:
  - Bandit security vulnerability scanner
  - Safety dependency vulnerability checker
  - Automated CI/CD security checks
  - Makefile commands for local security scanning
  - Security best practices documentation

### Changed
- Enhanced README with better organization
- Improved code documentation and type hints
- Updated development workflow to include security scanning

### Security
- **Security Issues Identified**: 13 security issues found and documented
  - 4 High priority (MD5 usage in cache keys)
  - 1 Medium priority (insecure tempfile usage)
  - 8 Low priority (assert statements, exception handling)
  - 1 Dependency vulnerability (outdated pip)
- **CI/CD Security**: Automated security scanning on every commit
- **Security Documentation**: Comprehensive security guidelines added

### Added
- Initial release of Weatherbot
- 5-level hurricane alert system
- National Hurricane Center (NHC) forecast cone integration
- National Weather Service (NWS) alert monitoring
- AI-powered threat analysis using OpenAI
- Global weather coverage via AI web search
- Windows toast notification system
- Geometric point-in-polygon and county-level intersection detection
- Comprehensive HTML report generation with interactive maps
- State management for alert deduplication
- API response caching for performance
- Coverage validation for NOAA data sources
- Command-line interface with multiple commands
- Configuration management via environment variables
- Logging system with configurable levels
- Pre-commit hooks for code quality
- Comprehensive test suite with pytest
- Type hints throughout codebase
- PEP 8 compliance with Black formatting
- Ruff linting for code quality

### Features
- **Real-time Hurricane Tracking**: Monitors active NHC forecast cones
- **NWS Alert Integration**: Processes official hurricane watches and warnings
- **AI-Enhanced Analysis**: Optional OpenAI integration for intelligent threat assessment
- **Multi-level Alert System**: 5-tier system from "All Clear" to "Hurricane Warning"
- **Toast Notifications**: Windows 10/11 native notifications with sounds
- **Geometric Precision**: Point-in-polygon and county-level intersection analysis
- **Comprehensive Reporting**: HTML reports with storm tracking maps
- **Global Coverage**: AI web search fallback for locations outside NOAA coverage
- **Flexible Configuration**: Point-based or county-based threat detection
- **State Persistence**: Prevents duplicate alerts and tracks storm advisories

### Commands
- `weatherbot run` - Main monitoring cycle
- `weatherbot ai-analysis` - AI-powered threat analysis
- `weatherbot test-alert` - Test notification systems
- `weatherbot check-coverage` - Validate coordinate coverage
- `weatherbot show-map` - Open official NOAA maps
- `weatherbot state show/clear` - State management
- `weatherbot debug` - Debug commands for development

### Configuration
- **Required**: HOME_LAT, HOME_LON coordinates
- **Optional**: OpenAI API key for AI features
- **Optional**: County-level intersection with GeoJSON files
- **Optional**: Notification and alert behavior settings
- **Optional**: Logging configuration

### Data Sources
- **NHC MapServer**: Real-time hurricane forecast cones
- **NWS API**: Official weather alerts and warnings
- **NOAA Maps**: Tropical weather outlook imagery
- **CurrentStorms.json**: Active storm position data
- **AI Web Search**: Global weather service integration

### Coverage Areas
- **Primary**: Atlantic Basin, Eastern Pacific, Central Pacific (NOAA coverage)
- **Secondary**: Global coverage via AI web search fallback
- **Optimal**: US East Coast, Caribbean, Gulf of Mexico

### Technical Details
- **Python**: 3.11+ required
- **Platform**: Windows 10/11 (primary), Linux/macOS (limited)
- **Dependencies**: Typer, Pydantic, Shapely, OpenAI, Requests, Rich
- **Architecture**: Modular design with dependency injection
- **Testing**: Comprehensive test suite with pytest
- **Code Quality**: Black formatting, Ruff linting, MyPy type checking

### Installation
- Standard installation via pip
- Development installation with pre-commit hooks
- Virtual environment support
- Configuration via .env files

### Documentation
- Comprehensive README with setup instructions
- API documentation for all modules
- User guide with examples
- Development guide for contributors
- Configuration reference
- Troubleshooting guide

## Version History

### Pre-1.0.0 Development

#### [0.9.0] - Development Phase
- Core hurricane tracking functionality
- Basic NHC and NWS integration
- Initial AI features
- Command-line interface development

#### [0.8.0] - Alpha Phase
- Geometric analysis implementation
- State management system
- Notification framework
- Testing infrastructure

#### [0.7.0] - Prototype Phase
- Basic weather data integration
- Alert level system design
- Configuration management
- Logging system

#### [0.6.0] - Proof of Concept
- Initial NHC data parsing
- Basic coordinate validation
- Simple notification system
- Core architecture design

## Migration Guide

### From 0.x to 1.0.0

#### Configuration Changes
- Environment variables now use consistent naming
- `.env` file format standardized
- New coverage validation system

#### API Changes
- Standardized function signatures
- Improved type hints throughout
- Better error handling

#### Feature Changes
- Enhanced 5-level alert system
- Improved AI integration
- Better global coverage support

#### Breaking Changes
- Configuration file format updated
- Some function names changed for consistency
- Alert level numbering system revised

## Future Roadmap

### Planned Features (v1.1.0)
- [ ] Docker container support
- [ ] Web dashboard interface
- [ ] Mobile app notifications
- [ ] Email notification support
- [ ] Slack/Discord integration
- [ ] Multiple location monitoring
- [ ] Historical storm tracking
- [ ] Advanced weather maps

### Planned Improvements (v1.2.0)
- [ ] Enhanced AI models
- [ ] Better global coverage
- [ ] Performance optimizations
- [ ] Advanced reporting features
- [ ] Real-time streaming updates
- [ ] Machine learning predictions
- [ ] Social media integration
- [ ] Emergency contact system

### Long-term Goals (v2.0.0)
- [ ] Multi-hazard monitoring (earthquakes, floods, etc.)
- [ ] Commercial API offering
- [ ] Mobile applications
- [ ] Enterprise features
- [ ] Advanced analytics
- [ ] Predictive modeling
- [ ] Integration with emergency services
- [ ] Community features

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details on:
- Development setup
- Code standards
- Testing requirements
- Pull request process

## Support

- **Documentation**: See `docs/` directory
- **Issues**: Report bugs on GitHub
- **Discussions**: Join project discussions
- **Email**: Contact maintainers for support

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **NOAA/NHC**: For providing comprehensive hurricane data
- **National Weather Service**: For official weather alerts
- **OpenAI**: For AI analysis capabilities
- **Python Community**: For excellent libraries and tools
- **Contributors**: All developers who have contributed to this project

## Security

### Reporting Security Issues

Please report security vulnerabilities to the maintainers privately before public disclosure.

### Security Considerations

- API keys are stored in environment variables
- No sensitive data is logged
- Network requests use HTTPS
- Input validation prevents injection attacks

## Performance

### System Requirements
- **RAM**: 512MB minimum, 1GB recommended
- **Storage**: 100MB for installation, 500MB for cache/logs
- **Network**: Broadband internet connection recommended
- **CPU**: Modern multi-core processor recommended

### Performance Metrics
- **Startup Time**: < 5 seconds
- **Analysis Time**: 10-30 seconds per cycle
- **Memory Usage**: 50-100MB typical
- **Network Usage**: 1-5MB per analysis cycle

### Optimization Tips
- Use appropriate alert cooldown periods
- Enable caching for frequent API calls
- Adjust logging levels for performance
- Monitor system resources during continuous operation
