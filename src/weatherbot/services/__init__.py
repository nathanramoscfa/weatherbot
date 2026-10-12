# src/weatherbot/services/__init__.py
"""Services layer: time, state, and side effects.

Services own the scheduler, change detection, notification policy and channels,
persistence, and the Claude integration. The command line and the web app share the
same services and the same database, so both show the same assessment.
"""
