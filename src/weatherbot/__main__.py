# src/weatherbot/__main__.py
"""Run the command-line interface with ``python -m weatherbot``."""

from weatherbot.cli import app

if __name__ == "__main__":
    app(prog_name="weatherbot")
