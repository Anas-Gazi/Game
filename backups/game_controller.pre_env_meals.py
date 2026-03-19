"""Core game controller - orchestrates all game systems."""
from __future__ import annotations

import random
from typing import Callable

from config import constants
from modes.base_mode import ClassicMode, GameMode, HardcoreMode, NoWallMode, TimeAttackMode
from systems.input_handler import InputHandler
from systems.scoring import ScoringSystem


class Food:
    """Food entity."""

    def __init__(self) -> None:
        self.position = (0, 0)
        self.food_type = "normal"
        self.food_variant = "apple"

    def respawn(
        self,
        cols: int,
        rows: int,
        occupied: set,
        rng: random.Random,
        special_spawn_rate: float = constants.SPECIAL_FOOD_SPAWN_RATE,
    ) -> None:
        """Respawn food at random position."""
        while True:
            self.position = (rng.randint(0, cols - 1), rng.randint(0, rows - 1))
            if self.position not in occupied:
                # Determine food type
                if rng.random() < special_spawn_rate:
                    self.food_type = rng.choice(["bonus", "poison"])
                    self.food_variant = "golden" if self.food_type == "bonus" else "poison"
                else:
                    self.food_type = "normal"
                    self.food_variant = rng.choice(constants.FRUIT_VARIANTS)
                break


class Snake:
    """Snake entity with movement and state."""

    DIRECTIONS = {
        "up": (0, 1),
        "down": (0, -1),
        "left": (-1, 0),
        "right": (1, 0),
    }

    def __init__(self, start_pos: tuple[int, int], length: int = 4) -> None:
        self.segments = [start_pos]
        for i in range(1, length):
            self.segments.append((start_pos[0] - i, start_pos[1]))
        self.previous_segments = list(self.segments)
        self.direction = (1, 0)  # Moving right
        self.trail = []  # Visual trail
        self.turn_trail_boost = 0.0

    @property
    def head(self) -> tuple[int, int]:
        return self.segments[0]

    @property
    def occupied(self) -> set[tuple[int, int]]:
        return set(self.segments)

    def move(self, direction: tuple[int, int], grow: bool = False, wrap: tuple[int, int] | None = None) -> None:
        """Move snake one step.
        
        Args:
            direction: Direction vector (dx, dy).
            grow: Whether snake grows (ate food).
            wrap: Wrap dimensions (cols, rows), or None for no wrapping.
        """
        self.previous_segments = list(self.segments)
        turned = direction != self.direction
        self.direction = direction
        new_head = (self.head[0] + direction[0], self.head[1] + direction[1])

        # Apply wrapping if enabled
        if wrap:
            new_head = (new_head[0] % wrap[0], new_head[1] % wrap[1])

        # Add to trail for effects
        self.trail.append(self.head)
        if len(self.trail) > constants.TRAIL_SEGMENTS:
            self.trail.pop(0)

        # Quick turns get a temporary trail intensity boost.
        if turned:
            self.turn_trail_boost = 1.0
        else:
            self.turn_trail_boost = max(0.0, self.turn_trail_boost - 0.22)

        self.segments.insert(0, new_head)
        if not grow:
            self.segments.pop()

    def reset(self, start_pos: tuple[int, int], length: int = 4) -> None:
        """Reset snake to starting state."""
        self.segments = [start_pos]
        for i in range(1, length):
            self.segments.append((start_pos[0] - i, start_pos[1]))
        self.previous_segments = list(self.segments)
        self.direction = (1, 0)
        self.trail = []
        self.turn_trail_boost = 0.0

    def get_interpolated_segments(
        self,
        alpha: float,
        cols: int | None = None,
        rows: int | None = None,
    ) -> list[tuple[float, float]]:
        """Return smooth in-between positions for rendering at 60 FPS.

        When board dimensions are provided, interpolation is done on a torus so
        wrapped moves (crossing edges) animate smoothly instead of snapping.
        """
        interpolated: list[tuple[float, float]] = []
        for index, current in enumerate(self.segments):
            previous = self.previous_segments[index] if index < len(self.previous_segments) else current

            prev_x = float(previous[0])
            prev_y = float(previous[1])
            curr_x = float(current[0])
            curr_y = float(current[1])

            if cols and abs(curr_x - prev_x) > cols / 2:
                curr_x += cols if curr_x < prev_x else -cols
            if rows and abs(curr_y - prev_y) > rows / 2:
                curr_y += rows if curr_y < prev_y else -rows

            x_pos = prev_x + (curr_x - prev_x) * alpha
            y_pos = prev_y + (curr_y - prev_y) * alpha

            if cols:
                x_pos %= cols
            if rows:
                y_pos %= rows

            interpolated.append((x_pos, y_pos))
        return interpolated


