# src/weatherbot/state.py
"""State management for Weatherbot."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WeatherbotState(BaseModel):
    """Persistent state for Weatherbot."""

    last_cone_advisories: dict[str, str] = Field(
        default_factory=dict,
        description="Last advisory number per storm ID",
    )
    last_alert_ids: list[str] = Field(
        default_factory=list,
        description="Previously processed alert CAP IDs",
    )
    was_in_cone: bool = Field(
        default=False,
        description="Whether location was in cone on last check",
    )
    updated: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Last update timestamp",
    )

    def is_new_cone_advisory(self, storm_id: str, advisory_num: str) -> bool:
        """Check if this is a new advisory for the storm.

        Args:
            storm_id: Storm identifier
            advisory_num: Advisory number

        Returns:
            True if this is a new advisory
        """
        last_advisory = self.last_cone_advisories.get(storm_id)
        return last_advisory != advisory_num

    def is_new_alert(self, alert_id: str) -> bool:
        """Check if this is a new alert.

        Args:
            alert_id: Alert CAP ID

        Returns:
            True if this is a new alert
        """
        return alert_id not in self.last_alert_ids

    def update_cone_advisory(self, storm_id: str, advisory_num: str) -> None:
        """Update the last advisory for a storm.

        Args:
            storm_id: Storm identifier
            advisory_num: Advisory number
        """
        self.last_cone_advisories[storm_id] = advisory_num
        self.updated = datetime.now(UTC)

    def add_alert_id(self, alert_id: str) -> None:
        """Add a processed alert ID.

        Args:
            alert_id: Alert CAP ID to add
        """
        if alert_id not in self.last_alert_ids:
            self.last_alert_ids.append(alert_id)
            # Keep only last 100 alert IDs to prevent unbounded growth
            if len(self.last_alert_ids) > 100:
                self.last_alert_ids = self.last_alert_ids[-100:]
            self.updated = datetime.now(UTC)

    def set_in_cone_status(self, in_cone: bool) -> None:
        """Update the in-cone status.

        Args:
            in_cone: Whether location is currently in a cone
        """
        self.was_in_cone = in_cone
        self.updated = datetime.now(UTC)


class StateManager:
    """Manages persistent state storage."""

    def __init__(self, state_file: Path = Path("state/state.json")) -> None:
        """Initialize state manager.

        Args:
            state_file: Path to state file
        """
        self.state_file = state_file
        self.state_file.parent.mkdir(exist_ok=True)

    def load_state(self) -> WeatherbotState:
        """Load state from file.

        Returns:
            Current state (empty if file doesn't exist)
        """
        if not self.state_file.exists():
            logger.info("No existing state file, starting fresh")
            return WeatherbotState()

        try:
            with open(self.state_file, encoding="utf-8") as f:
                data = json.load(f)
            state = WeatherbotState.model_validate(data)
            logger.debug(f"Loaded state from {self.state_file}")
            return state
        except Exception as e:
            logger.warning(f"Failed to load state from {self.state_file}: {e}")
            logger.warning("Starting with fresh state")
            return WeatherbotState()

    def save_state(self, state: WeatherbotState) -> None:
        """Save state to file.

        Args:
            state: State to save
        """
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                # Use model_dump with mode='json' for datetime serialization
                data = state.model_dump(mode="json")
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved state to {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to save state to {self.state_file}: {e}")

    def clear_state(self) -> None:
        """Clear the state file."""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
                logger.info(f"Cleared state file {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to clear state file {self.state_file}: {e}")

    def show_state(self) -> dict[str, Any]:
        """Get current state as dictionary for display.

        Returns:
            State data as dictionary
        """
        state = self.load_state()
        return state.model_dump(mode="json")
