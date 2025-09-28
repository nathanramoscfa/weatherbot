# tests/test_alert_levels.py
"""Alert levels tests for weatherbot."""


from weatherbot.alert_levels import (
    ALERT_DEFINITIONS,
    AlertInfo,
    AlertLevel,
    format_alert_message,
    get_alert_info,
    get_alert_level,
)


class TestAlertLevel:
    """Test AlertLevel enum."""

    def test_alert_level_values(self) -> None:
        """Test alert level enum values."""
        assert AlertLevel.ALL_CLEAR.value == 1
        assert AlertLevel.TROPICAL_STORM_THREAT.value == 2
        assert AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT.value == 3
        assert AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION.value == 4
        assert AlertLevel.HURRICANE_WARNING.value == 5

    def test_alert_level_comparison(self) -> None:
        """Test alert level comparison."""
        # Test that alert levels have increasing severity
        assert AlertLevel.ALL_CLEAR.value < AlertLevel.TROPICAL_STORM_THREAT.value
        assert AlertLevel.TROPICAL_STORM_THREAT.value < AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT.value
        assert AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT.value < AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION.value
        assert AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION.value < AlertLevel.HURRICANE_WARNING.value


class TestAlertInfo:
    """Test AlertInfo class."""

    def test_alert_info_creation(self) -> None:
        """Test AlertInfo creation."""
        info = AlertInfo(
            level=AlertLevel.ALL_CLEAR,
            icon="✅",
            color="#4CAF50",
            sound_pattern="none",
            title_prefix="ALL CLEAR",
            guidance="No active disturbances."
        )

        assert info.level == AlertLevel.ALL_CLEAR
        assert info.icon == "✅"
        assert info.color == "#4CAF50"
        assert info.sound_pattern == "none"
        assert info.title_prefix == "ALL CLEAR"
        assert info.guidance == "No active disturbances."

    def test_alert_definitions_completeness(self) -> None:
        """Test that all alert levels have definitions."""
        for level in AlertLevel:
            assert level in ALERT_DEFINITIONS
            info = ALERT_DEFINITIONS[level]
            assert isinstance(info, AlertInfo)
            assert info.level == level
            assert info.icon
            assert info.color
            assert info.sound_pattern
            assert info.title_prefix
            assert info.guidance


