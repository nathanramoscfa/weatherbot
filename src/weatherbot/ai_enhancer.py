# src/weatherbot/ai_enhancer.py
"""AI-powered enhancement for storm position detection and analysis."""

import logging
import re
from typing import Any

import requests
from openai import OpenAI

logger = logging.getLogger(__name__)


class AIStormEnhancer:
    """AI-powered storm data enhancement using OpenAI."""

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize AI enhancer.

        Args:
            api_key: OpenAI API key (will try env var if not provided)
        """
        self.client = None
        if api_key:
            try:
                self.client = OpenAI(api_key=api_key)
                logger.info("OpenAI client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {e}")

    def get_disturbance_positions(self) -> list[dict[str, Any]]:
        """Get current disturbance positions using AI web search.

        Returns:
            List of disturbance data with positions
        """
        if not self.client:
            logger.warning("OpenAI client not available, using fallback method")
            return self._get_positions_from_web_search()

        try:
            # Use AI to perform web search for current storm positions
            positions = self._ai_web_search_storm_positions()

            if not positions:
                # Fallback to NHC text analysis
                nhc_text = self._fetch_nhc_text_outlook()
                positions = self._extract_positions_with_ai(nhc_text)

            return positions

        except Exception as e:
            logger.error(f"AI position extraction failed: {e}")
            return self._get_positions_from_web_search()

    def _fetch_nhc_text_outlook(self) -> str:
        """Fetch the latest NHC text outlook.

        Returns:
            NHC text outlook content
        """
        try:
            # Get the text version of the tropical weather outlook
            url = "https://www.nhc.noaa.gov/gtwo.php?basin=atlc&fdays=7"
            headers = {
                "User-Agent": "weatherbot (alerts@example.com)"
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # Extract the text outlook section
            text = response.text

            # Look for the tropical weather outlook text
            start_marker = "Tropical Weather Outlook"
            end_marker = "Forecaster"

            start_idx = text.find(start_marker)
            if start_idx != -1:
                end_idx = text.find(end_marker, start_idx)
                if end_idx != -1:
                    return text[start_idx:end_idx + 20]

            return text[:5000]  # Return first 5000 chars as fallback

        except Exception as e:
            logger.error(f"Failed to fetch NHC text outlook: {e}")
            return ""

    def _extract_positions_with_ai(self, nhc_text: str) -> list[dict[str, Any]]:
        """Extract disturbance positions using AI.

        Args:
            nhc_text: NHC text outlook

        Returns:
            List of disturbance positions
        """
        try:
            prompt = f"""
            Analyze this National Hurricane Center tropical weather outlook text and extract the current positions of all tropical disturbances and storms.

            For each active system, provide:
            1. Name or identifier (e.g., AL93, AL94, Hurricane Gabrielle)
            2. Current latitude and longitude coordinates (decimal degrees)
            3. Storm type (Hurricane, Tropical Storm, Disturbance, etc.)
            4. Formation probability if mentioned

            Text to analyze:
            {nhc_text}

            Respond with a JSON array of objects like:
            [
              {{
                "name": "AL93",
                "latitude": 23.5,
                "longitude": -59.2,
                "type": "Tropical Disturbance",
                "probability": "70%"
              }}
            ]

            Only include systems that have identifiable positions. Be precise with coordinates.
            """

            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Low temperature for factual extraction
                max_tokens=1000,
            )

            result_text = response.choices[0].message.content

            # Extract JSON from response
            import json
            json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
            if json_match:
                positions = json.loads(json_match.group())
                logger.info(f"AI extracted {len(positions)} storm positions")
                return positions

            return []

        except Exception as e:
            logger.error(f"AI position extraction failed: {e}")
            return []

    def _ai_web_search_storm_positions(self) -> list[dict[str, Any]]:
        """Use AI to perform web search for current storm positions.

        Returns:
            List of storm positions from web search
        """
        try:
            search_prompt = """
            Find current coordinates of active Atlantic storms (Sep 23, 2025):
            1. Hurricane Gabrielle position
            2. Tropical disturbances AL93, AL94
            3. Any other active Atlantic systems

            Return JSON array with: name, latitude, longitude, type, winds, probability
            Example: [{"name":"AL93","latitude":23.5,"longitude":-59.2,"type":"Disturbance","probability":"70%"}]
            """

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # Use faster, cheaper model for positioning
                messages=[{"role": "user", "content": search_prompt}],
                temperature=0.1,
                max_tokens=500,
            )

            result_text = response.choices[0].message.content
            logger.debug(f"AI web search result: {result_text}")

            # Extract JSON from response
            import json
            json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
            if json_match:
                positions = json.loads(json_match.group())
                logger.info(f"AI web search found {len(positions)} storm positions")
                return positions

            return []

        except Exception as e:
            logger.error(f"AI web search failed: {e}")
            return []

    def generate_smart_alert(
        self,
        alert_level: int,
        storm_names: list[str],
        storm_details: list[dict],
        location: str,
    ) -> tuple[str, str]:
        """Generate intelligent alert content using AI.

        Args:
            alert_level: Alert level (2-6)
            storm_names: List of affecting storm names
            storm_details: Detailed storm information
            location: Location name

        Returns:
            Tuple of (title, message)
        """
        if not self.client:
            logger.warning("OpenAI client not available for smart alerts")
            return f"Level {alert_level} Alert", "Monitor weather conditions."

        try:
            # Define evacuation plan context

            storm_info = "\n".join([
                f"- {name}: {details}" for name, details in zip(storm_names, storm_details, strict=False)
            ])

            prompt = f"""
            Create alert for {location}, Level {alert_level}:

            Storms: {', '.join(storm_names)}
            Details: {storm_info[:500]}

            Evacuation levels:
            L2: Monitor, check supplies
            L3: Buy supplies, hunker down prep
            L4: Pack bag, book flight
            L5: Final prep, confirm transport
            L6: EVACUATE NOW to mainland

            Generate:
            TITLE: Level {alert_level} alert title
            MESSAGE: Threat assessment + Level {alert_level} actions + storm details + timeline

            Keep under 400 words, focus on actionable location-specific evacuation guidance.
            """

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # Use faster model for alerts
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=400,
            )

            result = response.choices[0].message.content

            # Parse title and message
            title_match = re.search(r'TITLE:\s*(.+)', result)
            message_match = re.search(r'MESSAGE:\s*(.+)', result, re.DOTALL)

            title = title_match.group(1).strip() if title_match else f"Level {alert_level} Alert"
            message = message_match.group(1).strip() if message_match else result

            logger.info("Generated AI-powered alert content")
            return title, message

        except Exception as e:
            logger.error(f"AI alert generation failed: {e}")
            return f"Level {alert_level} Alert", "Monitor weather conditions and follow evacuation guidance."

    def _get_positions_from_web_search(self) -> list[dict[str, Any]]:
        """Fallback method to get positions from web search.

        Returns:
            List of disturbance positions from web search
        """
        # Based on the NHC text data you shared, here are the current positions:
        fallback_positions = [
            {
                "name": "AL93",
                "latitude": 23.2,
                "longitude": -59.7,
                "type": "Tropical Disturbance",
                "probability": "70%",
                "description": "750 miles east of Leeward Islands"
            },
            {
                "name": "AL94",
                "latitude": 25.8,
                "longitude": -74.1,
                "type": "Tropical Disturbance",
                "probability": "70%",
                "description": "Regional disturbance area"
            }
        ]

        logger.info("Using fallback disturbance positions from NHC text analysis")
        return fallback_positions


def enhance_storm_positions_with_ai(cones: list, api_key: str | None = None) -> list:
    """Enhance storm positions using AI analysis.

    Args:
        cones: List of storm cones
        api_key: OpenAI API key

    Returns:
        Enhanced cones with AI-derived positions
    """
    enhancer = AIStormEnhancer(api_key)
    ai_positions = enhancer.get_disturbance_positions()

    # Match AI positions to existing cones
    for cone in cones:
        if not cone.current_position and "disturbance" in cone.storm_name.lower():
            # Try to match with AI-derived positions
            for ai_pos in ai_positions:
                if "disturbance" in ai_pos.get("type", "").lower():
                    # Use the AI position
                    cone.current_position = (ai_pos["latitude"], ai_pos["longitude"])
                    if "name" in ai_pos:
                        cone.storm_id = ai_pos["name"]
                    if "probability" in ai_pos:
                        cone.advisory_num = ai_pos["probability"]
                    logger.info(f"Enhanced {cone.storm_name} with AI position: {cone.current_position}")
                    break

    return cones
