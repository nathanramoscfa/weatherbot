# src/weatherbot/__init__.py
"""Weatherbot: a personal hurricane-threat monitor built on official NHC and NWS products.

Weatherbot is informational only and is never a substitute for official guidance.
"""

from importlib.metadata import version

__version__ = version("weatherbot")

__all__ = ["__version__"]
