"""Production-ready Snake game with multiple game modes, progression systems, and retention mechanics."""

import math
from dataclasses import dataclass

# Kivy config - must come first
from kivy.config import Config
Config.set("graphics", "width", "420")
Config.set("graphics", "height", "760")
Config.set("graphics", "resizable", "1")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle, RoundedRectangle, Line
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import FadeTransition, Screen, ScreenManager
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from config import constants
from core.game_controller import GameController
from systems.input_handler import InputHandler
from progression.progression_system import ProgressionSystem
from retention.daily_rewards import DailyRewardSystem, ReviveSystem
from services.save_manager import SaveManager
from services.ads_manager import AdsManager
from services.leaderboard import LocalLeaderboard


@dataclass(slots=True)
class Particle:
    """Visual particle for effects."""
    x_pos: float
    y_pos: float
    velocity_x: float
    velocity_y: float
    size: float
    life: float
    total_life: float


class SoundManager:
    """Global sound manager."""
    
    def __init__(self):
        self.enabled = True
        self._sounds = {}
        self._load_sounds()

    def _load_sounds(self):
        """Load all game sounds."""
        sound_files = {
            "eat": constants.EAT_SOUND,
            "game_over": constants.GAME_OVER_SOUND,
            "click": constants.CLICK_SOUND,
        }
        for name, path in sound_files.items():
            try:
                self._sounds[name] = SoundLoader.load(path)
            except Exception:
                self._sounds[name] = None

    def play(self, sound_name: str):
        """Play a sound."""
        if not self.enabled or sound_name not in self._sounds:
            return
        sound = self._sounds[sound_name]
        if sound:
            try:
                sound.stop()
                sound.play()
            except Exception:
                pass


