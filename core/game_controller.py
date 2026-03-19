"""Core game controller - orchestrates all game systems."""
from __future__ import annotations

import random
from typing import Callable

from config import constants
from modes.base_mode import ClassicMode, GameMode, HardcoreMode, NoWallMode, TimeAttackMode
from systems.input_handler import InputHandler
from systems.scoring import ScoringSystem


class Food:
    """Meal entity with environment-aware variants."""

    MEADOW_MOVEMENT_PROFILES = {
        "mouse": {"interval": 0.33, "turn_chance": 0.46, "axis": "horizontal"},
        "frog": {"interval": 0.31, "turn_chance": 0.62, "axis": "any"},
        "small_bird": {"interval": 0.29, "turn_chance": 0.68, "axis": "any"},
    }

    UNDERWATER_MOVEMENT_PROFILES = {
        "salmon": {"interval": 0.22, "turn_chance": 0.30, "axis": "horizontal"},
        "tuna": {"interval": 0.19, "turn_chance": 0.24, "axis": "horizontal"},
        "shrimp": {"interval": 0.27, "turn_chance": 0.62, "axis": "any"},
        "octopus": {"interval": 0.32, "turn_chance": 0.70, "axis": "any"},
        "lobster": {"interval": 0.28, "turn_chance": 0.40, "axis": "horizontal"},
        "crab": {"interval": 0.29, "turn_chance": 0.76, "axis": "horizontal"},
    }

    ICELAND_MOVEMENT_PROFILES = {
        "vole": {"interval": 0.34, "turn_chance": 0.42, "axis": "horizontal"},
        "mouse": {"interval": 0.32, "turn_chance": 0.46, "axis": "horizontal"},
        "shrew": {"interval": 0.36, "turn_chance": 0.58, "axis": "any"},
        "frog": {"interval": 0.30, "turn_chance": 0.64, "axis": "any"},
        "lizard": {"interval": 0.31, "turn_chance": 0.52, "axis": "horizontal"},
    }

    DESERT_MOVEMENT_PROFILES = {
        "kangaroo_rat": {"interval": 0.31, "turn_chance": 0.60, "axis": "horizontal"},
        "mouse": {"interval": 0.32, "turn_chance": 0.46, "axis": "horizontal"},
        "shrew": {"interval": 0.36, "turn_chance": 0.58, "axis": "any"},
        "small_bird": {"interval": 0.28, "turn_chance": 0.68, "axis": "any"},
        "lizard": {"interval": 0.31, "turn_chance": 0.52, "axis": "horizontal"},
    }

    MEAL_VARIANTS = {
        "meadow": {
            "normal": ["mouse", "frog", "small_bird"],
            "bonus": ["small_bird"],
            "poison": ["toadstool"],
        },
        "underwater": {
            "normal": ["salmon", "tuna", "shrimp", "octopus", "lobster", "crab"],
            "bonus": ["tuna", "lobster"],
            "poison": ["crab", "octopus"],
        },
        "iceland": {
            "normal": ["vole", "mouse", "shrew", "frog", "lizard"],
            "bonus": ["frog", "lizard"],
            "poison": ["shrew"],
        },
        "desert": {
            "normal": ["kangaroo_rat", "mouse", "shrew", "small_bird", "lizard"],
            "bonus": ["small_bird", "lizard"],
            "poison": ["shrew"],
        },
    }

    def __init__(self) -> None:
        self.position = (0, 0)
        self.previous_position = (0, 0)
        self.food_type = "normal"
        self.food_variant = "mouse"
        self.environment_theme = "meadow"
        self.move_direction = (1, 0)
        self.move_timer = 0.0
        self.move_interval = 0.34
        self.transition_progress = 1.0
        self.bird_wave_step = 0
        self.behavior_step = 0

    def _pick_variant(self, rng: random.Random) -> str:
        pools = self.MEAL_VARIANTS.get(self.environment_theme, self.MEAL_VARIANTS["meadow"])
        options = pools.get(self.food_type, pools["normal"])
        return rng.choice(options)

    def downgrade_bonus_to_normal(self, rng: random.Random) -> None:
        """Convert bonus meal into a normal meal at the same position.

        This avoids sudden disappear-and-respawn behavior when bonus lifetime ends.
        """
        if self.food_type != "bonus":
            return
        pools = self.MEAL_VARIANTS.get(self.environment_theme, self.MEAL_VARIANTS["meadow"])
        normal_pool = pools.get("normal", ["mouse"])
        self.food_type = "normal"
        if self.food_variant not in normal_pool:
            self.food_variant = rng.choice(normal_pool)

        # Keep movement smooth after conversion.
        profile = self._get_environment_profile()
        self.move_interval = max(0.16, min(0.36, float(profile["interval"])))

    def _get_environment_profile(self) -> dict[str, float | str]:
        if self.environment_theme == "meadow":
            return self.MEADOW_MOVEMENT_PROFILES.get(
                self.food_variant,
                {"interval": 0.33, "turn_chance": 0.46, "axis": "any"},
            )
        if self.environment_theme == "underwater":
            return self.UNDERWATER_MOVEMENT_PROFILES.get(
                self.food_variant,
                {"interval": 0.24, "turn_chance": 0.45, "axis": "any"},
            )
        if self.environment_theme == "iceland":
            return self.ICELAND_MOVEMENT_PROFILES.get(
                self.food_variant,
                {"interval": 0.33, "turn_chance": 0.46, "axis": "any"},
            )
        if self.environment_theme == "desert":
            return self.DESERT_MOVEMENT_PROFILES.get(
                self.food_variant,
                {"interval": 0.33, "turn_chance": 0.46, "axis": "any"},
            )
        return {"interval": 0.34, "turn_chance": 0.45, "axis": "any"}

    def _build_direction_pool(self) -> list[tuple[int, int]]:
        profile = self._get_environment_profile()
        axis = profile["axis"]
        if axis == "horizontal":
            # Horizontal species tend to side-glide more often.
            return [(1, 0), (-1, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
        return [(1, 0), (-1, 0), (0, 1), (0, -1)]

    def _build_bird_direction_pool(self, rng: random.Random) -> list[tuple[int, int]]:
        """Create a smooth, wave-like flight path for birds.

        Birds mostly glide forward and occasionally climb/dive in gentle arcs.
        """
        glide_x = self.move_direction[0] if self.move_direction[0] != 0 else rng.choice([-1, 1])
        self.bird_wave_step = (self.bird_wave_step + 1) % 8

        vertical_hint = 0
        if self.bird_wave_step in (1, 2):
            vertical_hint = 1
        elif self.bird_wave_step in (5, 6):
            vertical_hint = -1

        directions: list[tuple[int, int]] = []
        if vertical_hint != 0:
            directions.append((glide_x, vertical_hint))
        directions.extend(
            [
                (glide_x, 0),
                (glide_x, 1),
                (glide_x, -1),
                (0, 1),
                (0, -1),
                (-glide_x, 0),
            ]
        )
        return directions

    def _movement_group(self) -> str:
        """Return a coarse behavior group for species-like movement."""
        variant = self.food_variant
        if variant == "toadstool":
            return "static"
        if variant == "small_bird":
            return "bird"
        if variant in {"mouse", "vole", "shrew", "kangaroo_rat"}:
            return "rodent"
        if variant == "frog":
            return "frog"
        if variant == "lizard":
            return "lizard"
        if variant in {"salmon", "tuna"}:
            return "fish_glide"
        if variant == "shrimp":
            return "shrimp"
        if variant == "octopus":
            return "octopus"
        if variant in {"crab", "lobster"}:
            return "crustacean"
        return "default"

    def _environment_behavior_adjustments(self, group: str) -> dict[str, float]:
        """Return environment-based movement tuning multipliers.

        interval: lower means faster movement cadence.
        turn: lower means straighter paths.
        pause: lower means fewer idle beats.
        """
        base = {"interval": 1.0, "turn": 1.0, "pause": 1.0}
        env = self.environment_theme

        if env == "desert":
            if group in {"bird", "lizard"}:
                base["turn"] = 0.82
                base["pause"] = 0.86
            if group == "rodent":
                base["interval"] = 0.92
                base["turn"] = 0.88
            if group == "frog":
                base["pause"] = 1.12
        elif env == "underwater":
            if group in {"fish_glide", "shrimp"}:
                base["interval"] = 0.90
                base["turn"] = 0.92
            if group in {"octopus", "crustacean"}:
                base["pause"] = 1.16
        elif env == "iceland":
            if group in {"rodent", "lizard", "frog"}:
                base["interval"] = 1.08
                base["pause"] = 1.12
            if group == "bird":
                base["turn"] = 0.90
        elif env == "meadow":
            if group == "rodent":
                base["turn"] = 0.86
            if group == "bird":
                base["turn"] = 0.94

        return base

    def _build_species_direction_pool(self, group: str, rng: random.Random) -> list[tuple[int, int]]:
        """Build weighted movement candidates by species behavior."""
        dx, dy = self.move_direction
        env = self.environment_theme
        if dx == 0 and dy == 0:
            dx, dy = rng.choice([(1, 0), (-1, 0)])

        if group == "bird":
            return self._build_bird_direction_pool(rng)

        if group == "rodent":
            side_axis = (0, 1) if dx != 0 else (1, 0)
            options = [
                (dx, dy),
                (dx, dy),
                (dx, 0) if dx != 0 else (0, dy),
                (side_axis[0], side_axis[1]),
                (-side_axis[0], -side_axis[1]),
                (-dx, -dy),
            ]
            # Meadow rodents scurry with fewer full reversals.
            if env == "meadow":
                options.insert(0, (dx, dy))
            # Desert rodents sprint longer in one direction.
            if env == "desert":
                options.insert(0, (dx, 0) if dx != 0 else (0, dy))
            return options

        if group == "frog":
            vertical_bias = [(0, 1), (0, -1), (0, 1), (0, -1)]
            horizontal_bias = [(1, 0), (-1, 0)]
            return [self.move_direction] + vertical_bias + horizontal_bias

        if group == "lizard":
            return [
                (dx, dy),
                (dx, dy),
                (dx, 0) if dx != 0 else (0, dy),
                (1, 0),
                (-1, 0),
                (0, 1),
                (0, -1),
            ]

        if group == "fish_glide":
            # Underwater fish prefer long horizontal lanes with less vertical jitter.
            vertical_moves = [] if env == "underwater" else [(0, 1), (0, -1)]
            return [
                (dx if dx != 0 else rng.choice([-1, 1]), 0),
                (dx if dx != 0 else rng.choice([-1, 1]), 0),
                (1, 0),
                (-1, 0),
                *vertical_moves,
            ]

        if group == "shrimp":
            zig = 1 if self.behavior_step % 2 == 0 else -1
            forward_x = dx if dx != 0 else rng.choice([-1, 1])
            return [
                (forward_x, zig),
                (forward_x, -zig),
                (forward_x, 0),
                (0, zig),
                (0, -zig),
                (-forward_x, 0),
            ]

        if group == "octopus":
            return [
                (0, 1),
                (1, 0),
                (0, -1),
                (-1, 0),
                self.move_direction,
            ]

        if group == "crustacean":
            side = dx if dx != 0 else rng.choice([-1, 1])
            return [
                (side, 0),
                (side, 0),
                (-side, 0),
                (0, 1),
                (0, -1),
            ]

        return [self.move_direction] + self._build_direction_pool()

    def _pause_chance_for_group(self, group: str) -> float:
        """Chance to briefly pause movement for natural cadence."""
        base = {
            "static": 1.0,
            "bird": 0.02,
            "rodent": 0.10,
            "frog": 0.24,
            "lizard": 0.14,
            "fish_glide": 0.04,
            "shrimp": 0.08,
            "octopus": 0.18,
            "crustacean": 0.16,
            "default": 0.08,
        }.get(group, 0.08)
        adjustments = self._environment_behavior_adjustments(group)
        return max(0.0, min(0.95, base * adjustments["pause"]))

    def respawn(
        self,
        cols: int,
        rows: int,
        occupied: set[tuple[int, int]],
        rng: random.Random,
        environment_theme: str = "meadow",
        special_spawn_rate: float = constants.SPECIAL_FOOD_SPAWN_RATE,
    ) -> None:
        """Respawn meal at random position."""
        self.environment_theme = environment_theme if environment_theme in self.MEAL_VARIANTS else "meadow"
        free_cells = [
            (x_pos, y_pos)
            for x_pos in range(cols)
            for y_pos in range(rows)
            if (x_pos, y_pos) not in occupied
        ]

        if not free_cells:
            # Keep current position when no free cell exists; caller handles game-over logic.
            self.previous_position = self.position
            self.transition_progress = 1.0
            return

        self.position = rng.choice(free_cells)

        # Determine meal type.
        if rng.random() < special_spawn_rate:
            self.food_type = rng.choice(["bonus", "poison"])
        else:
            self.food_type = "normal"
        self.food_variant = self._pick_variant(rng)
        self.previous_position = self.position
        self.move_timer = 0.0
        self.transition_progress = 1.0
        self.behavior_step = 0
        if self.environment_theme in {"meadow", "underwater", "iceland", "desert"}:
            direction_pool = self._build_direction_pool()
            self.move_direction = rng.choice(direction_pool)
            profile = self._get_environment_profile()
            speed_modifier = 1.0
            if self.food_type == "bonus":
                speed_modifier = 0.92
            elif self.food_type == "poison":
                speed_modifier = 1.08
            self.move_interval = max(0.16, min(0.36, float(profile["interval"]) * speed_modifier))
            if self.food_variant == "small_bird":
                self.bird_wave_step = rng.randint(0, 7)
                self.move_direction = (rng.choice([-1, 1]), 0)
        else:
            self.move_direction = (1, 0)
            self.move_interval = 0.34

    def update_movement(
        self,
        dt: float,
        cols: int,
        rows: int,
        occupied: set[tuple[int, int]],
        blocked: set[tuple[int, int]],
        rng: random.Random,
    ) -> None:
        """Move meal entity for dynamic environments (meadow, underwater, iceland, desert)."""
        if self.environment_theme not in {"meadow", "underwater", "iceland", "desert"}:
            return

        profile = self._get_environment_profile()
        step_interval = self.move_interval
        turn_chance = float(profile["turn_chance"])
        group = self._movement_group()
        is_bird = group == "bird"
        adjustments = self._environment_behavior_adjustments(group)

        if group == "static":
            self.transition_progress = 1.0
            return

        if is_bird:
            # Slightly faster cadence to resemble flapping flight.
            step_interval = max(0.14, step_interval * 0.92)
        elif group == "frog":
            # Frogs hop in bursts with brief pauses.
            step_interval = max(0.20, step_interval * (0.92 if self.behavior_step % 3 == 0 else 1.12))
        elif group == "rodent":
            step_interval = max(0.16, step_interval * (0.90 if self.behavior_step % 2 == 0 else 1.06))
        elif group == "fish_glide":
            step_interval = max(0.16, step_interval * 0.88)
        elif group == "lizard":
            step_interval = max(0.17, step_interval * 1.02)
        elif group == "crustacean":
            step_interval = max(0.18, step_interval * 1.06)
        elif group == "octopus":
            step_interval = max(0.19, step_interval * 1.10)

        step_interval = max(0.14, step_interval * adjustments["interval"])
        turn_chance = max(0.02, min(0.95, turn_chance * adjustments["turn"]))

        self.move_timer += dt
        self.transition_progress = min(1.0, self.move_timer / max(step_interval, 0.001))
        if self.move_timer < step_interval:
            return
        self.move_timer = 0.0
        self.behavior_step += 1

        if rng.random() < self._pause_chance_for_group(group):
            self.previous_position = self.position
            self.transition_progress = 1.0
            return

        if is_bird:
            directions = self._build_bird_direction_pool(rng)
            # Birds keep momentum, with occasional banking turns.
            if rng.random() < turn_chance * 0.22:
                tail = directions[2:]
                rng.shuffle(tail)
                directions = directions[:2] + tail
        else:
            directions = self._build_species_direction_pool(group, rng)
            if rng.random() < turn_chance:
                rng.shuffle(directions)

        tried = set()
        for dx, dy in directions:
            if (dx, dy) in tried:
                continue
            tried.add((dx, dy))
            new_pos = (self.position[0] + dx, self.position[1] + dy)
            if new_pos[0] < 0 or new_pos[0] >= cols or new_pos[1] < 0 or new_pos[1] >= rows:
                continue
            if new_pos in occupied or new_pos in blocked:
                continue
            self.previous_position = self.position
            self.position = new_pos
            self.move_direction = (dx, dy)
            self.transition_progress = 0.0
            return

    def get_render_position(self) -> tuple[float, float]:
        """Return smooth in-between render position for meal entity."""
        prev_x, prev_y = self.previous_position
        curr_x, curr_y = self.position
        alpha = max(0.0, min(1.0, self.transition_progress))
        return (
            prev_x + (curr_x - prev_x) * alpha,
            prev_y + (curr_y - prev_y) * alpha,
        )


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
        self.boost_active = False
        self.boost_timer = 0.0
        self.boost_cooldown_timer = 0.0
        self.boost_recovery_timer = 0.0
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
        self.boost_active = False
        self.boost_timer = 0.0
        self.boost_cooldown_timer = 0.0
        self.boost_recovery_timer = 0.0
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

        # Cap long frame spikes (alt-tab/background wake) to prevent simulation bursts.
        dt = max(0.0, min(0.25, dt))
        self.elapsed_time += dt

        if self.elapsed_time >= 600:
            self.progression_system.unlock_achievement("ten_minutes")

        # Update poison effect
        if self.poison_active:
            self.poison_timer -= dt
            if self.poison_timer <= 0:
                self.poison_active = False

        if self.boost_active:
            self.boost_timer -= dt
            if self.boost_timer <= 0:
                self.boost_active = False
                self.boost_recovery_timer = constants.BOOST_RECOVERY_DURATION

        if self.boost_recovery_timer > 0:
            self.boost_recovery_timer = max(0.0, self.boost_recovery_timer - dt)

        if self.boost_cooldown_timer > 0:
            self.boost_cooldown_timer = max(0.0, self.boost_cooldown_timer - dt)

        if self.effect_message_timer > 0:
            self.effect_message_timer -= dt
            if self.effect_message_timer <= 0:
                self.effect_message = ""

        # Bonus food expires after a short lifetime.
        if self.food.food_type == "bonus":
            self.food_timer += dt
            if self.food_timer >= constants.BONUS_FOOD_LIFETIME:
                self.food.downgrade_bonus_to_normal(self.rng)
                self.food_timer = 0.0

        # Keep active meal variant aligned with current environment theme.
        self._ensure_food_matches_environment()

        # Environment-based dynamic meal movement (fish/swimmers in underwater).
        snake_occupied = self.snake.occupied
        self.food.update_movement(
            dt,
            constants.BOARD_COLS,
            constants.BOARD_ROWS,
            snake_occupied,
            self.walls,
            self.rng,
        )
        self._ensure_food_valid()

        # Update mode (for time attack, etc.)
        self.current_mode.update(dt)

        # Time Attack timeout must end through controller flow for save/callback consistency.
        if isinstance(self.current_mode, TimeAttackMode) and self.current_mode.is_game_over:
            self._end_game()
            return

        if self.current_mode.is_paused or self.current_mode.is_game_over:
            return

        # Update scoring (combo timeout)
        self.scoring.update(dt)

        # Fixed timestep movement
        move_interval = self._get_move_interval()
        self.accumulator += dt

        max_substeps = 5
        substeps = 0
        while self.accumulator >= move_interval and substeps < max_substeps:
            self.accumulator -= move_interval
            self._step()
            substeps += 1

        if self.accumulator >= move_interval:
            # Prevent endless catch-up and keep controls responsive on low-end devices.
            self.accumulator = min(self.accumulator, move_interval)

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
        """Handle meal consumption."""
        food_type = self.food.food_type
        food_variant = self.food.food_variant
        eaten_position = self.food.position

        if food_type == "bonus":
            self.scoring.add_score(constants.BONUS_FOOD_SCORE, "bonus")
            self._set_effect_message(f"Rare Meal: {self._meal_display_name(food_variant)} +{constants.BONUS_FOOD_SCORE}")
            self.progression_system.unlock_achievement("first_food")
        elif food_type == "poison":
            self.scoring.add_score(constants.POISON_FOOD_PENALTY, "poison")
            self.poison_active = True
            self.poison_timer = constants.POISON_EFFECTS_DURATION
            self._set_effect_message(f"Toxic Meal: {self._meal_display_name(food_variant)}")
        else:
            self.scoring.add_score(constants.FOOD_SCORE, "normal")
            self._set_effect_message(f"Meal Eaten: {self._meal_display_name(food_variant)}")
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
        """Respawn meal and reset timer for timed meal types."""
        occupied = self.snake.occupied | self.walls
        self.food.respawn(
            constants.BOARD_COLS,
            constants.BOARD_ROWS,
            occupied,
            self.rng,
            environment_theme=self._current_environment_theme(),
            special_spawn_rate=self._special_food_spawn_rate(),
        )
        self.food_timer = 0.0

        # No free cell left means the board is full; finish run as a clean win/end state.
        if self.food.position in occupied and len(occupied) >= constants.BOARD_COLS * constants.BOARD_ROWS:
            self._end_game()

    def _ensure_food_valid(self) -> None:
        """Keep meal position valid so it never disappears due to invalid state."""
        fx, fy = self.food.position
        out_of_bounds = fx < 0 or fx >= constants.BOARD_COLS or fy < 0 or fy >= constants.BOARD_ROWS
        occupied = self.snake.occupied | self.walls
        if out_of_bounds or self.food.position in occupied:
            self._respawn_food()

    def _ensure_food_matches_environment(self) -> None:
        """Respawn food if its variant/type is not valid for the current theme.

        This prevents cross-theme leftovers (e.g., birds persisting in underwater).
        """
        current_theme = self._current_environment_theme()
        if self.food.environment_theme != current_theme:
            self._respawn_food()
            return

        pools = self.food.MEAL_VARIANTS.get(current_theme, self.food.MEAL_VARIANTS["meadow"])
        valid_variants = set(pools.get(self.food.food_type, []))
        if self.food.food_variant not in valid_variants:
            self._respawn_food()

        # Hard safety: underwater map must never show bird variants.
        if current_theme == "underwater" and self.food.food_variant == "small_bird":
            self.food.food_type = "normal"
            self.food.food_variant = self.rng.choice(["salmon", "tuna", "shrimp", "octopus", "lobster", "crab"])
            self.food.environment_theme = "underwater"

    def _current_environment_theme(self) -> str:
        """Read active render environment from settings."""
        value = self.progression_system.save_manager.get_nested("settings.environment_theme", "meadow")
        return value if value in {"meadow", "underwater", "iceland", "desert"} else "meadow"

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

        # Player-triggered boost with smooth post-boost recovery.
        if self.boost_active:
            boost_factor = constants.BOOST_INTERVAL_FACTOR
            base = max(constants.MIN_MOVE_INTERVAL * 0.85, base * boost_factor)
        elif self.boost_recovery_timer > 0 and constants.BOOST_RECOVERY_DURATION > 0:
            # Blend from boost speed back to normal speed to avoid hard braking feel.
            progress = 1.0 - (self.boost_recovery_timer / constants.BOOST_RECOVERY_DURATION)
            progress = max(0.0, min(1.0, progress))
            eased = progress * progress * (3.0 - 2.0 * progress)
            factor = constants.BOOST_INTERVAL_FACTOR + (1.0 - constants.BOOST_INTERVAL_FACTOR) * eased
            base = max(constants.MIN_MOVE_INTERVAL * 0.85, base * factor)

        return base

    def activate_boost(self) -> bool:
        """Activate temporary snake speed boost if available."""
        if self.current_mode.is_game_over or self.current_mode.is_paused:
            return False
        if self.boost_active or self.boost_cooldown_timer > 0:
            return False

        self.boost_active = True
        self.boost_timer = constants.BOOST_DURATION
        self.boost_cooldown_timer = constants.BOOST_COOLDOWN
        self.boost_recovery_timer = 0.0
        self._set_effect_message("Boost Activated", duration=0.95)
        return True

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
        """Set short-lived HUD message for meal/gameplay effects."""
        self.effect_message = text
        self.effect_message_timer = duration

    def _meal_display_name(self, meal_variant: str) -> str:
        """Format meal variant id for HUD text."""
        return meal_variant.replace("_", " ").title()
