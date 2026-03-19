"""Base game mode class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from config import constants


class GameMode(ABC):
    """Abstract base class for game modes."""

    def __init__(self, name: str) -> None:
        """Initialize game mode.
        
        Args:
            name: Mode name.
        """
        self.name = name
        self.score = 0
        self.high_score = 0
        self.is_paused = False
        self.is_game_over = False
        self.elapsed_time = 0.0
        self.on_game_over: Callable[[int], None] | None = None

    @abstractmethod
    def get_base_move_interval(self) -> float:
        """Get base movement interval for this mode."""
        pass

    @abstractmethod
    def get_wall_count(self) -> int:
        """Get number of walls/obstacles for this mode."""
        pass

    @abstractmethod
    def should_wrap_edges(self) -> bool:
        """Whether snake wraps around board edges."""
        pass

    def update(self, dt: float) -> None:
        """Update mode-specific logic."""
        self.elapsed_time += dt

    def pause(self) -> None:
        """Pause the game."""
        self.is_paused = True

    def resume(self) -> None:
        """Resume the game."""
        self.is_paused = False

    def reset(self) -> None:
        """Reset mode state for new game."""
        self.is_paused = False
        self.is_game_over = False
        self.elapsed_time = 0.0

    def end_game(self) -> None:
        """End the game."""
        self.is_game_over = True
        if self.on_game_over:
            self.on_game_over(self.score)


class ClassicMode(GameMode):
    """Classic mode: normal gameplay with walls."""

    def __init__(self) -> None:
        super().__init__("Classic")

    def get_base_move_interval(self) -> float:
        return constants.BASE_MOVE_INTERVAL

    def get_wall_count(self) -> int:
        return constants.WALL_COUNT

    def should_wrap_edges(self) -> bool:
        return True


class NoWallMode(GameMode):
    """No Wall mode: screen wraps, no obstacles."""

    def __init__(self) -> None:
        super().__init__("No Wall")

    def get_base_move_interval(self) -> float:
        return constants.BASE_MOVE_INTERVAL

    def get_wall_count(self) -> int:
        return 0  # No walls

    def should_wrap_edges(self) -> bool:
        return True


class TimeAttackMode(GameMode):
    """Time Attack mode: 60 seconds, maximize score."""

    def __init__(self) -> None:
        super().__init__("Time Attack")
        self.remaining_time = constants.TIME_ATTACK_DURATION

    def get_base_move_interval(self) -> float:
        return constants.BASE_MOVE_INTERVAL

    def get_wall_count(self) -> int:
        return constants.WALL_COUNT // 2  # Half walls

    def should_wrap_edges(self) -> bool:
        return True

    def update(self, dt: float) -> None:
        """Update timer and end game when time reaches zero."""
        if not self.is_paused and not self.is_game_over:
            self.elapsed_time += dt
            self.remaining_time = max(0, constants.TIME_ATTACK_DURATION - self.elapsed_time)
            if self.remaining_time <= 0:
                self.end_game()

    def reset(self) -> None:
        super().reset()
        self.remaining_time = constants.TIME_ATTACK_DURATION

    def get_time_remaining(self) -> float:
        """Get remaining time."""
        return self.remaining_time

    def get_time_percentage(self) -> float:
        """Get remaining time as percentage (0-1)."""
        return self.remaining_time / constants.TIME_ATTACK_DURATION


class HardcoreMode(GameMode):
    """Hardcore mode: fast speed from start, high difficulty."""

    def __init__(self) -> None:
        super().__init__("Hardcore")

    def get_base_move_interval(self) -> float:
        return constants.HARDCORE_BASE_MOVE_INTERVAL  # Faster from start

    def get_wall_count(self) -> int:
        return int(constants.WALL_COUNT * 1.5)  # More walls

    def should_wrap_edges(self) -> bool:
        return True

    def update(self, dt: float) -> None:
        """Update elapsed time for hardcore mode."""
        self.elapsed_time += dt
