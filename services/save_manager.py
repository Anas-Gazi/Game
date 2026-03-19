"""Save and load game progress using JSON."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from config import constants


class SaveManager:
    """Handles all game progress persistence."""

    def __init__(self, save_dir: Path | None = None) -> None:
        """Initialize save manager.
        
        Args:
            save_dir: Directory to store save files. Defaults to Kivy user data directory.
        """
        if save_dir is None:
            from kivy.app import App
            app = App.get_running_app()
            if app is not None:
                save_dir = Path(app.user_data_dir)
            else:
                # Fallback for tests/scripts that run without a live Kivy app instance.
                save_dir = Path.cwd() / ".snake_data"
        
        self.save_dir = save_dir
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.save_file = self.save_dir / constants.SAVE_DATA_FILENAME
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> dict[str, Any]:
        """Load save data from file."""
        if self.save_file.exists():
            try:
                with open(self.save_file, "r") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = self._create_default_save()
        else:
            self._data = self._create_default_save()
        return self._data

    def save(self) -> None:
        """Persist save data to file."""
        self._data["last_saved"] = datetime.now().isoformat()
        try:
            with open(self.save_file, "w") as f:
                json.dump(self._data, f, indent=2)
        except IOError as e:
            print(f"Failed to save game: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from save data."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set value in save data."""
        self._data[key] = value

    def get_nested(self, path: str, default: Any = None) -> Any:
        """Get nested value using dot notation (e.g., 'player.level')."""
        keys = path.split(".")
        value = self._data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
        return value if value is not None else default

    def set_nested(self, path: str, value: Any) -> None:
        """Set nested value using dot notation."""
        keys = path.split(".")
        target = self._data
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value

    def _create_default_save(self) -> dict[str, Any]:
        """Create default save structure."""
        return {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "last_saved": datetime.now().isoformat(),
            "player": {
                "name": "Player",
                "level": 1,
                "xp": 0,
                "total_xp": 0,
                "high_score": 0,
                "coins": 0,
            },
            "stats": {
                "games_played": 0,
                "total_score": 0,
                "total_time_played": 0.0,
                "best_streak": 0,
            },
            "modes": {
                "classic": {"high_score": 0, "unlocked": True},
                "no_wall": {"high_score": 0, "unlocked": False},
                "time_attack": {"high_score": 0, "unlocked": False},
                "hardcore": {"high_score": 0, "unlocked": False},
            },
            "unlocks": {
                "snake_skins": {"default": True, **{skin: False for skin in list(constants.SNAKE_SKINS.keys())[1:]}},
                "food_styles": {"default": True, **{style: False for style in list(constants.FOOD_STYLES.keys())[1:]}},
            },
            "selected": {
                "snake_skin": "default",
                "food_style": "default",
            },
            "settings": {
                "sound_enabled": True,
                "master_volume": 1.0,
                "sfx_volume": 1.0,
                "audio_output_mode": "auto",
                "vibration_enabled": True,
                "ads_removed": False,
                "control_sensitivity": 1.0,
                "graphics_quality": "balanced",
                "show_grid": False,
            },
            "achievements": {ach: False for ach in constants.ACHIEVEMENTS},
            "daily_rewards": {
                "last_claimed": None,
                "streak": 0,
                "total_claimed": 0,
            },
            "leaderboard": [],
        }
