# src/weatherbot/alert_levels.py
"""Alert level definitions and evacuation guidance."""

from enum import Enum


class AlertLevel(Enum):
    """5-Level Storm Alert System with evacuation guidance."""

    ALL_CLEAR = 1
    TROPICAL_STORM_THREAT = 2
    TROPICAL_STORM_WATCH_HURRICANE_THREAT = 3
    TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION = 4
    HURRICANE_WARNING = 5


class AlertInfo:
    """Alert information and guidance."""

    def __init__(
        self,
        level: AlertLevel,
        icon: str,
        color: str,
        sound_pattern: str,
        title_prefix: str,
        guidance: str,
    ) -> None:
        """Initialize alert info.

        Args:
            level: Alert level
            icon: Alert icon emoji
            color: Alert color (hex)
            sound_pattern: Sound pattern description
            title_prefix: Title prefix for alerts
            guidance: Evacuation guidance text
        """
        self.level = level
        self.icon = icon
        self.color = color
        self.sound_pattern = sound_pattern
        self.title_prefix = title_prefix
        self.guidance = guidance


# Alert level definitions
ALERT_DEFINITIONS: dict[AlertLevel, AlertInfo] = {
    AlertLevel.ALL_CLEAR: AlertInfo(
        level=AlertLevel.ALL_CLEAR,
        icon="✅",
        color="#4CAF50",  # Green
        sound_pattern="none",
        title_prefix="ALL CLEAR",
        guidance="No active disturbances threatening South Florida. Normal activities. No prep needed.",
    ),

    AlertLevel.TROPICAL_STORM_THREAT: AlertInfo(
        level=AlertLevel.TROPICAL_STORM_THREAT,
        icon="🌪️",
        color="#FF9800",  # Orange
        sound_pattern="gentle",
        title_prefix="TROPICAL STORM THREAT",
        guidance=(
            "Disturbance or depression in the Atlantic/Caribbean with potential to impact South Florida within 5–7 days.\n\n"
            "ACTION:\n"
            "• Monitor forecasts daily\n"
            "• Review evacuation plan, supplies, and travel options\n"
            "• No immediate action required"
        ),
    ),

    AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT: AlertInfo(
        level=AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT,
        icon="🛑",
        color="#FF5722",  # Deep Orange
        sound_pattern="moderate",
        title_prefix="TROPICAL STORM WATCH OR HURRICANE THREAT",
        guidance=(
            "Tropical Storm Watch (winds possible within 48h) OR Hurricane shows potential Florida trajectory within 3–5 days.\n\n"
            "ACTION:\n"
            "• Stock up on food, water, fuel, batteries\n"
            "• Pack go-bag & important documents\n"
            "• Book flight or set exit plan (even if refundable)\n"
            "• Check building notices"
        ),
    ),

    AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION: AlertInfo(
        level=AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION,
        icon="🚨",
        color="#F44336",  # Red
        sound_pattern="urgent",
        title_prefix="TROPICAL STORM WARNING OR HURRICANE WATCH OR EVACUATION ORDER",
        guidance=(
            "Tropical Storm Warning (winds expected within 36h with surge risk) OR Hurricane Watch (possible hurricane within 48h) OR Local evacuation order issued.\n\n"
            "ACTION:\n"
            "• Evacuate vulnerable areas immediately\n"
            "• Use available transportation to reach safe locations\n"
            "• Assume access routes may soon be compromised"
        ),
    ),

    AlertLevel.HURRICANE_WARNING: AlertInfo(
        level=AlertLevel.HURRICANE_WARNING,
        icon="🌀",
        color="#B71C1C",  # Very Dark Red
        sound_pattern="emergency",
        title_prefix="HURRICANE WARNING",
        guidance=(
            "Hurricane conditions expected within 36h.\n\n"
            "ACTION (if not already evacuated):\n"
            "• Take shelter in safest interior room away from windows\n"
            "• Expect power, water, and communication outages\n"
            "• Prepare for possible flooding"
        ),
    ),
}


