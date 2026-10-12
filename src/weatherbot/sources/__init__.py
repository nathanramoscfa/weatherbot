# src/weatherbot/sources/__init__.py
"""Sources layer: async HTTP clients, one per official feed.

Sources fetch, validate, and return typed models that carry provenance (URL,
fetched-at time, product issuance time, advisory number). They never interpret what
they fetch, and they never import the engine.
"""
