# src/weatherbot/services/ai/__init__.py
"""The Claude layer: the only code that talks to Anthropic, and only as a narrator.

Rules every module here keeps:

- It is the only code in the package that imports ``anthropic`` or ``httpx2``, and only
  ``client.py`` and ``caller.py`` import the SDK at module level, so a command that never
  uses AI never loads it.
- It reads and writes the database only through the AI engine (``guard.ai_engine``), whose
  SQLite authorizer lets it write ``ai_calls`` and ``ai_outputs`` and nothing else.
- It never imports the sources layer or ``httpx``, never fetches a URL, and never decides,
  stores, or changes a level, a storm, an alert, a location, a setting, or a notification:
  official products decide, and the model narrates.
- Model output is data. It is validated before it is shown, and never executed, followed,
  or written to an official table.
- The credential is the SDK's to resolve. No code here copies the key into a variable, a
  setting, a log record, a row, or an answer, and every SDK error is mapped to a fixed
  reason before it is logged or shown, because an SDK message can quote request content.
"""
