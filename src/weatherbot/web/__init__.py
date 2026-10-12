# src/weatherbot/web/__init__.py
"""Web layer: the FastAPI app that serves the local web interface.

The web layer sits above the services layer, with the cli layer. It binds to the
loopback interface and shares its services and database with the command line.
"""
