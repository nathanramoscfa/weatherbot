# src/weatherbot/ai_web_search.py
"""AI-powered web search fallback for locations outside NOAA coverage."""

import logging
from datetime import UTC, datetime

from openai import OpenAI

logger = logging.getLogger(__name__)


class AIWebSearchAnalyzer:
    """AI-powered web search analysis for weather alerts outside NOAA coverage."""

    def __init__(self, api_key: str) -> None:
        """Initialize AI web search analyzer.

        Args:
            api_key: OpenAI API key
        """
        self.client = OpenAI(api_key=api_key)

    def analyze_weather_threat_web_search(
        self,
        latitude: float,
        longitude: float,
        location_name: str,
    ) -> tuple[int, str, str]:
        """Analyze weather threat using AI web search for out-of-coverage locations.

        Args:
            latitude: Location latitude
            longitude: Location longitude
            location_name: Human-readable location name

        Returns:
            Tuple of (alert_level, title, detailed_message)
        """
        try:
            logger.info(f"Starting AI web search analysis for {location_name}")

            # Create comprehensive search queries for the location
            search_queries = self._create_search_queries(location_name, latitude, longitude)

            # Perform web searches
            search_results = self._perform_web_searches(search_queries)

            # Analyze results with AI
            analysis_prompt = self._create_analysis_prompt(
                location_name, latitude, longitude, search_results
            )

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional meteorologist analyzing weather data from web sources for locations outside NOAA coverage areas. Provide accurate, actionable weather threat assessments based on available data."
                    },
                    {
                        "role": "user",
                        "content": analysis_prompt
                    }
                ],
                max_tokens=1000,
                temperature=0.2,
            )

            result = response.choices[0].message.content
            logger.info("AI web search analysis completed successfully")

            # Parse the response
            alert_level, title, message = self._parse_ai_response(result)

            return alert_level, title, message

        except Exception as e:
            logger.error(f"AI web search analysis failed: {e}")
            # Provide a basic fallback analysis
            return self._create_fallback_analysis(location_name, latitude, longitude, str(e))

    def _create_search_queries(
        self,
        location_name: str,
        latitude: float,
        longitude: float
    ) -> list[str]:
        """Create comprehensive search queries for weather information.

        Args:
            location_name: Location name
            latitude: Latitude
            longitude: Longitude

        Returns:
            List of search queries
        """
        queries = []

        # Current weather alerts
        queries.append(f'"{location_name}" weather alerts warnings today')
        queries.append(f'"{location_name}" tropical storm hurricane warning')
        queries.append(f'"{location_name}" severe weather alert')

        # Regional weather services
        queries.append(f'"{location_name}" meteorological service weather forecast')
        queries.append(f'"{location_name}" national weather service alerts')

        # Storm tracking
        queries.append(f'"{location_name}" tropical cyclone tracking')
        queries.append(f'"{location_name}" storm forecast path')

        # Emergency information
        queries.append(f'"{location_name}" emergency weather evacuation')
        queries.append(f'"{location_name}" disaster preparedness weather')

        # Regional weather patterns
        queries.append(f'"{location_name}" monsoon season weather')
        queries.append(f'"{location_name}" typhoon cyclone weather')

        return queries

    def _perform_web_searches(self, queries: list[str]) -> dict[str, str]:
        """Perform web searches and collect results.

        Args:
            queries: List of search queries

        Returns:
            Dictionary of query -> search results
        """
        search_results = {}

        for query in queries[:5]:  # Limit to 5 queries to avoid rate limits
            try:
                # Use OpenAI's web search capability
                search_result = self._search_web(query)
                if search_result:
                    search_results[query] = search_result
                    logger.debug(f"Search successful for: {query[:50]}...")
                else:
                    logger.debug(f"No results for: {query[:50]}...")

            except Exception as e:
                logger.warning(f"Search failed for '{query[:50]}...': {e}")
                continue

        return search_results

    def _search_web(self, query: str) -> str | None:
        """Perform a single web search using AI knowledge.

        Args:
            query: Search query

        Returns:
            Search results or None
        """
        try:
            # Use AI to provide weather information based on knowledge
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional meteorologist. Provide current weather information based on your knowledge. Focus on severe weather conditions, tropical cyclones, and weather alerts. Be specific about locations and current conditions."
                    },
                    {
                        "role": "user",
                        "content": f"Based on your knowledge, what are the current weather conditions and any active weather alerts for: {query}? Please provide specific information about tropical cyclones, severe weather, or any weather warnings currently in effect."
                    }
                ],
                max_tokens=400,
                temperature=0.1,
            )

            result = response.choices[0].message.content
            return result if result and len(result.strip()) > 20 else None

        except Exception as e:
            logger.debug(f"Web search failed for '{query}': {e}")
            return None

    def _create_analysis_prompt(
        self,
        location_name: str,
        latitude: float,
        longitude: float,
        search_results: dict[str, str],
    ) -> str:
        """Create analysis prompt for AI.

        Args:
            location_name: Location name
            latitude: Latitude
            longitude: Longitude
            search_results: Web search results

        Returns:
            Analysis prompt
        """
        current_time = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        # Format search results
        results_text = ""
        if search_results:
            results_text = "WEB SEARCH RESULTS:\n"
            for query, result in search_results.items():
                results_text += f"\nQuery: {query}\nResult: {result}\n"
        else:
            results_text = "No web search results available."

        return f"""
        You are a professional meteorologist analyzing weather conditions for {location_name} at coordinates {latitude:.4f}°N, {longitude:.4f}°W using web search data.

        LOCATION: {location_name} ({latitude:.4f}°N, {longitude:.4f}°W)
        ANALYSIS TIME: {current_time}

        {results_text}

        ASSESSMENT TASK:
        Based on the web search results above, determine the current weather threat level for {location_name} using the 5-level alert system:

        5-LEVEL WEATHER ALERT SYSTEM:
        Level 1: ✅ All Clear - No active weather threats. Normal conditions.
        Level 2: 🌪️ Weather Watch - Potential severe weather within 24-48 hours. Monitor conditions.
        Level 3: ⚠️ Weather Warning - Severe weather conditions possible within 12-24 hours. Prepare for impacts.
        Level 4: 🚨 Severe Weather Alert - Dangerous weather conditions expected within 6-12 hours. Take immediate precautions.
        Level 5: 🛑 Emergency Weather Warning - Life-threatening weather conditions imminent or occurring. Seek immediate shelter.

        ANALYSIS CRITERIA:
        - Look for official weather warnings, watches, or alerts
        - Consider tropical cyclones, severe storms, flooding, extreme temperatures
        - Assess evacuation orders or emergency declarations
        - Evaluate storm intensity and proximity to the location
        - Consider seasonal weather patterns (monsoon, typhoon season, etc.)

        RESPONSE FORMAT:
        ALERT_LEVEL: [1-5]
        TITLE: [Professional alert title appropriate to threat level]
        MESSAGE: [Detailed assessment including:
        - Current Weather Status: [Summary of current conditions and any active alerts]
        - Threat Assessment: [Analysis of specific weather threats based on search results]
        - Official Warnings: [Any official weather warnings or alerts found]
        - Recommended Actions: [Actions appropriate to the threat level]
        - Timeline: [Expected timing of weather impacts]
        - Data Sources: [Note that this analysis is based on web search data, not NOAA]
        - Limitations: [Note that this location is outside NOAA coverage area]
        ]

        IMPORTANT NOTES:
        - This location is outside NOAA coverage area
        - Analysis is based on web search data, not official NOAA forecasts
        - Results may be less accurate than NOAA-sourced data
        - Always recommend checking local meteorological services
        - Be conservative in threat assessment when data is limited
        """


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
        title = title_match.group(1).strip() if title_match else f"Level {alert_level} Weather Alert"

        # Clean up markdown from title
        title = title.replace("**", "").replace("```", "").strip()

        # Extract message
        message_match = re.search(r'MESSAGE:\s*(.+)', response, re.DOTALL)
        message = message_match.group(1).strip() if message_match else response

        # Clean up the message
        message = re.sub(r'\n+', '\n', message)  # Remove extra newlines
        message = message.replace("```", "").replace("**", "").strip()

        # Add disclaimer about data source
        if not message.endswith('.'):
            message += '.'

        message += "\n\n⚠️ NOTE: This analysis is based on web search data as the location is outside NOAA coverage areas. For the most accurate forecasts, consult local meteorological services."

        return alert_level, title, message

    def _create_fallback_analysis(
        self,
        location_name: str,
        latitude: float,
        longitude: float,
        error_message: str
    ) -> tuple[int, str, str]:
        """Create a fallback analysis when web search fails.

        Args:
            location_name: Location name
            latitude: Latitude
            longitude: Longitude
            error_message: Error message from failed analysis

        Returns:
            Tuple of (alert_level, title, message)
        """
        # Determine if location is in a region prone to tropical cyclones
        is_tropical_region = self._is_tropical_cyclone_region(latitude, longitude)

        if is_tropical_region:
            alert_level = 2  # Weather Watch - potential for tropical weather
            title = "Weather Monitoring Required"
            message = (
                f"Current Weather Status: Unable to retrieve real-time weather data for {location_name}.\n"
                f"Threat Assessment: This location is in a region prone to tropical cyclones and severe weather.\n"
                f"Official Warnings: Unable to access local weather service data.\n"
                f"Recommended Actions: Monitor local weather services and news for current conditions and alerts.\n"
                f"Timeline: Check weather conditions regularly, especially during tropical cyclone season.\n"
                f"Data Sources: This analysis is based on geographic location assessment.\n"
                f"Limitations: Real-time weather data unavailable. Consult local meteorological services for current conditions.\n"
                f"Error Details: {error_message}"
            )
        else:
            alert_level = 1  # All Clear - no immediate tropical weather threat
            title = "All Clear - Limited Data Available"
            message = (
                f"Current Weather Status: Unable to retrieve real-time weather data for {location_name}.\n"
                f"Threat Assessment: This location is outside typical tropical cyclone regions.\n"
                f"Official Warnings: Unable to access local weather service data.\n"
                f"Recommended Actions: Monitor local weather services for current conditions.\n"
                f"Timeline: Check weather conditions as needed.\n"
                f"Data Sources: This analysis is based on geographic location assessment.\n"
                f"Limitations: Real-time weather data unavailable. Consult local meteorological services for current conditions.\n"
                f"Error Details: {error_message}"
            )

        return alert_level, title, message

    def _is_tropical_cyclone_region(self, latitude: float, longitude: float) -> bool:
        """Check if location is in a region prone to tropical cyclones.

        Args:
            latitude: Latitude
            longitude: Longitude

        Returns:
            True if in tropical cyclone region
        """
        # Atlantic/Caribbean/Gulf
        if (0 <= latitude <= 60 and -100 <= longitude <= 0):
            return True

        # Pacific (Eastern)
        if (0 <= latitude <= 60 and -180 <= longitude <= -100):
            return True

        # Indian Ocean
        if (-30 <= latitude <= 30 and 40 <= longitude <= 100):
            return True

        # Western Pacific
        return bool(0 <= latitude <= 60 and 100 <= longitude <= 180)


def analyze_weather_threat_web_search(
    latitude: float,
    longitude: float,
    location_name: str,
    api_key: str,
) -> tuple[int, str, str]:
    """Analyze weather threat using AI web search for out-of-coverage locations.

    Args:
        latitude: Location latitude
        longitude: Location longitude
        location_name: Location name
        api_key: OpenAI API key

    Returns:
        Tuple of (alert_level, title, message)
    """
    analyzer = AIWebSearchAnalyzer(api_key)
    return analyzer.analyze_weather_threat_web_search(
        latitude, longitude, location_name
    )