class GameController:
    """Main game controller orchestrating all systems."""

    def __init__(self, progression_system, input_handler: InputHandler) -> None:
        """Initialize game controller.
        
        Args:
            progression_system: ProgressionSystem instance.
            input_handler: InputHandler instance.
        """
        self.progression_system = progression_system
        self.input_handler = input_handler
        self.scoring = ScoringSystem(progression_system)
        
        self.current_mode: GameMode = ClassicMode()
        self.snake = Snake((constants.BOARD_COLS // 2, constants.BOARD_ROWS // 2), constants.START_LENGTH)
        self.food = Food()
        self.walls: set[tuple[int, int]] = set()
        
        self.rng = random.Random()
        self.accumulator = 0.0
        self.elapsed_time = 0.0
        self.poison_active = False
        self.poison_timer = 0.0
        self.banana_slow_active = False
        self.banana_slow_timer = 0.0
        self.food_timer = 0.0
        self.effect_message = ""
        self.effect_message_timer = 0.0

        # Callbacks
        self.on_food_eaten: Callable[[tuple[int, int]], None] | None = None
        self.on_game_over: Callable[[int, int], None] | None = None
        self.on_mode_changed: Callable[[str], None] | None = None

    @property
    def interpolation_alpha(self) -> float:
        """Render interpolation alpha for smooth visuals between fixed simulation steps."""
        if self.current_mode.is_game_over:
            return 1.0
        move_interval = self._get_move_interval()
        if move_interval <= 0:
            return 1.0
        return min(1.0, self.accumulator / move_interval)

    def set_mode(self, mode_name: str) -> None:
        """Change game mode.
        
        Args:
            mode_name: "classic", "no_wall", "time_attack", "hardcore".
        """
        mode_map = {
            "classic": ClassicMode(),
            "no_wall": NoWallMode(),
            "time_attack": TimeAttackMode(),
            "hardcore": HardcoreMode(),
        }
        
        if mode_name in mode_map:
            self.current_mode = mode_map[mode_name]
            if self.on_mode_changed:
                self.on_mode_changed(self.current_mode.name)

    def start_new_game(self, mode_name: str = "classic") -> None:
        """Start a new game.
        
        Args:
            mode_name: Game mode to start.
        """
        self.set_mode(mode_name)
        self.current_mode.reset()
        self.snake.reset((constants.BOARD_COLS // 2, constants.BOARD_ROWS // 2), constants.START_LENGTH)
        self.scoring.reset()
        self.input_handler.reset()
        self.poison_active = False
        self.poison_timer = 0.0
        self.banana_slow_active = False
        self.banana_slow_timer = 0.0
        self.food_timer = 0.0
        self.effect_message = ""
        self.effect_message_timer = 0.0
        self.accumulator = 0.0
        self.elapsed_time = 0.0
        
        # Generate walls
        self._generate_walls()
        
        # Spawn food
        self._respawn_food()

    def update(self, dt: float) -> None:
        """Update game state.
        
        Args:
            dt: Delta time.
        """
        if self.current_mode.is_game_over:
            return

        self.elapsed_time += dt
        self.current_mode.elapsed_time = self.elapsed_time

        if self.elapsed_time >= 600:
            self.progression_system.unlock_achievement("ten_minutes")

        # Update poison effect
        if self.poison_active:
            self.poison_timer -= dt
            if self.poison_timer <= 0:
                self.poison_active = False

        # Banana effect temporarily slows speed for better control.
        if self.banana_slow_active:
            self.banana_slow_timer -= dt
            if self.banana_slow_timer <= 0:
                self.banana_slow_active = False

        if self.effect_message_timer > 0:
            self.effect_message_timer -= dt
            if self.effect_message_timer <= 0:
                self.effect_message = ""

        # Bonus food expires after a short lifetime.
        if self.food.food_type == "bonus":
            self.food_timer += dt
            if self.food_timer >= constants.BONUS_FOOD_LIFETIME:
                self._respawn_food()

        # Update mode (for time attack, etc.)
        self.current_mode.update(dt)

        if self.current_mode.is_paused or self.current_mode.is_game_over:
            return

        # Update scoring (combo timeout)
        self.scoring.update(dt)

        # Fixed timestep movement
        move_interval = self._get_move_interval()
        self.accumulator += dt

        while self.accumulator >= move_interval:
            self.accumulator -= move_interval
            self._step()

    def _step(self) -> None:
        """One game tick."""
        # Get input
        direction = self.input_handler.get_buffered_direction() or self.input_handler.current_direction
        self.input_handler.apply_direction()
        direction_vec = InputHandler.DIRECTION_VECTORS[direction]

        next_head = (self.snake.head[0] + direction_vec[0], self.snake.head[1] + direction_vec[1])

        if self.current_mode.should_wrap_edges():
            next_head = (next_head[0] % constants.BOARD_COLS, next_head[1] % constants.BOARD_ROWS)
        else:
            if next_head[0] < 0 or next_head[0] >= constants.BOARD_COLS or next_head[1] < 0 or next_head[1] >= constants.BOARD_ROWS:
                self._end_game()
                return

        will_grow = next_head == self.food.position

        # Self-collision check excludes tail when not growing (tail moves away this tick).
        body_to_check = self.snake.segments if will_grow else self.snake.segments[:-1]
        if next_head in body_to_check:
            self._end_game()
            return

        if next_head in self.walls:
            self._end_game()
            return

        # Move snake
        wrap_dims = (constants.BOARD_COLS, constants.BOARD_ROWS) if self.current_mode.should_wrap_edges() else None
        self.snake.move(direction_vec, grow=will_grow, wrap=wrap_dims)

        if will_grow:
            self._handle_food_eaten()

    def _handle_food_eaten(self) -> None:
        """Handle food consumption."""
        food_type = self.food.food_type
        food_variant = self.food.food_variant
        eaten_position = self.food.position

        if food_type == "bonus":
            self.scoring.add_score(constants.BONUS_FOOD_SCORE, "bonus")
            self._set_effect_message("Golden Fruit! Big Score")
            self.progression_system.unlock_achievement("first_food")
        elif food_type == "poison":
            self.scoring.add_score(constants.POISON_FOOD_PENALTY, "poison")
            self.poison_active = True
            self.poison_timer = constants.POISON_EFFECTS_DURATION
            self._set_effect_message("Poison Fruit! Speed Up")
        else:
            self.scoring.add_score(constants.FOOD_SCORE, "normal")
            if food_variant == "orange":
                self.scoring.add_flat_points(constants.ORANGE_BURST_SCORE)
                self._set_effect_message(f"Orange Burst +{constants.ORANGE_BURST_SCORE}")
            elif food_variant == "mango":
                self.scoring.extend_combo(constants.MANGO_COMBO_EXTENSION)
                self.scoring.boost_combo(constants.MANGO_COMBO_BOOST)
                self._set_effect_message("Mango Combo Boost!")
            elif food_variant == "banana":
                self.banana_slow_active = True
                self.banana_slow_timer = constants.BANANA_SLOW_DURATION
                self._set_effect_message("Banana Focus: Slow Motion")
            else:
                self._set_effect_message("Apple Collected")
            self.progression_system.unlock_achievement("first_food")

        # Respawn food
        self._respawn_food()

        if self.on_food_eaten:
            self.on_food_eaten(eaten_position)

        # Check achievements
        if self.scoring.score >= 10:
            self.progression_system.unlock_achievement("ten_points")
        if self.scoring.score >= 50:
            self.progression_system.unlock_achievement("fifty_points")
        if self.scoring.score >= 100:
            self.progression_system.unlock_achievement("hundred_points")
        if self.scoring.combo_level >= 5:
            self.progression_system.unlock_achievement("combo_5")

    def _end_game(self) -> None:
        """End game and persist high score."""
        self.current_mode.end_game()
        
        # Update high score
        high_score = max(self.progression_system.save_manager.get_nested("player.high_score", 0),
                        self.scoring.score)
        self.progression_system.save_manager.set_nested("player.high_score", high_score)
        self.progression_system.save_manager.save()

        if self.on_game_over:
            self.on_game_over(self.scoring.score, high_score)

    def _generate_walls(self) -> None:
        """Generate random wall clusters."""
        self.walls.clear()
        safe_radius = constants.WALL_SAFE_RADIUS
        start = (constants.BOARD_COLS // 2, constants.BOARD_ROWS // 2)
        
        # Safe zone around spawn
        safe = {(start[0] + dx, start[1] + dy) 
               for dx in range(-safe_radius, safe_radius + 1)
               for dy in range(-safe_radius, safe_radius + 1)}
        safe |= self.snake.occupied

        wall_count = self.current_mode.get_wall_count()
        attempts = 0

        while len(self.walls) < wall_count and attempts < 600:
            attempts += 1
            sx = self.rng.randint(1, constants.BOARD_COLS - 2)
            sy = self.rng.randint(1, constants.BOARD_ROWS - 2)

            if (sx, sy) in safe or (sx, sy) in self.walls:
                continue

            # Create cluster (larger groups for tighter navigation).
            cluster = {(sx, sy)}
            for _ in range(self.rng.randint(2, 4)):
                adjacent = [(cx + dx, cy + dy)
                           for cx, cy in cluster
                           for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                           if 1 <= cx + dx < constants.BOARD_COLS - 1
                           and 1 <= cy + dy < constants.BOARD_ROWS - 1
                           and (cx + dx, cy + dy) not in safe
                           and (cx + dx, cy + dy) not in cluster]
                if adjacent:
                    cluster.add(self.rng.choice(adjacent))

            self.walls |= cluster

    def _special_food_spawn_rate(self) -> float:
        """Scale special-food chance up slightly as player progresses."""
        level_bonus = (self.progression_system.level - 1) * 0.005
        score_bonus = min(0.10, self.scoring.score / 1000)
        return min(0.35, constants.SPECIAL_FOOD_SPAWN_RATE + level_bonus + score_bonus)

    def _respawn_food(self) -> None:
        """Respawn food and reset food timer for timed food types."""
        self.food.respawn(
            constants.BOARD_COLS,
            constants.BOARD_ROWS,
            self.snake.occupied | self.walls,
            self.rng,
            special_spawn_rate=self._special_food_spawn_rate(),
        )
        self.food_timer = 0.0

    def _get_move_interval(self) -> float:
        """Get current movement interval considering poison effect and speed mode."""
        base = self.current_mode.get_base_move_interval()
        
        # Apply speed mode multiplier
        speed_mode = self.progression_system.get_speed_mode()
        speed_multiplier = constants.SPEED_MODES.get(speed_mode, 1.0)
        base = base * speed_multiplier
        
        # Dynamic difficulty scaling
        level = self.progression_system.level
        speed_boost = (level - 1) * constants.SPEED_STEP
        base = max(base - speed_boost, constants.MIN_MOVE_INTERVAL)

        # Poison effect increases speed temporarily
        if self.poison_active:
            base = base / constants.POISON_SPEED_MULTIPLIER

        # Banana effect slows movement briefly.
        if self.banana_slow_active:
            base = min(base * constants.BANANA_SLOW_MULTIPLIER, constants.BASE_MOVE_INTERVAL * 2.2)

        return base

    def pause(self) -> None:
        """Pause game."""
        if not self.current_mode.is_game_over:
            self.current_mode.pause()

    def resume(self) -> None:
        """Resume game."""
        if not self.current_mode.is_game_over:
            self.current_mode.resume()

    def request_direction(self, direction: str) -> bool:
        """Request direction change.
        
        Args:
            direction: Direction name.
            
        Returns:
            True if buffered.
        """
        return self.input_handler.request_direction(direction)

    def _set_effect_message(self, text: str, duration: float = 1.25) -> None:
        """Set short-lived HUD message for fruit/gameplay effects."""
        self.effect_message = text
        self.effect_message_timer = duration
