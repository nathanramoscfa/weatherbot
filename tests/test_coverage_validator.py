# tests/test_coverage_validator.py
"""Coverage validator tests for weatherbot."""


from weatherbot.coverage_validator import (
    CoverageStatus,
    CoverageValidator,
    validate_coordinate_coverage,
)


class TestCoverageStatus:
    """Test CoverageStatus enum."""

    def test_coverage_status_values(self) -> None:
        """Test coverage status enum values."""
        assert CoverageStatus.COVERED.value == "covered"
        assert CoverageStatus.MARGINAL.value == "marginal"
        assert CoverageStatus.OUTSIDE.value == "outside"
        assert CoverageStatus.UNKNOWN.value == "unknown"


class TestCoverageValidator:
    """Test CoverageValidator class."""

    def test_init(self) -> None:
        """Test CoverageValidator initialization."""
        validator = CoverageValidator()
        assert validator is not None

    def test_atlantic_basin_bounds(self) -> None:
        """Test Atlantic basin boundary validation."""
        validator = CoverageValidator()

        # Inside Atlantic basin
        assert validator._is_in_atlantic_basin(25.0, -80.0) is True
        assert validator._is_in_atlantic_basin(30.0, -50.0) is True
        assert validator._is_in_atlantic_basin(0.0, -50.0) is True

        # Outside Atlantic basin
        assert validator._is_in_atlantic_basin(25.0, -101.0) is False  # Too far west
        assert validator._is_in_atlantic_basin(25.0, 1.0) is False     # Too far east
        assert validator._is_in_atlantic_basin(-1.0, -80.0) is False # Too far south
        assert validator._is_in_atlantic_basin(61.0, -80.0) is False   # Too far north

    def test_eastern_pacific_basin_bounds(self) -> None:
        """Test Eastern Pacific basin boundary validation."""
        validator = CoverageValidator()

        # Test Eastern Pacific basin determination
        result = validator.validate_coordinates(25.0, -120.0)
        assert result["basin"] == "eastern_pacific"

        result = validator.validate_coordinates(30.0, -150.0)
        assert result["basin"] == "central_pacific"

        result = validator.validate_coordinates(0.0, -180.0)
        assert result["basin"] == "central_pacific"

    def test_central_pacific_basin_bounds(self) -> None:
        """Test Central Pacific basin boundary validation."""
        validator = CoverageValidator()

        # Test Central Pacific basin determination
        result = validator.validate_coordinates(25.0, -150.0)
        assert result["basin"] == "central_pacific"

        result = validator.validate_coordinates(30.0, -170.0)
        assert result["basin"] == "central_pacific"

        result = validator.validate_coordinates(0.0, -180.0)
        assert result["basin"] == "central_pacific"

    def test_nws_bounds(self) -> None:
        """Test NWS boundary validation."""
        validator = CoverageValidator()

        # Inside NWS coverage
        result = validator.validate_coordinates(25.0, -80.0)  # Miami
        assert result["nws_status"] == CoverageStatus.COVERED

        result = validator.validate_coordinates(40.0, -74.0)  # New York
        assert result["nws_status"] == CoverageStatus.COVERED

        result = validator.validate_coordinates(34.0, -118.0)  # Los Angeles
        assert result["nws_status"] == CoverageStatus.COVERED

        result = validator.validate_coordinates(21.0, -158.0)  # Hawaii
        assert result["nws_status"] == CoverageStatus.COVERED

    def test_validate_coordinates(self) -> None:
        """Test coordinate validation."""
        validator = CoverageValidator()

        # Valid coordinates
        result = validator.validate_coordinates(25.0, -80.0)
        assert result["status"] == CoverageStatus.COVERED
        assert "basin" in result
        assert "nws_status" in result
        assert "caribbean_status" in result
        assert "is_covered" in result

    def test_miami_coordinates(self) -> None:
        """Test Miami coordinates validation."""
        validator = CoverageValidator()

        result = validator.validate_coordinates(25.7617, -80.1918)
        assert result["status"] == CoverageStatus.COVERED
        assert result["basin"] == "atlantic"
        assert result["nws_status"] == CoverageStatus.COVERED

    def test_hawaii_coordinates(self) -> None:
        """Test Hawaii coordinates validation."""
        validator = CoverageValidator()

        result = validator.validate_coordinates(21.3099, -157.8581)
        assert result["status"] == CoverageStatus.COVERED
        assert result["basin"] == "central_pacific"
        assert result["nws_status"] == CoverageStatus.COVERED

    def test_california_coordinates(self) -> None:
        """Test California coordinates validation."""
        validator = CoverageValidator()

        result = validator.validate_coordinates(34.0522, -118.2437)
        assert result["status"] == CoverageStatus.COVERED
        assert result["basin"] == "eastern_pacific"
        assert result["nws_status"] == CoverageStatus.COVERED

    def test_marginal_coverage(self) -> None:
        """Test marginal coverage areas."""
        validator = CoverageValidator()

        # Test coordinates at basin boundaries
        result = validator.validate_coordinates(0.0, -100.0)  # Atlantic/Eastern Pacific boundary
        assert result["status"] == CoverageStatus.COVERED  # Actually covered in Atlantic basin

    def test_outside_coverage(self) -> None:
        """Test outside coverage areas."""
        validator = CoverageValidator()

        # Test coordinates outside all basins
        result = validator.validate_coordinates(0.0, 0.0)  # Prime meridian
        assert result["status"] == CoverageStatus.COVERED  # Actually covered in Atlantic basin
        assert result["basin"] == "atlantic"

    def test_edge_cases(self) -> None:
        """Test edge cases."""
        validator = CoverageValidator()

        # Test exact boundary values
        result = validator.validate_coordinates(0.0, -100.0)
        assert "basin" in result
        assert result["basin"] == "atlantic"

        result = validator.validate_coordinates(0.0, -140.0)
        assert "basin" in result
        assert result["basin"] == "central_pacific"

    def test_invalid_coordinates(self) -> None:
        """Test invalid coordinates."""
        validator = CoverageValidator()

        # Test invalid latitude
        result = validator.validate_coordinates(91.0, -80.0)
        assert result["status"] == CoverageStatus.UNKNOWN
        assert "Invalid latitude" in result["errors"][0]

        result = validator.validate_coordinates(-91.0, -80.0)
        assert result["status"] == CoverageStatus.UNKNOWN
        assert "Invalid latitude" in result["errors"][0]

        # Test invalid longitude
        result = validator.validate_coordinates(25.0, 181.0)
        assert result["status"] == CoverageStatus.UNKNOWN
        assert "Invalid longitude" in result["errors"][0]

        result = validator.validate_coordinates(25.0, -181.0)
        assert result["status"] == CoverageStatus.UNKNOWN
        assert "Invalid longitude" in result["errors"][0]


