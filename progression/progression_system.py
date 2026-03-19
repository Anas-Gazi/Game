"""Progression system: XP, levels, achievements, and unlocks."""
from __future__ import annotations

from typing import Callable

from config import constants


class ProgressionSystem:
    """Manages player progression (XP, levels, achievements, unlocks)."""

    def __init__(self, save_manager) -> None:
        """Initialize progression system.
        
        Args:
            save_manager: SaveManager instance for persistence.
        """
        self.save_manager = save_manager
        self.on_level_up: Callable[[int, int], None] | None = None
        self.on_achievement_unlocked: Callable[[str, str, int], None] | None = None
        self.on_unlock: Callable[[str, str], None] | None = None

        # Keep unlocks in sync with current level when app boots or old saves are loaded.
        self._check_unlocks(self.level)

    @property
    def level(self) -> int:
        """Get current player level."""
        return self.save_manager.get_nested("player.level", 1)

    @property
    def xp(self) -> int:
        """Get current XP in this level."""
        return self.save_manager.get_nested("player.xp", 0)

    @property
    def total_xp(self) -> int:
        """Get total XP earned."""
        return self.save_manager.get_nested("player.total_xp", 0)

    @property
    def coins(self) -> int:
        """Get player coins (for future cosmetics)."""
        return self.save_manager.get_nested("player.coins", 0)

    def add_xp(self, amount: int) -> None:
        """Add XP and handle level-ups.
        
        Args:
            amount: XP to add.
        """
        if amount <= 0:
            return

        total_xp = self.total_xp + amount
        new_level = self.level
        new_xp = self.xp + amount
        leveled_up = False

        while new_xp >= constants.LEVEL_THRESHOLD and new_level < constants.LEVELS_MAX:
            new_xp -= constants.LEVEL_THRESHOLD
            new_level += 1
            leveled_up = True

        if new_level >= constants.LEVELS_MAX:
            new_xp = min(new_xp, constants.LEVEL_THRESHOLD - 1)

        self.save_manager.set_nested("player.level", new_level)
        self.save_manager.set_nested("player.xp", new_xp)
        self.save_manager.set_nested("player.total_xp", total_xp)
        self.save_manager.save()

        if new_level >= constants.LEVELS_MAX:
            self.unlock_achievement("100_level")

        if leveled_up:
            self._check_unlocks(new_level)
            if self.on_level_up:
                self.on_level_up(new_level, new_xp)

    def unlock_achievement(self, achievement_id: str) -> bool:
        """Unlock an achievement.
        
        Args:
            achievement_id: Achievement ID.
            
        Returns:
            True if newly unlocked, False if already unlocked.
        """
        if achievement_id not in constants.ACHIEVEMENTS:
            return False

        current = self.save_manager.get_nested(f"achievements.{achievement_id}", False)
        if current:
            return False

        # Unlock it
        self.save_manager.set_nested(f"achievements.{achievement_id}", True)
        ach_data = constants.ACHIEVEMENTS[achievement_id]
        
        # Award XP
        if ach_data.get("xp", 0) > 0:
            self.add_xp(ach_data["xp"])

        self.save_manager.save()

        if self.on_achievement_unlocked:
            self.on_achievement_unlocked(achievement_id, ach_data["name"], ach_data.get("xp", 0))

        return True

    def is_achievement_unlocked(self, achievement_id: str) -> bool:
        """Check if achievement is unlocked."""
        return self.save_manager.get_nested(f"achievements.{achievement_id}", False)

    def get_unlocked_achievements(self) -> list[str]:
        """Get list of unlocked achievement IDs."""
        achievements = self.save_manager.get("achievements", {})
        return [ach_id for ach_id, unlocked in achievements.items() if unlocked]

    def unlock_skin(self, skin_id: str) -> bool:
        """Unlock a snake skin.
        
        Args:
            skin_id: Skin ID.
            
        Returns:
            True if newly unlocked.
        """
        if skin_id not in constants.SNAKE_SKINS:
            return False

        current = self.save_manager.get_nested(f"unlocks.snake_skins.{skin_id}", False)
        if current:
            return False

        self.save_manager.set_nested(f"unlocks.snake_skins.{skin_id}", True)
        self.save_manager.save()

        if self.on_unlock:
            self.on_unlock("snake_skin", skin_id)

        return True

    def unlock_food_style(self, style_id: str) -> bool:
        """Unlock a food style.
        
        Args:
            style_id: Style ID.
            
        Returns:
            True if newly unlocked.
        """
        if style_id not in constants.FOOD_STYLES:
            return False

        current = self.save_manager.get_nested(f"unlocks.food_styles.{style_id}", False)
        if current:
            return False

        self.save_manager.set_nested(f"unlocks.food_styles.{style_id}", True)
        self.save_manager.save()

        if self.on_unlock:
            self.on_unlock("food_style", style_id)

        return True

    def _check_unlocks(self, current_level: int) -> None:
        """Check for new unlocks when leveling up.
        
        Args:
            current_level: Current player level.
        """
        # Check snake skins
        for skin_id, skin_data in constants.SNAKE_SKINS.items():
            if current_level >= skin_data["unlocked_at_level"]:
                if self.unlock_skin(skin_id):
                    pass  # on_unlock callback fired

        # Check food styles
        for style_id, style_data in constants.FOOD_STYLES.items():
            if current_level >= style_data["unlocked_at_level"]:
                if self.unlock_food_style(style_id):
                    pass  # on_unlock callback fired

    def set_selected_skin(self, skin_id: str) -> None:
        """Set active snake skin."""
        if skin_id in constants.SNAKE_SKINS and self.save_manager.get_nested(f"unlocks.snake_skins.{skin_id}"):
            self.save_manager.set_nested("selected.snake_skin", skin_id)
            self.save_manager.save()

    def set_selected_food_style(self, style_id: str) -> None:
        """Set active food style."""
        if style_id in constants.FOOD_STYLES and self.save_manager.get_nested(f"unlocks.food_styles.{style_id}"):
            self.save_manager.set_nested("selected.food_style", style_id)
            self.save_manager.save()

    def get_selected_skin(self) -> str:
        """Get currently selected snake skin."""
        return self.save_manager.get_nested("selected.snake_skin", "default")

    def get_selected_food_style(self) -> str:
        """Get currently selected food style."""
        return self.save_manager.get_nested("selected.food_style", "default")

    def get_speed_mode(self) -> str:
        """Get currently selected speed mode (slow, medium, fast)."""
        return self.save_manager.get_nested("settings.speed_mode", constants.DEFAULT_SPEED_MODE)

    def set_speed_mode(self, mode: str) -> None:
        """Set speed mode."""
        if mode in constants.SPEED_MODES:
            self.save_manager.set_nested("settings.speed_mode", mode)
            self.save_manager.save()

    def get_unlocked_skins(self) -> list[str]:
        """Get list of unlocked skin IDs."""
        skins = self.save_manager.get_nested("unlocks.snake_skins", {})
        return [skin_id for skin_id, unlocked in skins.items() if unlocked]

    def get_unlocked_food_styles(self) -> list[str]:
        """Get list of unlocked food style IDs."""
        styles = self.save_manager.get_nested("unlocks.food_styles", {})
        return [style_id for style_id, unlocked in styles.items() if unlocked]

    def reset_progress(self) -> None:
        """Reset all progress (for testing or user request)."""
        self.save_manager.set_nested("player.level", 1)
        self.save_manager.set_nested("player.xp", 0)
        self.save_manager.set_nested("player.total_xp", 0)
        self.save_manager.set_nested("player.high_score", 0)

        # Reset achievements
        for ach_id in constants.ACHIEVEMENTS:
            self.save_manager.set_nested(f"achievements.{ach_id}", False)

        self.save_manager.save()
