# src/weatherbot/ai_map_analyzer.py
"""AI-powered analysis of official NOAA hurricane maps."""

import logging

import requests
from openai import OpenAI

logger = logging.getLogger(__name__)

# NOAA map URLs for different basins
NOAA_MAP_URLS = {
    "atlantic": {
        "7day": "https://www.nhc.noaa.gov/xgtwo/two_atl_7d0.png",
        "2day": "https://www.nhc.noaa.gov/xgtwo/two_atl_2d0.png",
        "text": "https://www.nhc.noaa.gov/gtwo.php?basin=atlc&fdays=7"
    },
    "eastern_pacific": {
        "7day": "https://www.nhc.noaa.gov/xgtwo/two_epac_7d0.png",
        "2day": "https://www.nhc.noaa.gov/xgtwo/two_epac_2d0.png",
        "text": "https://www.nhc.noaa.gov/gtwo.php?basin=epac&fdays=7"
    },
    "central_pacific": {
        "7day": "https://www.nhc.noaa.gov/xgtwo/two_cpac_7d0.png",
        "2day": "https://www.nhc.noaa.gov/xgtwo/two_cpac_2d0.png",
        "text": "https://www.nhc.noaa.gov/gtwo.php?basin=cpac&fdays=7"
    }
}


class AIMapAnalyzer:
    """AI-powered analysis of NOAA hurricane maps."""

    def __init__(self, api_key: str) -> None:
        """Initialize AI map analyzer.

        Args:
            api_key: OpenAI API key
        """
        self.client = OpenAI(api_key=api_key)

    def analyze_threat_for_location(
        self,
        latitude: float,
        longitude: float,
        location_name: str,
        basin: str = "atlantic",
        geometric_results: dict | None = None,
    ) -> tuple[int, str, str]:
        """Analyze hurricane threat for a specific location using hybrid AI.

        Args:
            latitude: Location latitude
            longitude: Location longitude
            location_name: Human-readable location name
            basin: NHC basin ('atlantic', 'eastern_pacific', 'central_pacific')
            geometric_results: Pre-computed geometric analysis results

        Returns:
            Tuple of (alert_level, title, detailed_message)
        """
        try:
            # Get basin-specific URLs
            basin_urls = NOAA_MAP_URLS.get(basin, NOAA_MAP_URLS["atlantic"])
            map_url = basin_urls["7day"]

            # Get current NHC text outlook for context
            nhc_context = self._get_nhc_text_context(basin)

            # Prepare geometric analysis context if available
            geometric_context = ""
            if geometric_results:
                geometric_context = self._format_geometric_context(geometric_results)

            # Get basin display name
            basin_names = {
                "atlantic": "Atlantic",
                "eastern_pacific": "Eastern Pacific",
                "central_pacific": "Central Pacific"
            }
            basin_display = basin_names.get(basin, "Atlantic")

            # Analyze the map with AI
            analysis_prompt = f"""
            You are a professional meteorologist analyzing the official National Hurricane Center 7-day {basin_display} tropical weather outlook map for {location_name} at coordinates {latitude:.4f}°N, {longitude:.4f}°W.

            LOCATION CONTEXT:
            - {location_name} at coordinates {latitude:.4f}°N, {longitude:.4f}°W
            - Located in the {basin_display} Basin
            - Assess local geography for evacuation requirements (island, coastal, inland)
            - Consider nearest safe evacuation destinations based on location

            CURRENT NHC OUTLOOK CONTEXT:
            {nhc_context[:1000]}

            {geometric_context}

            ⚠️⚠️⚠️ CRITICAL PRIORITY ORDER:
            1. NWS ALERTS TAKE ABSOLUTE PRECEDENCE - Official watches/warnings override everything
            2. If NO NWS alerts, then geometric analysis applies - if it shows "Location in any forecast cone: False", you MUST assign Level 1
            3. NEVER override official NWS alerts with geometric analysis ⚠️⚠️⚠️

            5-LEVEL STORM ALERT SYSTEM (CRITICAL - ASSESS STORM INTENSITY CAREFULLY):
            Level 1: ✅ All Clear - No active disturbances threatening the area. Normal activities.
            Level 2: 🌪️ Tropical Storm Threat - TROPICAL WAVE, DEPRESSION, or DISTURBANCE with potential to impact within 5–7 days. Monitor forecasts daily.
            Level 3: 🛑 Tropical Storm Watch or Hurricane Threat - NAMED TROPICAL STORM Watch (winds possible within 48h) OR HURRICANE shows potential trajectory within 3–5 days. Stock up on supplies, pack go-bag.
            Level 4: 🚨 Tropical Storm Warning or Hurricane Watch or Evacuation Order - NAMED TROPICAL STORM Warning (winds expected within 36h with surge risk) OR HURRICANE Watch OR County evacuation order. EVACUATE if in danger zone.
            Level 5: 🌀 Hurricane Warning - HURRICANE conditions expected within 36h. Take shelter if not already evacuated.

            CRITICAL ASSESSMENT CRITERIA - FOLLOW GEOMETRIC ANALYSIS:
            - MANDATORY: If geometric analysis shows "In Any Cone: False" AND no threatening disturbances, you MUST assign Level 1 (All Clear)
            - NEVER override geometric cone intersection results for NAMED STORMS - they are mathematically precise
            - For NAMED STORMS: Only assign Level 2+ if geometric analysis confirms the location is actually IN a forecast cone
            - For TROPICAL WAVES/DISTURBANCES: Level 2 is appropriate if they show development potential within 5-7 days, even without traditional forecast cones
            - Being in a "development area" or "disturbance region" DOES qualify for Level 2 if it's an active tropical wave/disturbance with development potential
            - The geometric analysis uses official NOAA polygon data and is 100% accurate for cone intersection of NAMED STORMS
            - Your role is to provide detailed explanation and apply appropriate threat levels for both named storms and developing disturbances

            ⚠️ CRITICAL: If the geometric analysis shows "Location in any forecast cone: False", you MUST NOT claim the location is "within the forecast cone" in your analysis. The geometric analysis is definitive and overrides any visual interpretation of the map.

            ANALYSIS TASK:
            1. Examine the official NHC {basin_display} map image at {map_url}
            2. Identify ALL active systems and their classifications:
               - Named hurricanes (Category 1-5)
               - Named tropical storms (39+ mph winds)
               - Tropical depressions (organized circulation, <39 mph)
               - Tropical waves/disturbances (no organized circulation yet)
            3. For EACH system, determine:
               - Exact storm classification and intensity
               - Whether {location_name} ({latitude:.4f}°N, {longitude:.4f}°W) is within its cone/development area
               - Distance from {location_name}
               - Movement direction and speed
               - Any official watches/warnings in effect for this location
            4. MANDATORY: Use the geometric analysis results as the PRIMARY determinant for NAMED STORMS:
               - If geometric analysis shows "In Any Cone: False" for NAMED STORMS → Level 1 for those storms
               - If geometric analysis shows "In Any Cone: True" → Apply storm-based levels:
                 * Level 2: Tropical wave/depression/disturbance in actual forecast cone OR active tropical wave with development potential
                 * Level 3: NAMED tropical storm in cone OR hurricane threat within 3-5 days
                 * Level 4: Named tropical storm WARNING OR hurricane WATCH
                 * Level 5: Hurricane WARNING
            5. For TROPICAL WAVES/DISTURBANCES: Level 2 is appropriate even without traditional forecast cones if development potential exists
            6. Your image analysis should EXPLAIN the geometric results, not contradict them

            RESPONSE FORMAT:
            ALERT_LEVEL: [1-5] - MUST match geometric analysis if it shows "In Any Cone: False" then use 1
            TITLE: [Professional alert title appropriate to threat level]
            MESSAGE: [Detailed assessment including:
            - Current Threat Status for {location_name}: [State whether location is in cone and current threat level justification]
            - Specific Storms/Disturbances Affecting the Area: [List each system with EXACT classification - Hurricane/Tropical Storm/Depression/Wave/Disturbance]
            - Storm Intensity Analysis: [For each system, specify maximum winds, pressure, and development stage]
            - Cone Analysis: [CRITICAL - Specify which systems have {location_name} in their SPECIFIC FORECAST CONE vs broad development area. Distinguish between precise forecast cones and general development regions.]
            - Official Watches/Warnings: [List any NHC watches or warnings in effect for this location]
            - Recommended Actions Based on Alert Level: [Actions specific to the assigned level]
            - Timeline and Next Steps: [Expected development timeline and monitoring guidance]
            - Evacuation Guidance: [Location-specific evacuation recommendations based on geography]
            - Storm Details (Position, Intensity, Movement): [Technical details for each system]
            ]

            CRITICAL: Be precise about storm classifications. Only use Level 3+ for named tropical storms or hurricanes.

            VISUAL MAP ANALYSIS INSTRUCTIONS:
            - Your image analysis should SUPPORT and EXPLAIN the geometric analysis results
            - If geometric analysis shows "In Any Cone: False", explain why the location appears outside cones in the image
            - If geometric analysis shows "In Any Cone: True", identify which specific cone contains the location
            - NEVER contradict the geometric analysis - it uses precise NOAA polygon data
            - Focus on providing context about storm positions, movements, and development areas for educational purposes
            - Remember: Development areas ≠ Forecast cones. Only forecast cones warrant Level 2+ alerts.

            Be precise, professional, and focus on actionable guidance for location-specific evacuation planning.

        FORMATTING REQUIREMENTS:
        - Use plain text only, no markdown formatting
        - No code blocks (```), no asterisks (*), no special formatting
        - Use simple bullet points with "- " prefix
        - End with a period, not with code formatting symbols
            """

            response = self.client.chat.completions.create(
                model="gpt-4o",  # Use current GPT-4 with vision
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": analysis_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": map_url}
                            }
                        ]
                    }
                ],
                max_tokens=800,
                temperature=0.2,
            )

            result = response.choices[0].message.content
            logger.info("AI map analysis completed successfully")

            # Parse the response
            alert_level, title, message = self._parse_ai_response(result)

            # CRITICAL: Check for NWS alerts first - they take precedence over geometric analysis
            nws_alerts = geometric_results.get("nws_alerts", []) if geometric_results else []
            has_nws_alerts = len(nws_alerts) > 0

            logger.info(f"Checking override conditions: geometric_results={geometric_results is not None}, is_in_any_cone={geometric_results.get('is_in_any_cone', False) if geometric_results else 'None'}, has_nws_alerts={has_nws_alerts}")

            if has_nws_alerts:
                # NWS alerts take precedence - do not override them
                logger.info(f"NWS alerts present - respecting official alert level {alert_level}")
            elif geometric_results and not geometric_results.get("is_in_any_cone", False):
                # Only override if NO NWS alerts and location is NOT in any cone
                if alert_level > 1:
                    logger.warning(f"AI assigned Level {alert_level} but geometric analysis shows 'In Any Cone: False' and no NWS alerts. Overriding to Level 1.")
                    alert_level = 1
                    title = "All Clear - No Active Threats"
                    message = f"Geometric analysis confirms {location_name} is not within any forecast cone. No immediate threat detected. Continue monitoring weather conditions."
                else:
                    logger.info(f"AI already assigned Level {alert_level}, no override needed")
            else:
                logger.info(f"No override needed: geometric_results={geometric_results is not None}, is_in_any_cone={geometric_results.get('is_in_any_cone', False) if geometric_results else 'None'}")

            return alert_level, title, message

        except Exception as e:
            logger.error(f"AI map analysis failed: {e}")
            return 1, "System Error", f"Unable to analyze hurricane threat: {e}"

    def _get_nhc_text_context(self, basin: str = "atlantic") -> str:
        """Get comprehensive NHC text outlook and active storm data.

        Args:
            basin: NHC basin ('atlantic', 'eastern_pacific', 'central_pacific')

        Returns:
            Combined NHC text outlook and active storm information
        """
        context_parts = []

        try:
            # Get basin-specific URL
            basin_urls = NOAA_MAP_URLS.get(basin, NOAA_MAP_URLS["atlantic"])
            url = basin_urls["text"]
            headers = {"User-Agent": "weatherbot (alerts@example.com)"}

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            text = response.text

            # Extract active systems section
            if "Active Systems:" in text:
                start = text.find("Active Systems:")
                end = text.find("Forecaster", start)
                if end != -1:
                    context_parts.append("ACTIVE SYSTEMS:\n" + text[start:end])

            # Try to get additional storm details
            try:
                # Get current storms JSON for detailed info
                storms_url = "https://www.nhc.noaa.gov/CurrentStorms.json"
                storms_response = requests.get(storms_url, headers=headers, timeout=15)
                if storms_response.status_code == 200:
                    storms_data = storms_response.json()
                    if storms_data and 'activeStorms' in storms_data:
                        storm_details = []
                        for storm in storms_data['activeStorms']:
                            if storm.get('isActive'):
                                name = storm.get('name', 'Unknown')
                                classification = storm.get('classification', 'Unknown')
                                intensity = storm.get('intensity', 'Unknown')
                                movement = storm.get('movement', 'Unknown')
                                storm_details.append(f"- {name}: {classification}, {intensity}, {movement}")

                        if storm_details:
                            context_parts.append("DETAILED STORM INFO:\n" + "\n".join(storm_details))
            except Exception as e:
                logger.debug(f"Could not fetch detailed storm data: {e}")

            if not context_parts:
                context_parts.append(text[:2000])  # Fallback

        except Exception as e:
            logger.warning(f"Failed to get NHC context for {basin} basin: {e}")
            context_parts.append("NHC context unavailable")

        return "\n\n".join(context_parts)

    def _parse_ai_response(self, response: str) -> tuple[int, str, str]:
        """Parse AI response into components.

        Args:
            response: AI response text

        Returns:
            Tuple of (alert_level, title, message)
        """
        import re

        # Extract alert level
        level_match = re.search(r'ALERT_LEVEL:\s*(\d+)', response)
        alert_level = int(level_match.group(1)) if level_match else 1

        # Extract title
        title_match = re.search(r'TITLE:\s*(.+?)(?=\n|MESSAGE:|$)', response, re.DOTALL)
        title = title_match.group(1).strip() if title_match else f"Level {alert_level} Alert"

        # Clean up markdown from title
        title = title.replace("**", "").replace("```", "").strip()

        # Extract message
        message_match = re.search(r'MESSAGE:\s*(.+)', response, re.DOTALL)
        message = message_match.group(1).strip() if message_match else response

        # Clean up the message
        message = re.sub(r'\n+', '\n', message)  # Remove extra newlines

        # Clean up any markdown artifacts
        message = message.replace("```", "").replace("**", "").strip()
        # Remove any trailing markdown artifacts
        lines = message.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line and line != "```":
                cleaned_lines.append(line)
        message = '\n'.join(cleaned_lines)
        message = message.strip()

        return alert_level, title, message

    def _format_geometric_context(self, geometric_results: dict) -> str:
        """Format geometric analysis results for AI context.

        Args:
            geometric_results: Results from enhanced cone analyzer

        Returns:
            Formatted context string
        """
        if not geometric_results:
            return ""

        context_parts = ["PRECISE GEOMETRIC ANALYSIS RESULTS:"]

        # Overall status
        alert_level = geometric_results.get("alert_level")
        if alert_level:
            context_parts.append(f"- Geometric Alert Level: {alert_level.name} (Level {alert_level.value})")

        is_in_cone = geometric_results.get("is_in_any_cone", False)
        context_parts.append(f"- Location in any forecast cone: {is_in_cone}")

        # Storm threats
        storm_threats = geometric_results.get("storm_threats", [])
        if storm_threats:
            context_parts.append(f"- Number of threatening storms: {len(storm_threats)}")
            for i, threat in enumerate(storm_threats[:3]):  # Limit to top 3
                cone = threat.cone
                distance_str = f"{threat.distance_km:.0f}km" if threat.distance_km is not None else "Unknown"
                context_parts.append(
                    f"  Storm {i+1}: {cone.storm_name} ({threat.category.value}) - "
                    f"Distance: {distance_str}, "
                    f"Confidence: {threat.confidence:.1f}"
                )

        # NWS alerts
        nws_alerts = geometric_results.get("nws_alerts", [])
        if nws_alerts:
            context_parts.append(f"- Active NWS alerts: {len(nws_alerts)}")
            for alert in nws_alerts[:2]:  # Limit to top 2
                # NWSAlert is a Pydantic model, not a dict, so use attribute access
                event = getattr(alert, 'event', 'Unknown')
                context_parts.append(f"  - {event}")

        total_storms = geometric_results.get("total_storms_analyzed", 0)
        context_parts.append(f"- Total storms analyzed: {total_storms}")

        context_parts.append("")
        context_parts.append("🚨 MANDATORY PRIORITY INSTRUCTIONS:")

        # Check for NWS alerts first
        nws_alerts = geometric_results.get("nws_alerts", [])
        if nws_alerts:
            context_parts.append("🔥 NWS ALERTS PRESENT - OFFICIAL WARNINGS TAKE ABSOLUTE PRECEDENCE!")
            context_parts.append("The National Weather Service has issued official alerts for this location.")
            context_parts.append("You MUST respect these official alerts regardless of geometric analysis.")
            context_parts.append("Do NOT override official NWS alerts with geometric analysis.")
        elif not is_in_cone:
            context_parts.append("The geometric analysis shows this location is NOT in any forecast cone.")
            context_parts.append("For ALL SYSTEMS: You MUST assign Level 1 if not in their forecast cone or development area.")
            context_parts.append("For TROPICAL WAVES/DISTURBANCES (AL94, AL95, etc.): Level 2 ONLY if the location is visually within or very close to the actual development area shown on the map.")
            context_parts.append("Development potential alone does NOT warrant Level 2 unless the location is directly within the visible development area.")
            context_parts.append("⚠️ CRITICAL: Do NOT claim the location is 'within the forecast cone' if geometric analysis shows 'In Any Cone: False'")
        else:
            context_parts.append("The geometric analysis shows this location IS in a forecast cone.")
            context_parts.append("Assign appropriate level based on the threatening storms identified above.")

        context_parts.append("")
        context_parts.append("PRIORITY ORDER: NWS Alerts > Geometric Analysis > Visual Map Analysis")
        context_parts.append("Official warnings always take precedence over mathematical calculations.")

        return "\n".join(context_parts)


def analyze_hurricane_threat_with_ai(
    latitude: float,
    longitude: float,
    location_name: str,
    api_key: str,
    basin: str = "atlantic",
    geometric_results: dict | None = None,
) -> tuple[int, str, str]:
    """Analyze hurricane threat using hybrid AI + geometric analysis.

    Args:
        latitude: Location latitude
        longitude: Location longitude
        location_name: Location name
        api_key: OpenAI API key
        basin: NHC basin ('atlantic', 'eastern_pacific', 'central_pacific')
        geometric_results: Pre-computed geometric analysis results

    Returns:
        Tuple of (alert_level, title, message)
    """
    analyzer = AIMapAnalyzer(api_key)
    return analyzer.analyze_threat_for_location(
        latitude, longitude, location_name, basin, geometric_results
    )
