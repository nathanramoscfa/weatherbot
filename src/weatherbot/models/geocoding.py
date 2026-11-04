# src/weatherbot/models/geocoding.py
"""Nominatim reverse-geocoding and forward-search models."""

from weatherbot.models.alerts import GeocodeCandidate, GeocodeResult, OsmType

__all__ = ["GeocodeCandidate", "GeocodeResult", "OsmType"]
