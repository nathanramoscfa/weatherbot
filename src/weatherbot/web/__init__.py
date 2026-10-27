# src/weatherbot/web/__init__.py
"""Web layer: the FastAPI app that serves the local web interface.

The web layer sits below the cli layer and above the services layer (``weatherbot.web``
imports ``weatherbot.services`` and ``weatherbot.models``, and never imports ``cli``,
``sources``, or ``engine``). It binds to the loopback interface and shares its services
and database with the command line.
"""