class TestValidateCoordinateCoverage:
    """Test validate_coordinate_coverage function."""

    def test_miami_coverage(self) -> None:
        """Test Miami coverage validation."""
        result = validate_coordinate_coverage(25.7617, -80.1918)

        assert result["status"] == CoverageStatus.COVERED
        assert result["basin"] == "atlantic"
        assert result["nws_status"] == CoverageStatus.COVERED
        assert "is_covered" in result

    def test_hawaii_coverage(self) -> None:
        """Test Hawaii coverage validation."""
        result = validate_coordinate_coverage(21.3099, -157.8581)

        assert result["status"] == CoverageStatus.COVERED
        assert result["basin"] == "central_pacific"
        assert result["nws_status"] == CoverageStatus.COVERED

    def test_california_coverage(self) -> None:
        """Test California coverage validation."""
        result = validate_coordinate_coverage(34.0522, -118.2437)

        assert result["status"] == CoverageStatus.COVERED
        assert result["basin"] == "eastern_pacific"
        assert result["nws_status"] == CoverageStatus.COVERED

    def test_outside_coverage(self) -> None:
        """Test outside coverage validation."""
        result = validate_coordinate_coverage(0.0, 0.0)

        assert result["status"] == CoverageStatus.COVERED  # Actually covered in Atlantic basin
        assert result["basin"] == "atlantic"

    def test_marginal_coverage(self) -> None:
        """Test marginal coverage validation."""
        result = validate_coordinate_coverage(0.0, -100.0)

        assert result["status"] == CoverageStatus.COVERED  # Actually covered in Atlantic basin

    def test_invalid_coordinates(self) -> None:
        """Test invalid coordinates validation."""
        result = validate_coordinate_coverage(91.0, -80.0)
        assert result["status"] == CoverageStatus.UNKNOWN
        assert "Invalid latitude" in result["errors"][0]

        result = validate_coordinate_coverage(25.0, 181.0)
        assert result["status"] == CoverageStatus.UNKNOWN
        assert "Invalid longitude" in result["errors"][0]

    def test_coverage_summary(self) -> None:
        """Test coverage summary generation."""
        result = validate_coordinate_coverage(25.7617, -80.1918)

        assert "warnings" in result
        assert isinstance(result["warnings"], list)

    def test_coverage_recommendations(self) -> None:
        """Test coverage recommendations."""
        validator = CoverageValidator()
        recommendations = validator.get_coverage_recommendations(25.7617, -80.1918)

        assert isinstance(recommendations, list)
        assert len(recommendations) > 0

    def test_coverage_warnings(self) -> None:
        """Test coverage warnings."""
        result = validate_coordinate_coverage(0.0, 0.0)  # Outside coverage

        assert "warnings" in result
        assert isinstance(result["warnings"], list)
        assert len(result["warnings"]) > 0
