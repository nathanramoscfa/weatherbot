# tests/test_state.py
"""State management tests for weatherbot."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

from weatherbot.state import StateManager, WeatherbotState


class TestWeatherbotState:
    """Test WeatherbotState class."""

    def test_default_state(self) -> None:
        """Test default state initialization."""
        state = WeatherbotState()
        assert state.last_cone_advisories == {}
        assert state.last_alert_ids == []
        assert state.was_in_cone is False
        assert isinstance(state.updated, datetime)

    def test_is_new_cone_advisory(self) -> None:
        """Test cone advisory tracking."""
        state = WeatherbotState()

        # First advisory should be new
        assert state.is_new_cone_advisory("AL012023", "001") is True

        # Update the advisory
        state.update_cone_advisory("AL012023", "001")

        # Same advisory should not be new
        assert state.is_new_cone_advisory("AL012023", "001") is False

        # Different advisory should be new
        assert state.is_new_cone_advisory("AL012023", "002") is True

        # Different storm should be new
        assert state.is_new_cone_advisory("AL022023", "001") is True

    def test_is_new_alert(self) -> None:
        """Test alert tracking."""
        state = WeatherbotState()

        # First alert should be new
        assert state.is_new_alert("test-alert-1") is True

        # Add the alert
        state.add_alert_id("test-alert-1")

        # Same alert should not be new
        assert state.is_new_alert("test-alert-1") is False

        # Different alert should be new
        assert state.is_new_alert("test-alert-2") is True

    def test_update_cone_advisory(self) -> None:
        """Test updating cone advisory."""
        state = WeatherbotState()
        original_time = state.updated

        state.update_cone_advisory("AL012023", "001")

        assert state.last_cone_advisories["AL012023"] == "001"
        assert state.updated >= original_time

    def test_add_alert_id(self) -> None:
        """Test adding alert ID."""
        state = WeatherbotState()
        original_time = state.updated

        state.add_alert_id("test-alert-1")

        assert "test-alert-1" in state.last_alert_ids
        assert state.updated >= original_time

    def test_add_alert_id_duplicate(self) -> None:
        """Test adding duplicate alert ID."""
        state = WeatherbotState()
        state.add_alert_id("test-alert-1")
        original_time = state.updated

        # Adding duplicate should not change the list or timestamp
        state.add_alert_id("test-alert-1")

        assert state.last_alert_ids.count("test-alert-1") == 1
        assert state.updated == original_time

    def test_add_alert_id_limit(self) -> None:
        """Test alert ID list size limit."""
        state = WeatherbotState()

        # Add 101 alerts
        for i in range(101):
            state.add_alert_id(f"alert-{i}")

        # Should only keep last 100
        assert len(state.last_alert_ids) == 100
        assert "alert-0" not in state.last_alert_ids  # First one removed
        assert "alert-100" in state.last_alert_ids    # Last one kept

    def test_set_in_cone_status(self) -> None:
        """Test setting in-cone status."""
        state = WeatherbotState()
        original_time = state.updated

        state.set_in_cone_status(True)

        assert state.was_in_cone is True
        assert state.updated >= original_time

        state.set_in_cone_status(False)

        assert state.was_in_cone is False

    def test_model_dump_json(self) -> None:
        """Test JSON serialization."""
        state = WeatherbotState()
        state.update_cone_advisory("AL012023", "001")
        state.add_alert_id("test-alert-1")
        state.set_in_cone_status(True)

        data = state.model_dump(mode="json")

        assert isinstance(data, dict)
        assert data["last_cone_advisories"] == {"AL012023": "001"}
        assert data["last_alert_ids"] == ["test-alert-1"]
        assert data["was_in_cone"] is True
        assert "updated" in data


class TestStateManager:
    """Test StateManager class."""

    def test_init(self) -> None:
        """Test StateManager initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "test_state.json"
            manager = StateManager(state_file)

            assert manager.state_file == state_file
            assert state_file.parent.exists()

    def test_load_state_no_file(self) -> None:
        """Test loading state when file doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "nonexistent.json"
            manager = StateManager(state_file)

            state = manager.load_state()

            assert isinstance(state, WeatherbotState)
            assert state.last_cone_advisories == {}
            assert state.last_alert_ids == []

    def test_load_state_valid_file(self) -> None:
        """Test loading state from valid file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "test_state.json"
            manager = StateManager(state_file)

            # Create a test state
            original_state = WeatherbotState()
            original_state.update_cone_advisory("AL012023", "001")
            original_state.add_alert_id("test-alert-1")
            original_state.set_in_cone_status(True)

            # Save it
            manager.save_state(original_state)

            # Load it
            loaded_state = manager.load_state()

            assert loaded_state.last_cone_advisories == {"AL012023": "001"}
            assert loaded_state.last_alert_ids == ["test-alert-1"]
            assert loaded_state.was_in_cone is True

    def test_load_state_invalid_file(self) -> None:
        """Test loading state from invalid file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "invalid_state.json"
            manager = StateManager(state_file)

            # Create invalid JSON file
            with open(state_file, "w") as f:
                f.write("invalid json content")

            # Should return fresh state
            state = manager.load_state()

            assert isinstance(state, WeatherbotState)
            assert state.last_cone_advisories == {}
            assert state.last_alert_ids == []

    def test_save_state(self) -> None:
        """Test saving state to file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "test_state.json"
            manager = StateManager(state_file)

            # Create a test state
            state = WeatherbotState()
            state.update_cone_advisory("AL012023", "001")
            state.add_alert_id("test-alert-1")
            state.set_in_cone_status(True)

            # Save it
            manager.save_state(state)

            # Verify file was created and contains correct data
            assert state_file.exists()

            with open(state_file) as f:
                data = json.load(f)

            assert data["last_cone_advisories"] == {"AL012023": "001"}
            assert data["last_alert_ids"] == ["test-alert-1"]
            assert data["was_in_cone"] is True

    def test_save_state_error(self) -> None:
        """Test saving state with file error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a directory with the same name as the state file
            state_file = Path(temp_dir) / "test_state.json"
            state_file.mkdir()  # This will cause an error when trying to write

            manager = StateManager(state_file)
            state = WeatherbotState()

            # Should not raise exception, but log error
            manager.save_state(state)

    def test_clear_state(self) -> None:
        """Test clearing state file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "test_state.json"
            manager = StateManager(state_file)

            # Create and save state
            state = WeatherbotState()
            manager.save_state(state)
            assert state_file.exists()

            # Clear state
            manager.clear_state()
            assert not state_file.exists()

    def test_clear_state_no_file(self) -> None:
        """Test clearing state when file doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "nonexistent.json"
            manager = StateManager(state_file)

            # Should not raise exception
            manager.clear_state()

    def test_clear_state_error(self) -> None:
        """Test clearing state with file error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "test_state.json"
            manager = StateManager(state_file)

            # Create state file
            state = WeatherbotState()
            manager.save_state(state)

            # Remove write permissions
            state_file.chmod(0o444)

            try:
                # Should not raise exception, but log error
                manager.clear_state()
            finally:
                # Restore permissions for cleanup
                state_file.chmod(0o644)

    def test_show_state(self) -> None:
        """Test showing state as dictionary."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "test_state.json"
            manager = StateManager(state_file)

            # Create and save state
            state = WeatherbotState()
            state.update_cone_advisory("AL012023", "001")
            state.add_alert_id("test-alert-1")
            state.set_in_cone_status(True)
            manager.save_state(state)

            # Show state
            state_dict = manager.show_state()

            assert isinstance(state_dict, dict)
            assert state_dict["last_cone_advisories"] == {"AL012023": "001"}
            assert state_dict["last_alert_ids"] == ["test-alert-1"]
            assert state_dict["was_in_cone"] is True
            assert "updated" in state_dict
