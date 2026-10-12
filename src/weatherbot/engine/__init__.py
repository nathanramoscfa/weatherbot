# src/weatherbot/engine/__init__.py
"""Engine layer: pure functions from a snapshot and a location to an assessment.

The engine is deterministic. It imports nothing from the sources, services, cli, or web
layers and no I/O library (HTTP, sockets, databases, web frameworks, the Anthropic SDK,
or schedulers), so recorded and replayed data fully exercise it.
"""