class TestGetAlertLevel:
    """Test get_alert_level function."""

    def test_hurricane_warning(self) -> None:
        """Test hurricane warning level."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=False,
            has_hurricane_watch=False,
            has_hurricane_warning=True,
        )
        assert level == AlertLevel.HURRICANE_WARNING

    def test_tropical_storm_warning(self) -> None:
        """Test tropical storm warning level."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=False,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
            has_tropical_storm_warning=True,
        )
        assert level == AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION

    def test_hurricane_watch(self) -> None:
        """Test hurricane watch level."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=False,
            has_hurricane_watch=True,
            has_hurricane_warning=False,
        )
        assert level == AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION

    def test_evacuation_order(self) -> None:
        """Test evacuation order level."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=False,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
            has_evacuation_order=True,
        )
        assert level == AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION

    def test_tropical_storm_watch(self) -> None:
        """Test tropical storm watch level."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=False,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
            has_tropical_storm_watch=True,
        )
        assert level == AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT

    def test_hurricane_cone_5_days(self) -> None:
        """Test hurricane cone within 5 days."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=True,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
            days_until_impact=5,
        )
        assert level == AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT

    def test_hurricane_cone_6_days(self) -> None:
        """Test hurricane cone beyond 5 days."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=True,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
            days_until_impact=6,
        )
        assert level == AlertLevel.ALL_CLEAR

    def test_hurricane_storm_type_5_days(self) -> None:
        """Test hurricane storm type within 5 days."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=False,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
            storm_type="hurricane",
            days_until_impact=5,
        )
        assert level == AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT

    def test_hurricane_storm_type_6_days(self) -> None:
        """Test hurricane storm type beyond 5 days."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=False,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
            storm_type="hurricane",
            days_until_impact=6,
        )
        assert level == AlertLevel.ALL_CLEAR

    def test_disturbance_cone(self) -> None:
        """Test disturbance cone."""
        level = get_alert_level(
            in_disturbance_cone=True,
            in_hurricane_cone=False,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
        )
        assert level == AlertLevel.TROPICAL_STORM_THREAT

    def test_disturbance_storm_type_7_days(self) -> None:
        """Test disturbance storm type within 7 days."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=False,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
            storm_type="disturbance",
            days_until_impact=7,
        )
        assert level == AlertLevel.TROPICAL_STORM_THREAT

    def test_disturbance_storm_type_8_days(self) -> None:
        """Test disturbance storm type beyond 7 days."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=False,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
            storm_type="disturbance",
            days_until_impact=8,
        )
        assert level == AlertLevel.ALL_CLEAR

    def test_depression_storm_type_7_days(self) -> None:
        """Test depression storm type within 7 days."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=False,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
            storm_type="depression",
            days_until_impact=7,
        )
        assert level == AlertLevel.TROPICAL_STORM_THREAT

    def test_depression_storm_type_8_days(self) -> None:
        """Test depression storm type beyond 7 days."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=False,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
            storm_type="depression",
            days_until_impact=8,
        )
        assert level == AlertLevel.ALL_CLEAR

    def test_all_clear(self) -> None:
        """Test all clear level."""
        level = get_alert_level(
            in_disturbance_cone=False,
            in_hurricane_cone=False,
            has_hurricane_watch=False,
            has_hurricane_warning=False,
        )
        assert level == AlertLevel.ALL_CLEAR

    def test_priority_order(self) -> None:
        """Test that higher priority conditions override lower ones."""
        # Hurricane warning should override everything
        level = get_alert_level(
            in_disturbance_cone=True,
            in_hurricane_cone=True,
            has_hurricane_watch=True,
            has_hurricane_warning=True,
            has_tropical_storm_watch=True,
            has_tropical_storm_warning=True,
            has_evacuation_order=True,
        )
        assert level == AlertLevel.HURRICANE_WARNING

        # Tropical storm warning should override watch and threat
        level = get_alert_level(
            in_disturbance_cone=True,
            in_hurricane_cone=True,
            has_hurricane_watch=True,
            has_hurricane_warning=False,
            has_tropical_storm_watch=True,
            has_tropical_storm_warning=True,
            has_evacuation_order=False,
        )
        assert level == AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION


class TestGetAlertInfo:
    """Test get_alert_info function."""

    def test_all_clear_info(self) -> None:
        """Test all clear alert info."""
        info = get_alert_info(AlertLevel.ALL_CLEAR, "Miami")

        assert info.level == AlertLevel.ALL_CLEAR
        assert "Miami" in info.guidance
        assert "No active weather disturbances" in info.guidance

    def test_tropical_storm_threat_info(self) -> None:
        """Test tropical storm threat alert info."""
        info = get_alert_info(AlertLevel.TROPICAL_STORM_THREAT, "Miami")

        assert info.level == AlertLevel.TROPICAL_STORM_THREAT
        assert "Miami" in info.guidance
        assert "5–7 days" in info.guidance

    def test_tropical_storm_watch_info(self) -> None:
        """Test tropical storm watch alert info."""
        info = get_alert_info(AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT, "Miami")

        assert info.level == AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT
        assert "Miami" in info.guidance
        assert "3–5 days" in info.guidance

    def test_tropical_storm_warning_info(self) -> None:
        """Test tropical storm warning alert info."""
        info = get_alert_info(AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION, "Miami")

        assert info.level == AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION
        assert "Miami" in info.guidance
        assert "36h" in info.guidance

    def test_hurricane_warning_info(self) -> None:
        """Test hurricane warning alert info."""
        info = get_alert_info(AlertLevel.HURRICANE_WARNING, "Miami")

        assert info.level == AlertLevel.HURRICANE_WARNING
        assert "Miami" in info.guidance
        assert "36h" in info.guidance

    def test_default_location(self) -> None:
        """Test default location name."""
        info = get_alert_info(AlertLevel.ALL_CLEAR)

        assert "your location" in info.guidance


class TestFormatAlertMessage:
    """Test format_alert_message function."""

    def test_all_clear_message(self) -> None:
        """Test all clear message formatting."""
        title, message = format_alert_message(
            AlertLevel.ALL_CLEAR,
            [],
            "Miami"
        )

        assert "ALL CLEAR" in title
        assert "your location" in message  # Uses default location name
        assert "No active weather disturbances" in message

    def test_storm_message_with_details(self) -> None:
        """Test storm message with details."""
        title, message = format_alert_message(
            AlertLevel.TROPICAL_STORM_THREAT,
            ["Hurricane Ian"],
            "Miami",
            ["Category 3 Hurricane", "Winds: 120 mph"]
        )

        assert "TROPICAL STORM THREAT" in title
        assert "your location" in message  # Uses default location name
        # When storm_details are provided, storm names are not included in message
        assert "STORM DETAILS" in message
        assert "Category 3 Hurricane" in message
        assert "Winds: 120 mph" in message

    def test_storm_message_without_details(self) -> None:
        """Test storm message without details."""
        title, message = format_alert_message(
            AlertLevel.TROPICAL_STORM_THREAT,
            ["Hurricane Ian"],
            "Miami"
        )

        assert "TROPICAL STORM THREAT" in title
        assert "your location" in message  # Uses default location name
        assert "Hurricane Ian" in message
        assert "Affecting System(s): Hurricane Ian" in message

    def test_storm_message_no_storm_names(self) -> None:
        """Test storm message with no storm names."""
        title, message = format_alert_message(
            AlertLevel.TROPICAL_STORM_THREAT,
            [],
            "Miami"
        )

        assert "TROPICAL STORM THREAT" in title
        assert "your location" in message  # Uses default location name
        assert "Affecting System(s): Active System" in message

    def test_multiple_storms(self) -> None:
        """Test message with multiple storms."""
        _title, message = format_alert_message(
            AlertLevel.TROPICAL_STORM_THREAT,
            ["Hurricane Ian", "Tropical Storm Jose"],
            "Miami"
        )

        assert "Hurricane Ian" in message
        assert "Tropical Storm Jose" in message
        assert "Hurricane Ian, Tropical Storm Jose" in message
