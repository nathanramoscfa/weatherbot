# Changelog

All notable changes to Weatherbot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Phase 1 verification
- Add the 50-check foundation verifier, full V1-V7 post sweep, QA findings ledger,
  and the required aggregate phase-verify workflow. Keep fixture bytes unchanged
  while guarding LF line endings for repository text.


### Added
- The NWS client, `weatherbot.sources.nws`. `lookup_point` resolves a point
  to its forecast zone, county, office, and time zone, and returns
  `OutsideNwsCoverage` for the documented `InvalidPoint` 404. `fetch_alerts`
  queries the point, the county, and the forecast zone and merges the
  answers by alert id. Each alert keeps `found_by`, its affected zones, and
  both geocode lists, which issue #10's rule needs in Phase 3, and nothing
  is filtered by zone. A location outside NWS coverage sends no alert
  request. `fetch_zone` reads a zone's metadata and shape with conditional
  requests. `format_point` writes every point with four decimals, the
  precision the API serves (recorded in the register 2026-10-17). It is
  the only function that writes a coordinate into a URL, and the fixture
  recorder now uses it too.
- The Nominatim client, `weatherbot.sources.nominatim`: `reverse_geocode`
  returns the place's display name, country, and the licence text for the
  attribution. It sends one request per location, at setup, never per
  fetch, and returns none when Nominatim finds no place.
- The first recorded NWS alert: a Rip Current Statement (2026-10-17) that
  the point, county, and forecast-zone queries all returned, recorded
  beside the 2026-10-12 set. The register's points, alerts, and Nominatim
  "Fields v2 uses" lists now name nested members as `object.member`.
- The register source `nhc-arrival-times` (issue #11): the arrival-time KMZ
  that the roster links, with its row, an "Arrival-time KMZ" section, and a
  narrowed "Not used" row in `docs/DATA_SOURCES.md` (verified 2026-10-17).
  The recorder records the archived Dorian 036 pair, whose checksums the
  replay corpus manifest pins, and every active storm's linked pair.
  `scripts/check_personal_data.py` now scans every member of a zip capture,
  under the client's bounds.
- The arrival-time client, `weatherbot.sources.nhc_arrival_times`. It opens
  the KMZ in memory under member, size, ratio, and path limits, parses its
  KML with `defusedxml`, and resolves every labelled line to an instant from
  the product's `timezone` and `pubAdvTime`. When the KMZ disagrees with the
  roster or with its own URL, every line stays unresolved and the reason is
  given. `prefer_kmz` applies the snapshot rule: a KMZ product supersedes
  the map-layer product of the same storm, advisory, and kind. Links outside
  the arrival-time pattern are never fetched.
- The text-product client, `weatherbot.sources.nhc_text_products`: the
  newest TCP of each storm's slot and the newest English TWO of each basin,
  from the NWS API. A TCP from a reused slot is logged and not attributed
  to the storm, and an older TCP keeps its own advisory number.
- The outlook-graphic client, `weatherbot.sources.nhc_outlook_graphics`:
  the six `two_{atl,pac,cpac}_{2d0,7d0}.png` maps, fetched with conditional
  requests, with the PNG signature checked and the size read from `IHDR`.
- The GIS RSS client, `weatherbot.sources.nhc_gis_rss`: the three feeds,
  parsed with `defusedxml`. The no-storm placeholder item is recognized.
- The catalog client, `weatherbot.sources.catalogs`: the `StormSurgeRisk`
  catalog, with the five US East and Gulf Coast images resolved by group
  path, and the nowCOAST radar and satellite WMS capabilities. All network
  XML goes through `weatherbot.sources.markup`, which uses `defusedxml` and
  refuses any DTD. `defusedxml` is a new runtime dependency.
- The HTTP layer, `weatherbot.sources.http`: one `httpx` client per run with the
  register's User-Agent (`weatherbot.sources.USER_AGENT`, which the fixture
  recorder now imports with the per-host intervals and the ArcGIS query
  parameters), TLS verification on, redirects refused, and fixed timeouts;
  per-host pacing, at most four attempts with full-jitter backoff and
  `Retry-After`, an 8 MiB body cap, conditional requests through a
  `ValidatorStore`, typed errors in `weatherbot.sources.errors`, and log
  records that never carry a request coordinate above DEBUG.
- The roster client (`nhc_current_storms`), the ArcGIS client (`arcgis`:
  catalogs, layer resolution by name or group path, paging, counts), and the
  NHC map clients (`nhc_map`), which parse every register layer of the
  tropical, summary, breakpoint, and peak-surge services into the shared
  models, including one wind-probability product per threshold held by the
  snapshot (issue #12), and log Source-drift warnings where the products
  disagree. `tests/contract/test_field_coverage.py` keeps each parser's
  fields equal to the register's "Fields v2 uses".
- `.github/workflows/live-smoke.yml`, which runs `pytest -m live` when
  dispatched by hand.
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
- `weatherbot.models`, the domain models every layer shares and the lowest
  layer of the import contracts: frozen, strict Pydantic models with a
  `Provenance` on every record; GeoJSON-shaped geometry with an explicit
  CRS and Shapely's validity verdict, never relabeled or transformed; UTC
  instants with NOAA's local text kept beside them and parsed only by the
  tested functions of `weatherbot.models.times`; coded values that keep
  unknown official codes; units in field names only where NHC states them;
  `ArrivalTimeProduct`, resolved from the arrival-time KMZ's own zone and
  publication time (issue #11); `WindProbabilityProduct`, held by the
  snapshot with no storm field (issue #12); and `Snapshot` with one outcome
  per source. `pydantic` and `shapely` join the runtime dependencies.

### Changed
- Phase 1 verification checks 7, 9, and 12 read Phase 1's version, its
  eight-file skeleton, and its Typer-only dependency list from the
  `v2.0.0-phase-1` tag, so the package can grow while `phase-verify (01)`
  stays green; the identity, entry-point, and still-tracked halves stay
  live, and a missing tag fails.
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
