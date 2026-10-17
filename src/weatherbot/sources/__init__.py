# src/weatherbot/sources/__init__.py
"""Sources layer: async HTTP clients, one per official feed.

Sources fetch, validate, and return typed models that carry provenance (URL,
fetched-at time, product issuance time, advisory number). They never interpret what
they fetch, and they never import the engine.
"""

from typing import Final

from weatherbot import __version__

USER_AGENT: Final = f"weatherbot/{__version__} (+https://github.com/nathanramoscfa/weatherbot)"
"""The register's User-Agent (``docs/DATA_SOURCES.md``, "User-Agent"): the one definition.

Every request the clients and the fixture recorder send carries it; a contract test keeps
it equal to the register's string.
"""