class GameBoard(Widget):
    """Game board renderer with particles and swipe input."""
    
    controller = ObjectProperty(allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._gesture_origin = None
        self._particles = []
        self._shake_intensity = 0
        self._shake_timer = 0
        self._animation_time = 0.0
        self.bind(pos=self._request_redraw, size=self._request_redraw)

    def spawn_particles(self, cell):
        """Spawn particle burst at cell."""
        cell_width = self.width / constants.BOARD_COLS if self.width > 0 else 1
        cell_height = self.height / constants.BOARD_ROWS if self.height > 0 else 1
        unit_size = min(cell_width, cell_height)
        
        center_x = self.x + cell[0] * cell_width + cell_width / 2
        center_y = self.y + cell[1] * cell_height + cell_height / 2

        for i in range(constants.PARTICLE_COUNT):
            angle = (math.pi * 2 / constants.PARTICLE_COUNT) * i
            speed = unit_size * 1.6
            self._particles.append(
                Particle(
                    x_pos=center_x,
                    y_pos=center_y,
                    velocity_x=math.cos(angle) * speed,
                    velocity_y=math.sin(angle) * speed,
                    size=max(4.0, unit_size * 0.16),
                    life=constants.PARTICLE_LIFETIME,
                    total_life=constants.PARTICLE_LIFETIME,
                )
            )

    def screen_shake(self, intensity=0.15, duration=0.2):
        """Trigger screen shake effect."""
        self._shake_intensity = intensity
        self._shake_timer = duration

    def advance(self, dt):
        """Update particles and shake."""
        self._animation_time += dt
        # Update particles
        alive = []
        for p in self._particles:
            p.life -= dt
            if p.life > 0:
                p.x_pos += p.velocity_x * dt
                p.y_pos += p.velocity_y * dt
                alive.append(p)
        self._particles = alive

        # Update shake
        if self._shake_timer > 0:
            self._shake_timer -= dt
        else:
            self._shake_intensity = 0

        self.render()

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        self._gesture_origin = touch.pos
        return True

    def on_touch_up(self, touch):
        if self._gesture_origin is None:
            return super().on_touch_up(touch)

        start_x, start_y = self._gesture_origin
        delta_x = touch.x - start_x
        delta_y = touch.y - start_y
        self._gesture_origin = None

        sensitivity = App.get_running_app().save_manager.get_nested("settings.control_sensitivity", 1.0)
        threshold = max(12, int(constants.TOUCH_SWIPE_THRESHOLD * sensitivity))
        if max(abs(delta_x), abs(delta_y)) < threshold:
            return True

        # Determine direction
        if abs(delta_x) > abs(delta_y):
            direction = "right" if delta_x > 0 else "left"
        else:
            direction = "up" if delta_y > 0 else "down"

        if self.controller:
            self.controller.request_direction(direction)
        return True

    def _request_redraw(self, *_args):
        self.render()

    def _snake_palette(self) -> dict:
        """Return active snake palette from progression-selected skin."""
        app = App.get_running_app()
        selected = app.progression.get_selected_skin()
        return constants.SNAKE_SKIN_PALETTES.get(selected, constants.SNAKE_SKIN_PALETTES["default"])

    def render(self):
        """Render game board."""
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0 or not self.controller:
            return

        with self.canvas:
            # Background
            Color(0.06, 0.08, 0.12, 1)
            Rectangle(pos=self.pos, size=self.size)
            Color(0.08, 0.14, 0.2, 0.35)
            Rectangle(pos=(self.x, self.y + self.height * 0.45), size=(self.width, self.height * 0.55))

            if self.controller.current_mode.is_game_over:
                return

            # Apply shake
            offset_x = 0
            offset_y = 0
            if self._shake_intensity > 0:
                import random
                offset_x = random.uniform(-self._shake_intensity, self._shake_intensity)
                offset_y = random.uniform(-self._shake_intensity, self._shake_intensity)

            # Draw grid
            cell_width = self.width / constants.BOARD_COLS
            cell_height = self.height / constants.BOARD_ROWS

            Color(0.2, 0.2, 0.2, 0.3)
            for i in range(constants.BOARD_COLS + 1):
                x = self.x + offset_x + i * cell_width
                Line(points=[x, self.y, x, self.y + self.height], width=0.5)
            for j in range(constants.BOARD_ROWS + 1):
                y = self.y + offset_y + j * cell_height
                Line(points=[self.x, y, self.x + self.width, y], width=0.5)

            # Draw walls
            Color(0.4, 0.4, 0.4, 1)
            for wall in self.controller.walls:
                x = self.x + offset_x + wall[0] * cell_width
                y = self.y + offset_y + wall[1] * cell_height
                RoundedRectangle(pos=(x, y), size=(cell_width, cell_height), radius=(2,))

            # Draw food
            food_pos = self.controller.food.position
            if self.controller.food.food_type == "bonus":
                Color(1, 0.84, 0, 1)  # Gold
            elif self.controller.food.food_type == "poison":
                Color(0.5, 0, 1, 1)  # Purple
            else:
                Color(1, 0.2, 0.2, 1)  # Red

            x = self.x + offset_x + food_pos[0] * cell_width
            y = self.y + offset_y + food_pos[1] * cell_height
            pulse = 0.12 * (1 + math.sin(self._animation_time * 6.0))
            food_size_factor = 0.72 + pulse
            glow_size = cell_width * (1.08 + pulse)

            # Food glow
            if self.controller.food.food_type == "bonus":
                Color(1, 0.84, 0, 0.26)
            elif self.controller.food.food_type == "poison":
                Color(0.65, 0.2, 1, 0.26)
            else:
                Color(1, 0.35, 0.35, 0.24)
            Ellipse(pos=(x + (cell_width - glow_size) * 0.5, y + (cell_height - glow_size) * 0.5), size=(glow_size, glow_size))

            # Food core
            core_size_w = cell_width * food_size_factor
            core_size_h = cell_height * food_size_factor
            Ellipse(
                pos=(x + (cell_width - core_size_w) * 0.5, y + (cell_height - core_size_h) * 0.5),
                size=(core_size_w, core_size_h),
            )

            # Draw snake trail (old head positions)
            trail = self.controller.snake.trail
            for idx, trail_seg in enumerate(trail):
                fade = (idx + 1) / max(1, len(trail))
                Color(0.16, 0.92, 0.65, 0.07 + fade * 0.14)
                tx = self.x + offset_x + trail_seg[0] * cell_width
                ty = self.y + offset_y + trail_seg[1] * cell_height
                inset = cell_width * (0.22 + (1 - fade) * 0.12)
                Ellipse(pos=(tx + inset, ty + inset), size=(cell_width - inset * 2, cell_height - inset * 2))

            # Draw snake with torus interpolation and mirrored edge copies.
            interpolated = self.controller.snake.get_interpolated_segments(
                self.controller.interpolation_alpha,
                constants.BOARD_COLS,
                constants.BOARD_ROWS,
            )
            board_w = constants.BOARD_COLS
            board_h = constants.BOARD_ROWS

            def _mirror_offsets(seg_x: float, seg_y: float) -> list[tuple[float, float]]:
                offsets = [(0.0, 0.0)]
                threshold = 1.0
                left = seg_x < threshold
                right = seg_x > board_w - threshold
                bottom = seg_y < threshold
                top = seg_y > board_h - threshold

                if left:
                    offsets.append((board_w, 0.0))
                if right:
                    offsets.append((-board_w, 0.0))
                if bottom:
                    offsets.append((0.0, board_h))
                if top:
                    offsets.append((0.0, -board_h))
                if left and bottom:
                    offsets.append((board_w, board_h))
                if left and top:
                    offsets.append((board_w, -board_h))
                if right and bottom:
                    offsets.append((-board_w, board_h))
                if right and top:
                    offsets.append((-board_w, -board_h))
                return offsets

            palette = self._snake_palette()
            for i, seg in enumerate(interpolated):
                for dx, dy in _mirror_offsets(seg[0], seg[1]):
                    x = self.x + offset_x + (seg[0] + dx) * cell_width
                    y = self.y + offset_y + (seg[1] + dy) * cell_height
                    if i == 0:  # Head - 3D effect with layers
                        # Shadow/depth layer
                        Color(palette["glow"][0] * 0.4, palette["glow"][1] * 0.4, palette["glow"][2] * 0.4, palette["glow"][3] * 0.5)
                        Ellipse(pos=(x - cell_width * 0.15, y - cell_height * 0.15), size=(cell_width * 1.3, cell_height * 1.3))
                        
                        # Glow halo
                        Color(*palette["glow"])
                        Ellipse(pos=(x - cell_width * 0.12, y - cell_height * 0.12), size=(cell_width * 1.24, cell_height * 1.24))
                        
                        # Main head color
                        Color(*palette["head"])
                        Ellipse(pos=(x, y), size=(cell_width, cell_height))
                        
                        # 3D top shadow (darker shade for depth)
                        Color(
                            palette["head"][0] * 0.7,
                            palette["head"][1] * 0.7,
                            palette["head"][2] * 0.7,
                            palette["head"][3] * 0.4
                        )
                        Ellipse(pos=(x + cell_width * 0.1, y + cell_height * 0.6), size=(cell_width * 0.8, cell_height * 0.25))
                        
                        # Glossy highlight (3D shine effect)
                        Color(1, 1, 1, 0.3)
                        Ellipse(pos=(x + cell_width * 0.15, y + cell_height * 0.68), size=(cell_width * 0.35, cell_height * 0.18))

                        # Eyes with 3D depth
                        # Left eye
                        Color(*palette["eye"])
                        eye_size = min(cell_width, cell_height) * 0.13
                        Ellipse(pos=(x + cell_width * 0.22, y + cell_height * 0.60), size=(eye_size, eye_size))
                        # Pupil
                        Color(0, 0, 0, 0.8)
                        pupil_size = eye_size * 0.6
                        Ellipse(pos=(x + cell_width * 0.265, y + cell_height * 0.635), size=(pupil_size, pupil_size))
                        # Eye shine
                        Color(1, 1, 1, 0.7)
                        shine_size = eye_size * 0.3
                        Ellipse(pos=(x + cell_width * 0.295, y + cell_height * 0.665), size=(shine_size, shine_size))
                        
                        # Right eye
                        Color(*palette["eye"])
                        Ellipse(pos=(x + cell_width * 0.65, y + cell_height * 0.60), size=(eye_size, eye_size))
                        # Pupil
                        Color(0, 0, 0, 0.8)
                        Ellipse(pos=(x + cell_width * 0.695, y + cell_height * 0.635), size=(pupil_size, pupil_size))
                        # Eye shine
                        Color(1, 1, 1, 0.7)
                        Ellipse(pos=(x + cell_width * 0.725, y + cell_height * 0.665), size=(shine_size, shine_size))
                        
                    else:  # Body - 3D with overlapping effect
                        # Shadow/depth (segment behind current one)
                        Color(
                            palette["body"][0] * 0.4,
                            palette["body"][1] * 0.4,
                            palette["body"][2] * 0.4,
                            palette["body"][3] * 0.3
                        )
                        RoundedRectangle(pos=(x + cell_width * 0.06, y - cell_height * 0.04), size=(cell_width * 0.98, cell_height * 0.98), radius=(3,))
                        
                        # Main body color
                        Color(*palette["body"])
                        RoundedRectangle(pos=(x, y), size=(cell_width, cell_height), radius=(3,))

                        # Dorsal stripe (3D depth from top)
                        Color(*palette["dorsal"])
                        RoundedRectangle(
                            pos=(x + cell_width * 0.16, y + cell_height * 0.56),
                            size=(cell_width * 0.68, cell_height * 0.28),
                            radius=(2,),
                        )
                        
                        # Scale pattern texture (subtle grid)
                        Color(
                            palette["body"][0] * 0.8,
                            palette["body"][1] * 0.8,
                            palette["body"][2] * 0.8,
                            palette["body"][3] * 0.25
                        )
                        # Horizontal scale lines
                        for scale_y in [0.25, 0.5, 0.75]:
                            Line(
                                points=[
                                    x + cell_width * 0.1, y + cell_height * scale_y,
                                    x + cell_width * 0.9, y + cell_height * scale_y
                                ],
                                width=0.5
                            )

                        # Belly highlight (light underbelly)
                        Color(*palette["belly"])
                        RoundedRectangle(
                            pos=(x + cell_width * 0.18, y + cell_height * 0.08),
                            size=(cell_width * 0.64, cell_height * 0.22),
                            radius=(2,),
                        )
                        
                        # Bottom shadow for 3D depth
                        Color(
                            palette["belly"][0] * 0.6,
                            palette["belly"][1] * 0.6,
                            palette["belly"][2] * 0.6,
                            palette["belly"][3] * 0.3
                        )
                        RoundedRectangle(
                            pos=(x + cell_width * 0.20, y + cell_height * 0.02),
                            size=(cell_width * 0.60, cell_height * 0.08),
                            radius=(2,),
                        )

            # Draw particles
            Color(1, 0.8, 0, 0.8)
            for p in self._particles:
                Ellipse(pos=(p.x_pos, p.y_pos), size=(p.size, p.size))


class MenuScreen(Screen):
    """Main menu screen."""
    
    def on_enter(self):
        app = App.get_running_app()
        if hasattr(self, 'ids') and 'mode_spinner' in self.ids:
            self.ids.mode_spinner.values = ["Classic", "No Wall", "Time Attack", "Hardcore"]
            self.ids.mode_spinner.text = "Classic"
        if hasattr(self, 'ids') and 'name_input' in self.ids:
            current_name = app.save_manager.get_nested("player.name", "Player")
            self.ids['name_input'].text = current_name
        
        # Update stats display
        if hasattr(self, 'ids') and 'high_score_label' in self.ids:
            high_score = app.save_manager.get_nested("player.high_score", 0)
            self.ids['high_score_label'].text = f"🏆 High Score: {high_score}"
        
        if hasattr(self, 'ids') and 'level_label' in self.ids:
            level = app.progression.level
            self.ids['level_label'].text = f"⭐ Level: {level}"
        
        # Update daily reward status
        if hasattr(self, 'ids') and 'daily_label' in self.ids:
            if app.daily_rewards.can_claim_reward():
                self.ids['daily_label'].text = "Daily Reward Ready!"
                self.ids['daily_label'].color = (1.0, 1.0, 0.5, 1.0)
            else:
                self.ids['daily_label'].text = "Come back tomorrow!"
                self.ids['daily_label'].color = (0.7, 0.7, 0.7, 0.7)

    def start_game(self):
        """Start selected game mode."""
        app = App.get_running_app()
        app._revived_this_run = False
        mode = "classic"
        if hasattr(self, 'ids') and 'mode_spinner' in self.ids:
            mode_map = {"Classic": "classic", "No Wall": "no_wall", "Time Attack": "time_attack", "Hardcore": "hardcore"}
            mode = mode_map.get(self.ids.mode_spinner.text, "classic")
        
        app.game_controller.start_new_game(mode)
        app.root.current = "game"

    def show_progression(self):
        """Show progression screen."""
        App.get_running_app().root.current = "progression"

    def show_leaderboard(self):
        """Show leaderboard screen."""
        App.get_running_app().root.current = "leaderboard"

    def show_settings(self):
        """Show settings screen."""
        App.get_running_app().root.current = "settings"

    def claim_daily_reward(self):
        """Claim daily reward."""
        app = App.get_running_app()
        if app.daily_rewards.can_claim_reward():
            amount, streak = app.daily_rewards.claim_reward()
            if hasattr(self, 'ids') and 'daily_label' in self.ids:
                self.ids.daily_label.text = f"Daily Reward: +{amount} coins (Streak: {streak})"
        else:
            if hasattr(self, 'ids') and 'daily_label' in self.ids:
                self.ids.daily_label.text = "You already claimed today's reward!"

    def save_player_name(self):
        """Persist player display name for leaderboard entries."""
        if not (hasattr(self, 'ids') and 'name_input' in self.ids):
            return
        value = self.ids['name_input'].text.strip()
        final_name = value[:18] if value else "Player"
        app = App.get_running_app()
        app.save_manager.set_nested("player.name", final_name)
        app.save_manager.save()
        self.ids['name_input'].text = final_name


class GameScreen(Screen):
    """Main gameplay screen."""
    
    score_text = StringProperty("Score: 0")
    high_score_text = StringProperty("High: 0")
    combo_text = StringProperty("Combo: 0x")
    mode_text = StringProperty("Classic")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._death_slowmo_timer = 0.0

    def on_enter(self):
        app = App.get_running_app()
        if hasattr(self, 'ids') and 'game_board' in self.ids:
            self.ids.game_board.controller = app.game_controller
        Clock.schedule_interval(self.update_game, 1.0 / constants.TARGET_FPS)
        Clock.schedule_interval(self.update_hud, 0.1)
        Window.bind(on_keyboard=self.on_keyboard)

    def on_leave(self):
        Clock.unschedule(self.update_game)
        Clock.unschedule(self.update_hud)
        Window.unbind(on_keyboard=self.on_keyboard)

    def update_game(self, dt):
        """Update game logic."""
        if self.manager.current != "game":
            return
        app = App.get_running_app()
        effective_dt = dt
        if self._death_slowmo_timer > 0:
            self._death_slowmo_timer -= dt
            effective_dt = dt * 0.28

        app.game_controller.update(effective_dt)
        if hasattr(self, 'ids') and 'game_board' in self.ids:
            self.ids.game_board.advance(dt)

    def update_hud(self, dt):
        """Update HUD display."""
        app = App.get_running_app()
        self.score_text = f"Score: {app.game_controller.scoring.score}"
        self.high_score_text = f"High: {app.game_controller.scoring.high_score}"
        self.combo_text = f"Combo: {app.game_controller.scoring.combo_level}x"
        self.mode_text = app.game_controller.current_mode.name

        if hasattr(self, 'ids'):
            if 'score_label' in self.ids:
                self.ids['score_label'].text = self.score_text
            if 'high_label' in self.ids:
                self.ids['high_label'].text = self.high_score_text
            if 'mode_label' in self.ids:
                self.ids['mode_label'].text = self.mode_text
            if 'combo_label' in self.ids:
                self.ids['combo_label'].text = self.combo_text

    def start_death_effect(self):
        """Trigger collision shake and short slow-motion window."""
        self._death_slowmo_timer = 0.45
        if hasattr(self, 'ids') and 'game_board' in self.ids:
            self.ids['game_board'].screen_shake(
                intensity=constants.COLLISION_SHAKE_INTENSITY,
                duration=constants.COLLISION_SHAKE_DURATION,
            )

    def on_keyboard(self, window, key, scancode, codepoint, modifier):
        """Handle keyboard input."""
        if codepoint in ('w', 'W'):
            App.get_running_app().game_controller.request_direction("up")
        elif codepoint in ('s', 'S'):
            App.get_running_app().game_controller.request_direction("down")
        elif codepoint in ('a', 'A'):
            App.get_running_app().game_controller.request_direction("left")
        elif codepoint in ('d', 'D'):
            App.get_running_app().game_controller.request_direction("right")
        elif codepoint == ' ':
            app = App.get_running_app()
            if app.game_controller.current_mode.is_paused:
                app.game_controller.resume()
            else:
                app.game_controller.pause()
        return False

    def go_menu(self):
        """Return to menu."""
        App.get_running_app().root.current = "menu"


class ProgressionScreen(Screen):
    """Player progression and unlocks screen."""
    
    level_text = StringProperty("Level: 1")
    xp_text = StringProperty("XP: 0/100")

    def on_enter(self):
        app = App.get_running_app()
        prog = app.progression
        self.level_text = f"Level: {prog.level}"
        self.xp_text = f"XP: {prog.xp}/{constants.LEVEL_THRESHOLD}"

        if hasattr(self, 'ids'):
            if 'skins_label' in self.ids:
                unlocked_skins = prog.get_unlocked_skins()
                self.ids.skins_label.text = f"Snake Skins: {len(unlocked_skins)}/{len(constants.SNAKE_SKINS)}"
            
            if 'styles_label' in self.ids:
                unlocked_styles = prog.get_unlocked_food_styles()
                self.ids.styles_label.text = f"Food Styles: {len(unlocked_styles)}/{len(constants.FOOD_STYLES)}"
            
            if 'achievements_label' in self.ids:
                unlocked_ach = prog.get_unlocked_achievements()
                self.ids.achievements_label.text = f"Achievements: {len(unlocked_ach)}/{len(constants.ACHIEVEMENTS)}"

    def go_back(self):
        """Return to menu."""
        App.get_running_app().root.current = "menu"


class LeaderboardScreen(Screen):
    """Leaderboard screen."""
    
    leaderboard_text = StringProperty("Loading...")

    def on_enter(self):
        app = App.get_running_app()
        lb = app.local_leaderboard
        
        # Get top scores
        top_scores = lb.get_top_scores(limit=10)
        
        text = "TOP 10 HIGH SCORES\n" + "=" * 40 + "\n"
        if top_scores:
            for i, entry in enumerate(top_scores, 1):
                text += f"{i:2d}. {entry['player']:15s} {entry['score']:6d}\n"
        else:
            text += "No scores yet! Start playing!\n"
        
        self.leaderboard_text = text

    def go_back(self):
        """Return to menu."""
        App.get_running_app().root.current = "menu"


class GameOverScreen(Screen):
    """Game-over summary screen with restart/menu actions."""

    summary_text = StringProperty("Game Over")

    def on_enter(self):
        if hasattr(self, 'ids') and 'summary_label' in self.ids:
            self.ids['summary_label'].text = self.summary_text

    def restart_game(self):
        app = App.get_running_app()
        app.root.current = "menu"
        app.root.get_screen("menu").start_game()

    def go_menu(self):
        App.get_running_app().root.current = "menu"

    def open_leaderboard(self):
        App.get_running_app().root.current = "leaderboard"


class SettingsScreen(Screen):
    """Settings screen."""
    
    def on_enter(self):
        app = App.get_running_app()
        if hasattr(self, 'ids') and 'sound_toggle' in self.ids:
            sound_enabled = app.save_manager.get_nested("settings.sound_enabled", True)
            self.ids['sound_toggle'].text = "Sound: ON" if sound_enabled else "Sound: OFF"
        if hasattr(self, 'ids') and 'sensitivity_label' in self.ids:
            current = app.save_manager.get_nested("settings.control_sensitivity", 1.0)
            self.ids['sensitivity_label'].text = f"Swipe Sensitivity: {current:.2f}"
        if hasattr(self, 'ids') and 'vibration_toggle' in self.ids:
            vib_enabled = app.save_manager.get_nested("settings.vibration_enabled", True)
            self.ids['vibration_toggle'].text = "Vibration: ON" if vib_enabled else "Vibration: OFF"
        if hasattr(self, 'ids') and 'skin_label' in self.ids:
            selected = app.progression.get_selected_skin()
            skin_name = constants.SNAKE_SKINS.get(selected, {"name": selected}).get("name", selected)
            self.ids['skin_label'].text = f"Snake Skin: {skin_name}"
        if hasattr(self, 'ids') and 'speed_label' in self.ids:
            speed_mode = app.progression.get_speed_mode()
            speed_display = speed_mode.capitalize()
            self.ids['speed_label'].text = f"Game Speed: {speed_display}"

    def toggle_sound(self):
        """Toggle sound."""
        app = App.get_running_app()
        current = app.save_manager.get_nested("settings.sound_enabled", True)
        updated = not current
        app.sound_manager.enabled = updated
        app.save_manager.set_nested("settings.sound_enabled", updated)
        app.save_manager.save()
        if hasattr(self, 'ids') and 'sound_toggle' in self.ids:
            self.ids['sound_toggle'].text = "Sound: ON" if updated else "Sound: OFF"

    def toggle_vibration(self):
        """Toggle vibration feedback setting."""
        app = App.get_running_app()
        current = app.save_manager.get_nested("settings.vibration_enabled", True)
        updated = not current
        app.save_manager.set_nested("settings.vibration_enabled", updated)
        app.save_manager.save()
        if hasattr(self, 'ids') and 'vibration_toggle' in self.ids:
            self.ids['vibration_toggle'].text = "Vibration: ON" if updated else "Vibration: OFF"

    def reset_progress(self):
        """Reset all progress."""
        app = App.get_running_app()
        app.progression.reset_progress()
        if hasattr(self, 'ids') and 'status_label' in self.ids:
            self.ids.status_label.text = "Progress reset!"

    def adjust_sensitivity(self, delta: float):
        """Increase or decrease swipe sensitivity tuning."""
        app = App.get_running_app()
        current = app.save_manager.get_nested("settings.control_sensitivity", 1.0)
        updated = min(2.0, max(0.5, current + delta))
        app.save_manager.set_nested("settings.control_sensitivity", round(updated, 2))
        app.save_manager.save()
        if hasattr(self, 'ids') and 'sensitivity_label' in self.ids:
            self.ids['sensitivity_label'].text = f"Swipe Sensitivity: {updated:.2f}"

    def cycle_snake_skin(self):
        """Cycle through unlocked snake skins."""
        app = App.get_running_app()
        unlocked = app.progression.get_unlocked_skins()
        if not unlocked:
            return

        unlocked_sorted = sorted(unlocked, key=lambda skin_id: constants.SNAKE_SKINS.get(skin_id, {}).get("name", skin_id))
        current = app.progression.get_selected_skin()
        if current not in unlocked_sorted:
            next_skin = unlocked_sorted[0]
        else:
            idx = unlocked_sorted.index(current)
            next_skin = unlocked_sorted[(idx + 1) % len(unlocked_sorted)]

        app.progression.set_selected_skin(next_skin)
        skin_name = constants.SNAKE_SKINS.get(next_skin, {"name": next_skin}).get("name", next_skin)
        if hasattr(self, 'ids') and 'skin_label' in self.ids:
            self.ids['skin_label'].text = f"Snake Skin: {skin_name}"

    def cycle_speed_mode(self):
        """Cycle through available speed modes (Slow -> Medium -> Fast -> Slow)."""
        app = App.get_running_app()
        current = app.progression.get_speed_mode()
        modes = list(constants.SPEED_MODES.keys())
        if current not in modes:
            next_mode = modes[0]
        else:
            idx = modes.index(current)
            next_mode = modes[(idx + 1) % len(modes)]
        
        app.progression.set_speed_mode(next_mode)
        speed_display = next_mode.capitalize()
        if hasattr(self, 'ids') and 'speed_label' in self.ids:
            self.ids['speed_label'].text = f"Game Speed: {speed_display}"

    def go_back(self):
        """Return to menu."""
        App.get_running_app().root.current = "menu"


class SnakeGameApp(App):
    """Main application."""
    
    title = "Snake Game Pro"

    def build(self):
        # Initialize core systems
        self.save_manager = SaveManager()
        self.progression = ProgressionSystem(self.save_manager)
        self.sound_manager = SoundManager()
        self.input_handler = InputHandler()
        self.game_controller = GameController(self.progression, self.input_handler)
        self.daily_rewards = DailyRewardSystem(self.save_manager)
        self.revive_system = ReviveSystem(self.save_manager)
        # Ads are temporarily disabled. Keep this hook for future integration.
        # self.ads_manager = AdsManager(self.save_manager)
        self.ads_manager = None
        self.local_leaderboard = LocalLeaderboard(self.save_manager)
        self.death_counter = 0
        self._revived_this_run = False
        self._revive_popup = None

        # Wire up callbacks
        self.game_controller.on_food_eaten = self._on_food_eaten
        self.game_controller.on_game_over = self._on_game_over

        # Create screen manager
        sm = ScreenManager(transition=FadeTransition())
        
        # Build UI programmatically
        menu_screen = self._build_menu_screen()
        game_screen = self._build_game_screen()
        progression_screen = self._build_progression_screen()
        leaderboard_screen = self._build_leaderboard_screen()
        game_over_screen = self._build_game_over_screen()
        settings_screen = self._build_settings_screen()
        
        sm.add_widget(menu_screen)
        sm.add_widget(game_screen)
        sm.add_widget(progression_screen)
        sm.add_widget(leaderboard_screen)
        sm.add_widget(game_over_screen)
        sm.add_widget(settings_screen)

        return sm

    def _build_menu_screen(self):
        """Build a fantasy-epic PC style menu dashboard with animated premium effects."""
        screen = MenuScreen(name="menu")

        root_layout = BoxLayout(orientation="vertical", padding=[14, 12], spacing=8)

        animated_panels = []
        animated_buttons = []
        animated_snakes = []
        animation_time = {"value": 0.0}

        def apply_panel_style(widget, fill_rgba, border_rgba, radius=16):
            with widget.canvas.before:
                shadow_color = Color(0.0, 0.0, 0.0, 0.35)
                shadow_rect = RoundedRectangle(radius=[radius])
                panel_fill = Color(*fill_rgba)
                panel_rect = RoundedRectangle(radius=[radius])
                top_highlight = Color(1.0, 1.0, 1.0, 0.08)
                highlight_rect = RoundedRectangle(radius=[radius])
                border_color = Color(*border_rgba)
                border_line = Line(width=1.6)

            def update_panel(*_):
                x_pos, y_pos = widget.pos
                width, height = widget.size
                shadow_rect.pos = (x_pos + 2, y_pos - 3)
                shadow_rect.size = (width, height)
                panel_rect.pos = (x_pos, y_pos)
                panel_rect.size = (width, height)
                highlight_rect.pos = (x_pos + 1, y_pos + height * 0.56)
                highlight_rect.size = (max(0.0, width - 2), max(0.0, height * 0.40))
                border_line.rounded_rectangle = (x_pos, y_pos, width, height, radius)

            widget.bind(pos=update_panel, size=update_panel)
            update_panel()

            animated_panels.append(border_color)

        def style_button(button, base_rgba, edge_rgba, radius=10):
            button.background_normal = ""
            button.background_down = ""
            button.background_color = (0, 0, 0, 0)

            with button.canvas.before:
                shadow_color = Color(0.0, 0.0, 0.0, 0.40)
                shadow_rect = RoundedRectangle(radius=[radius])
                lower_body = Color(base_rgba[0] * 0.55, base_rgba[1] * 0.55, base_rgba[2] * 0.55, 0.95)
                lower_rect = RoundedRectangle(radius=[radius])
                upper_body = Color(*base_rgba)
                upper_rect = RoundedRectangle(radius=[radius])
                top_edge = Color(1.0, 1.0, 1.0, 0.10)
                top_rect = RoundedRectangle(radius=[radius])
                border_color = Color(*edge_rgba)
                border = Line(width=1.6)

            def update_button_canvas(*_):
                x_pos, y_pos = button.pos
                width, height = button.size
                shadow_rect.pos = (x_pos + 2, y_pos - 3)
                shadow_rect.size = (width, height)
                lower_rect.pos = (x_pos, y_pos)
                lower_rect.size = (width, height)
                upper_rect.pos = (x_pos, y_pos + height * 0.12)
                upper_rect.size = (width, height * 0.80)
                top_rect.pos = (x_pos + 1, y_pos + height * 0.66)
                top_rect.size = (max(0.0, width - 2), max(0.0, height * 0.20))
                border.rounded_rectangle = (x_pos, y_pos, width, height, radius)

            def on_press(_):
                upper_body.a = 0.85
                shadow_color.a = 0.25

            def on_release(_):
                upper_body.a = base_rgba[3]
                shadow_color.a = 0.40

            button.bind(pos=update_button_canvas, size=update_button_canvas)
            button.bind(on_press=on_press, on_release=on_release)
            update_button_canvas()

            animated_buttons.append(border_color)

        with root_layout.canvas.before:
            bg_color = Color(0.03, 0.05, 0.12, 1.0)
            bg_rect = Rectangle()
            gradient_color = Color(0.11, 0.22, 0.42, 0.36)
            gradient_rect = Rectangle()
            depth_color = Color(0.92, 0.72, 0.23, 0.07)
            depth_rect = Rectangle()

            snake_colors = [
                (0.22, 0.77, 0.58, 0.20),
                (0.23, 0.62, 0.95, 0.18),
                (0.94, 0.78, 0.30, 0.16),
            ]
            for color_rgba in snake_colors:
                body_color = Color(*color_rgba)
                body_line = Line(points=[], width=3.0)
                head_color = Color(min(1.0, color_rgba[0] + 0.15), min(1.0, color_rgba[1] + 0.15), min(1.0, color_rgba[2] + 0.15), color_rgba[3] + 0.08)
                head_shape = Ellipse(size=(11, 11))
                eye_color = Color(0.98, 0.98, 1.0, color_rgba[3] + 0.15)
                eye_shape = Ellipse(size=(2.2, 2.2))
                animated_snakes.append((body_color, body_line, head_shape, eye_shape))

        with root_layout.canvas.after:
            frame_color = Color(0.97, 0.79, 0.29, 0.30)
            frame_line = Line(width=1.1)

        def update_root_canvas(*_):
            bg_rect.pos = root_layout.pos
            bg_rect.size = root_layout.size
            gradient_rect.pos = root_layout.pos
            gradient_rect.size = root_layout.size
            depth_rect.pos = (root_layout.x, root_layout.y + root_layout.height * 0.34)
            depth_rect.size = (root_layout.width, root_layout.height * 0.66)
            frame_line.rounded_rectangle = (root_layout.x + 2, root_layout.y + 2, root_layout.width - 4, root_layout.height - 4, 14)

        root_layout.bind(pos=update_root_canvas, size=update_root_canvas)
        update_root_canvas()

        top_bar = BoxLayout(orientation="vertical", size_hint_y=0.14, padding=[2, 4], spacing=1)
        title = Label(
            text="[b][color=5fd9ff]SNAKE LEGENDS[/color][/b]",
            markup=True,
            font_size="35sp",
            bold=True,
            color=(0.95, 0.96, 1.0, 1.0),
            outline_width=1,
            outline_color=(0.15, 0.28, 0.45, 0.65),
            size_hint_y=0.72,
        )
        subtitle = Label(
            text="[color=e8b83d]Calm Command Deck[/color]",
            markup=True,
            font_size="12sp",
            color=(0.90, 0.82, 0.58, 1.0),
            size_hint_y=0.28,
        )
        top_bar.add_widget(title)
        top_bar.add_widget(subtitle)
        root_layout.add_widget(top_bar)

        dashboard = BoxLayout(orientation="horizontal", size_hint_y=0.76, spacing=8)
        left_column = BoxLayout(orientation="vertical", spacing=7, size_hint_x=0.56)
        right_column = BoxLayout(orientation="vertical", spacing=7, size_hint_x=0.44)

        mode_panel = BoxLayout(orientation="vertical", size_hint_y=0.21, padding=[10, 7], spacing=5)
        apply_panel_style(mode_panel, (0.10, 0.14, 0.24, 0.70), (0.42, 0.76, 1.0, 0.48))
        mode_panel.add_widget(Label(
            text="[b][color=7ec6ff]MODE SELECTOR[/color][/b]",
            markup=True,
            font_size="10sp",
            size_hint_y=0.34,
        ))
        spinner = Spinner(
            text="Classic",
            values=("Classic", "No Wall", "Time Attack", "Hardcore"),
            size_hint_y=0.66,
            background_color=(0.09, 0.13, 0.22, 0.95),
            color=(0.93, 0.97, 1.0, 1.0),
            font_size="13sp",
        )
        spinner.id = "mode_spinner"
        mode_panel.add_widget(spinner)

        start_button = Button(
            text="[b]PLAY MATCH[/b]\n[size=11][ENTER] Start[/size]",
            markup=True,
            size_hint_y=0.23,
            font_size="16sp",
            color=(0.97, 0.99, 1.0, 1.0),
        )
        style_button(start_button, (0.24, 0.43, 0.80, 1.0), (0.96, 0.80, 0.34, 0.62), radius=12)
        start_button.bind(on_press=lambda _: screen.start_game())

        action_grid = BoxLayout(orientation="horizontal", size_hint_y=0.20, spacing=7)
        btn_scores = Button(
            text="[b]SCORES[/b]\n[size=11][F2][/size]",
            markup=True,
            font_size="12sp",
            color=(0.96, 0.98, 1.0, 1.0),
        )
        style_button(btn_scores, (0.16, 0.27, 0.52, 1.0), (0.86, 0.92, 1.0, 0.56))
        btn_scores.bind(on_press=lambda _: screen.show_leaderboard())

        btn_settings = Button(
            text="[b]SETTINGS[/b]\n[size=11][F3][/size]",
            markup=True,
            font_size="12sp",
            color=(0.97, 0.99, 1.0, 1.0),
        )
        style_button(btn_settings, (0.22, 0.19, 0.42, 1.0), (0.88, 0.75, 1.0, 0.56))
        btn_settings.bind(on_press=lambda _: screen.show_settings())

        action_grid.add_widget(btn_scores)
        action_grid.add_widget(btn_settings)

        stats_panel = BoxLayout(orientation="horizontal", size_hint_y=0.18, padding=[10, 7], spacing=8)
        apply_panel_style(stats_panel, (0.09, 0.13, 0.22, 0.72), (0.95, 0.78, 0.32, 0.42))
        high_score_label = Label(
            text="🏆 High Score: 0",
            font_size="11sp",
            color=(0.99, 0.91, 0.58, 1.0),
            bold=True,
            halign="left",
            valign="middle",
        )
        high_score_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        high_score_label.id = "high_score_label"
        level_label = Label(
            text="⭐ Level: 1",
            font_size="11sp",
            color=(0.77, 0.88, 1.0, 1.0),
            bold=True,
            halign="left",
            valign="middle",
        )
        level_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        level_label.id = "level_label"
        stats_panel.add_widget(high_score_label)
        stats_panel.add_widget(level_label)

        left_column.add_widget(mode_panel)
        left_column.add_widget(start_button)
        left_column.add_widget(action_grid)
        left_column.add_widget(stats_panel)

        name_panel = BoxLayout(orientation="vertical", size_hint_y=0.21, padding=[10, 7], spacing=5)
        apply_panel_style(name_panel, (0.12, 0.14, 0.23, 0.74), (0.98, 0.81, 0.33, 0.45))
        name_panel.add_widget(Label(
            text="[b][color=f0c55d]PILOT TAG[/color][/b]",
            markup=True,
            font_size="10sp",
            size_hint_y=0.34,
        ))
        name_row = BoxLayout(size_hint_y=0.66, spacing=6)
        name_input = TextInput(
            text="Player",
            multiline=False,
            size_hint_x=0.72,
            background_color=(0.06, 0.10, 0.17, 1.0),
            foreground_color=(0.90, 0.96, 1.0, 1.0),
            cursor_color=(0.95, 0.84, 0.41, 1.0),
            font_size="13sp",
        )
        name_input.id = "name_input"
        save_name_btn = Button(
            text="[b]SAVE[/b]",
            markup=True,
            size_hint_x=0.28,
            font_size="11sp",
            color=(0.97, 0.99, 1.0, 1.0),
        )
        style_button(save_name_btn, (0.32, 0.28, 0.14, 1.0), (0.98, 0.83, 0.41, 0.60), radius=9)
        save_name_btn.bind(on_press=lambda _: screen.save_player_name())
        name_row.add_widget(name_input)
        name_row.add_widget(save_name_btn)
        name_panel.add_widget(name_row)

        reward_panel = BoxLayout(orientation="vertical", size_hint_y=0.21, padding=[10, 7], spacing=5)
        apply_panel_style(reward_panel, (0.19, 0.16, 0.08, 0.72), (1.0, 0.84, 0.36, 0.54))
        daily_label = Label(
            text="🎁 Daily reward online",
            font_size="11sp",
            color=(0.99, 0.91, 0.58, 1.0),
            bold=True,
            size_hint_y=0.42,
        )
        daily_label.id = "daily_label"
        btn_daily = Button(
            text="[b]CLAIM REWARD[/b]\n[size=10][F4][/size]",
            markup=True,
            size_hint_y=0.58,
            font_size="11sp",
            color=(0.97, 0.99, 1.0, 1.0),
        )
        style_button(btn_daily, (0.50, 0.35, 0.10, 1.0), (1.0, 0.87, 0.39, 0.66), radius=10)
        btn_daily.bind(on_press=lambda _: screen.claim_daily_reward())
        reward_panel.add_widget(daily_label)
        reward_panel.add_widget(btn_daily)

        btn_progress = Button(
            text="[b]PROGRESSION[/b]\n[size=10][F1] Rank and unlocks[/size]",
            markup=True,
            size_hint_y=0.20,
            font_size="12sp",
            color=(0.97, 0.99, 1.0, 1.0),
        )
        style_button(btn_progress, (0.14, 0.31, 0.46, 1.0), (0.64, 0.90, 1.0, 0.58), radius=10)
        btn_progress.bind(on_press=lambda _: screen.show_progression())

        hotkey_panel = BoxLayout(orientation="vertical", size_hint_y=0.18, padding=[10, 7], spacing=2)
        apply_panel_style(hotkey_panel, (0.09, 0.12, 0.20, 0.72), (0.68, 0.80, 1.0, 0.36))
        hotkey_panel.add_widget(Label(
            text="[b][color=9abfff]COMMAND HINTS[/color][/b]",
            markup=True,
            font_size="10sp",
            size_hint_y=0.30,
        ))
        hotkey_panel.add_widget(Label(
            text="[size=11][color=dde6ff]WASD move   |   Space pause\nF1 progression, F2 scores, F3 settings[/color][/size]",
            markup=True,
            font_size="10sp",
            halign="center",
            valign="middle",
            size_hint_y=0.70,
        ))

        right_column.add_widget(name_panel)
        right_column.add_widget(reward_panel)
        right_column.add_widget(btn_progress)
        right_column.add_widget(hotkey_panel)

        dashboard.add_widget(left_column)
        dashboard.add_widget(right_column)
        root_layout.add_widget(dashboard)

        footer = BoxLayout(size_hint_y=0.10, spacing=8)
        footer_left = Label(
            text="[size=11][color=8ca6d9]Server: Local Arena | Build: Pro[/color][/size]",
            markup=True,
            halign="left",
            valign="middle",
        )
        footer_left.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        footer_right = Label(
            text="[size=11][color=e4bf58]Season Rank UI Active[/color][/size]",
            markup=True,
            halign="right",
            valign="middle",
        )
        footer_right.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        footer.add_widget(footer_left)
        footer.add_widget(footer_right)
        root_layout.add_widget(footer)

        def animate_menu(dt):
            animation_time["value"] += dt
            t_value = animation_time["value"]

            gradient_color.a = 0.25 + (math.sin(t_value * 0.30) + 1.0) * 0.03
            depth_color.a = 0.05 + (math.sin(t_value * 0.45 + 1.3) + 1.0) * 0.012
            frame_color.a = 0.20 + (math.sin(t_value * 0.55) + 1.0) * 0.05

            app = App.get_running_app()
            audio_factor = 1.0 if app and app.sound_manager.enabled else 0.72

            # Calm background snakes: slow horizontal drift with gentle wave body.
            snake_paths = [
                (0.27, 0.12, 0.22, 1.00),
                (0.62, 0.10, 0.20, -1.00),
                (0.84, 0.14, 0.24, 1.00),
            ]
            for index, (_, line_shape, head_shape, eye_shape) in enumerate(animated_snakes):
                y_ratio, amplitude_ratio, speed, direction = snake_paths[index]
                base_y = root_layout.y + root_layout.height * y_ratio
                amplitude = root_layout.height * amplitude_ratio
                wave_step = root_layout.width * 0.07
                points = []
                for point_index in range(18):
                    x_ratio = point_index / 17
                    travel = ((x_ratio + t_value * speed * 0.03 * direction) % 1.1) - 0.05
                    x_pos = root_layout.x + root_layout.width * travel
                    phase = (point_index * 0.65) + (t_value * speed * 0.85)
                    y_pos = base_y + math.sin(phase) * amplitude
                    points.extend([x_pos, y_pos])
                line_shape.points = points

                head_x = points[-2]
                head_y = points[-1]
                head_shape.pos = (head_x - 5.5, head_y - 5.5)
                eye_shape.pos = (head_x + 1.8, head_y + 1.6)

            for index, border_color in enumerate(animated_panels):
                border_color.a = 0.22 + (math.sin(t_value * 0.75 + index * 0.4) + 1.0) * 0.045 * audio_factor

            for index, border_color in enumerate(animated_buttons):
                border_color.a = 0.34 + (math.sin(t_value * 1.0 + index * 0.5) + 1.0) * 0.06 * audio_factor

            return True

        animation_event = Clock.schedule_interval(animate_menu, 1.0 / 30.0)

        def stop_animation(*_):
            if animation_event is not None:
                animation_event.cancel()

        screen.bind(on_leave=stop_animation)
        screen.add_widget(root_layout)
        screen.ids = {
            "mode_spinner": spinner,
            "name_input": name_input,
            "daily_label": daily_label,
            "high_score_label": high_score_label,
            "level_label": level_label,
        }
        return screen

    def _build_game_screen(self):
        """Build game screen with compact PC-style HUD and controls."""
        screen = GameScreen(name="game")
        layout = BoxLayout(orientation="vertical", padding=[10, 8], spacing=6)

        with layout.canvas.before:
            Color(0.03, 0.05, 0.11, 1.0)
            bg_rect = Rectangle(pos=layout.pos, size=layout.size)
            Color(0.10, 0.17, 0.30, 0.18)
            glow_rect = Rectangle(pos=layout.pos, size=layout.size)

        def _update_layout_bg(*_):
            bg_rect.pos = layout.pos
            bg_rect.size = layout.size
            glow_rect.pos = layout.pos
            glow_rect.size = layout.size

        layout.bind(pos=_update_layout_bg, size=_update_layout_bg)

        hud = BoxLayout(size_hint_y=0.10, spacing=6, padding=[8, 6])
        with hud.canvas.before:
            Color(0.08, 0.11, 0.19, 0.92)
            hud_rect = RoundedRectangle(pos=hud.pos, size=hud.size, radius=[8])
            Color(0.38, 0.62, 0.95, 0.35)
            hud_line = Line(rounded_rectangle=(hud.x, hud.y, hud.width, hud.height, 8), width=1.2)

        def _update_hud(*_):
            hud_rect.pos = hud.pos
            hud_rect.size = hud.size
            hud_line.rounded_rectangle = (hud.x, hud.y, hud.width, hud.height, 8)

        hud.bind(pos=_update_hud, size=_update_hud)

        score_label = Label(text=screen.score_text, font_size="13sp", color=(0.95, 0.98, 1, 1), bold=True)
        high_label = Label(text=screen.high_score_text, font_size="13sp", color=(0.95, 0.90, 0.55, 1), bold=True)
        combo_label = Label(text=screen.combo_text, font_size="13sp", color=(0.68, 0.87, 1, 1), bold=True)
        mode_label = Label(text=screen.mode_text, font_size="13sp", color=(0.82, 0.92, 1, 1), bold=True)
        hud.add_widget(score_label)
        hud.add_widget(high_label)
        hud.add_widget(combo_label)
        hud.add_widget(mode_label)
        layout.add_widget(hud)

        board = GameBoard(size_hint_y=0.80)
        board.id = 'game_board'
        layout.add_widget(board)

        controls = BoxLayout(size_hint_y=0.10, spacing=8, padding=[8, 2])
        btn_pause = Button(text="[b]PAUSE / RESUME[/b]", markup=True, font_size="12sp")
        btn_pause.background_normal = ""
        btn_pause.background_down = ""
        btn_pause.background_color = (0.12, 0.19, 0.35, 1.0)
        btn_pause.bind(on_press=lambda x: App.get_running_app().game_controller.pause() if not App.get_running_app().game_controller.current_mode.is_paused else App.get_running_app().game_controller.resume())

        btn_menu = Button(text="[b]MAIN MENU[/b]", markup=True, font_size="12sp")
        btn_menu.background_normal = ""
        btn_menu.background_down = ""
        btn_menu.background_color = (0.22, 0.17, 0.36, 1.0)
        btn_menu.bind(on_press=lambda x: screen.go_menu())

        controls.add_widget(btn_pause)
        controls.add_widget(btn_menu)
        layout.add_widget(controls)

        screen.ids = {
            'game_board': board,
            'score_label': score_label,
            'high_label': high_label,
            'combo_label': combo_label,
            'mode_label': mode_label,
        }
        screen.add_widget(layout)
        return screen

    def _build_progression_screen(self):
        """Build progression screen with card-like information rows."""
        screen = ProgressionScreen(name="progression")
        layout = BoxLayout(orientation="vertical", padding=[12, 10], spacing=8)

        with layout.canvas.before:
            Color(0.03, 0.05, 0.11, 1.0)
            Rectangle(pos=layout.pos, size=layout.size)

        header = Label(
            text="[b][color=82c6ff]PLAYER PROGRESSION[/color][/b]",
            markup=True,
            font_size="22sp",
            size_hint_y=0.14,
        )
        layout.add_widget(header)

        level_label = Label(text=screen.level_text, font_size="16sp", size_hint_y=0.12, color=(0.93, 0.97, 1, 1), bold=True)
        xp_label = Label(text=screen.xp_text, font_size="14sp", size_hint_y=0.10, color=(0.85, 0.91, 1, 1))
        layout.add_widget(level_label)
        layout.add_widget(xp_label)

        def build_info_row(text, color_rgba):
            row = Label(text=text, font_size="13sp", size_hint_y=0.12, color=color_rgba, bold=True)
            return row

        skins_label = build_info_row("Snake Skins: 0/6", (0.92, 0.88, 0.56, 1))
        skins_label.id = 'skins_label'
        styles_label = build_info_row("Food Styles: 0/4", (0.73, 0.91, 1.0, 1))
        styles_label.id = 'styles_label'
        ach_label = build_info_row("Achievements: 0/8", (0.86, 0.80, 1.0, 1))
        ach_label.id = 'achievements_label'

        layout.add_widget(skins_label)
        layout.add_widget(styles_label)
        layout.add_widget(ach_label)
        layout.add_widget(Widget(size_hint_y=0.20))

        btn_back = Button(text="[b]BACK TO MENU[/b]", markup=True, size_hint_y=0.12, font_size="12sp")
        btn_back.background_normal = ""
        btn_back.background_down = ""
        btn_back.background_color = (0.14, 0.20, 0.36, 1.0)
        btn_back.bind(on_press=lambda x: screen.go_back())
        layout.add_widget(btn_back)

        screen.add_widget(layout)
        screen.ids = {
            'skins_label': skins_label,
            'styles_label': styles_label,
            'achievements_label': ach_label,
        }
        return screen

    def _build_leaderboard_screen(self):
        """Build leaderboard screen with a readable scoreboard panel."""
        screen = LeaderboardScreen(name="leaderboard")
        layout = BoxLayout(orientation="vertical", padding=[12, 10], spacing=8)

        with layout.canvas.before:
            Color(0.03, 0.05, 0.11, 1.0)
            Rectangle(pos=layout.pos, size=layout.size)

        title = Label(
            text="[b][color=8fd2ff]LEADERBOARD[/color][/b]",
            markup=True,
            font_size="24sp",
            size_hint_y=0.14,
        )
        layout.add_widget(title)

        panel = BoxLayout(orientation="vertical", size_hint_y=0.72, padding=[10, 8])
        with panel.canvas.before:
            Color(0.08, 0.11, 0.20, 0.95)
            panel_rect = RoundedRectangle(pos=panel.pos, size=panel.size, radius=[10])
            Color(0.43, 0.67, 0.98, 0.40)
            panel_border = Line(rounded_rectangle=(panel.x, panel.y, panel.width, panel.height, 10), width=1.2)

        def _update_panel(*_):
            panel_rect.pos = panel.pos
            panel_rect.size = panel.size
            panel_border.rounded_rectangle = (panel.x, panel.y, panel.width, panel.height, 10)

        panel.bind(pos=_update_panel, size=_update_panel)

        lb_label = Label(text=screen.leaderboard_text, font_size="13sp", halign="left", valign="top", color=(0.94, 0.97, 1.0, 1.0))
        lb_label.bind(size=lambda inst, _: setattr(inst, 'text_size', (inst.width * 0.95, None)))
        panel.add_widget(lb_label)
        layout.add_widget(panel)

        btn_back = Button(text="[b]BACK TO MENU[/b]", markup=True, size_hint_y=0.12, font_size="12sp")
        btn_back.background_normal = ""
        btn_back.background_down = ""
        btn_back.background_color = (0.14, 0.20, 0.36, 1.0)
        btn_back.bind(on_press=lambda x: screen.go_back())
        layout.add_widget(btn_back)

        screen.add_widget(layout)
        return screen

    def _build_settings_screen(self):
        """Build settings screen with grouped compact controls."""
        screen = SettingsScreen(name="settings")
        layout = BoxLayout(orientation="vertical", padding=[12, 10], spacing=8)

        with layout.canvas.before:
            Color(0.03, 0.05, 0.11, 1.0)
            Rectangle(pos=layout.pos, size=layout.size)

        title = Label(
            text="[b][color=8fd2ff]SETTINGS[/color][/b]",
            markup=True,
            font_size="22sp",
            size_hint_y=0.11,
        )
        layout.add_widget(title)

        def _make_row(label_text):
            row = BoxLayout(size_hint_y=0.095, spacing=6)
            label = Label(text=label_text, size_hint_x=0.36, font_size="12sp", color=(0.82, 0.91, 1, 1), halign="left")
            label.bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))
            row.add_widget(label)
            return row

        sound_box = _make_row("Sound")
        sound_toggle = Button(text="Sound: ON", size_hint_x=0.64, font_size="12sp")
        sound_toggle.background_normal = ""
        sound_toggle.background_down = ""
        sound_toggle.background_color = (0.12, 0.19, 0.35, 1.0)
        sound_toggle.id = 'sound_toggle'
        sound_toggle.bind(on_press=lambda x: screen.toggle_sound())
        sound_box.add_widget(sound_toggle)
        layout.add_widget(sound_box)

        vibration_box = _make_row("Haptics")
        vibration_toggle = Button(text="Vibration: ON", size_hint_x=0.64, font_size="12sp")
        vibration_toggle.background_normal = ""
        vibration_toggle.background_down = ""
        vibration_toggle.background_color = (0.12, 0.19, 0.35, 1.0)
        vibration_toggle.id = 'vibration_toggle'
        vibration_toggle.bind(on_press=lambda x: screen.toggle_vibration())
        vibration_box.add_widget(vibration_toggle)
        layout.add_widget(vibration_box)

        speed_label = Label(text="Game Speed: Medium", size_hint_y=0.09, font_size="12sp", color=(0.94, 0.90, 0.58, 1.0), bold=True)
        speed_label.id = 'speed_label'
        layout.add_widget(speed_label)

        speed_btn = Button(text="Change Game Speed", size_hint_y=0.09, font_size="12sp")
        speed_btn.background_normal = ""
        speed_btn.background_down = ""
        speed_btn.background_color = (0.15, 0.24, 0.41, 1.0)
        speed_btn.bind(on_press=lambda x: screen.cycle_speed_mode())
        layout.add_widget(speed_btn)

        sensitivity_label = Label(text="Swipe Sensitivity: 1.00", size_hint_y=0.09, font_size="12sp", color=(0.86, 0.94, 1.0, 1.0), bold=True)
        sensitivity_label.id = 'sensitivity_label'
        layout.add_widget(sensitivity_label)

        sensitivity_controls = BoxLayout(size_hint_y=0.09, spacing=8)
        less_btn = Button(text="- Less", font_size="11sp")
        less_btn.background_normal = ""
        less_btn.background_down = ""
        less_btn.background_color = (0.17, 0.22, 0.33, 1.0)
        less_btn.bind(on_press=lambda x: screen.adjust_sensitivity(0.1))
        more_btn = Button(text="+ More", font_size="11sp")
        more_btn.background_normal = ""
        more_btn.background_down = ""
        more_btn.background_color = (0.17, 0.22, 0.33, 1.0)
        more_btn.bind(on_press=lambda x: screen.adjust_sensitivity(-0.1))
        sensitivity_controls.add_widget(less_btn)
        sensitivity_controls.add_widget(more_btn)
        layout.add_widget(sensitivity_controls)

        skin_label = Label(text="Snake Skin: Classic", size_hint_y=0.09, font_size="12sp", color=(0.92, 0.86, 0.60, 1.0), bold=True)
        skin_label.id = 'skin_label'
        layout.add_widget(skin_label)

        skin_btn = Button(text="Change Snake Skin", size_hint_y=0.09, font_size="12sp")
        skin_btn.background_normal = ""
        skin_btn.background_down = ""
        skin_btn.background_color = (0.22, 0.17, 0.36, 1.0)
        skin_btn.bind(on_press=lambda x: screen.cycle_snake_skin())
        layout.add_widget(skin_btn)

        status_label = Label(text="", size_hint_y=0.06, font_size="11sp", color=(0.95, 0.78, 0.45, 1.0))
        status_label.id = 'status_label'
        layout.add_widget(status_label)

        btn_row = BoxLayout(size_hint_y=0.11, spacing=8)
        btn_reset = Button(text="Reset Progress", font_size="12sp")
        btn_reset.background_normal = ""
        btn_reset.background_down = ""
        btn_reset.background_color = (0.36, 0.15, 0.17, 1.0)
        btn_reset.bind(on_press=lambda x: screen.reset_progress())
        btn_back = Button(text="Back", font_size="12sp")
        btn_back.background_normal = ""
        btn_back.background_down = ""
        btn_back.background_color = (0.14, 0.20, 0.36, 1.0)
        btn_back.bind(on_press=lambda x: screen.go_back())
        btn_row.add_widget(btn_reset)
        btn_row.add_widget(btn_back)
        layout.add_widget(btn_row)

        screen.add_widget(layout)
        screen.ids = {
            'sensitivity_label': sensitivity_label,
            'sound_toggle': sound_toggle,
            'vibration_toggle': vibration_toggle,
            'skin_label': skin_label,
            'speed_label': speed_label,
            'status_label': status_label,
        }
        return screen

    def _build_game_over_screen(self):
        """Build game-over screen with focused summary and actions."""
        screen = GameOverScreen(name="game_over")
        layout = BoxLayout(orientation="vertical", padding=[12, 10], spacing=8)

        with layout.canvas.before:
            Color(0.03, 0.05, 0.11, 1.0)
            Rectangle(pos=layout.pos, size=layout.size)

        title = Label(
            text="[b][color=f3b164]RUN ENDED[/color][/b]",
            markup=True,
            font_size="28sp",
            size_hint_y=0.18,
        )
        layout.add_widget(title)

        summary_panel = BoxLayout(orientation="vertical", size_hint_y=0.42, padding=[10, 8])
        with summary_panel.canvas.before:
            Color(0.11, 0.09, 0.08, 0.92)
            panel_rect = RoundedRectangle(pos=summary_panel.pos, size=summary_panel.size, radius=[10])
            Color(0.93, 0.64, 0.29, 0.45)
            panel_line = Line(rounded_rectangle=(summary_panel.x, summary_panel.y, summary_panel.width, summary_panel.height, 10), width=1.2)

        def _update_summary(*_):
            panel_rect.pos = summary_panel.pos
            panel_rect.size = summary_panel.size
            panel_line.rounded_rectangle = (summary_panel.x, summary_panel.y, summary_panel.width, summary_panel.height, 10)

        summary_panel.bind(pos=_update_summary, size=_update_summary)

        summary_label = Label(text=screen.summary_text, font_size="13sp", color=(0.95, 0.96, 1, 1), halign="left", valign="middle")
        summary_label.bind(size=lambda inst, _: setattr(inst, 'text_size', (inst.width * 0.95, inst.height * 0.95)))
        summary_label.id = 'summary_label'
        summary_panel.add_widget(summary_label)
        layout.add_widget(summary_panel)

        restart_btn = Button(text="[b]PLAY AGAIN[/b]", markup=True, size_hint_y=0.14, font_size="13sp")
        restart_btn.background_normal = ""
        restart_btn.background_down = ""
        restart_btn.background_color = (0.14, 0.35, 0.22, 1.0)
        restart_btn.bind(on_press=lambda x: screen.restart_game())
        layout.add_widget(restart_btn)

        row = BoxLayout(size_hint_y=0.14, spacing=8)
        menu_btn = Button(text="Main Menu", font_size="12sp")
        menu_btn.background_normal = ""
        menu_btn.background_down = ""
        menu_btn.background_color = (0.14, 0.20, 0.36, 1.0)
        menu_btn.bind(on_press=lambda x: screen.go_menu())

        lb_btn = Button(text="Leaderboard", font_size="12sp")
        lb_btn.background_normal = ""
        lb_btn.background_down = ""
        lb_btn.background_color = (0.22, 0.17, 0.36, 1.0)
        lb_btn.bind(on_press=lambda x: screen.open_leaderboard())

        row.add_widget(menu_btn)
        row.add_widget(lb_btn)
        layout.add_widget(row)

        screen.add_widget(layout)
        screen.ids = {'summary_label': summary_label}
        return screen

    def on_start(self):
        """Initialize services after app startup."""
        # Ads are disabled for now.
        # self.ads_manager.initialize(test_mode=True)
        # self.ads_manager.load_banner()
        print("[APP] Snake Game Pro initialized!")

    def _on_food_eaten(self, food_pos):
        """Callback when food is eaten."""
        self.sound_manager.play("eat")
        game_screen = self.root.get_screen("game")
        if hasattr(game_screen, 'ids') and 'game_board' in game_screen.ids:
            game_screen.ids['game_board'].spawn_particles(food_pos)

    def _on_game_over(self, score, high_score):
        """Callback when game ends."""
        self.sound_manager.play("game_over")
        self._vibrate(milliseconds=50)
        if self.root and self.root.has_screen("game"):
            self.root.get_screen("game").start_death_effect()
        self.death_counter += 1

        # Ads are disabled for now.
        # Offer one rewarded-ad revive per run when available.
        # if not self._revived_this_run and self.revive_system.can_revive() and self.ads_manager.should_show_ads():
        #     self._show_revive_prompt(score, high_score)
        #     return

        self._finalize_game_over(score, high_score)

    def _show_revive_prompt(self, score: int, high_score: int):
        """Show revive decision popup with ad-based continue."""
        if self._revive_popup is not None:
            return

        content = BoxLayout(orientation="vertical", spacing=8, padding=8)
        content.add_widget(Label(text="Continue this run once by watching a rewarded ad?"))

        controls = BoxLayout(size_hint_y=0.4, spacing=8)
        revive_btn = Button(text="Watch Ad & Revive")
        finish_btn = Button(text="Finish Run")
        controls.add_widget(revive_btn)
        controls.add_widget(finish_btn)
        content.add_widget(controls)

        popup = Popup(title="Revive", content=content, size_hint=(0.85, 0.35), auto_dismiss=False)
        self._revive_popup = popup

        def _finish(*_args):
            popup.dismiss()
            self._revive_popup = None
            self._finalize_game_over(score, high_score)

        def _revive(*_args):
            # Ads are disabled for now.
            # success = self.ads_manager.show_rewarded() and self.revive_system.use_revive()
            success = False
            popup.dismiss()
            self._revive_popup = None
            if success:
                self._revive_player()
                self._revived_this_run = True
            else:
                self._finalize_game_over(score, high_score)

        finish_btn.bind(on_press=_finish)
        revive_btn.bind(on_press=_revive)
        popup.open()

    def _finalize_game_over(self, score: int, high_score: int):
        """Persist stats, leaderboard entry, monetization cadence, and navigate to summary screen."""
        self.save_manager.save()

        player_name = self.save_manager.get_nested("player.name", "Player")
        mode = self.game_controller.current_mode.name.lower().replace(" ", "_")
        self.local_leaderboard.submit_score(player_name, mode, score)

        # Ads are disabled for now.
        # if self.ads_manager.should_show_ads() and self.death_counter % constants.SHOW_INTERSTITIAL_AFTER_DEATHS == 0:
        #     self.ads_manager.show_interstitial()

        if self.root and self.root.has_screen("game_over"):
            summary = (
                f"Mode: {self.game_controller.current_mode.name}\n"
                f"Score: {score}\n"
                f"High Score: {high_score}\n"
                f"Level: {self.progression.level}"
            )
            game_over_screen = self.root.get_screen("game_over")
            game_over_screen.summary_text = summary
            self.root.current = "game_over"

        print(f"[APP] Game Over! Score: {score}, High: {high_score}")

    def _revive_player(self):
        """Revive the player in-place once after a rewarded ad."""
        self.game_controller.current_mode.is_game_over = False
        self.game_controller.current_mode.is_paused = False
        self.game_controller.poison_active = False
        self.game_controller.poison_timer = 0.0
        self.game_controller.accumulator = 0.0
        self.game_controller.input_handler.reset()

        # Reset snake to a safe central lane to prevent immediate repeated deaths.
        start = (constants.BOARD_COLS // 2, constants.BOARD_ROWS // 2)
        self.game_controller.snake.reset(start, constants.START_LENGTH)

        # Respawn food away from snake/walls.
        self.game_controller.food.respawn(
            constants.BOARD_COLS,
            constants.BOARD_ROWS,
            self.game_controller.snake.occupied | self.game_controller.walls,
            self.game_controller.rng,
        )

    def _vibrate(self, milliseconds: int = 35):
        """Android vibration hook with safe fallback on desktop."""
        if not self.save_manager.get_nested("settings.vibration_enabled", True):
            return
        try:
            from plyer import vibrator

            vibrator.vibrate(time=milliseconds / 1000)
        except Exception:
            # No vibration service on desktop/testing environments.
            return


if __name__ == "__main__":
    SnakeGameApp().run()