def get_alert_level(
    in_disturbance_cone: bool,
    in_hurricane_cone: bool,
    has_hurricane_watch: bool,
    has_hurricane_warning: bool,
    has_tropical_storm_watch: bool = False,
    has_tropical_storm_warning: bool = False,
    has_evacuation_order: bool = False,
    storm_type: str = "unknown",
    days_until_impact: int = 7,
) -> AlertLevel:
    """Determine alert level based on current conditions using 5-level system.

    Args:
        in_disturbance_cone: Location is in a disturbance development area
        in_hurricane_cone: Location is in a hurricane forecast cone
        has_hurricane_watch: Hurricane watch is in effect
        has_hurricane_warning: Hurricane warning is in effect
        has_tropical_storm_watch: Tropical storm watch is in effect
        has_tropical_storm_warning: Tropical storm warning is in effect
        has_evacuation_order: Evacuation order is in effect
        storm_type: Type of storm (hurricane, tropical storm, disturbance)
        days_until_impact: Days until potential impact

    Returns:
        Appropriate alert level (1-5)
    """
    # Level 5: Hurricane Warning (highest priority)
    if has_hurricane_warning:
        return AlertLevel.HURRICANE_WARNING

    # Level 4: Tropical Storm Warning OR Hurricane Watch OR Evacuation Order
    if (has_tropical_storm_warning or has_hurricane_watch or
        has_evacuation_order):
        return AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION

    # Level 3: Tropical Storm Watch OR Hurricane threat within 3-5 days
    if (has_tropical_storm_watch or
        (in_hurricane_cone and days_until_impact <= 5) or
        ("hurricane" in storm_type.lower() and days_until_impact <= 5)):
        return AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT

    # Level 2: Disturbance/Depression with potential impact within 5-7 days
    if (in_disturbance_cone or
        ("disturbance" in storm_type.lower() and days_until_impact <= 7) or
        ("depression" in storm_type.lower() and days_until_impact <= 7)):
        return AlertLevel.TROPICAL_STORM_THREAT

    # Level 1: All clear
    return AlertLevel.ALL_CLEAR


def get_alert_info(level: AlertLevel, location_name: str = "your location") -> AlertInfo:
    """Get alert information for a given level.

    Args:
        level: Alert level
        location_name: Name of the location for personalized guidance

    Returns:
        Alert information
    """
    base_info = ALERT_DEFINITIONS[level]

    # Create location-specific guidance
    if level == AlertLevel.ALL_CLEAR:
        guidance = f"No active weather disturbances threatening {location_name}. Normal activities. No immediate preparation needed."
    elif level == AlertLevel.TROPICAL_STORM_THREAT:
        guidance = (
            f"Weather disturbance with potential to impact {location_name} within 5–7 days.\n\n"
            "ACTION:\n"
            "• Monitor local weather forecasts daily\n"
            "• Review evacuation plan and emergency supplies\n"
            "• Check local emergency services for updates\n"
            "• No immediate action required"
        )
    elif level == AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT:
        guidance = (
            f"Tropical Storm Watch (winds possible within 48h) OR Hurricane shows potential trajectory toward {location_name} within 3–5 days.\n\n"
            "ACTION:\n"
            "• Stock up on food, water, fuel, batteries\n"
            "• Pack emergency go-bag & important documents\n"
            "• Plan evacuation route and transportation\n"
            "• Check local building notices and emergency services"
        )
    elif level == AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION:
        guidance = (
            f"Tropical Storm Warning (winds expected within 36h) OR Hurricane Watch (possible hurricane within 48h) OR Local evacuation order for {location_name}.\n\n"
            "ACTION:\n"
            "• Evacuate vulnerable areas immediately\n"
            "• Use available transportation to reach safe locations\n"
            "• Follow local emergency services instructions\n"
            "• Assume access routes may soon be compromised"
        )
    elif level == AlertLevel.HURRICANE_WARNING:
        guidance = (
            f"Hurricane conditions expected near {location_name} within 36h.\n\n"
            "ACTION (if not already evacuated):\n"
            "• Take shelter in safest interior room away from windows\n"
            "• Expect power, water, and communication outages\n"
            "• Prepare for possible flooding\n"
            "• Follow local emergency services instructions"
        )
    else:
        guidance = base_info.guidance

    # Create new AlertInfo with location-specific guidance
    return AlertInfo(
        level=base_info.level,
        icon=base_info.icon,
        color=base_info.color,
        sound_pattern=base_info.sound_pattern,
        title_prefix=base_info.title_prefix,
        guidance=guidance,
    )


def format_alert_message(
    level: AlertLevel,
    storm_names: list,
    location_name: str = "your location",
    storm_details: list | None = None,
) -> tuple[str, str]:
    """Format alert title and message for a given level.

    Args:
        level: Alert level
        storm_names: List of affecting storm names
        location_name: Name of the location
        storm_details: List of storm detail strings

    Returns:
        Tuple of (title, message)
    """
    alert_info = get_alert_info(level)

    if level == AlertLevel.ALL_CLEAR:
        title = f"{alert_info.icon} {alert_info.title_prefix}"
        message = alert_info.guidance
    else:
        storms_text = ", ".join(storm_names) if storm_names else "Active System"
        title = f"{alert_info.icon} {alert_info.title_prefix}"

        # Build detailed message
        message_parts = [alert_info.guidance]

        if storm_details:
            message_parts.append("\n--- STORM DETAILS ---")
            for detail in storm_details:
                message_parts.append(detail)
        else:
            message_parts.append(f"\nAffecting System(s): {storms_text}")

        message = "\n".join(message_parts)

    return title, message
