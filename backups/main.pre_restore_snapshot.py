"""Production-ready Snake game with multiple game modes, progression systems, and retention mechanics."""

import math
import os
import random
import sys
from pathlib import Path
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
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.floatlayout import FloatLayout
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


@dataclass(slots=True)
class FloatingText:
    """Transient world-space text that rises and fades."""
    label: Label
    x_pos: float
    y_pos: float
    velocity_y: float
    life: float
    total_life: float


class SoundManager:
    """Global sound manager."""
    
    def __init__(self):
        self.enabled = True
        self._sounds = {}
        self._sound_paths = {}
        self._current_music = None
        self._current_music_name = ""
        self.master_volume = 1.0
        self.sfx_volume = 1.0
        self.output_mode = "auto"
        self._load_sounds()

    def _load_sounds(self):
        """Load all game sounds."""
        sound_files = {
            "eat": constants.EAT_SOUND,
            "game_over": constants.GAME_OVER_SOUND,
            "click": constants.CLICK_SOUND,
            "ui_nav": constants.resource_path("assets", "sounds", "ui_nav.wav"),
            "bgm_meadow": constants.resource_path("assets", "sounds", "bgm_meadow.wav"),
            "bgm_underwater": constants.resource_path("assets", "sounds", "bgm_underwater.wav"),
            "bgm_iceland": constants.resource_path("assets", "sounds", "bgm_iceland.wav"),
            "bgm_desert": constants.resource_path("assets", "sounds", "bgm_desert.wav"),
            "bgm_soft": constants.resource_path("assets", "sounds", "bgm_soft.wav"),
        }
        for name, path in sound_files.items():
            resolved_path = self._resolve_sound_path(path)
            self._sound_paths[name] = resolved_path
            try:
                loaded = SoundLoader.load(resolved_path)
                self._sounds[name] = loaded
            except Exception:
                self._sounds[name] = None

    def _resolve_sound_path(self, preferred_path: str) -> str:
        """Pick an existing sound file by trying multiple common audio formats."""
        candidate = Path(preferred_path)
        suffix_order = [candidate.suffix, ".ogg", ".mp3", ".m4a", ".wav", ".mp4"]
        tried = set()
        for suffix in suffix_order:
            if suffix in tried:
                continue
            tried.add(suffix)
            option = candidate.with_suffix(suffix)
            if option.exists():
                return str(option)
        return str(candidate)

    def _play_windows_fallback(self, sound_name: str):
        """Fallback path for environments where Kivy audio backend is unavailable."""
        if sys.platform != "win32":
            return
        if self.master_volume * self.sfx_volume <= 0.0:
            return
        sound_path = self._sound_paths.get(sound_name)
        try:
            import winsound

            if sound_path and Path(sound_path).exists() and Path(sound_path).suffix.lower() == ".wav":
                winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                return

            # Guaranteed audible fallback tones for unsupported/failed audio file playback.
            if sound_name == "click":
                winsound.MessageBeep(winsound.MB_OK)
            elif sound_name == "eat":
                winsound.Beep(980, 70)
                winsound.Beep(1175, 70)
            elif sound_name == "game_over":
                winsound.Beep(520, 120)
                winsound.Beep(390, 180)
            else:
                winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass

    def set_volumes(self, master: float, sfx: float):
        """Set runtime audio volumes, clamped to [0.0, 1.0]."""
        self.master_volume = max(0.0, min(1.0, float(master)))
        self.sfx_volume = max(0.0, min(1.0, float(sfx)))

    def set_output_mode(self, mode: str):
        """Set output mode. Supported: auto, beep."""
        self.output_mode = mode if mode in {"auto", "beep"} else "auto"

    def play(self, sound_name: str):
        """Play a sound."""
        if not self.enabled or sound_name not in self._sounds:
            return
        if self.output_mode == "beep":
            self._play_windows_fallback(sound_name)
            return
        sound = self._sounds[sound_name]
        effective_volume = max(0.0, min(1.0, self.master_volume * self.sfx_volume))
        if sound:
            try:
                if hasattr(sound, "volume"):
                    sound.volume = effective_volume
                sound.stop()
                sound.play()
            except Exception:
                self._play_windows_fallback(sound_name)
        else:
            self._play_windows_fallback(sound_name)

    def play_music(self, sound_name: str):
        """Play looping background music (single active track)."""
        if not self.enabled or sound_name not in self._sounds:
            return
        if self.output_mode == "beep":
            return
        sound = self._sounds[sound_name]
        if not sound:
            return
        if self._current_music is sound and self._current_music_name == sound_name and getattr(sound, "state", "") == "play":
            return
        self.stop_music()
        try:
            if hasattr(sound, "loop"):
                sound.loop = True
            if hasattr(sound, "volume"):
                sound.volume = max(0.0, min(1.0, self.master_volume * 0.28))
            sound.play()
            self._current_music = sound
            self._current_music_name = sound_name
        except Exception:
            self._current_music = None
            self._current_music_name = ""

    def _music_track_for_theme(self, environment_theme: str) -> str:
        """Return best available background track key for the given environment."""
        theme_tracks = {
            "meadow": ["bgm_meadow", "bgm_soft"],
            "underwater": ["bgm_underwater", "bgm_meadow", "bgm_soft"],
            "iceland": ["bgm_iceland", "bgm_meadow", "bgm_soft"],
            "desert": ["bgm_desert", "bgm_meadow", "bgm_soft"],
        }
        candidates = theme_tracks.get(environment_theme, ["bgm_meadow", "bgm_soft"])
        for key in candidates:
            if self._sounds.get(key) is not None:
                return key
        return "bgm_soft"

    def play_environment_music(self, environment_theme: str):
        """Play environment-appropriate music track with graceful fallback."""
        track = self._music_track_for_theme(environment_theme)
        self.play_music(track)

    def stop_music(self):
        """Stop currently active background music track."""
        if self._current_music is None:
            return
        try:
            self._current_music.stop()
        except Exception:
            pass
        self._current_music = None
        self._current_music_name = ""


class GameBoard(Widget):
    """Game board renderer with particles and swipe input."""
    
    controller = ObjectProperty(allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._gesture_origin = None
        self._particles = []
        self._floating_texts = []
        self._shake_intensity = 0
        self._shake_timer = 0
        self._shake_duration = 0
        self._animation_time = 0.0
        self._quality_cache = "balanced"
        self._quality_cache_timer = 0.0
        self._theme_cache = "meadow"
        self._theme_cache_timer = 0.0
        self.bind(pos=self._request_redraw, size=self._request_redraw)

    def spawn_particles(self, cell):
        """Spawn particle burst at cell."""
        if len(self._particles) >= constants.MAX_PARTICLES:
            return

        cell_width = self.width / constants.BOARD_COLS if self.width > 0 else 1
        cell_height = self.height / constants.BOARD_ROWS if self.height > 0 else 1
        unit_size = min(cell_width, cell_height)
        
        center_x = self.x + cell[0] * cell_width + cell_width / 2
        center_y = self.y + cell[1] * cell_height + cell_height / 2

        spawn_count = min(constants.PARTICLE_COUNT, constants.MAX_PARTICLES - len(self._particles))
        for i in range(spawn_count):
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
        safe_duration = max(0.0, float(duration))
        self._shake_intensity = max(0.0, float(intensity))
        self._shake_duration = safe_duration
        self._shake_timer = safe_duration

    def spawn_floating_text(self, cell, text: str, color=(1.0, 0.94, 0.72, 1.0)):
        """Spawn a floating text at board-cell position."""
        if not text or self.width <= 0 or self.height <= 0:
            return

        while len(self._floating_texts) >= constants.MAX_FLOATING_TEXTS:
            oldest = self._floating_texts.pop(0)
            if oldest.label.parent is self:
                self.remove_widget(oldest.label)

        cell_width = self.width / constants.BOARD_COLS
        cell_height = self.height / constants.BOARD_ROWS
        center_x = self.x + cell[0] * cell_width + cell_width * 0.5
        center_y = self.y + cell[1] * cell_height + cell_height * 0.5

        label = Label(
            text=text,
            font_size="14sp",
            bold=True,
            size_hint=(None, None),
            color=color,
            opacity=1.0,
        )
        label.texture_update()
        label.size = (label.texture_size[0] + 10, label.texture_size[1] + 6)
        label.pos = (center_x - label.width * 0.5, center_y - label.height * 0.5)
        self.add_widget(label)

        self._floating_texts.append(
            FloatingText(
                label=label,
                x_pos=center_x,
                y_pos=center_y,
                velocity_y=max(26.0, cell_height * 1.0),
                life=1.05,
                total_life=1.05,
            )
        )

    def advance(self, dt):
        """Update particles and shake."""
        visual_dt = max(0.0, min(constants.VISUAL_DT_CAP, dt))
        self._animation_time += visual_dt
        self._quality_cache_timer = max(0.0, self._quality_cache_timer - visual_dt)
        self._theme_cache_timer = max(0.0, self._theme_cache_timer - visual_dt)
        # Update particles
        alive = []
        for p in self._particles:
            p.life -= visual_dt
            if p.life > 0:
                p.x_pos += p.velocity_x * visual_dt
                p.y_pos += p.velocity_y * visual_dt
                alive.append(p)
        self._particles = alive

        # Update floating texts
        active_texts = []
        for item in self._floating_texts:
            item.life -= visual_dt
            if item.life > 0:
                item.y_pos += item.velocity_y * visual_dt
                fade = item.life / item.total_life
                item.label.opacity = max(0.0, fade)
                item.label.pos = (item.x_pos - item.label.width * 0.5, item.y_pos - item.label.height * 0.5)
                active_texts.append(item)
            else:
                if item.label.parent is self:
                    self.remove_widget(item.label)
        self._floating_texts = active_texts

        # Update shake
        if self._shake_timer > 0:
            self._shake_timer -= visual_dt
            if self._shake_timer <= 0:
                self._shake_timer = 0
                self._shake_intensity = 0
                self._shake_duration = 0
        else:
            self._shake_intensity = 0
            self._shake_duration = 0

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

    def _graphics_quality(self) -> str:
        """Return configured graphics quality preset."""
        if self._quality_cache_timer <= 0.0:
            app = App.get_running_app()
            self._quality_cache = app.save_manager.get_nested("settings.graphics_quality", "balanced")
            self._quality_cache_timer = 0.4
        return self._quality_cache

    def _show_grid(self) -> bool:
        """Return whether the board grid should be rendered."""
        app = App.get_running_app()
        return app.save_manager.get_nested("settings.show_grid", True)

    def _environment_theme(self) -> str:
        """Return active gameplay environment theme."""
        if self._theme_cache_timer <= 0.0:
            app = App.get_running_app()
            self._theme_cache = app.save_manager.get_nested("settings.environment_theme", "meadow")
            self._theme_cache_timer = 0.4
        theme = self._theme_cache
        valid = {"meadow", "underwater", "iceland", "desert"}
        return theme if theme in valid else "meadow"

    def _draw_rodent(self, core_x, core_y, core_size_w, core_size_h, meal_color, facing, species="mouse", ear_color=None, ear_size_override=None, tail_length_override=None):
        body_w = core_size_w * (0.60 if species == "shrew" else 0.66)
        body_h = core_size_h * 0.44
        body_x = core_x + core_size_w * 0.20
        body_y = core_y + core_size_h * 0.30
        Color(*meal_color)
        Ellipse(pos=(body_x, body_y), size=(body_w, body_h))

        head_w = core_size_w * (0.22 if species == "shrew" else 0.26)
        head_h = core_size_h * 0.30

        tail_length = tail_length_override
        if tail_length is None:
            tail_length = {
                "kangaroo_rat": 0.24,
                "shrew": 0.20,
            }.get(species, 0.16)

        if facing > 0:
            head_x = body_x + body_w * 0.74
            tail_from_x = body_x + body_w * 0.04
            tail_to_x = body_x - core_size_w * tail_length
        else:
            head_x = body_x - head_w * 0.10
            tail_from_x = body_x + body_w * 0.96
            tail_to_x = body_x + body_w + core_size_w * tail_length
        head_y = body_y + body_h * 0.26
        Ellipse(pos=(head_x, head_y), size=(head_w, head_h))

        if ear_color is None:
            ear_color = {
                "vole": (0.88, 0.76, 0.72, 0.90),
                "kangaroo_rat": (0.88, 0.76, 0.72, 0.90),
                "shrew": (0.66, 0.72, 0.80, 0.82),
            }.get(species, (0.96, 0.82, 0.82, 0.92))
        Color(*ear_color)

        if ear_size_override is None:
            ear_size = {
                "mouse": 0.10,
                "kangaroo_rat": 0.08,
            }.get(species, 0.07)
            ear_size = core_size_w * ear_size
        else:
            ear_size = core_size_w * ear_size_override

        Ellipse(pos=(head_x + head_w * 0.14, head_y + head_h * 0.58), size=(ear_size, ear_size * 0.86))
        Ellipse(pos=(head_x + head_w * 0.54, head_y + head_h * 0.56), size=(ear_size, ear_size * 0.86))

        Color(meal_color[0] * 0.74, meal_color[1] * 0.74, meal_color[2] * 0.74, 1.0)
        Line(points=[tail_from_x, body_y + body_h * 0.50, tail_to_x, body_y + body_h * 0.60], width=1.1)

        if species == "kangaroo_rat":
            Color(meal_color[0] * 0.72, meal_color[1] * 0.72, meal_color[2] * 0.72, 1.0)
            Line(points=[body_x + body_w * 0.34, body_y + body_h * 0.18, body_x + body_w * 0.26, body_y - core_size_h * 0.06], width=1.0)
            Line(points=[body_x + body_w * 0.56, body_y + body_h * 0.18, body_x + body_w * 0.66, body_y - core_size_h * 0.06], width=1.0)

        if species == "shrew":
            Color(meal_color[0] * 0.70, meal_color[1] * 0.70, meal_color[2] * 0.70, 1.0)
            if facing > 0:
                Line(points=[head_x + head_w * 0.96, head_y + head_h * 0.50, head_x + head_w * 1.26, head_y + head_h * 0.56], width=1.0)
            else:
                Line(points=[head_x, head_y + head_h * 0.50, head_x - head_w * 0.26, head_y + head_h * 0.56], width=1.0)

        eye_x = head_x + head_w * (0.72 if facing > 0 else 0.18)
        Color(0.08, 0.08, 0.10, 0.90)
        Ellipse(pos=(eye_x, head_y + head_h * 0.54), size=(core_size_w * 0.05, core_size_h * 0.08))

    def _draw_frog(self, core_x, core_y, core_size_w, core_size_h, meal_color, limb_color=None):
        Color(*meal_color)
        Ellipse(pos=(core_x + core_size_w * 0.20, core_y + core_size_h * 0.30), size=(core_size_w * 0.60, core_size_h * 0.42))
        Ellipse(pos=(core_x + core_size_w * 0.30, core_y + core_size_h * 0.48), size=(core_size_w * 0.40, core_size_h * 0.30))

        if limb_color is None:
            limb_color = (meal_color[0] * 0.82, meal_color[1] * 0.82, meal_color[2] * 0.82, 1.0)
        Color(*limb_color)
        Line(points=[core_x + core_size_w * 0.22, core_y + core_size_h * 0.36, core_x + core_size_w * 0.10, core_y + core_size_h * 0.24], width=1.2)
        Line(points=[core_x + core_size_w * 0.78, core_y + core_size_h * 0.36, core_x + core_size_w * 0.90, core_y + core_size_h * 0.24], width=1.2)

        Color(0.92, 0.98, 1.0, 0.92)
        Ellipse(pos=(core_x + core_size_w * 0.36, core_y + core_size_h * 0.66), size=(core_size_w * 0.10, core_size_h * 0.10))
        Ellipse(pos=(core_x + core_size_w * 0.54, core_y + core_size_h * 0.66), size=(core_size_w * 0.10, core_size_h * 0.10))
        Color(0.08, 0.10, 0.10, 0.90)
        Ellipse(pos=(core_x + core_size_w * 0.40, core_y + core_size_h * 0.69), size=(core_size_w * 0.04, core_size_h * 0.05))
        Ellipse(pos=(core_x + core_size_w * 0.58, core_y + core_size_h * 0.69), size=(core_size_w * 0.04, core_size_h * 0.05))

    def _draw_lizard(self, core_x, core_y, core_size_w, core_size_h, meal_color, facing):
        Color(*meal_color)
        body_x = core_x + core_size_w * 0.20
        body_y = core_y + core_size_h * 0.38
        body_w = core_size_w * 0.56
        body_h = core_size_h * 0.28
        Ellipse(pos=(body_x, body_y), size=(body_w, body_h))

        Color(meal_color[0] * 0.80, meal_color[1] * 0.80, meal_color[2] * 0.80, 1.0)
        if facing > 0:
            Line(points=[body_x + body_w * 0.08, body_y + body_h * 0.50, body_x - core_size_w * 0.22, body_y + body_h * 0.42], width=1.2)
            head_x = body_x + body_w * 0.84
        else:
            Line(points=[body_x + body_w * 0.92, body_y + body_h * 0.50, body_x + body_w + core_size_w * 0.22, body_y + body_h * 0.42], width=1.2)
            head_x = body_x - core_size_w * 0.04

        Ellipse(pos=(head_x, body_y + body_h * 0.14), size=(core_size_w * 0.18, core_size_h * 0.20))
        Line(points=[body_x + body_w * 0.30, body_y + body_h * 0.22, body_x + body_w * 0.22, body_y - core_size_h * 0.04], width=1.0)
        Line(points=[body_x + body_w * 0.66, body_y + body_h * 0.22, body_x + body_w * 0.74, body_y - core_size_h * 0.04], width=1.0)
        Color(0.08, 0.10, 0.10, 0.88)
        Ellipse(pos=(head_x + core_size_w * (0.12 if facing > 0 else 0.03), body_y + body_h * 0.50), size=(core_size_w * 0.04, core_size_h * 0.06))

    def _draw_small_bird(self, core_x, core_y, core_size_w, core_size_h, meal_color, facing):
        Color(*meal_color)
        body_x = core_x + core_size_w * 0.24
        body_y = core_y + core_size_h * 0.34
        body_w = core_size_w * 0.54
        body_h = core_size_h * 0.34
        Ellipse(pos=(body_x, body_y), size=(body_w, body_h))

        Color(meal_color[0] * 0.86, meal_color[1] * 0.86, meal_color[2] * 0.86, 1.0)
        Ellipse(pos=(body_x + body_w * 0.28, body_y + body_h * 0.10), size=(body_w * 0.42, body_h * 0.52))

        # Wing flap animation: smooth up/down motion synchronized with board animation time.
        flap = math.sin(self._animation_time * 17.0 + body_x * 0.06)
        wing_lift = flap * body_h * 0.22
        wing_drop = flap * body_h * 0.12
        Color(meal_color[0] * 0.70, meal_color[1] * 0.70, meal_color[2] * 0.70, 0.95)
        if facing > 0:
            wing_root_x = body_x + body_w * 0.42
            wing_tip_back_x = body_x - body_w * 0.22
            wing_tip_mid_x = body_x + body_w * 0.06
        else:
            wing_root_x = body_x + body_w * 0.58
            wing_tip_back_x = body_x + body_w * 1.22
            wing_tip_mid_x = body_x + body_w * 0.94
        wing_root_y = body_y + body_h * 0.58
        Line(points=[wing_root_x, wing_root_y, wing_tip_back_x, wing_root_y + body_h * 0.36 + wing_lift], width=1.5)
        Line(points=[wing_root_x, wing_root_y, wing_tip_mid_x, wing_root_y + body_h * 0.08 - wing_drop], width=1.2)

        if facing > 0:
            Line(points=[body_x + body_w * 0.98, body_y + body_h * 0.56, body_x + body_w * 1.18, body_y + body_h * 0.62], width=1.0)
            Line(points=[body_x + body_w * 0.04, body_y + body_h * 0.52, body_x - body_w * 0.24, body_y + body_h * 0.72], width=1.1)
            eye_x = body_x + body_w * 0.76
        else:
            Line(points=[body_x + body_w * 0.02, body_y + body_h * 0.56, body_x - body_w * 0.18, body_y + body_h * 0.62], width=1.0)
            Line(points=[body_x + body_w * 0.96, body_y + body_h * 0.52, body_x + body_w * 1.24, body_y + body_h * 0.72], width=1.1)
            eye_x = body_x + body_w * 0.18
        Color(0.08, 0.10, 0.10, 0.90)
        Ellipse(pos=(eye_x, body_y + body_h * 0.60), size=(core_size_w * 0.05, core_size_h * 0.06))

    def render(self):
        """Render game board."""
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0 or not self.controller:
            return

        quality = self._graphics_quality()
        full_fx = quality == "high"
        medium_fx = quality in ("high", "balanced")
        fx_scale = 1.0 if quality == "high" else 0.65 if quality == "balanced" else 0.35

        # Balanced mode alternates heavy ambience every other visual frame.
        if quality == "balanced" and int(self._animation_time * 18.0) % 2 == 1:
            medium_fx = False

        def _scaled_count(value: int, *, min_value: int = 1) -> int:
            return max(min_value, int(value * fx_scale))

        with self.canvas:
            # Background by selected environment theme.
            environment = self._environment_theme()
            gradient_steps = 44 if quality == "high" else 28 if quality == "balanced" else 18

            if environment == "underwater":
                for idx in range(gradient_steps):
                    t = idx / max(1, gradient_steps - 1)
                    r = 0.04 + (0.00 - 0.04) * t
                    g = 0.20 + (0.44 - 0.20) * t
                    b = 0.34 + (0.66 - 0.34) * t
                    Color(r, g, b, 1)
                    Rectangle(pos=(self.x, self.y + self.height * (idx / gradient_steps)), size=(self.width, self.height / gradient_steps + 1))

                Color(0.10, 0.56, 0.72, 0.10)
                Rectangle(pos=(self.x, self.y), size=(self.width, self.height))

                if medium_fx:
                    for i in range(_scaled_count(6)):
                        ray_x = self.x + self.width * ((i * 0.16 + self._animation_time * 0.02) % 1.1)
                        Color(0.76, 0.94, 1.0, 0.08)
                        Line(points=[ray_x, self.y + self.height, ray_x - self.width * 0.08, self.y], width=1.1)

                    bubble_count = _scaled_count(18 if full_fx else 10)
                    for i in range(bubble_count):
                        rise = (self._animation_time * (20 + (i % 5) * 5) + i * 34) % (self.height + 40)
                        bx = self.x + (i * 0.113 % 1.0) * self.width + math.sin(self._animation_time * 1.1 + i) * self.width * 0.01
                        by = self.y + rise - 20
                        size = min(self.width, self.height) * (0.006 + (i % 4) * 0.0015)
                        Color(0.86, 0.97, 1.0, 0.24)
                        Ellipse(pos=(bx, by), size=(size, size))

                for i in range(_scaled_count(14)):
                    sx = self.x + self.width * ((i * 0.071) % 1.0)
                    sway = math.sin(self._animation_time * 1.3 + i * 0.7) * self.width * 0.010
                    Color(0.10, 0.44, 0.33, 0.30)
                    Line(points=[sx, self.y, sx + sway, self.y + self.height * (0.12 + (i % 3) * 0.04)], width=1.6)

                if medium_fx:
                    # Underwater moving tree/kelp clusters (replaces decorative fish to avoid visual conflict).
                    cluster_x = (0.14, 0.34, 0.56, 0.76, 0.90)
                    for idx, ratio in enumerate(cluster_x):
                        base_x = self.x + self.width * ratio
                        base_y = self.y + self.height * 0.02
                        trunk_h = self.height * (0.20 + (idx % 2) * 0.04)
                        sway = math.sin(self._animation_time * (0.9 + idx * 0.08) + idx * 0.7) * self.width * 0.018

                        # Trunk
                        Color(0.12, 0.42, 0.34, 0.46)
                        Line(points=[base_x, base_y, base_x + sway * 0.5, base_y + trunk_h], width=2.2)

                        # Leafy canopy branches
                        Color(0.18, 0.56, 0.44, 0.34)
                        Line(points=[base_x + sway * 0.26, base_y + trunk_h * 0.44, base_x - self.width * 0.025 + sway, base_y + trunk_h * 0.64], width=1.3)
                        Line(points=[base_x + sway * 0.26, base_y + trunk_h * 0.58, base_x + self.width * 0.022 + sway, base_y + trunk_h * 0.78], width=1.3)
                        Line(points=[base_x + sway * 0.26, base_y + trunk_h * 0.72, base_x - self.width * 0.018 + sway, base_y + trunk_h * 0.90], width=1.2)

                        # Soft canopy glow
                        Color(0.26, 0.70, 0.56, 0.16)
                        Ellipse(pos=(base_x - self.width * 0.06 + sway, base_y + trunk_h * 0.64), size=(self.width * 0.12, self.height * 0.10))

                # Static background snails (non-eatable decorative elements).
                snail_positions = (
                    (0.10, 0.06),
                    (0.26, 0.05),
                    (0.44, 0.07),
                    (0.62, 0.05),
                    (0.82, 0.06),
                )
                for idx, (sx_ratio, sy_ratio) in enumerate(snail_positions):
                    sx = self.x + self.width * sx_ratio
                    sy = self.y + self.height * sy_ratio
                    shell_tint = 0.48 + (idx % 3) * 0.08
                    Color(shell_tint, 0.42, 0.34, 0.45)
                    Ellipse(pos=(sx, sy + self.height * 0.008), size=(self.width * 0.030, self.height * 0.022))
                    Color(0.44, 0.58, 0.62, 0.42)
                    Ellipse(pos=(sx + self.width * 0.010, sy), size=(self.width * 0.034, self.height * 0.016))

            elif environment == "iceland":
                for idx in range(gradient_steps):
                    t = idx / max(1, gradient_steps - 1)
                    # Calm Iceland-inspired sky: low-saturation cool tones with smooth blend.
                    r = 0.20 + (0.70 - 0.20) * t
                    g = 0.28 + (0.80 - 0.28) * t
                    b = 0.38 + (0.92 - 0.38) * t
                    Color(r, g, b, 1)
                    Rectangle(pos=(self.x, self.y + self.height * (idx / gradient_steps)), size=(self.width, self.height / gradient_steps + 1))

                # Soft ambient glow layer (no harsh shadows).
                Color(0.78, 0.88, 0.96, 0.08)
                Rectangle(pos=(self.x, self.y), size=(self.width, self.height))

                # Distant glaciers and stylized mountain silhouettes (clean, simplified forms).
                mountain_layers = (
                    (0.38, 0.16, 0.48, 0.10, 0.16),
                    (0.44, 0.28, 0.42, 0.12, 0.18),
                    (0.50, 0.52, 0.46, 0.14, 0.20),
                    (0.42, 0.76, 0.40, 0.11, 0.16),
                    (0.36, 0.90, 0.30, 0.08, 0.14),
                )
                for peak_y, center_x, width_ratio, height_ratio, alpha in mountain_layers:
                    left_x = self.x + self.width * (center_x - width_ratio * 0.5)
                    right_x = self.x + self.width * (center_x + width_ratio * 0.5)
                    base_y = self.y + self.height * 0.26
                    top_y = self.y + self.height * peak_y
                    Color(0.60, 0.72, 0.84, alpha)
                    Line(points=[left_x, base_y, self.x + self.width * center_x, top_y, right_x, base_y], width=2.0)

                # Horizon fog layers for atmospheric depth.
                Color(0.74, 0.84, 0.92, 0.12)
                Rectangle(pos=(self.x, self.y + self.height * 0.24), size=(self.width, self.height * 0.09))
                Color(0.82, 0.90, 0.96, 0.08)
                Rectangle(pos=(self.x, self.y + self.height * 0.30), size=(self.width, self.height * 0.07))

                # Foreground frozen ground (clear play area with minimal clutter).
                Color(0.84, 0.92, 0.98, 0.22)
                Rectangle(pos=(self.x, self.y), size=(self.width, self.height * 0.24))
                Color(0.94, 0.98, 1.0, 0.08)
                Rectangle(pos=(self.x, self.y + self.height * 0.10), size=(self.width, self.height * 0.06))

                # Subtle icy cracks texture near foreground only.
                crack_lines = (
                    (0.10, 0.06, 0.18, 0.09, 0.26, 0.07),
                    (0.28, 0.08, 0.36, 0.11, 0.44, 0.09),
                    (0.52, 0.05, 0.60, 0.08, 0.68, 0.06),
                    (0.72, 0.09, 0.80, 0.12, 0.88, 0.10),
                )
                Color(0.88, 0.96, 1.0, 0.18)
                for x1, y1, x2, y2, x3, y3 in crack_lines:
                    Line(
                        points=[
                            self.x + self.width * x1,
                            self.y + self.height * y1,
                            self.x + self.width * x2,
                            self.y + self.height * y2,
                            self.x + self.width * x3,
                            self.y + self.height * y3,
                        ],
                        width=1.0,
                    )

                if medium_fx:
                    # Lightweight snowfall, intentionally subtle for visibility.
                    snow_count = 24 if full_fx else 12
                    for i in range(snow_count):
                        drift = (self._animation_time * (10 + (i % 4)) + i * 24) % (self.height + 24)
                        sx = self.x + ((i * 0.091 + self._animation_time * 0.014) % 1.05) * self.width
                        sy = self.y + self.height - drift
                        size = min(self.width, self.height) * (0.0035 + (i % 3) * 0.0009)
                        Color(0.94, 0.98, 1.0, 0.24)
                        Ellipse(pos=(sx, sy), size=(size, size))

                    # Soft drifting fog ribbons.
                    fog_specs = (
                        (0.10, 0.34, 0.28, 0.06),
                        (0.46, 0.32, 0.34, 0.07),
                        (0.72, 0.35, 0.24, 0.06),
                    )
                    for fx, fy, fw, fh in fog_specs:
                        shift = math.sin(self._animation_time * 0.5 + fx * 9.0) * self.width * 0.012
                        Color(0.86, 0.92, 0.98, 0.10)
                        Ellipse(
                            pos=(self.x + self.width * fx + shift, self.y + self.height * fy),
                            size=(self.width * fw, self.height * fh),
                        )

                if full_fx:
                    # Faint aurora borealis ribbon (pale cyan + violet blend).
                    Color(0.58, 0.92, 0.90, 0.05)
                    Line(points=[
                        self.x - 16,
                        self.y + self.height * 0.84,
                        self.x + self.width * 0.22,
                        self.y + self.height * 0.90,
                        self.x + self.width * 0.48,
                        self.y + self.height * 0.83,
                        self.x + self.width * 0.74,
                        self.y + self.height * 0.89,
                        self.x + self.width + 16,
                        self.y + self.height * 0.84,
                    ], width=2.0)
                    Color(0.72, 0.70, 0.90, 0.04)
                    Line(points=[
                        self.x - 20,
                        self.y + self.height * 0.80,
                        self.x + self.width * 0.26,
                        self.y + self.height * 0.86,
                        self.x + self.width * 0.56,
                        self.y + self.height * 0.79,
                        self.x + self.width * 0.82,
                        self.y + self.height * 0.85,
                        self.x + self.width + 20,
                        self.y + self.height * 0.80,
                    ], width=1.8)

            elif environment == "desert":
                for idx in range(gradient_steps):
                    t = idx / max(1, gradient_steps - 1)
                    r = 0.74 + (0.95 - 0.74) * t
                    g = 0.46 + (0.72 - 0.46) * t
                    b = 0.24 + (0.48 - 0.24) * t
                    Color(r, g, b, 1)
                    Rectangle(pos=(self.x, self.y + self.height * (idx / gradient_steps)), size=(self.width, self.height / gradient_steps + 1))

                Color(1.0, 0.86, 0.52, 0.24)
                Ellipse(pos=(self.x + self.width * 0.70, self.y + self.height * 0.74), size=(self.width * 0.24, self.height * 0.20))

                for i in range(5):
                    dune_w = self.width * (0.62 + (i % 2) * 0.18)
                    dune_h = self.height * (0.14 + (i % 3) * 0.03)
                    dune_x = self.x + self.width * (i * 0.22 - 0.20)
                    dune_y = self.y + self.height * (0.02 + (i % 2) * 0.03)
                    Color(0.87, 0.68, 0.34, 0.30)
                    Ellipse(pos=(dune_x, dune_y), size=(dune_w, dune_h))

                if medium_fx:
                    dust_count = 14 if full_fx else 8
                    for i in range(dust_count):
                        dx = self.x + ((self._animation_time * (22 + i) + i * 45) % (self.width + 30)) - 15
                        dy = self.y + self.height * (0.16 + (i * 0.09) % 0.70) + math.sin(self._animation_time * 1.6 + i) * self.height * 0.01
                        Color(0.93, 0.78, 0.48, 0.16)
                        Ellipse(pos=(dx, dy), size=(self.width * 0.016, self.height * 0.010))

                if full_fx:
                    for i in range(5):
                        cx = self.x + self.width * (0.12 + i * 0.18)
                        Color(0.36, 0.44, 0.20, 0.36)
                        Line(points=[cx, self.y + self.height * 0.03, cx, self.y + self.height * 0.12], width=1.5)
                        Line(points=[cx, self.y + self.height * 0.11, cx - self.width * 0.02, self.y + self.height * 0.15], width=1.1)
                        Line(points=[cx, self.y + self.height * 0.10, cx + self.width * 0.02, self.y + self.height * 0.14], width=1.1)

            else:
                # Meadow (existing default field).
                for idx in range(gradient_steps):
                    t = idx / max(1, gradient_steps - 1)
                    r = 0.20 + (0.36 - 0.20) * t
                    g = 0.34 + (0.58 - 0.34) * t
                    b = 0.16 + (0.25 - 0.16) * t
                    Color(r, g, b, 1)
                    Rectangle(pos=(self.x, self.y + self.height * (idx / gradient_steps)), size=(self.width, self.height / gradient_steps + 1))

                Color(0.11, 0.19, 0.09, 0.18)
                Rectangle(pos=(self.x, self.y), size=(self.width, self.height))
                Color(0.97, 0.90, 0.66, 0.08)
                Ellipse(pos=(self.x - self.width * 0.18, self.y + self.height * 0.62), size=(self.width * 1.36, self.height * 0.62))

                if medium_fx:
                    cloud_specs = (
                        (0.18, 0.84, 0.09, 0.06, 0.42),
                        (0.52, 0.78, 0.12, 0.07, 0.34),
                        (0.86, 0.88, 0.10, 0.05, 0.36),
                    )
                    for idx, (x_anchor, y_anchor, size_factor, alpha, speed) in enumerate(cloud_specs):
                        drift = math.sin(self._animation_time * speed + idx * 1.7) * self.width * 0.015
                        cx = self.x + self.width * x_anchor + drift
                        cy = self.y + self.height * y_anchor
                        cw = self.width * size_factor
                        ch = self.height * (size_factor * 0.48)
                        Color(0.96, 0.98, 0.92, alpha)
                        Ellipse(pos=(cx - cw * 0.5, cy - ch * 0.5), size=(cw, ch))

                for i in range(_scaled_count(18)):
                    sway = math.sin(self._animation_time * 1.2 + i * 0.9)
                    px = self.x + self.width * ((i * 0.137) % 1.0) + sway * (self.width * 0.004)
                    py = self.y + self.height * ((i * 0.193 + 0.11) % 1.0) + math.cos(self._animation_time * 0.8 + i * 0.6) * (self.height * 0.002)
                    grass_w = self.width * (0.022 + (i % 3) * 0.004)
                    grass_h = self.height * (0.010 + (i % 4) * 0.002)
                    Color(0.30, 0.52, 0.19, 0.16)
                    Ellipse(pos=(px, py), size=(grass_w, grass_h))
                    if i % 4 == 0:
                        Color(0.96, 0.95, 0.86, 0.22)
                        flower_size = min(self.width, self.height) * 0.007
                        Ellipse(pos=(px + grass_w * 0.20 + sway * 0.8, py + grass_h * 0.65), size=(flower_size, flower_size))
                        Color(0.92, 0.72, 0.22, 0.20)
                        Ellipse(pos=(px + grass_w * 0.24 + sway * 0.8, py + grass_h * 0.69), size=(flower_size * 0.5, flower_size * 0.5))

                if medium_fx:
                    drift_count = 8 if full_fx else 4
                    for i in range(drift_count):
                        px = self.x + ((self._animation_time * (18 + i * 2) + i * self.width * 0.14) % (self.width + 30)) - 15
                        py = self.y + self.height * (0.18 + ((i * 0.17 + self._animation_time * 0.08) % 0.74))
                        wobble = math.sin(self._animation_time * 2.1 + i * 0.9)
                        size_w = self.width * 0.010
                        size_h = self.height * 0.007
                        if i % 2 == 0:
                            Color(0.92, 0.78, 0.34, 0.24)
                        else:
                            Color(0.66, 0.86, 0.40, 0.22)
                        Ellipse(pos=(px + wobble * 2.4, py + wobble * 1.5), size=(size_w, size_h))

                if medium_fx:
                    Color(0.10, 0.15, 0.08, 0.12)
                    Ellipse(pos=(self.x - self.width * 0.10, self.y - self.height * 0.18), size=(self.width * 1.20, self.height * 1.36))
                if full_fx:
                    Color(0.88, 0.94, 0.78, 0.05)
                    Ellipse(pos=(self.x - self.width * 0.08, self.y - self.height * 0.10), size=(self.width * 1.16, self.height * 1.20))

                    butterfly_specs = (
                        (0.21, 0.74, 0.20, 0.06, 0.86, 0.12),
                        (0.93, 0.80, 0.16, 0.08, 0.92, 0.16),
                        (0.95, 0.62, 0.20, 0.10, 0.88, 0.10),
                    )
                    for idx, (cr, cg, cb, base_y, speed, amp) in enumerate(butterfly_specs):
                        phase = self._animation_time * speed + idx * 1.6
                        bx = self.x + ((self._animation_time * 24.0 + idx * self.width * 0.22) % (self.width + 40)) - 20
                        by = self.y + self.height * (base_y + math.sin(phase) * amp * 0.18)
                        flap = 0.55 + (math.sin(self._animation_time * 8.0 + idx * 2.3) + 1.0) * 0.35
                        wing_w = self.width * 0.010 * flap
                        wing_h = self.height * 0.013

                        Color(cr, cg, cb, 0.32)
                        Ellipse(pos=(bx - wing_w * 0.95, by), size=(wing_w, wing_h))
                        Ellipse(pos=(bx + wing_w * 0.12, by), size=(wing_w, wing_h))
                        Color(0.24, 0.20, 0.12, 0.38)
                        Rectangle(pos=(bx - 0.6, by + wing_h * 0.15), size=(1.2, wing_h * 0.9))

            # Ambient predators: cinematic flavor only (non-collision), keeps hunting vibe realistic.
            if medium_fx:
                if environment in {"meadow", "desert", "iceland"}:
                    hawk_x = self.x + ((self._animation_time * (26.0 if environment == "desert" else 20.0)) % (self.width + 120)) - 60
                    hawk_y = self.y + self.height * (0.72 if environment == "desert" else (0.80 if environment == "iceland" else 0.76))
                    wing = self.width * 0.10
                    flap = math.sin(self._animation_time * 7.2) * self.height * 0.010
                    Color(0.12, 0.12, 0.14, 0.22)
                    Ellipse(pos=(hawk_x - wing * 1.1, hawk_y - self.height * 0.01 + flap), size=(wing * 1.1, self.height * 0.028))
                    Ellipse(pos=(hawk_x, hawk_y - self.height * 0.01 - flap), size=(wing * 1.1, self.height * 0.028))

                if environment == "meadow":
                    mx = self.x + self.width * 0.14 + math.sin(self._animation_time * 0.52) * self.width * 0.05
                    my = self.y + self.height * 0.11
                    Color(0.16, 0.14, 0.12, 0.17)
                    Ellipse(pos=(mx, my), size=(self.width * 0.10, self.height * 0.04))
                    Ellipse(pos=(mx + self.width * 0.08, my + self.height * 0.01), size=(self.width * 0.035, self.height * 0.03))
                elif environment == "desert":
                    mx = self.x + self.width * 0.78 + math.sin(self._animation_time * 0.44) * self.width * 0.04
                    my = self.y + self.height * 0.09
                    Color(0.14, 0.12, 0.10, 0.18)
                    RoundedRectangle(pos=(mx, my), size=(self.width * 0.11, self.height * 0.042), radius=(2,))
                    Ellipse(pos=(mx + self.width * 0.085, my + self.height * 0.008), size=(self.width * 0.03, self.height * 0.027))
                elif environment == "iceland":
                    bx = self.x + self.width * 0.20 + math.sin(self._animation_time * 0.40) * self.width * 0.03
                    by = self.y + self.height * 0.10
                    Color(0.10, 0.10, 0.12, 0.18)
                    RoundedRectangle(pos=(bx, by), size=(self.width * 0.11, self.height * 0.042), radius=(2,))
                    Color(0.76, 0.79, 0.84, 0.14)
                    RoundedRectangle(pos=(bx + self.width * 0.008, by + self.height * 0.018), size=(self.width * 0.09, self.height * 0.015), radius=(2,))
                elif environment == "underwater":
                    # Underwater ambience uses marine predators (no land birds/animals here).
                    shark_x = self.x + ((self._animation_time * 16.0) % (self.width + 160)) - 80
                    shark_y = self.y + self.height * 0.28 + math.sin(self._animation_time * 0.7) * self.height * 0.02
                    shark_w = self.width * 0.22
                    shark_h = self.height * 0.06
                    Color(0.14, 0.20, 0.24, 0.16)
                    Ellipse(pos=(shark_x, shark_y), size=(shark_w, shark_h))
                    Color(0.18, 0.26, 0.30, 0.18)
                    Line(points=[shark_x + shark_w * 0.32, shark_y + shark_h * 0.56, shark_x + shark_w * 0.44, shark_y + shark_h * 1.18, shark_x + shark_w * 0.56, shark_y + shark_h * 0.56], width=1.0)
                    Line(points=[shark_x + shark_w * 0.02, shark_y + shark_h * 0.46, shark_x - shark_w * 0.16, shark_y + shark_h * 0.72, shark_x - shark_w * 0.16, shark_y + shark_h * 0.22], width=1.0)

                    eel_x = self.x + self.width - (((self._animation_time * 11.0) + 120.0) % (self.width + 140))
                    eel_y = self.y + self.height * 0.40 + math.sin(self._animation_time * 1.1 + 1.4) * self.height * 0.018
                    Color(0.10, 0.18, 0.20, 0.15)
                    Line(points=[
                        eel_x,
                        eel_y,
                        eel_x + self.width * 0.08,
                        eel_y + self.height * 0.01,
                        eel_x + self.width * 0.16,
                        eel_y - self.height * 0.006,
                    ], width=1.2)

            if self.controller.current_mode.is_game_over:
                return

            # Apply shake
            offset_x = 0
            offset_y = 0
            if self._shake_intensity > 0:
                duration = max(0.001, self._shake_duration)
                decay = max(0.0, min(1.0, self._shake_timer / duration))
                amplitude = self._shake_intensity * decay
                phase = self._animation_time * 42.0
                offset_x = math.sin(phase) * amplitude
                offset_y = math.cos(phase * 1.27 + 0.6) * amplitude

            # Keep gameplay clean: no graph-paper grid lines.
            cell_width = self.width / constants.BOARD_COLS
            cell_height = self.height / constants.BOARD_ROWS

            # Speed lines at higher velocity for cinematic motion feel.
            move_interval = self.controller._get_move_interval()
            speed_ratio = max(
                0.0,
                min(
                    1.0,
                    (constants.BASE_MOVE_INTERVAL - move_interval)
                    / max(0.001, (constants.BASE_MOVE_INTERVAL - constants.MIN_MOVE_INTERVAL)),
                ),
            )
            if medium_fx and speed_ratio > 0.28:
                dir_x, dir_y = self.controller.snake.direction
                line_len = min(cell_width, cell_height) * (0.9 + speed_ratio * 1.6)
                alpha = min(constants.SPEED_LINE_MAX_ALPHA, speed_ratio * constants.SPEED_LINE_MAX_ALPHA)
                Color(0.90, 0.96, 0.82, alpha)
                speed_line_count = _scaled_count(constants.SPEED_LINE_COUNT)
                for i in range(speed_line_count):
                    px = self.x + ((self._animation_time * 140.0 + i * (self.width / max(1, speed_line_count))) % self.width)
                    py = self.y + ((i * 0.173 * self.height + self._animation_time * 18.0) % self.height)
                    start_x = px - dir_x * line_len * 0.15
                    start_y = py - dir_y * line_len * 0.15
                    end_x = px + dir_x * line_len
                    end_y = py + dir_y * line_len
                    Line(points=[start_x, start_y, end_x, end_y], width=0.8)

            # Gameplay blockers: clean premium hazard tiles for fair collision readability.
            wall_tile_color = {
                "underwater": (0.16, 0.30, 0.36, 1.0),
                "iceland": (0.26, 0.34, 0.44, 1.0),
                "desert": (0.46, 0.34, 0.22, 1.0),
            }.get(environment, (0.22, 0.30, 0.22, 1.0))

            for wall in self.controller.walls:
                x = self.x + offset_x + wall[0] * cell_width
                y = self.y + offset_y + wall[1] * cell_height

                inset = min(cell_width, cell_height) * 0.07
                inner_x = x + inset
                inner_y = y + inset
                inner_w = max(1.0, cell_width - inset * 2)
                inner_h = max(1.0, cell_height - inset * 2)

                if medium_fx:
                    Color(0.04, 0.05, 0.05, 0.22)
                    Ellipse(pos=(inner_x + inner_w * 0.08, inner_y - inner_h * 0.16), size=(inner_w * 0.86, inner_h * 0.34))

                # Biome-aware tile tint with strong contrast.
                Color(*wall_tile_color)
                RoundedRectangle(pos=(inner_x, inner_y), size=(inner_w, inner_h), radius=(3,))

                if medium_fx:
                    Color(0.92, 0.96, 1.0, 0.16)
                    Rectangle(pos=(inner_x + 1, inner_y + inner_h * 0.62), size=(max(0.0, inner_w - 2), max(0.0, inner_h * 0.16)))

                # Hazard symbol (claw-like mark) for immediate readability.
                Color(0.96, 0.34, 0.24, 0.88)
                Line(points=[inner_x + inner_w * 0.30, inner_y + inner_h * 0.22, inner_x + inner_w * 0.44, inner_y + inner_h * 0.74], width=1.0)
                Line(points=[inner_x + inner_w * 0.50, inner_y + inner_h * 0.20, inner_x + inner_w * 0.64, inner_y + inner_h * 0.72], width=1.0)
                Line(points=[inner_x + inner_w * 0.70, inner_y + inner_h * 0.24, inner_x + inner_w * 0.82, inner_y + inner_h * 0.68], width=1.0)

                Color(0.96, 0.84, 0.38, 0.22)
                Ellipse(pos=(inner_x + inner_w * 0.16, inner_y + inner_h * 0.16), size=(inner_w * 0.68, inner_h * 0.68))

                Color(0.90, 0.96, 1.0, 0.38)
                Line(rounded_rectangle=(inner_x, inner_y, inner_w, inner_h, 3), width=1.0)

            # Draw environment meal.
            food_pos = self.controller.food.get_render_position()
            x = self.x + offset_x + food_pos[0] * cell_width
            y = self.y + offset_y + food_pos[1] * cell_height
            pulse = 0.12 * (1 + math.sin(self._animation_time * 6.0))
            meal_size_factor = 0.74 + pulse
            glow_size = cell_width * (1.16 + pulse)

            if medium_fx:
                # Ground contact shadow for readable depth.
                Color(0.06, 0.10, 0.08, 0.18 if full_fx else 0.13)
                Ellipse(pos=(x + cell_width * 0.16, y + cell_height * 0.08), size=(cell_width * 0.68, cell_height * 0.26))

            variant = self.controller.food.food_variant
            food_type = self.controller.food.food_type

            # Fail-safe: underwater must not display bird variants.
            if environment == "underwater" and variant == "small_bird":
                variant = "tuna"
                food_type = "normal"

            # Theme-aware glow.
            if medium_fx:
                if environment == "underwater":
                    glow_color = (0.44, 0.92, 1.0, 0.30) if food_type != "poison" else (0.84, 0.40, 1.0, 0.32)
                elif environment == "iceland":
                    if food_type == "bonus":
                        glow_color = (1.00, 0.86, 0.44, 0.34)
                    elif food_type == "poison":
                        glow_color = (0.86, 0.40, 0.98, 0.34)
                    else:
                        glow_color = (0.22, 0.88, 0.56, 0.30)
                elif environment == "desert":
                    glow_color = (1.00, 0.84, 0.50, 0.28) if food_type != "poison" else (0.76, 0.62, 0.34, 0.30)
                else:
                    glow_color = (0.62, 0.88, 0.46, 0.26) if food_type != "poison" else (0.70, 0.38, 0.84, 0.28)
                Color(*glow_color)
                Ellipse(pos=(x + (cell_width - glow_size) * 0.5, y + (cell_height - glow_size) * 0.5), size=(glow_size, glow_size))

            core_size_w = cell_width * meal_size_factor
            core_size_h = cell_height * meal_size_factor
            core_x = x + (cell_width - core_size_w) * 0.5
            core_y = y + (cell_height - core_size_h) * 0.5

            if medium_fx:
                # Crisp readability ring so food stays visible against detailed backgrounds.
                Color(0.02, 0.03, 0.05, 0.34)
                Line(
                    ellipse=(
                        core_x - core_size_w * 0.08,
                        core_y - core_size_h * 0.08,
                        core_size_w * 1.16,
                        core_size_h * 1.16,
                    ),
                    width=1.2,
                )

            if environment == "underwater":
                dir_x, _ = self.controller.food.move_direction
                facing = -1 if dir_x < 0 else 1
                fish_color = {
                    "salmon": (0.96, 0.56, 0.42, 1.0),
                    "tuna": (0.60, 0.78, 0.92, 1.0),
                    "shrimp": (0.98, 0.74, 0.56, 1.0),
                    "octopus": (0.82, 0.54, 0.88, 1.0),
                    "lobster": (0.88, 0.30, 0.24, 1.0),
                    "crab": (0.90, 0.42, 0.30, 1.0),
                }.get(variant, (0.84, 0.92, 0.98, 1.0))
                Color(*fish_color)
                species_scale = {
                    "salmon": 0.98,
                    "tuna": 1.08,
                    "shrimp": 0.82,
                    "octopus": 1.00,
                    "lobster": 1.10,
                    "crab": 0.92,
                }.get(variant, 1.0)
                swim_bob = math.sin(self._animation_time * 3.2 + (0.7 if facing > 0 else 2.2))
                fish_w = core_size_w * 0.90 * species_scale
                fish_h = core_size_h * 0.48 * species_scale
                fish_x = core_x + (core_size_w - fish_w) * 0.5
                fish_y = core_y + (core_size_h - fish_h) * 0.5 + swim_bob * core_size_h * 0.015
                if variant == "octopus":
                    Ellipse(pos=(core_x + core_size_w * 0.18, core_y + core_size_h * 0.34), size=(core_size_w * 0.64, core_size_h * 0.54))
                    Color(fish_color[0] * 0.9, fish_color[1] * 0.9, fish_color[2] * 0.9, 0.95)
                    for i in range(6):
                        tx = core_x + core_size_w * (0.16 + i * 0.13)
                        Line(points=[tx, core_y + core_size_h * 0.40, tx + math.sin(self._animation_time * 2.8 + i) * core_size_w * 0.07, core_y + core_size_h * 0.08], width=1.2)
                    eye_x = core_x + core_size_w * (0.60 if facing > 0 else 0.34)
                    Color(0.10, 0.08, 0.14, 0.85)
                    Ellipse(pos=(eye_x, core_y + core_size_h * 0.64), size=(core_size_w * 0.08, core_size_h * 0.12))
                elif variant == "crab":
                    Ellipse(pos=(core_x + core_size_w * 0.14, core_y + core_size_h * 0.32), size=(core_size_w * 0.72, core_size_h * 0.44))
                    Color(fish_color[0] * 0.86, fish_color[1] * 0.86, fish_color[2] * 0.86, 1.0)
                    claw_y = core_y + core_size_h * 0.62
                    if facing > 0:
                        Line(points=[core_x + core_size_w * 0.22, claw_y, core_x + core_size_w * 0.04, claw_y + core_size_h * 0.14], width=1.4)
                        Line(points=[core_x + core_size_w * 0.78, claw_y, core_x + core_size_w * 0.96, claw_y + core_size_h * 0.14], width=1.4)
                    else:
                        Line(points=[core_x + core_size_w * 0.22, claw_y, core_x + core_size_w * 0.04, claw_y + core_size_h * 0.10], width=1.4)
                        Line(points=[core_x + core_size_w * 0.78, claw_y, core_x + core_size_w * 0.96, claw_y + core_size_h * 0.10], width=1.4)
                    for i in range(4):
                        leg_y = core_y + core_size_h * (0.26 + i * 0.08)
                        Line(points=[core_x + core_size_w * 0.24, leg_y, core_x + core_size_w * 0.08, leg_y - core_size_h * 0.07], width=1.0)
                        Line(points=[core_x + core_size_w * 0.76, leg_y, core_x + core_size_w * 0.92, leg_y - core_size_h * 0.07], width=1.0)
                    Color(0.10, 0.08, 0.14, 0.85)
                    Ellipse(pos=(core_x + core_size_w * 0.40, core_y + core_size_h * 0.58), size=(core_size_w * 0.07, core_size_h * 0.10))
                    Ellipse(pos=(core_x + core_size_w * 0.54, core_y + core_size_h * 0.58), size=(core_size_w * 0.07, core_size_h * 0.10))
                elif variant == "lobster":
                    RoundedRectangle(pos=(core_x + core_size_w * 0.28, core_y + core_size_h * 0.24), size=(core_size_w * 0.48, core_size_h * 0.56), radius=(4,))
                    Color(fish_color[0] * 0.84, fish_color[1] * 0.84, fish_color[2] * 0.84, 1.0)
                    Line(points=[core_x + core_size_w * 0.30, core_y + core_size_h * 0.56, core_x + core_size_w * 0.14, core_y + core_size_h * 0.74], width=1.3)
                    Line(points=[core_x + core_size_w * 0.74, core_y + core_size_h * 0.56, core_x + core_size_w * 0.90, core_y + core_size_h * 0.74], width=1.3)
                    for i in range(4):
                        sx = core_x + core_size_w * (0.35 + i * 0.10)
                        Line(points=[sx, core_y + core_size_h * 0.28, sx, core_y + core_size_h * 0.76], width=1.0)
                    Color(0.10, 0.08, 0.14, 0.82)
                    Ellipse(pos=(core_x + core_size_w * (0.56 if facing > 0 else 0.36), core_y + core_size_h * 0.62), size=(core_size_w * 0.08, core_size_h * 0.10))
                elif variant == "shrimp":
                    Ellipse(pos=(core_x + core_size_w * 0.24, core_y + core_size_h * 0.36), size=(core_size_w * 0.54, core_size_h * 0.34))
                    Color(fish_color[0] * 0.88, fish_color[1] * 0.88, fish_color[2] * 0.88, 1.0)
                    Line(points=[core_x + core_size_w * 0.76, core_y + core_size_h * 0.54, core_x + core_size_w * 0.90, core_y + core_size_h * 0.70], width=1.1)
                    Line(points=[core_x + core_size_w * 0.76, core_y + core_size_h * 0.50, core_x + core_size_w * 0.90, core_y + core_size_h * 0.42], width=1.1)
                    for i in range(3):
                        line_y = core_y + core_size_h * (0.38 + i * 0.08)
                        Line(points=[core_x + core_size_w * 0.36, line_y, core_x + core_size_w * 0.64, line_y], width=1.0)
                    Color(0.10, 0.08, 0.14, 0.80)
                    Ellipse(pos=(core_x + core_size_w * 0.58, core_y + core_size_h * 0.52), size=(core_size_w * 0.07, core_size_h * 0.09))
                else:
                    body_h = fish_h * (0.56 if variant == "tuna" else 0.42)
                    body_y = fish_y + (fish_h - body_h) * 0.5
                    Ellipse(pos=(fish_x, body_y), size=(fish_w, body_h))
                    Color(fish_color[0] * 0.9, fish_color[1] * 0.9, fish_color[2] * 0.9, 1.0)
                    tail_w = fish_w * (0.38 if variant == "tuna" else 0.26)
                    if facing > 0:
                        Line(points=[fish_x, body_y + body_h * 0.5, fish_x - tail_w, body_y + body_h * 0.84, fish_x - tail_w, body_y + body_h * 0.16], width=1.2)
                        eye_x = fish_x + fish_w * (0.72 if variant == "tuna" else 0.76)
                    else:
                        tail_x = fish_x + fish_w
                        Line(points=[tail_x, body_y + body_h * 0.5, tail_x + tail_w, body_y + body_h * 0.84, tail_x + tail_w, body_y + body_h * 0.16], width=1.2)
                        eye_x = fish_x + fish_w * (0.24 if variant == "tuna" else 0.18)
                    if variant == "salmon":
                        Color(0.98, 0.84, 0.72, 0.55)
                        Line(points=[fish_x + fish_w * 0.26, body_y + body_h * 0.66, fish_x + fish_w * 0.72, body_y + body_h * 0.66], width=1.0)
                    else:
                        Color(0.80, 0.94, 0.98, 0.44)
                        Line(points=[fish_x + fish_w * 0.22, body_y + body_h * 0.52, fish_x + fish_w * 0.76, body_y + body_h * 0.52], width=1.0)
                    Color(0.08, 0.10, 0.14, 0.80)
                    Ellipse(pos=(eye_x, body_y + body_h * 0.56), size=(fish_w * 0.08, body_h * 0.24))

            elif environment == "iceland":
                dir_x, _ = self.controller.food.move_direction
                facing = -1 if dir_x < 0 else 1
                meal_color = {
                    "vole": (0.84, 0.62, 0.46, 1.0),
                    "mouse": (0.94, 0.82, 0.64, 1.0),
                    "shrew": (0.38, 0.48, 0.62, 1.0),
                    "frog": (0.24, 0.84, 0.34, 1.0),
                    "lizard": (0.56, 0.92, 0.30, 1.0),
                }.get(variant, (0.78, 0.90, 1.0, 1.0))
                if variant in {"mouse", "vole", "shrew"}:
                    self._draw_rodent(core_x, core_y, core_size_w, core_size_h, meal_color, facing, species=variant)

                elif variant == "frog":
                    self._draw_frog(core_x, core_y, core_size_w, core_size_h, meal_color)

                elif variant == "lizard":
                    self._draw_lizard(core_x, core_y, core_size_w, core_size_h, meal_color, facing)

                else:
                    Color(*meal_color)
                    Ellipse(pos=(core_x, core_y), size=(core_size_w, core_size_h))

                Color(0.98, 1.0, 1.0, 0.32)
                Ellipse(pos=(core_x + core_size_w * 0.14, core_y + core_size_h * 0.56), size=(core_size_w * 0.26, core_size_h * 0.18))
                Color(0.04, 0.06, 0.10, 0.46)
                Line(
                    ellipse=(
                        core_x - core_size_w * 0.02,
                        core_y - core_size_h * 0.02,
                        core_size_w * 1.04,
                        core_size_h * 1.04,
                    ),
                    width=1.1,
                )

            elif environment == "desert":
                dir_x, _ = self.controller.food.move_direction
                facing = -1 if dir_x < 0 else 1
                meal_color = {
                    "kangaroo_rat": (0.86, 0.60, 0.40, 1.0),
                    "mouse": (0.94, 0.82, 0.64, 1.0),
                    "shrew": (0.38, 0.48, 0.62, 1.0),
                    "small_bird": (0.92, 0.74, 0.26, 1.0),
                    "lizard": (0.56, 0.92, 0.30, 1.0),
                }.get(variant, (0.78, 0.56, 0.28, 1.0))

                if variant in {"mouse", "kangaroo_rat", "shrew"}:
                    self._draw_rodent(core_x, core_y, core_size_w, core_size_h, meal_color, facing, species=variant)

                elif variant == "small_bird":
                    self._draw_small_bird(core_x, core_y, core_size_w, core_size_h, meal_color, facing)

                elif variant == "lizard":
                    self._draw_lizard(core_x, core_y, core_size_w, core_size_h, meal_color, facing)

                else:
                    Color(*meal_color)
                    Ellipse(pos=(core_x, core_y), size=(core_size_w, core_size_h * 0.88))

                Color(0.94, 0.78, 0.48, 0.26)
                Ellipse(pos=(core_x + core_size_w * 0.14, core_y + core_size_h * 0.48), size=(core_size_w * 0.28, core_size_h * 0.18))

            else:
                # Meadow
                if variant == "toadstool":
                    Color(0.62, 0.22, 0.70, 1.0)
                    Ellipse(pos=(core_x + core_size_w * 0.10, core_y + core_size_h * 0.34), size=(core_size_w * 0.80, core_size_h * 0.46))
                    Color(0.92, 0.88, 0.76, 0.95)
                    Rectangle(pos=(core_x + core_size_w * 0.42, core_y + core_size_h * 0.10), size=(core_size_w * 0.16, core_size_h * 0.34))
                elif variant == "mouse":
                    dir_x, _ = self.controller.food.move_direction
                    facing = -1 if dir_x < 0 else 1
                    self._draw_rodent(
                        core_x,
                        core_y,
                        core_size_w,
                        core_size_h,
                        (0.78, 0.66, 0.56, 1.0),
                        facing,
                        species="mouse",
                        ear_color=(0.92, 0.80, 0.74, 0.95),
                        ear_size_override=0.09,
                        tail_length_override=0.18,
                    )
                elif variant == "frog":
                    self._draw_frog(
                        core_x,
                        core_y,
                        core_size_w,
                        core_size_h,
                        (0.30, 0.78, 0.36, 1.0),
                        limb_color=(0.24, 0.62, 0.28, 1.0),
                    )
                elif variant == "small_bird":
                    dir_x, _ = self.controller.food.move_direction
                    facing = -1 if dir_x < 0 else 1
                    self._draw_small_bird(core_x, core_y, core_size_w, core_size_h, (0.92, 0.76, 0.26, 1.0), facing)
                else:
                    meal_color = {
                        "mouse": (0.78, 0.66, 0.56, 1.0),
                        "frog": (0.30, 0.78, 0.36, 1.0),
                        "small_bird": (0.92, 0.76, 0.26, 1.0),
                    }.get(variant, (0.72, 0.82, 0.42, 1.0))
                    Color(*meal_color)
                    Ellipse(pos=(core_x, core_y), size=(core_size_w, core_size_h))
                    Color(0.98, 0.96, 0.84, 0.26)
                    Ellipse(pos=(core_x + core_size_w * 0.14, core_y + core_size_h * 0.56), size=(core_size_w * 0.30, core_size_h * 0.20))

            if medium_fx:
                # Universal top highlight for cleaner, high-definition finish.
                Color(1.0, 1.0, 1.0, 0.22)
                Ellipse(
                    pos=(core_x + core_size_w * 0.16, core_y + core_size_h * 0.60),
                    size=(core_size_w * 0.30, core_size_h * 0.18),
                )

            # Failsafe visibility marker: keeps meal readable even on complex backgrounds.
            marker_color = (0.96, 0.98, 1.0, 0.55) if food_type != "poison" else (0.98, 0.72, 1.0, 0.55)
            Color(*marker_color)
            Ellipse(
                pos=(core_x + core_size_w * 0.44, core_y + core_size_h * 0.44),
                size=(core_size_w * 0.12, core_size_h * 0.12),
            )

            # Draw snake trail (old head positions)
            if medium_fx:
                trail = self.controller.snake.trail
                turn_boost = self.controller.snake.turn_trail_boost
                for idx, trail_seg in enumerate(trail):
                    fade = (idx + 1) / max(1, len(trail))
                    alpha = (0.06 + fade * 0.12) + turn_boost * 0.10
                    Color(0.16, 0.92, 0.65, min(0.30, alpha))
                    tx = self.x + offset_x + trail_seg[0] * cell_width
                    ty = self.y + offset_y + trail_seg[1] * cell_height
                    inset = cell_width * (0.22 + (1 - fade) * 0.12) - (turn_boost * cell_width * 0.04)
                    inset = max(cell_width * 0.06, inset)
                    Ellipse(pos=(tx + inset, ty + inset), size=(cell_width - inset * 2, cell_height - inset * 2))

            # Only use torus interpolation/copies when wrap mode is explicitly enabled.
            wrap_enabled = bool(self.controller.current_mode.should_wrap_edges())
            if wrap_enabled:
                interpolated = self.controller.snake.get_interpolated_segments(
                    self.controller.interpolation_alpha,
                    constants.BOARD_COLS,
                    constants.BOARD_ROWS,
                )
            else:
                interpolated = self.controller.snake.get_interpolated_segments(
                    self.controller.interpolation_alpha,
                )
            board_w = constants.BOARD_COLS
            board_h = constants.BOARD_ROWS
            prev_segments = self.controller.snake.previous_segments
            curr_segments = self.controller.snake.segments

            def _mirror_offsets(index: int, seg_x: float, seg_y: float) -> list[tuple[float, float]]:
                # Duplicate only for segments actively crossing a wrapped edge this frame.
                if not wrap_enabled:
                    return [(0.0, 0.0)]

                if index >= len(prev_segments) or index >= len(curr_segments):
                    return [(0.0, 0.0)]

                prev_x, prev_y = prev_segments[index]
                curr_x, curr_y = curr_segments[index]
                wrapped_x = abs(curr_x - prev_x) > board_w / 2
                wrapped_y = abs(curr_y - prev_y) > board_h / 2

                x_offsets = [0.0]
                y_offsets = [0.0]

                if wrapped_x:
                    # Left wrap (e.g. 0 -> cols-1) interpolates into negatives.
                    if curr_x > prev_x and seg_x < 0.0:
                        x_offsets.append(board_w)
                    # Right wrap (e.g. cols-1 -> 0) interpolates above cols-1.
                    elif curr_x < prev_x and seg_x > board_w - 1.0:
                        x_offsets.append(-board_w)

                if wrapped_y:
                    # Bottom wrap (0 -> rows-1) interpolates into negatives.
                    if curr_y > prev_y and seg_y < 0.0:
                        y_offsets.append(board_h)
                    # Top wrap (rows-1 -> 0) interpolates above rows-1.
                    elif curr_y < prev_y and seg_y > board_h - 1.0:
                        y_offsets.append(-board_h)

                return [(ox, oy) for ox in x_offsets for oy in y_offsets]

            palette = self._snake_palette()
            for i, seg in enumerate(interpolated):
                for dx, dy in _mirror_offsets(i, seg[0], seg[1]):
                    x = self.x + offset_x + (seg[0] + dx) * cell_width
                    y = self.y + offset_y + (seg[1] + dy) * cell_height

                    if medium_fx:
                        # Ground contact shadow for depth.
                        shadow_alpha = 0.20 if i == 0 else 0.14
                        Color(0.05, 0.08, 0.04, shadow_alpha if full_fx else shadow_alpha * 0.8)
                        Ellipse(
                            pos=(x + cell_width * 0.12, y + cell_height * 0.06),
                            size=(cell_width * 0.76, cell_height * 0.26),
                        )

                    if i == 0:  # Head - 3D effect with layers
                        if medium_fx and self.controller.scoring.combo_level >= constants.COMBO_AURA_THRESHOLD:
                            aura_pulse = 0.08 * (1 + math.sin(self._animation_time * 9.0))
                            Color(0.95, 0.80, 0.35, 0.20 + aura_pulse)
                            Ellipse(
                                pos=(x - cell_width * 0.22, y - cell_height * 0.22),
                                size=(cell_width * 1.44, cell_height * 1.44),
                            )
                        if medium_fx:
                            # Shadow/depth layer.
                            Color(palette["glow"][0] * 0.4, palette["glow"][1] * 0.4, palette["glow"][2] * 0.4, palette["glow"][3] * 0.5)
                            Ellipse(pos=(x - cell_width * 0.15, y - cell_height * 0.15), size=(cell_width * 1.3, cell_height * 1.3))

                            # Glow halo.
                            Color(*palette["glow"])
                            Ellipse(pos=(x - cell_width * 0.12, y - cell_height * 0.12), size=(cell_width * 1.24, cell_height * 1.24))

                        # Main head color
                        Color(*palette["head"])
                        Ellipse(pos=(x, y), size=(cell_width, cell_height))

                        if medium_fx:
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
                        if medium_fx:
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

                        if medium_fx:
                            # Dorsal stripe (3D depth from top)
                            Color(*palette["dorsal"])
                            RoundedRectangle(
                                pos=(x + cell_width * 0.16, y + cell_height * 0.56),
                                size=(cell_width * 0.68, cell_height * 0.28),
                                radius=(2,),
                            )

                            if full_fx:
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
            particle_limit = len(self._particles) if full_fx else min(len(self._particles), 8)
            for p in self._particles[:particle_limit]:
                Ellipse(pos=(p.x_pos, p.y_pos), size=(p.size, p.size))


class MenuNeonButton(Button):
    """Premium neon button with hover glow and press feedback."""

    def __init__(self, secondary: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.secondary = secondary
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.color = (0.88, 0.98, 0.92, 1.0)
        self.bold = True
        self.markup = True
        self.halign = "center"
        self.valign = "middle"
        self.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))

        self._hovered = False
        self._hover_progress = 0.0
        self._press_progress = 0.0
        self._target_press = 0.0
        self._tick_event = Clock.schedule_interval(self._tick, 1.0 / 60.0)

        base_glow = (0.10, 0.94, 0.58, 0.34) if not secondary else (0.20, 0.84, 1.00, 0.24)
        base_fill = (0.08, 0.14, 0.12, 0.72) if not secondary else (0.08, 0.13, 0.16, 0.62)
        edge = (0.28, 1.00, 0.72, 0.85) if not secondary else (0.43, 0.90, 1.00, 0.72)

        with self.canvas.before:
            self._glow_color = Color(*base_glow)
            self._glow_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[16])
            self._shadow_color = Color(0.0, 0.0, 0.0, 0.34)
            self._shadow_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[16])
            self._fill_color = Color(*base_fill)
            self._fill_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[14])
            self._fill_band_color = Color(0.98, 1.0, 1.0, 0.08)
            self._fill_band = RoundedRectangle(pos=self.pos, size=self.size, radius=[14])
        with self.canvas.after:
            self._edge_color = Color(*edge)
            self._edge_line = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, 14), width=1.25)

        self.bind(pos=self._update_canvas, size=self._update_canvas)
        self.bind(on_press=self._on_press, on_release=self._on_release)
        Window.bind(mouse_pos=self._on_mouse_pos)
        self.bind(parent=self._on_parent_changed)

    def _on_parent_changed(self, *_):
        if self.parent is None:
            try:
                Window.unbind(mouse_pos=self._on_mouse_pos)
            except Exception:
                pass
            if self._tick_event is not None:
                self._tick_event.cancel()
                self._tick_event = None

    def _on_mouse_pos(self, _, pos):
        if not self.get_root_window() or self.disabled:
            self._hovered = False
            return
        local_x, local_y = self.to_widget(*pos)
        self._hovered = self.collide_point(local_x, local_y)

    def _on_press(self, *_):
        self._target_press = 1.0

    def _on_release(self, *_):
        self._target_press = 0.0

    def _tick(self, dt):
        hover_target = 1.0 if self._hovered else 0.0
        self._hover_progress += (hover_target - self._hover_progress) * min(1.0, dt * 14.0)
        self._press_progress += (self._target_press - self._press_progress) * min(1.0, dt * 24.0)

        self._update_canvas()
        return True

    def _update_canvas(self, *_):
        x_pos = self.x
        press_offset = 1.6 * self._press_progress
        y_pos = self.y - press_offset
        width = self.width
        height = self.height
        radius = 14

        glow_pad = 6.0 + self._hover_progress * 5.0
        self._glow_rect.pos = (x_pos - glow_pad * 0.5, y_pos - glow_pad * 0.4)
        self._glow_rect.size = (width + glow_pad, height + glow_pad * 0.8)
        self._glow_rect.radius = [radius + 2]

        self._shadow_rect.pos = (x_pos + 1.0, y_pos - 2.0)
        self._shadow_rect.size = (width, height)
        self._shadow_rect.radius = [radius]

        self._fill_rect.pos = (x_pos, y_pos)
        self._fill_rect.size = (width, height)
        self._fill_rect.radius = [radius]

        self._fill_band.pos = (x_pos + 1.0, y_pos + height * 0.52)
        self._fill_band.size = (max(0.0, width - 2.0), max(0.0, height * 0.42))
        self._fill_band.radius = [radius]

        self._edge_line.rounded_rectangle = (x_pos, y_pos, width, height, radius)

        if self.secondary:
            self._glow_color.rgba = (0.20, 0.84, 1.0, 0.16 + self._hover_progress * 0.34)
            self._fill_color.rgba = (0.08, 0.14, 0.18, 0.56 + self._hover_progress * 0.14)
            self._edge_color.rgba = (0.45, 0.93, 1.0, 0.56 + self._hover_progress * 0.40)
        else:
            self._glow_color.rgba = (0.10, 0.98, 0.62, 0.22 + self._hover_progress * 0.42)
            self._fill_color.rgba = (0.08, 0.15, 0.11, 0.66 + self._hover_progress * 0.18)
            self._edge_color.rgba = (0.33, 1.0, 0.74, 0.64 + self._hover_progress * 0.34)


class NeonSwitch(Button):
    """Animated neon toggle switch for settings rows."""

    def __init__(self, active: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.active = bool(active)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.text = ""

        self._hovered = False
        self._progress = 1.0 if self.active else 0.0
        self._target = self._progress
        self._tick_event = Clock.schedule_interval(self._tick, 1.0 / 60.0)

        with self.canvas.before:
            self._glow_color = Color(0.24, 1.0, 0.72, 0.08)
            self._glow = RoundedRectangle(pos=self.pos, size=self.size, radius=[12])
            self._track_color = Color(0.10, 0.17, 0.16, 0.95)
            self._track = RoundedRectangle(pos=self.pos, size=self.size, radius=[10])
            self._thumb_color = Color(0.88, 0.99, 0.94, 1.0)
            self._thumb = Ellipse(pos=self.pos, size=(12, 12))
        with self.canvas.after:
            self._edge_color = Color(0.32, 0.92, 0.74, 0.36)
            self._edge = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, 10), width=1.1)

        self.bind(pos=self._update_canvas, size=self._update_canvas)
        self.bind(on_press=self._toggle)
        Window.bind(mouse_pos=self._on_mouse_pos)
        self.bind(parent=self._on_parent_changed)

    def _on_parent_changed(self, *_):
        if self.parent is None:
            try:
                Window.unbind(mouse_pos=self._on_mouse_pos)
            except Exception:
                pass
            if self._tick_event is not None:
                self._tick_event.cancel()
                self._tick_event = None

    def _on_mouse_pos(self, _, pos):
        if not self.get_root_window():
            self._hovered = False
            return
        lx, ly = self.to_widget(*pos)
        self._hovered = self.collide_point(lx, ly)

    def _toggle(self, *_):
        self.set_active(not self.active)

    def set_active(self, value: bool):
        self.active = bool(value)
        self._target = 1.0 if self.active else 0.0

    def _tick(self, dt):
        self._progress += (self._target - self._progress) * min(1.0, dt * 16.0)
        self._update_canvas()
        return True

    def _update_canvas(self, *_):
        x_pos = self.x
        y_pos = self.y
        width = max(32.0, self.width)
        height = max(20.0, self.height)

        glow_pad = 2.0 + (4.0 * (0.5 + self._progress * 0.5))
        self._glow.pos = (x_pos - glow_pad * 0.5, y_pos - glow_pad * 0.5)
        self._glow.size = (width + glow_pad, height + glow_pad)
        self._glow.radius = [height * 0.5 + 2.0]

        self._track.pos = (x_pos, y_pos)
        self._track.size = (width, height)
        self._track.radius = [height * 0.5]

        thumb_size = height * 0.74
        thumb_x = x_pos + (height * 0.13) + (width - height * 1.0) * self._progress
        thumb_y = y_pos + (height - thumb_size) * 0.5
        self._thumb.pos = (thumb_x, thumb_y)
        self._thumb.size = (thumb_size, thumb_size)

        self._edge.rounded_rectangle = (x_pos, y_pos, width, height, height * 0.5)

        hover_boost = 0.18 if self._hovered else 0.0
        self._track_color.rgba = (
            0.10 + self._progress * 0.08,
            0.17 + self._progress * 0.30,
            0.16 + self._progress * 0.18,
            0.95,
        )
        self._edge_color.rgba = (0.30, 0.95, 0.72, 0.28 + self._progress * 0.42 + hover_boost)
        self._glow_color.rgba = (0.24, 1.0, 0.72, 0.06 + self._progress * 0.22 + hover_boost * 0.5)


class MenuScreen(Screen):
    """Main menu screen."""
    
    def on_enter(self):
        app = App.get_running_app()
        if not hasattr(self, '_menu_modes'):
            self._menu_modes = ["Classic", "No Wall", "Time Attack", "Hardcore"]
        if not hasattr(self, '_mode_index'):
            self._mode_index = 0

        last_mode = app.save_manager.get_nested("player.last_mode", "Classic")
        if last_mode in self._menu_modes:
            self._mode_index = self._menu_modes.index(last_mode)
        self._refresh_mode_ui()
        env = app.save_manager.get_nested("settings.environment_theme", "meadow")
        app.sound_manager.play_environment_music(env)

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
        app.sound_manager.play("ui_nav")
        selected_mode = self._menu_modes[getattr(self, '_mode_index', 0)] if hasattr(self, '_menu_modes') else "Classic"
        mode_map = {"Classic": "classic", "No Wall": "no_wall", "Time Attack": "time_attack", "Hardcore": "hardcore"}
        mode = mode_map.get(selected_mode, "classic")
        
        app.game_controller.start_new_game(mode)
        app.root.current = "game"

    def cycle_mode(self):
        """Cycle through game modes from the main menu button."""
        if not hasattr(self, '_menu_modes'):
            self._menu_modes = ["Classic", "No Wall", "Time Attack", "Hardcore"]
            self._mode_index = 0
        self._mode_index = (self._mode_index + 1) % len(self._menu_modes)
        app = App.get_running_app()
        app.save_manager.set_nested("player.last_mode", self._menu_modes[self._mode_index])
        app.save_manager.save()
        app.sound_manager.play("ui_nav")
        self._refresh_mode_ui()

    def _refresh_mode_ui(self):
        """Refresh selected-mode widgets if present."""
        if not hasattr(self, '_menu_modes'):
            return
        current_mode = self._menu_modes[getattr(self, '_mode_index', 0)]
        if hasattr(self, 'ids') and 'mode_button' in self.ids:
            self.ids['mode_button'].text = f"[b]\u25c9  MODES: {current_mode.upper()}[/b]"
        if hasattr(self, 'ids') and 'mode_value' in self.ids:
            self.ids['mode_value'].text = f"Mode: {current_mode}"

    def show_progression(self):
        """Show progression screen."""
        app = App.get_running_app()
        app.sound_manager.play("ui_nav")
        app.root.current = "progression"

    def show_leaderboard(self):
        """Show leaderboard screen."""
        app = App.get_running_app()
        app.sound_manager.play("ui_nav")
        app.root.current = "leaderboard"

    def show_settings(self):
        """Show settings screen."""
        app = App.get_running_app()
        app.sound_manager.play("ui_nav")
        app.root.current = "settings"

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
    fps_text = StringProperty("FPS: 60")
    quality_text = StringProperty("Quality: High")
    effect_text = StringProperty("")
    status_text = StringProperty("")
    debug_text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._death_slowmo_timer = 0.0
        self._fps_smooth = float(constants.TARGET_FPS)
        self._low_fps_hold = 0.0
        self._quality_switch_cooldown = 0.0

    def _get_target_fps(self) -> int:
        """Return update FPS based on graphics quality preference."""
        app = App.get_running_app()
        quality = app.save_manager.get_nested("settings.graphics_quality", "balanced")
        return {
            "high": constants.TARGET_FPS,
            "balanced": 45,
            "performance": 30,
        }.get(quality, constants.TARGET_FPS)

    def on_enter(self):
        app = App.get_running_app()
        if hasattr(self, 'ids') and 'game_board' in self.ids:
            self.ids.game_board.controller = app.game_controller
        env = app.save_manager.get_nested("settings.environment_theme", "meadow")
        app.sound_manager.play_environment_music(env)
        target_fps = self._get_target_fps()
        Clock.schedule_interval(self.update_game, 1.0 / max(1, target_fps))
        Clock.schedule_interval(self.update_hud, 0.1)
        Window.bind(on_keyboard=self.on_keyboard)

    def on_leave(self):
        App.get_running_app().sound_manager.stop_music()
        Clock.unschedule(self.update_game)
        Clock.unschedule(self.update_hud)
        Window.unbind(on_keyboard=self.on_keyboard)

    def update_game(self, dt):
        """Update game logic."""
        if self.manager.current != "game":
            return
        if dt > 0:
            current_fps = 1.0 / dt
            self._fps_smooth = (self._fps_smooth * 0.9) + (current_fps * 0.1)
        app = App.get_running_app()
        self._auto_tune_quality(dt, app)
        effective_dt = dt
        if self._death_slowmo_timer > 0:
            self._death_slowmo_timer -= dt
            effective_dt = dt * 0.28

        app.game_controller.update(effective_dt)
        if hasattr(self, 'ids') and 'game_board' in self.ids:
            self.ids.game_board.advance(dt)

    def _auto_tune_quality(self, dt: float, app) -> None:
        """Auto-downgrade graphics quality when FPS stays low for a while."""
        if not constants.AUTO_QUALITY_DOWNGRADE:
            return

        self._quality_switch_cooldown = max(0.0, self._quality_switch_cooldown - dt)
        quality = app.save_manager.get_nested("settings.graphics_quality", "balanced")

        threshold = None
        next_quality = None
        if quality == "high":
            threshold = constants.AUTO_QUALITY_HIGH_TO_BALANCED_FPS
            next_quality = "balanced"
        elif quality == "balanced":
            threshold = constants.AUTO_QUALITY_BALANCED_TO_PERFORMANCE_FPS
            next_quality = "performance"

        if threshold is None or next_quality is None:
            self._low_fps_hold = 0.0
            return

        if self._fps_smooth < threshold and self._quality_switch_cooldown <= 0.0:
            self._low_fps_hold += dt
        else:
            self._low_fps_hold = max(0.0, self._low_fps_hold - dt * 0.5)

        if self._low_fps_hold < constants.AUTO_QUALITY_DROP_HOLD_SECONDS:
            return

        app.save_manager.set_nested("settings.graphics_quality", next_quality)
        app.save_manager.save()
        self._low_fps_hold = 0.0
        self._quality_switch_cooldown = constants.AUTO_QUALITY_SWITCH_COOLDOWN_SECONDS

        # Rebuild update cadence for the newly selected quality tier.
        Clock.unschedule(self.update_game)
        target_fps = self._get_target_fps()
        Clock.schedule_interval(self.update_game, 1.0 / max(1, target_fps))

    def update_hud(self, dt):
        """Update HUD display."""
        app = App.get_running_app()
        self.score_text = f"Score: {app.game_controller.scoring.score}"
        self.high_score_text = f"High: {app.game_controller.scoring.high_score}"
        self.combo_text = f"Combo: {app.game_controller.scoring.combo_level}x"
        self.mode_text = app.game_controller.current_mode.name
        self.fps_text = f"FPS: {int(self._fps_smooth)}"
        quality = app.save_manager.get_nested("settings.graphics_quality", "balanced")
        self.quality_text = f"Quality: {quality.capitalize()}"
        self.effect_text = app.game_controller.effect_message
        status_parts = []
        if app.game_controller.poison_active:
            status_parts.append("Poison: FAST")
        if app.game_controller.boost_active:
            status_parts.append(f"Boost: {app.game_controller.boost_timer:.1f}s")
        self.status_text = "  |  ".join(status_parts)

        show_debug_overlay = self._is_dev_mode_enabled(app)
        food = getattr(app.game_controller, "food", None)
        theme = getattr(food, "environment_theme", None) or app.save_manager.get_nested("settings.environment_theme", "meadow")
        variant = getattr(food, "food_variant", "unknown")
        food_type = getattr(food, "food_type", "normal")
        self.debug_text = f"DEV | theme={theme} | variant={variant} | type={food_type}" if show_debug_overlay else ""

        if hasattr(self, 'ids'):
            if 'score_label' in self.ids:
                self.ids['score_label'].text = self.score_text
            if 'high_label' in self.ids:
                self.ids['high_label'].text = self.high_score_text
            if 'mode_label' in self.ids:
                self.ids['mode_label'].text = self.mode_text
            if 'combo_label' in self.ids:
                self.ids['combo_label'].text = self.combo_text
            if 'fps_label' in self.ids:
                self.ids['fps_label'].text = self.fps_text
            if 'quality_label' in self.ids:
                self.ids['quality_label'].text = self.quality_text
            if 'effect_label' in self.ids:
                self.ids['effect_label'].text = self.effect_text
                self.ids['effect_label'].opacity = 1 if self.effect_text else 0
            if 'status_label' in self.ids:
                self.ids['status_label'].text = self.status_text
                self.ids['status_label'].opacity = 1 if self.status_text else 0
            if 'debug_label' in self.ids:
                self.ids['debug_label'].text = self.debug_text
                self.ids['debug_label'].opacity = 0.85 if self.debug_text else 0
            if 'boost_btn' in self.ids:
                if app.game_controller.boost_active:
                    self.ids['boost_btn'].text = f"[b]BOOST ON[/b]\n[size=9]{app.game_controller.boost_timer:.1f}s[/size]"
                    self.ids['boost_btn'].disabled = True
                    self.ids['boost_btn'].background_color = (0.30, 0.36, 0.20, 1.0)
                elif app.game_controller.boost_cooldown_timer > 0:
                    self.ids['boost_btn'].text = f"[b]BOOST CD[/b]\n[size=9]{app.game_controller.boost_cooldown_timer:.1f}s[/size]"
                    self.ids['boost_btn'].disabled = True
                    self.ids['boost_btn'].background_color = (0.22, 0.18, 0.12, 1.0)
                else:
                    self.ids['boost_btn'].text = "[b]BOOST[/b]\n[size=9]Shift[/size]"
                    self.ids['boost_btn'].disabled = False
                    self.ids['boost_btn'].background_color = (0.22, 0.30, 0.16, 1.0)

    def _is_dev_mode_enabled(self, app) -> bool:
        """Return True when dev overlay should be visible."""
        from_env = os.environ.get("SNAKE_DEV_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
        from_settings = bool(app.save_manager.get_nested("settings.dev_mode", False))
        debug_attached = bool(getattr(sys, "gettrace", lambda: None)())
        return from_env or from_settings or debug_attached

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
        lower_code = (codepoint or "").lower()
        if lower_code == 'w' or key == 273:
            App.get_running_app().game_controller.request_direction("up")
        elif lower_code == 's' or key == 274:
            App.get_running_app().game_controller.request_direction("down")
        elif lower_code == 'a' or key == 276:
            App.get_running_app().game_controller.request_direction("left")
        elif lower_code == 'd' or key == 275:
            App.get_running_app().game_controller.request_direction("right")
        elif key == 32:
            app = App.get_running_app()
            if app.game_controller.current_mode.is_paused:
                app.game_controller.resume()
            else:
                app.game_controller.pause()
        elif key in (303, 304):
            self.use_boost()
        elif lower_code == 'r':
            app = App.get_running_app()
            app.root.current = "menu"
            app.root.get_screen("menu").start_game()
        elif key == 27:  # Esc
            self.go_menu()
        return False

    def use_boost(self):
        """Try to activate temporary speed boost."""
        app = App.get_running_app()
        if app.game_controller.activate_boost():
            app.sound_manager.play("ui_nav")

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
        app = App.get_running_app()
        app.sound_manager.play("ui_nav")
        if self.manager is not None:
            self.manager.current = "menu"
        else:
            app.root.current = "menu"


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
        self._refresh_leaderboard_cards(top_scores)

    def _refresh_leaderboard_cards(self, top_scores):
        """Refresh visual leaderboard card list."""
        if not hasattr(self, 'ids'):
            return
        if 'leaderboard_container' not in self.ids:
            return

        container = self.ids['leaderboard_container']
        container.clear_widgets()

        if 'leaderboard_count_label' in self.ids:
            self.ids['leaderboard_count_label'].text = f"{len(top_scores)}/10"

        if not top_scores:
            if 'leaderboard_empty_label' in self.ids:
                self.ids['leaderboard_empty_label'].text = "No scores yet. Play a match to create your first record."
            return

        if 'leaderboard_empty_label' in self.ids:
            self.ids['leaderboard_empty_label'].text = ""

        for i, entry in enumerate(top_scores, 1):
            row = BoxLayout(size_hint_y=None, height=58, spacing=10, padding=[10, 8, 10, 8])

            with row.canvas.before:
                if i == 1:
                    Color(0.28, 0.23, 0.08, 0.95)
                elif i == 2:
                    Color(0.19, 0.22, 0.26, 0.95)
                elif i == 3:
                    Color(0.24, 0.18, 0.12, 0.95)
                else:
                    Color(0.08, 0.12, 0.16, 0.92)
                row_bg = RoundedRectangle(pos=row.pos, size=row.size, radius=[12])

            with row.canvas.after:
                if i == 1:
                    Color(0.96, 0.80, 0.28, 0.92)
                elif i == 2:
                    Color(0.78, 0.86, 0.96, 0.80)
                elif i == 3:
                    Color(0.86, 0.62, 0.34, 0.80)
                else:
                    Color(0.46, 0.67, 0.90, 0.45)
                row_border = Line(rounded_rectangle=(row.x, row.y, row.width, row.height, 12), width=1.1)

            def _update_row(*_):
                row_bg.pos = row.pos
                row_bg.size = row.size
                row_border.rounded_rectangle = (row.x, row.y, row.width, row.height, 12)

            row.bind(pos=_update_row, size=_update_row)

            medal = ""
            if i == 1:
                medal = "[b]🥇[/b]"
            elif i == 2:
                medal = "[b]🥈[/b]"
            elif i == 3:
                medal = "[b]🥉[/b]"

            rank_label = Label(
                text=f"{medal} [b]#{i}[/b]" if medal else f"[b]#{i}[/b]",
                markup=True,
                size_hint_x=0.16,
                color=(0.94, 0.98, 1.0, 1.0),
                font_size="13sp",
            )

            player = str(entry.get("player", "Player"))[:18]
            player_label = Label(
                text=f"[b]{player}[/b]",
                markup=True,
                halign="left",
                valign="middle",
                size_hint_x=0.52,
                color=(0.92, 0.98, 1.0, 1.0),
                font_size="12sp",
            )
            player_label.bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))

            score = int(entry.get("score", 0))
            score_label = Label(
                text=f"[b]{score}[/b]",
                markup=True,
                size_hint_x=0.20,
                color=(0.98, 0.91, 0.56, 1.0),
                font_size="14sp",
            )

            mode = str(entry.get("mode", "classic")).replace("_", " ").title()
            mode_label = Label(
                text=mode,
                size_hint_x=0.24,
                color=(0.72, 0.88, 1.0, 0.92),
                font_size="10sp",
                halign="right",
                valign="middle",
            )
            mode_label.bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))

            row.add_widget(rank_label)
            row.add_widget(player_label)
            row.add_widget(score_label)
            row.add_widget(mode_label)
            container.add_widget(row)

    def go_back(self):
        """Return to menu."""
        app = App.get_running_app()
        app.sound_manager.play("ui_nav")
        app.root.current = "menu"


class GameOverScreen(Screen):
    """Game-over summary screen with restart/menu actions."""

    summary_text = StringProperty("Game Over")
    mode_text = StringProperty("Classic")
    score_text = StringProperty("0")
    high_score_text = StringProperty("0")
    level_text = StringProperty("1")
    mode_hint_text = StringProperty("Run Ended")

    def on_enter(self):
        if hasattr(self, 'ids') and 'summary_label' in self.ids:
            self.ids['summary_label'].text = self.summary_text
        if hasattr(self, 'ids') and 'mode_label' in self.ids:
            self.ids['mode_label'].text = self.mode_text
        if hasattr(self, 'ids') and 'score_value' in self.ids:
            self.ids['score_value'].text = self.score_text
        if hasattr(self, 'ids') and 'high_value' in self.ids:
            self.ids['high_value'].text = self.high_score_text
        if hasattr(self, 'ids') and 'level_value' in self.ids:
            self.ids['level_value'].text = self.level_text

    def restart_game(self):
        app = App.get_running_app()
        app.sound_manager.play("ui_nav")
        app.root.current = "menu"
        app.root.get_screen("menu").start_game()

    def go_menu(self):
        app = App.get_running_app()
        app.sound_manager.play("ui_nav")
        app.root.current = "menu"

    def open_leaderboard(self):
        app = App.get_running_app()
        app.sound_manager.play("ui_nav")
        app.root.current = "leaderboard"


class SettingsScreen(Screen):
    """Settings screen."""

    GAME_MODES = ["Classic", "No Wall", "Time Attack", "Hardcore"]

    def on_enter(self):
        app = App.get_running_app()
        self._syncing_controls = True

        sound_enabled = bool(app.save_manager.get_nested("settings.sound_enabled", True))
        if 'sound_toggle' in self.ids and hasattr(self.ids['sound_toggle'], 'set_active'):
            self.ids['sound_toggle'].set_active(sound_enabled)

        vibration_enabled = bool(app.save_manager.get_nested("settings.vibration_enabled", True))
        if 'vibration_toggle' in self.ids and hasattr(self.ids['vibration_toggle'], 'set_active'):
            self.ids['vibration_toggle'].set_active(vibration_enabled)

        show_grid = bool(app.save_manager.get_nested("settings.show_grid", True))
        if 'grid_toggle' in self.ids and hasattr(self.ids['grid_toggle'], 'set_active'):
            self.ids['grid_toggle'].set_active(show_grid)

        master = float(app.save_manager.get_nested("settings.master_volume", 1.0))
        sfx = float(app.save_manager.get_nested("settings.sfx_volume", 1.0))
        sensitivity = float(app.save_manager.get_nested("settings.control_sensitivity", 1.0))

        if 'master_slider' in self.ids:
            self.ids['master_slider'].value = master * 100.0
        if 'sfx_slider' in self.ids:
            self.ids['sfx_slider'].value = sfx * 100.0
        if 'sensitivity_slider' in self.ids:
            self.ids['sensitivity_slider'].value = sensitivity * 100.0

        self._update_audio_labels()
        self._update_sensitivity_label(sensitivity)
        self._refresh_gameplay_labels()
        self._refresh_graphics_labels()
        self._syncing_controls = False

    def _update_audio_labels(self):
        app = App.get_running_app()
        master = float(app.save_manager.get_nested("settings.master_volume", 1.0))
        sfx = float(app.save_manager.get_nested("settings.sfx_volume", 1.0))
        if 'master_value_label' in self.ids:
            self.ids['master_value_label'].text = f"{int(master * 100)}%"
        if 'sfx_value_label' in self.ids:
            self.ids['sfx_value_label'].text = f"{int(sfx * 100)}%"

    def _update_sensitivity_label(self, value: float):
        if 'sensitivity_value_label' in self.ids:
            self.ids['sensitivity_value_label'].text = f"{value:.2f}x"

    def _refresh_graphics_labels(self):
        app = App.get_running_app()
        quality = app.save_manager.get_nested("settings.graphics_quality", "balanced")
        if 'quality_button' in self.ids:
            self.ids['quality_button'].text = f"[b]{quality.capitalize()}[/b]"
        if 'quality_spinner' in self.ids:
            self.ids['quality_spinner'].text = quality.capitalize()
        env = app.save_manager.get_nested("settings.environment_theme", "meadow")
        env_map = {
            "meadow": "Meadow",
            "underwater": "Underwater",
            "iceland": "Iceland",
            "desert": "Desert",
        }
        if 'environment_button' in self.ids:
            self.ids['environment_button'].text = f"[b]{env_map.get(env, 'Meadow')}[/b]"

    def _refresh_gameplay_labels(self):
        app = App.get_running_app()
        current_mode = app.save_manager.get_nested("player.last_mode", "Classic")
        if current_mode not in self.GAME_MODES:
            current_mode = "Classic"
            app.save_manager.set_nested("player.last_mode", current_mode)
            app.save_manager.save()
        if 'mode_button' in self.ids:
            self.ids['mode_button'].text = f"[b]{current_mode}[/b]"

        speed_mode = app.progression.get_speed_mode()
        if 'speed_button' in self.ids:
            self.ids['speed_button'].text = f"[b]{speed_mode.capitalize()}[/b]"
        if 'speed_spinner' in self.ids:
            self.ids['speed_spinner'].text = speed_mode.capitalize()

        selected = app.progression.get_selected_skin()
        skin_name = constants.SNAKE_SKINS.get(selected, {"name": selected}).get("name", selected)
        if 'skin_button' in self.ids:
            self.ids['skin_button'].text = f"[b]{skin_name}[/b]"
        if 'skin_spinner' in self.ids:
            self.ids['skin_spinner'].text = skin_name

    def toggle_sound(self, state=None):
        app = App.get_running_app()
        current = bool(app.save_manager.get_nested("settings.sound_enabled", True))
        updated = (not current) if state is None else bool(state)
        app.sound_manager.enabled = updated
        app.save_manager.set_nested("settings.sound_enabled", updated)
        app.save_manager.save()
        if updated:
            app.sound_manager.play("click")

    def set_master_volume(self, value: float):
        if getattr(self, '_syncing_controls', False):
            return
        app = App.get_running_app()
        updated = max(0.0, min(1.0, float(value)))
        app.save_manager.set_nested("settings.master_volume", round(updated, 2))
        app.sound_manager.set_volumes(
            app.save_manager.get_nested("settings.master_volume", 1.0),
            app.save_manager.get_nested("settings.sfx_volume", 1.0),
        )
        app.save_manager.save()
        self._update_audio_labels()

    def set_sfx_volume(self, value: float):
        if getattr(self, '_syncing_controls', False):
            return
        app = App.get_running_app()
        updated = max(0.0, min(1.0, float(value)))
        app.save_manager.set_nested("settings.sfx_volume", round(updated, 2))
        app.sound_manager.set_volumes(
            app.save_manager.get_nested("settings.master_volume", 1.0),
            app.save_manager.get_nested("settings.sfx_volume", 1.0),
        )
        app.save_manager.save()
        self._update_audio_labels()

    def toggle_vibration(self, state=None):
        app = App.get_running_app()
        current = bool(app.save_manager.get_nested("settings.vibration_enabled", True))
        updated = (not current) if state is None else bool(state)
        app.save_manager.set_nested("settings.vibration_enabled", updated)
        app.save_manager.save()

    def set_sensitivity(self, value: float):
        if getattr(self, '_syncing_controls', False):
            return
        app = App.get_running_app()
        updated = min(2.0, max(0.5, float(value)))
        app.save_manager.set_nested("settings.control_sensitivity", round(updated, 2))
        app.save_manager.save()
        self._update_sensitivity_label(updated)

    def cycle_graphics_quality(self):
        app = App.get_running_app()
        modes = ["high", "balanced", "performance"]
        current = app.save_manager.get_nested("settings.graphics_quality", "balanced")
        next_mode = modes[(modes.index(current) + 1) % len(modes)] if current in modes else modes[0]
        app.save_manager.set_nested("settings.graphics_quality", next_mode)
        app.save_manager.save()
        self._refresh_graphics_labels()
        app.sound_manager.play("click")

    def set_graphics_quality(self, value: str):
        if getattr(self, '_syncing_controls', False):
            return
        app = App.get_running_app()
        options = {"High": "high", "Balanced": "balanced", "Performance": "performance"}
        selected = options.get(value.strip(), "balanced")
        app.save_manager.set_nested("settings.graphics_quality", selected)
        app.save_manager.save()
        self._refresh_graphics_labels()
        app.sound_manager.play("click")

    def toggle_grid(self, state=None):
        app = App.get_running_app()
        current = bool(app.save_manager.get_nested("settings.show_grid", True))
        updated = (not current) if state is None else bool(state)
        app.save_manager.set_nested("settings.show_grid", updated)
        app.save_manager.save()

    def cycle_environment_theme(self):
        app = App.get_running_app()
        themes = ["meadow", "underwater", "iceland", "desert"]
        current = app.save_manager.get_nested("settings.environment_theme", "meadow")
        next_theme = themes[(themes.index(current) + 1) % len(themes)] if current in themes else themes[0]
        app.save_manager.set_nested("settings.environment_theme", next_theme)
        app.save_manager.save()
        self._refresh_graphics_labels()
        app.sound_manager.play_environment_music(next_theme)
        app.sound_manager.play("click")

    def cycle_snake_skin(self):
        app = App.get_running_app()
        unlocked = app.progression.get_unlocked_skins()
        if not unlocked:
            return

        unlocked_sorted = sorted(unlocked, key=lambda skin_id: constants.SNAKE_SKINS.get(skin_id, {}).get("name", skin_id))
        current = app.progression.get_selected_skin()
        next_skin = unlocked_sorted[0] if current not in unlocked_sorted else unlocked_sorted[(unlocked_sorted.index(current) + 1) % len(unlocked_sorted)]
        app.progression.set_selected_skin(next_skin)
        self._refresh_gameplay_labels()
        app.sound_manager.play("click")

    def set_snake_skin(self, skin_name: str):
        if getattr(self, '_syncing_controls', False):
            return
        app = App.get_running_app()
        target_id = None
        for skin_id in app.progression.get_unlocked_skins():
            display = constants.SNAKE_SKINS.get(skin_id, {"name": skin_id}).get("name", skin_id)
            if display == skin_name:
                target_id = skin_id
                break
        if target_id is None:
            return
        app.progression.set_selected_skin(target_id)
        self._refresh_gameplay_labels()
        app.sound_manager.play("click")

    def cycle_speed_mode(self):
        app = App.get_running_app()
        modes = list(constants.SPEED_MODES.keys())
        current = app.progression.get_speed_mode()
        next_mode = modes[0] if current not in modes else modes[(modes.index(current) + 1) % len(modes)]
        app.progression.set_speed_mode(next_mode)
        self._refresh_gameplay_labels()
        app.sound_manager.play("click")

    def cycle_game_mode(self):
        app = App.get_running_app()
        current = app.save_manager.get_nested("player.last_mode", "Classic")
        next_mode = self.GAME_MODES[0] if current not in self.GAME_MODES else self.GAME_MODES[(self.GAME_MODES.index(current) + 1) % len(self.GAME_MODES)]
        app.save_manager.set_nested("player.last_mode", next_mode)
        app.save_manager.save()
        self._refresh_gameplay_labels()
        app.sound_manager.play("click")

    def set_speed_mode(self, display_mode: str):
        if getattr(self, '_syncing_controls', False):
            return
        app = App.get_running_app()
        selected = display_mode.strip().lower().replace(" ", "_")
        if selected not in constants.SPEED_MODES:
            return
        app.progression.set_speed_mode(selected)
        self._refresh_gameplay_labels()
        app.sound_manager.play("click")

    def reset_progress(self):
        app = App.get_running_app()
        app.progression.reset_progress()
        if 'status_label' in self.ids:
            self.ids['status_label'].text = "Progress reset!"
        self.on_enter()

    def go_back(self):
        app = App.get_running_app()
        app.sound_manager.play("ui_nav")
        app.root.current = "menu"


class SnakeGameApp(App):
    """Main application."""
    
    title = "Snake Game Pro"

    def build(self):
        # Initialize core systems
        self.save_manager = SaveManager()
        self.progression = ProgressionSystem(self.save_manager)
        self.sound_manager = SoundManager()
        self.sound_manager.enabled = bool(self.save_manager.get_nested("settings.sound_enabled", True))
        self.sound_manager.set_volumes(
            self.save_manager.get_nested("settings.master_volume", 1.0),
            self.save_manager.get_nested("settings.sfx_volume", 1.0),
        )
        self.sound_manager.set_output_mode(self.save_manager.get_nested("settings.audio_output_mode", "auto"))
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

    def _play_click(self, *_):
        """Play button click sound if audio is enabled."""
        self.sound_manager.play("click")

    def _wire_click_sounds(self, *buttons):
        """Attach click sound to one or more buttons."""
        for button in buttons:
            if button is not None:
                button.bind(on_press=self._play_click)

    def _build_menu_screen(self):
        """Build main menu screen."""
        screen = MenuScreen(name="menu")
        root = FloatLayout()

        with root.canvas.before:
            Color(0.01, 0.03, 0.05, 1.0)
            bg_base = Rectangle(pos=root.pos, size=root.size)
            Color(0.07, 0.25, 0.20, 0.66)
            bg_glow_top = Rectangle(pos=root.pos, size=root.size)
            Color(0.02, 0.14, 0.24, 0.36)
            bg_glow_bottom = Rectangle(pos=root.pos, size=root.size)
            Color(0.32, 0.98, 0.82, 0.12)
            frame_line = Line(rounded_rectangle=(0, 0, 1, 1, 20), width=1.0)
            Color(0.45, 0.86, 1.0, 0.08)
            accent_arc = Line(points=[], width=1.0)

            bg_particle_colors = []
            bg_particles = []
            for _ in range(34):
                bg_particle_colors.append(Color(0.18, 0.95, 0.76, 0.10))
                bg_particles.append(Ellipse(pos=(-100, -100), size=(3, 3)))

            hover_particle_colors = []
            hover_particles = []
            for _ in range(12):
                hover_particle_colors.append(Color(0.45, 1.0, 0.98, 0.0))
                hover_particles.append(Ellipse(pos=(-100, -100), size=(3, 3)))

            # Decorative menu snake in the same style as the gameplay snake.
            snake_shadow_color = Color(0.05, 0.08, 0.04, 0.20)
            snake_shadow_segments = []
            snake_body_color = Color(0.25, 0.86, 0.58, 0.74)
            snake_body_segments = []
            snake_dorsal_color = Color(0.14, 0.62, 0.42, 0.52)
            snake_dorsal_segments = []
            snake_belly_color = Color(0.66, 0.92, 0.64, 0.48)
            snake_belly_segments = []
            for _ in range(24):
                snake_shadow_segments.append(RoundedRectangle(pos=(-120, -120), size=(14, 8), radius=(4,)))
                snake_body_segments.append(RoundedRectangle(pos=(-120, -120), size=(14, 8), radius=(4,)))
                snake_dorsal_segments.append(RoundedRectangle(pos=(-120, -120), size=(10, 3), radius=(2,)))
                snake_belly_segments.append(RoundedRectangle(pos=(-120, -120), size=(8, 2), radius=(2,)))

            snake_head_shadow_color = Color(0.04, 0.07, 0.04, 0.28)
            snake_head_shadow = Ellipse(pos=(-120, -120), size=(20, 14))
            snake_head_color = Color(0.32, 0.94, 0.66, 0.88)
            snake_head = Ellipse(pos=(-120, -120), size=(19, 13))
            snake_head_shade_color = Color(0.12, 0.58, 0.40, 0.44)
            snake_head_shade = Ellipse(pos=(-120, -120), size=(14, 7))
            snake_head_gloss_color = Color(1.0, 1.0, 0.95, 0.30)
            snake_head_gloss = Ellipse(pos=(-120, -120), size=(8, 3))
            snake_eye_color = Color(0.96, 0.98, 0.82, 0.95)
            snake_eye_left = Ellipse(pos=(-120, -120), size=(3.2, 3.2))
            snake_eye_right = Ellipse(pos=(-120, -120), size=(3.2, 3.2))
            snake_pupil_color = Color(0.04, 0.06, 0.05, 0.96)
            snake_pupil_left = Ellipse(pos=(-120, -120), size=(1.8, 1.8))
            snake_pupil_right = Ellipse(pos=(-120, -120), size=(1.8, 1.8))

        menu_snake_heading = 0.0
        menu_snake_head_x = 0.0
        menu_snake_head_y = 0.0
        menu_snake_needs_spawn = True
        swim_min_x = 0.0
        swim_max_x = 0.0
        swim_min_y = 0.0
        swim_max_y = 0.0
        menu_snake_points: list[list[float]] = []

        def _request_menu_snake_spawn(*_):
            nonlocal menu_snake_needs_spawn
            menu_snake_needs_spawn = True

        screen.bind(on_enter=_request_menu_snake_spawn)

        def _update_menu_snake(*_):
            nonlocal menu_snake_heading, menu_snake_head_x, menu_snake_head_y
            nonlocal menu_snake_needs_spawn
            nonlocal swim_min_x, swim_max_x, swim_min_y, swim_max_y
            nonlocal menu_snake_points
            width, height = root.size
            if width <= 0 or height <= 0:
                return
            swim_min_x = root.x + width * 0.12
            swim_max_x = root.x + width * 0.88
            swim_min_y = root.y + height * 0.54
            swim_max_y = root.y + height * 0.82

            if menu_snake_needs_spawn or (menu_snake_head_x == 0.0 and menu_snake_head_y == 0.0):
                spawn_from_left = random.random() < 0.5
                menu_snake_head_x = swim_min_x + width * 0.008 if spawn_from_left else swim_max_x - width * 0.008
                menu_snake_head_y = random.uniform(swim_min_y + height * 0.02, swim_max_y - height * 0.02)
                menu_snake_heading = random.uniform(-0.28, 0.28) if spawn_from_left else math.pi + random.uniform(-0.28, 0.28)
                menu_snake_needs_spawn = False
                menu_snake_points = [[menu_snake_head_x, menu_snake_head_y] for _ in range(len(snake_body_segments))]

        root.bind(pos=_update_menu_snake, size=_update_menu_snake)
        _update_menu_snake()

        def _update_background(*_):
            x_pos, y_pos = root.pos
            width, height = root.size
            bg_base.pos = root.pos
            bg_base.size = root.size
            bg_glow_top.pos = (x_pos, y_pos + height * 0.43)
            bg_glow_top.size = (width, height * 0.57)
            bg_glow_bottom.pos = (x_pos, y_pos)
            bg_glow_bottom.size = (width, height * 0.52)
            frame_line.rounded_rectangle = (x_pos + 3.0, y_pos + 3.0, max(1.0, width - 6.0), max(1.0, height - 6.0), 20)
            accent_arc.points = [
                x_pos + width * 0.16, y_pos + height * 0.20,
                x_pos + width * 0.34, y_pos + height * 0.15,
                x_pos + width * 0.66, y_pos + height * 0.22,
                x_pos + width * 0.84, y_pos + height * 0.18,
            ]

        root.bind(pos=_update_background, size=_update_background)

        title_glow = Label(
            text="[b]SNAKE[/b]",
            markup=True,
            font_size="72sp",
            color=(0.34, 1.0, 0.88, 0.24),
            size_hint=(0.86, 0.24),
            pos_hint={"center_x": 0.5, "top": 0.985},
        )
        title = Label(
            text="[b]SNAKE[/b]",
            markup=True,
            font_size="62sp",
            color=(0.92, 1.0, 0.98, 1.0),
            size_hint=(0.84, 0.20),
            pos_hint={"center_x": 0.5, "top": 0.975},
        )
        subtitle = Label(
            text="ARCADE EVOLUTION",
            font_size="13sp",
            color=(0.56, 0.96, 0.92, 0.90),
            bold=True,
            size_hint=(0.8, 0.07),
            pos_hint={"center_x": 0.5, "top": 0.87},
        )
        root.add_widget(title_glow)
        root.add_widget(title)
        root.add_widget(subtitle)

        left_card = BoxLayout(orientation="vertical", padding=[12, 10], spacing=4, size_hint=(0.245, 0.235), pos_hint={"x": 0.045, "center_y": 0.56})
        right_card = BoxLayout(orientation="vertical", padding=[12, 10], spacing=4, size_hint=(0.245, 0.235), pos_hint={"right": 0.955, "center_y": 0.56})

        for card, edge_rgba in ((left_card, (0.42, 0.90, 0.66, 0.62)), (right_card, (1.0, 0.78, 0.46, 0.58))):
            with card.canvas.before:
                Color(0.04, 0.11, 0.14, 0.80)
                card_bg = RoundedRectangle(pos=card.pos, size=card.size, radius=[16])
                Color(0.98, 1.0, 1.0, 0.10)
                card_band = RoundedRectangle(pos=card.pos, size=card.size, radius=[16])
                Color(0.0, 0.0, 0.0, 0.24)
                card_shadow = RoundedRectangle(pos=card.pos, size=card.size, radius=[16])
            with card.canvas.after:
                Color(*edge_rgba)
                card_edge = Line(rounded_rectangle=(card.x, card.y, card.width, card.height, 16), width=1.45)
                Color(1.0, 1.0, 1.0, 0.08)
                card_inner = Line(rounded_rectangle=(card.x + 2.0, card.y + 2.0, card.width - 4.0, card.height - 4.0, 14), width=1.0)

            def _update_card(*_, _card=card, _bg=card_bg, _band=card_band, _shadow=card_shadow, _edge=card_edge, _inner=card_inner):
                _bg.pos = _card.pos
                _bg.size = _card.size
                _band.pos = (_card.x + 1.0, _card.y + _card.height * 0.56)
                _band.size = (max(0.0, _card.width - 2.0), max(0.0, _card.height * 0.40))
                _shadow.pos = (_card.x + 1.4, _card.y - 1.6)
                _shadow.size = _card.size
                _edge.rounded_rectangle = (_card.x, _card.y, _card.width, _card.height, 16)
                _inner.rounded_rectangle = (_card.x + 2.0, _card.y + 2.0, max(0.0, _card.width - 4.0), max(0.0, _card.height - 4.0), 14)

            card.bind(pos=_update_card, size=_update_card)

        level_title = Label(
            text="Level",
            color=(0.72, 0.96, 0.90, 0.98),
            font_size="11sp",
            bold=True,
            halign="center",
            valign="middle",
        )
        level_title.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        left_card.add_widget(level_title)
        level_label = Label(
            text="1",
            color=(0.95, 1.0, 0.96, 1.0),
            font_size="26sp",
            bold=True,
            halign="center",
            valign="middle",
        )
        level_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        left_card.add_widget(level_label)
        high_title = Label(
            text="High Score",
            color=(0.68, 0.90, 1.0, 0.98),
            font_size="11sp",
            bold=True,
            halign="center",
            valign="middle",
        )
        high_title.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        right_card.add_widget(high_title)
        high_score_label = Label(
            text="0",
            color=(0.95, 1.0, 0.96, 1.0),
            font_size="26sp",
            bold=True,
            halign="center",
            valign="middle",
        )
        high_score_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        right_card.add_widget(high_score_label)
        root.add_widget(left_card)
        root.add_widget(right_card)

        center_panel = BoxLayout(
            orientation="vertical",
            padding=[14, 14],
            spacing=10,
            size_hint=(0.56, 0.48),
            pos_hint={"center_x": 0.5, "center_y": 0.44},
        )
        with center_panel.canvas.before:
            Color(0.08, 0.10, 0.12, 0.60)
            panel_bg = RoundedRectangle(pos=center_panel.pos, size=center_panel.size, radius=[18])
            Color(0.96, 1.0, 1.0, 0.06)
            panel_band = RoundedRectangle(pos=center_panel.pos, size=center_panel.size, radius=[18])
        with center_panel.canvas.after:
            Color(0.58, 0.88, 0.96, 0.42)
            panel_edge = Line(rounded_rectangle=(center_panel.x, center_panel.y, center_panel.width, center_panel.height, 18), width=1.25)

        def _update_panel(*_):
            panel_bg.pos = center_panel.pos
            panel_bg.size = center_panel.size
            panel_band.pos = (center_panel.x + 1.0, center_panel.y + center_panel.height * 0.60)
            panel_band.size = (max(0.0, center_panel.width - 2.0), max(0.0, center_panel.height * 0.36))
            panel_edge.rounded_rectangle = (center_panel.x, center_panel.y, center_panel.width, center_panel.height, 18)

        center_panel.bind(pos=_update_panel, size=_update_panel)

        def _apply_menu_responsive_layout(*_):
            compact = root.height < 700
            if compact:
                left_card.size_hint = (0.255, 0.215)
                right_card.size_hint = (0.255, 0.215)
                left_card.pos_hint = {"x": 0.04, "center_y": 0.55}
                right_card.pos_hint = {"right": 0.96, "center_y": 0.55}
                center_panel.size_hint = (0.60, 0.47)
                center_panel.pos_hint = {"center_x": 0.5, "center_y": 0.42}
                btn_start.height = 54
                btn_scores.height = 48
                btn_settings.height = 48
                row_name.height = 42
            else:
                left_card.size_hint = (0.245, 0.235)
                right_card.size_hint = (0.245, 0.235)
                left_card.pos_hint = {"x": 0.045, "center_y": 0.56}
                right_card.pos_hint = {"right": 0.955, "center_y": 0.56}
                center_panel.size_hint = (0.56, 0.48)
                center_panel.pos_hint = {"center_x": 0.5, "center_y": 0.44}
                btn_start.height = 58
                btn_scores.height = 52
                btn_settings.height = 52
                row_name.height = 46

        mode_value = Label(
            text="Mode: Classic",
            color=(0.80, 0.90, 1.0, 0.96),
            font_size="12sp",
            bold=True,
            size_hint_y=None,
            height=22,
        )
        panel_hint = Label(
            text="Choose your run profile",
            color=(0.72, 0.82, 0.90, 0.74),
            font_size="10sp",
            size_hint_y=None,
            height=16,
        )
        center_panel.add_widget(panel_hint)
        center_panel.add_widget(mode_value)

        btn_start = MenuNeonButton(text="[b]▶  START GAME[/b]", size_hint_y=None, height=58)
        btn_scores = MenuNeonButton(text="[b]🏅  LEADERBOARDS[/b]", size_hint_y=None, height=52)
        btn_settings = MenuNeonButton(text="[b]⚙  SETTINGS[/b]", size_hint_y=None, height=52)

        btn_start.bind(on_press=lambda _: screen.start_game())
        btn_scores.bind(on_press=lambda _: screen.show_leaderboard())
        btn_settings.bind(on_press=lambda _: screen.show_settings())

        center_panel.add_widget(btn_start)
        center_panel.add_widget(btn_scores)
        center_panel.add_widget(btn_settings)

        row_name = BoxLayout(size_hint_y=None, height=46, spacing=8, padding=[6, 4, 6, 4])
        with row_name.canvas.before:
            name_row_bg_color = Color(0.08, 0.10, 0.12, 0.62)
            name_row_bg = RoundedRectangle(pos=row_name.pos, size=row_name.size, radius=[12])
            Color(0.95, 1.0, 1.0, 0.05)
            name_row_band = RoundedRectangle(pos=row_name.pos, size=row_name.size, radius=[12])
        with row_name.canvas.after:
            name_row_edge_color = Color(0.68, 0.86, 1.0, 0.34)
            name_row_edge = Line(rounded_rectangle=(row_name.x, row_name.y, row_name.width, row_name.height, 12), width=1.1)

        def _update_name_row(*_):
            name_row_bg.pos = row_name.pos
            name_row_bg.size = row_name.size
            name_row_band.pos = (row_name.x + 1.0, row_name.y + row_name.height * 0.52)
            name_row_band.size = (max(0.0, row_name.width - 2.0), max(0.0, row_name.height * 0.42))
            name_row_edge.rounded_rectangle = (row_name.x, row_name.y, row_name.width, row_name.height, 12)

        row_name.bind(pos=_update_name_row, size=_update_name_row)

        name_input = TextInput(
            text="Player",
            hint_text="Enter name",
            multiline=False,
            background_normal="",
            background_active="",
            background_color=(0.10, 0.13, 0.16, 0.96),
            foreground_color=(0.92, 0.96, 1.0, 1.0),
            cursor_color=(0.62, 0.86, 1.0, 1.0),
            hint_text_color=(0.66, 0.78, 0.90, 0.70),
            padding=[12, 10, 10, 10],
            font_size="16sp",
            size_hint_x=0.68,
        )
        with name_input.canvas.after:
            Color(0.62, 0.86, 1.0, 0.40)
            name_input_edge = Line(rounded_rectangle=(name_input.x, name_input.y, name_input.width, name_input.height, 10), width=1.0)

        def _update_name_input(*_):
            name_input_edge.rounded_rectangle = (name_input.x, name_input.y, name_input.width, name_input.height, 10)

        name_input.bind(pos=_update_name_input, size=_update_name_input)

        save_name_btn = MenuNeonButton(text="[b]APPLY[/b]", size_hint_x=0.32, secondary=True)
        save_name_btn.bind(on_press=lambda _: screen.save_player_name())
        row_name.add_widget(name_input)
        row_name.add_widget(save_name_btn)
        center_panel.add_widget(row_name)
        root.add_widget(center_panel)

        daily_label = Label(
            text="Daily reward available!",
            color=(0.98, 0.92, 0.56, 0.96),
            font_size="12sp",
            bold=True,
            size_hint=(0.5, 0.05),
            pos_hint={"center_x": 0.5, "y": 0.11},
        )

        bottom_bar = BoxLayout(size_hint=(0.50, 0.075), pos_hint={"center_x": 0.5, "y": 0.04}, spacing=10)
        btn_daily = MenuNeonButton(text="[b]🎁  DAILY[/b]", secondary=True)
        btn_exit = MenuNeonButton(text="[b]✖  EXIT[/b]", secondary=True)
        btn_daily.bind(on_press=lambda _: screen.claim_daily_reward())
        btn_exit.bind(on_press=lambda _: App.get_running_app().stop())
        bottom_bar.add_widget(btn_daily)
        bottom_bar.add_widget(btn_exit)

        root.add_widget(daily_label)
        root.add_widget(bottom_bar)

        footer = Label(
            text="WASD or Arrows   |   Space Pause   |   Shift Boost   |   R Restart",
            color=(0.66, 0.82, 0.92, 0.60),
            font_size="10sp",
            bold=True,
            size_hint=(0.8, 0.05),
            pos_hint={"center_x": 0.5, "y": 0.0},
        )
        root.add_widget(footer)

        anim_buttons = [btn_start, btn_scores, btn_settings, btn_daily, btn_exit]
        for index, button in enumerate(anim_buttons):
            button.opacity = 0.0
            button._intro_delay = index * 0.07

        anim_state = {
            "time": 0.0,
            "name_row_hover": 0.0,
            "particles": [
                {
                    "x": random.random(),
                    "y": random.random(),
                    "speed": 0.02 + random.random() * 0.06,
                    "size": 1.5 + random.random() * 3.8,
                    "phase": random.random() * math.tau,
                }
                for _ in bg_particles
            ],
            "hover_fx": [],
        }

        def _animate_menu(dt):
            if root.width < 8 or root.height < 8:
                return True

            anim_state["time"] += dt
            t_value = anim_state["time"]

            pulse = 0.74 + math.sin(t_value * 1.7) * 0.26
            title_glow.color = (0.22, 1.0, 0.66, 0.14 + pulse * 0.16)
            subtitle.color = (0.55, 0.98, 0.85, 0.66 + pulse * 0.20)

            for button in anim_buttons:
                intro_t = min(1.0, max(0.0, (t_value - button._intro_delay) / 0.48))
                eased = intro_t * intro_t * (3.0 - 2.0 * intro_t)
                button.opacity = eased

            for index, particle in enumerate(anim_state["particles"]):
                particle["y"] += particle["speed"] * dt
                if particle["y"] > 1.05:
                    particle["y"] = -0.06
                    particle["x"] = random.random()
                    particle["phase"] = random.random() * math.tau
                sway = math.sin(t_value * 0.9 + particle["phase"]) * 0.012
                px = root.x + (particle["x"] + sway) * root.width
                py = root.y + particle["y"] * root.height
                size = particle["size"] * (0.85 + 0.30 * math.sin(t_value * 2.0 + particle["phase"]))
                bg_particles[index].pos = (px, py)
                bg_particles[index].size = (size, size)
                bg_particle_colors[index].a = 0.05 + min(0.18, size * 0.02)

            hovered_buttons = [button for button in anim_buttons if getattr(button, "_hover_progress", 0.0) > 0.55 and button.opacity > 0.4]
            if hovered_buttons and random.random() < 0.18:
                source = random.choice(hovered_buttons)
                anim_state["hover_fx"].append(
                    {
                        "x": source.center_x + random.uniform(-source.width * 0.36, source.width * 0.36),
                        "y": source.center_y + random.uniform(-source.height * 0.12, source.height * 0.22),
                        "vx": random.uniform(-9.0, 9.0),
                        "vy": random.uniform(16.0, 38.0),
                        "life": 0.35,
                        "size": random.uniform(2.0, 3.8),
                    }
                )

            alive_fx = []
            for fx in anim_state["hover_fx"]:
                fx["life"] -= dt
                if fx["life"] > 0:
                    fx["x"] += fx["vx"] * dt
                    fx["y"] += fx["vy"] * dt
                    alive_fx.append(fx)
            anim_state["hover_fx"] = alive_fx[: len(hover_particles)]

            for index, ellipse in enumerate(hover_particles):
                if index < len(anim_state["hover_fx"]):
                    fx = anim_state["hover_fx"][index]
                    alpha = max(0.0, fx["life"] / 0.35)
                    ellipse.pos = (fx["x"], fx["y"])
                    ellipse.size = (fx["size"], fx["size"])
                    hover_particle_colors[index].a = 0.36 * alpha
                else:
                    ellipse.pos = (-100, -100)
                    hover_particle_colors[index].a = 0.0

            mouse_x, mouse_y = Window.mouse_pos
            local_x, local_y = row_name.to_widget(mouse_x, mouse_y)
            row_hovered = row_name.collide_point(local_x, local_y)
            target_hover = 1.0 if row_hovered else 0.0
            anim_state["name_row_hover"] += (target_hover - anim_state["name_row_hover"]) * 0.22
            hover_glow = anim_state["name_row_hover"]
            name_row_edge_color.a = 0.32 + hover_glow * 0.42
            name_row_bg_color.a = 0.70 + hover_glow * 0.10

            # Decorative menu snake movement using gameplay-like visuals.
            nonlocal menu_snake_head_x, menu_snake_head_y, menu_snake_heading, menu_snake_points

            app = App.get_running_app()
            selected_skin = app.progression.get_selected_skin() if app else "default"
            palette = constants.SNAKE_SKIN_PALETTES.get(selected_skin, constants.SNAKE_SKIN_PALETTES["default"])
            snake_body_color.rgba = (palette["body"][0], palette["body"][1], palette["body"][2], 0.72)
            snake_dorsal_color.rgba = (palette["dorsal"][0], palette["dorsal"][1], palette["dorsal"][2], 0.52)
            snake_belly_color.rgba = (palette["belly"][0], palette["belly"][1], palette["belly"][2], 0.48)
            snake_head_color.rgba = (palette["head"][0], palette["head"][1], palette["head"][2], 0.88)
            snake_head_shade_color.rgba = (
                palette["dorsal"][0] * 0.75,
                palette["dorsal"][1] * 0.75,
                palette["dorsal"][2] * 0.75,
                0.44,
            )

            if len(menu_snake_points) != len(snake_body_segments):
                menu_snake_points = [[menu_snake_head_x, menu_snake_head_y] for _ in range(len(snake_body_segments))]

            turn_wave = math.sin(t_value * 0.92) * 0.72 + math.sin(t_value * 0.43 + 0.8) * 0.30
            menu_snake_heading += turn_wave * dt * 0.56

            dir_x = math.cos(menu_snake_heading)
            dir_y = math.sin(menu_snake_heading)
            perp_x = -dir_y
            perp_y = dir_x

            swim_speed = root.width * 0.074
            slither = math.sin(t_value * 8.6) * (root.height * 0.009)
            menu_snake_head_x += (dir_x * swim_speed + perp_x * slither * 2.0) * dt
            menu_snake_head_y += (dir_y * swim_speed * 0.52 + perp_y * slither * 0.7) * dt

            if menu_snake_head_x < swim_min_x or menu_snake_head_x > swim_max_x:
                menu_snake_heading = math.pi - menu_snake_heading
                menu_snake_head_x = max(swim_min_x, min(swim_max_x, menu_snake_head_x))
            if menu_snake_head_y < swim_min_y or menu_snake_head_y > swim_max_y:
                menu_snake_heading = -menu_snake_heading
                menu_snake_head_y = max(swim_min_y, min(swim_max_y, menu_snake_head_y))

            menu_snake_points[0][0] = menu_snake_head_x
            menu_snake_points[0][1] = menu_snake_head_y
            for index in range(1, len(menu_snake_points)):
                prev_x, prev_y = menu_snake_points[index - 1]
                px, py = menu_snake_points[index]
                follow = 0.22 - index * 0.006
                follow = max(0.06, follow)
                menu_snake_points[index][0] = px + (prev_x - px) * follow
                menu_snake_points[index][1] = py + (prev_y - py) * follow

            base_size = max(24.0, min(42.0, root.height * 0.058))
            for index, (seg_x, seg_y) in enumerate(menu_snake_points):
                taper = 1.0 - (index / max(1, len(menu_snake_points) - 1)) * 0.22
                seg_w = base_size * taper
                seg_h = seg_w * 0.62

                snake_shadow_segments[index].size = (seg_w * 0.98, seg_h * 0.50)
                snake_shadow_segments[index].pos = (seg_x - seg_w * 0.49, seg_y - seg_h * 0.50)

                snake_body_segments[index].size = (seg_w, seg_h)
                snake_body_segments[index].pos = (seg_x - seg_w * 0.50, seg_y - seg_h * 0.40)
                snake_body_segments[index].radius = (max(2.0, seg_h * 0.45),)

                snake_dorsal_segments[index].size = (seg_w * 0.66, seg_h * 0.24)
                snake_dorsal_segments[index].pos = (seg_x - seg_w * 0.33, seg_y + seg_h * 0.02)
                snake_dorsal_segments[index].radius = (max(2.0, seg_h * 0.25),)

                snake_belly_segments[index].size = (seg_w * 0.56, seg_h * 0.20)
                snake_belly_segments[index].pos = (seg_x - seg_w * 0.28, seg_y - seg_h * 0.24)
                snake_belly_segments[index].radius = (max(2.0, seg_h * 0.22),)

            head_w = base_size * 1.02
            head_h = head_w * 0.66
            head_x = menu_snake_points[0][0]
            head_y = menu_snake_points[0][1]
            snake_head_shadow.size = (head_w * 1.02, head_h * 0.55)
            snake_head_shadow.pos = (head_x - head_w * 0.50, head_y - head_h * 0.56)
            snake_head.size = (head_w, head_h)
            snake_head.pos = (head_x - head_w * 0.50, head_y - head_h * 0.40)
            snake_head_shade.size = (head_w * 0.72, head_h * 0.30)
            snake_head_shade.pos = (head_x - head_w * 0.36, head_y - head_h * 0.10)
            snake_head_gloss.size = (head_w * 0.30, head_h * 0.16)
            snake_head_gloss.pos = (head_x - head_w * 0.16, head_y + head_h * 0.12)

            eye_size = max(2.4, head_h * 0.18)
            eye_dist = head_w * 0.17
            eye_forward = head_w * 0.16

            left_x = head_x + dir_x * eye_forward + perp_x * eye_dist
            left_y = head_y + dir_y * eye_forward + perp_y * eye_dist + head_h * 0.02
            right_x = head_x + dir_x * eye_forward - perp_x * eye_dist
            right_y = head_y + dir_y * eye_forward - perp_y * eye_dist + head_h * 0.02

            snake_eye_left.size = (eye_size, eye_size)
            snake_eye_right.size = (eye_size, eye_size)
            snake_eye_left.pos = (left_x - eye_size * 0.5, left_y - eye_size * 0.5)
            snake_eye_right.pos = (right_x - eye_size * 0.5, right_y - eye_size * 0.5)

            pupil_size = eye_size * 0.54
            snake_pupil_left.size = (pupil_size, pupil_size)
            snake_pupil_right.size = (pupil_size, pupil_size)
            snake_pupil_left.pos = (left_x - pupil_size * 0.5 + dir_x * 0.8, left_y - pupil_size * 0.5 + dir_y * 0.8)
            snake_pupil_right.pos = (right_x - pupil_size * 0.5 + dir_x * 0.8, right_y - pupil_size * 0.5 + dir_y * 0.8)

            return True

        animation_event = Clock.schedule_interval(_animate_menu, 1.0 / 30.0)

        def _stop_animation(*_):
            if animation_event is not None:
                animation_event.cancel()

        self._wire_click_sounds(btn_start, btn_scores, btn_settings, btn_daily, btn_exit, save_name_btn)

        root.bind(size=_apply_menu_responsive_layout)
        _apply_menu_responsive_layout()

        screen.bind(on_leave=_stop_animation)
        screen.add_widget(root)
        screen.ids = {
            "mode_value": mode_value,
            "name_input": name_input,
            "daily_label": daily_label,
            "high_score_label": high_score_label,
            "level_label": level_label,
        }
        return screen

    def _build_game_screen(self):
        """Build game screen with compact HUD and controls."""
        screen = GameScreen(name="game")
        layout = BoxLayout(orientation="vertical", padding=[10, 8], spacing=7)

        with layout.canvas.before:
            Color(0.03, 0.05, 0.11, 1.0)
            bg_rect = Rectangle(pos=layout.pos, size=layout.size)
            Color(0.10, 0.18, 0.32, 0.16)
            glow_rect = Rectangle(pos=layout.pos, size=layout.size)
            Color(0.62, 0.82, 1.0, 0.05)
            warm_rect = Rectangle(pos=layout.pos, size=layout.size)

        def _update_layout_bg(*_):
            bg_rect.pos = layout.pos
            bg_rect.size = layout.size
            glow_rect.pos = layout.pos
            glow_rect.size = layout.size
            warm_rect.pos = (layout.x, layout.y + layout.height * 0.30)
            warm_rect.size = (layout.width, layout.height * 0.70)

        layout.bind(pos=_update_layout_bg, size=_update_layout_bg)

        hud = BoxLayout(size_hint_y=0.085, spacing=4, padding=[4, 3])
        with hud.canvas.before:
            Color(0.08, 0.10, 0.16, 0.96)
            hud_rect = RoundedRectangle(pos=hud.pos, size=hud.size, radius=[10])
            Color(0.15, 0.24, 0.40, 0.16)
            stone_band_top = Rectangle(pos=hud.pos, size=hud.size)
            Color(0.12, 0.20, 0.34, 0.12)
            stone_band_mid = Rectangle(pos=hud.pos, size=hud.size)
            Color(0.72, 0.86, 1.0, 0.16)
            stone_crack_a = Line(points=[], width=1.0)
            Color(0.62, 0.78, 0.96, 0.12)
            stone_crack_b = Line(points=[], width=1.0)
            Color(0.84, 0.92, 1.0, 0.20)
            hud_line = Line(rounded_rectangle=(hud.x, hud.y, hud.width, hud.height, 10), width=1.2)

        def _update_hud(*_):
            hud_rect.pos = hud.pos
            hud_rect.size = hud.size
            stone_band_top.pos = (hud.x + 1, hud.y + hud.height * 0.58)
            stone_band_top.size = (max(0.0, hud.width - 2), max(0.0, hud.height * 0.36))
            stone_band_mid.pos = (hud.x + 1, hud.y + hud.height * 0.18)
            stone_band_mid.size = (max(0.0, hud.width - 2), max(0.0, hud.height * 0.24))
            stone_crack_a.points = [
                hud.x + hud.width * 0.07, hud.y + hud.height * 0.26,
                hud.x + hud.width * 0.24, hud.y + hud.height * 0.34,
                hud.x + hud.width * 0.33, hud.y + hud.height * 0.24,
                hud.x + hud.width * 0.45, hud.y + hud.height * 0.31,
            ]
            stone_crack_b.points = [
                hud.x + hud.width * 0.62, hud.y + hud.height * 0.68,
                hud.x + hud.width * 0.71, hud.y + hud.height * 0.60,
                hud.x + hud.width * 0.83, hud.y + hud.height * 0.66,
                hud.x + hud.width * 0.93, hud.y + hud.height * 0.58,
            ]
            hud_line.rounded_rectangle = (hud.x, hud.y, hud.width, hud.height, 10)

        hud.bind(pos=_update_hud, size=_update_hud)

        def make_chip(color_rgba):
            chip = BoxLayout(orientation="vertical", padding=[5, 3], spacing=0)
            with chip.canvas.before:
                Color(0.08, 0.10, 0.14, 0.98)
                chip_bg = RoundedRectangle(pos=chip.pos, size=chip.size, radius=[8])
                Color(0.16, 0.24, 0.34, 0.18)
                grain_a = Rectangle(pos=chip.pos, size=chip.size)
                Color(0.10, 0.18, 0.30, 0.12)
                grain_b = Rectangle(pos=chip.pos, size=chip.size)
                Color(0.78, 0.88, 1.0, 0.16)
                knot = Ellipse(pos=chip.pos, size=(1, 1))
                Color(*color_rgba)
                chip_line = Line(rounded_rectangle=(chip.x, chip.y, chip.width, chip.height, 8), width=1.1)

            def update_chip(*_):
                chip_bg.pos = chip.pos
                chip_bg.size = chip.size
                grain_a.pos = (chip.x + 1, chip.y + chip.height * 0.60)
                grain_a.size = (max(0.0, chip.width - 2), max(0.0, chip.height * 0.20))
                grain_b.pos = (chip.x + 1, chip.y + chip.height * 0.28)
                grain_b.size = (max(0.0, chip.width - 2), max(0.0, chip.height * 0.12))
                knot.pos = (chip.x + chip.width * 0.68, chip.y + chip.height * 0.20)
                knot.size = (chip.width * 0.12, chip.height * 0.30)
                chip_line.rounded_rectangle = (chip.x, chip.y, chip.width, chip.height, 8)

            chip.bind(pos=update_chip, size=update_chip)
            return chip

        score_chip = make_chip((0.52, 0.86, 1.0, 0.48))
        score_label = Label(text=screen.score_text, font_size="12sp", color=(0.95, 0.98, 1, 1), bold=True)
        score_chip.add_widget(Label(text="SCORE", font_size="8.5sp", color=(0.82, 0.92, 1.0, 0.98), bold=True))
        score_chip.add_widget(score_label)

        high_chip = make_chip((1.0, 0.84, 0.56, 0.48))
        high_label = Label(text=screen.high_score_text, font_size="12sp", color=(1.0, 0.95, 0.72, 1), bold=True)
        high_chip.add_widget(Label(text="BEST", font_size="8.5sp", color=(0.98, 0.90, 0.58, 0.98), bold=True))
        high_chip.add_widget(high_label)

        combo_chip = make_chip((1.0, 0.72, 0.56, 0.48))
        combo_label = Label(text=screen.combo_text, font_size="12sp", color=(1.0, 0.90, 0.82, 1), bold=True)
        combo_chip.add_widget(Label(text="COMBO", font_size="8.5sp", color=(1.0, 0.80, 0.68, 0.98), bold=True))
        combo_chip.add_widget(combo_label)

        mode_chip = make_chip((0.72, 0.80, 1.0, 0.48))
        mode_label = Label(text=screen.mode_text, font_size="12sp", color=(0.88, 0.96, 1.0, 1), bold=True)
        mode_chip.add_widget(Label(text="MODE", font_size="8.5sp", color=(0.72, 0.90, 1.0, 0.98), bold=True))
        mode_chip.add_widget(mode_label)

        hud.add_widget(score_chip)
        hud.add_widget(high_chip)
        hud.add_widget(combo_chip)
        hud.add_widget(mode_chip)
        layout.add_widget(hud)

        board_wrap = BoxLayout(orientation="vertical", size_hint_y=0.80, padding=[3, 3])
        with board_wrap.canvas.before:
            Color(0.08, 0.10, 0.14, 0.98)
            board_shadow = RoundedRectangle(pos=board_wrap.pos, size=board_wrap.size, radius=[12])
            Color(0.15, 0.24, 0.34, 0.18)
            board_stone_a = Rectangle(pos=board_wrap.pos, size=board_wrap.size)
            Color(0.12, 0.20, 0.30, 0.14)
            board_stone_b = Rectangle(pos=board_wrap.pos, size=board_wrap.size)
            Color(0.78, 0.88, 1.0, 0.14)
            board_crack = Line(points=[], width=1.0)
            Color(0.82, 0.92, 1.0, 0.24)
            board_border = Line(rounded_rectangle=(board_wrap.x, board_wrap.y, board_wrap.width, board_wrap.height, 12), width=1.2)

        def _update_board_wrap(*_):
            board_shadow.pos = board_wrap.pos
            board_shadow.size = board_wrap.size
            board_stone_a.pos = (board_wrap.x + 2, board_wrap.y + board_wrap.height * 0.64)
            board_stone_a.size = (max(0.0, board_wrap.width - 4), max(0.0, board_wrap.height * 0.20))
            board_stone_b.pos = (board_wrap.x + 2, board_wrap.y + board_wrap.height * 0.16)
            board_stone_b.size = (max(0.0, board_wrap.width - 4), max(0.0, board_wrap.height * 0.16))
            board_crack.points = [
                board_wrap.x + board_wrap.width * 0.06, board_wrap.y + board_wrap.height * 0.83,
                board_wrap.x + board_wrap.width * 0.18, board_wrap.y + board_wrap.height * 0.78,
                board_wrap.x + board_wrap.width * 0.24, board_wrap.y + board_wrap.height * 0.72,
                board_wrap.x + board_wrap.width * 0.35, board_wrap.y + board_wrap.height * 0.76,
            ]
            board_border.rounded_rectangle = (board_wrap.x, board_wrap.y, board_wrap.width, board_wrap.height, 12)

        board_wrap.bind(pos=_update_board_wrap, size=_update_board_wrap)

        board = GameBoard()
        board.id = 'game_board'
        board_wrap.add_widget(board)
        layout.add_widget(board_wrap)

        status_row = BoxLayout(size_hint_y=0.04, spacing=6, padding=[3, 0])
        fps_label = Label(text=screen.fps_text, font_size="9.5sp", color=(0.90, 0.82, 0.65, 1), bold=True)
        quality_label = Label(text=screen.quality_text, font_size="9.5sp", color=(0.97, 0.89, 0.66, 1), bold=True)
        status_label = Label(text="", font_size="9.5sp", color=(0.98, 0.79, 0.59, 1), bold=True, opacity=0)
        debug_label = Label(
            text="",
            font_size="8sp",
            color=(0.78, 0.86, 0.93, 1),
            bold=False,
            opacity=0,
            halign="right",
            valign="middle",
        )
        debug_label.bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))
        status_row.add_widget(fps_label)
        status_row.add_widget(quality_label)
        status_row.add_widget(status_label)
        status_row.add_widget(debug_label)
        layout.add_widget(status_row)

        controls = BoxLayout(size_hint_y=0.095, spacing=6, padding=[3, 1])

        def _restart_run(*_):
            app = App.get_running_app()
            app.root.current = 'menu'
            app.root.get_screen('menu').start_game()

        btn_pause = Button(text="PAUSE\n(Space)", font_size="11sp", background_color=(0.22, 0.26, 0.36, 0.92))
        btn_pause.bind(on_press=lambda x: App.get_running_app().game_controller.pause() if not App.get_running_app().game_controller.current_mode.is_paused else App.get_running_app().game_controller.resume())

        btn_restart = Button(text="RESTART\n(R)", font_size="11sp", background_color=(0.26, 0.30, 0.40, 0.92))
        btn_restart.bind(on_press=_restart_run)

        btn_boost = Button(text="BOOST\n(Shift)", font_size="11sp", background_color=(0.30, 0.44, 0.34, 0.94))
        btn_boost.bind(on_press=lambda x: screen.use_boost())

        btn_menu = Button(text="MENU\n(Esc)", font_size="11sp", background_color=(0.26, 0.24, 0.34, 0.92))
        btn_menu.bind(on_press=lambda x: screen.go_menu())

        self._wire_click_sounds(btn_pause, btn_restart, btn_boost, btn_menu)

        controls.add_widget(btn_pause)
        controls.add_widget(btn_restart)
        controls.add_widget(btn_boost)
        controls.add_widget(btn_menu)
        layout.add_widget(controls)

        helper = Label(
            text="[size=9][color=aec3de]WASD/Arrows  |  Space Pause  |  Shift Boost  |  R Restart  |  Esc Menu[/color][/size]",
            markup=True,
            size_hint_y=0.035,
            halign="center",
            valign="middle",
        )
        helper.bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))
        layout.add_widget(helper)

        effect_label = Label(
            text="",
            size_hint_y=0.03,
            font_size="10sp",
            color=(0.98, 0.92, 0.72, 1),
            bold=True,
            opacity=0,
        )
        layout.add_widget(effect_label)

        screen.ids = {
            'game_board': board,
            'score_label': score_label,
            'high_label': high_label,
            'combo_label': combo_label,
            'mode_label': mode_label,
            'fps_label': fps_label,
            'quality_label': quality_label,
            'status_label': status_label,
            'debug_label': debug_label,
            'boost_btn': btn_boost,
            'effect_label': effect_label,
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
        self._wire_click_sounds(btn_back)
        layout.add_widget(btn_back)

        screen.add_widget(layout)
        screen.ids = {
            'skins_label': skins_label,
            'styles_label': styles_label,
            'achievements_label': ach_label,
        }
        return screen

    def _build_leaderboard_screen(self):
        """Build premium leaderboard screen with dynamic rank cards."""
        screen = LeaderboardScreen(name="leaderboard")
        root = FloatLayout()

        with root.canvas.before:
            Color(0.02, 0.03, 0.06, 1.0)
            bg = Rectangle(pos=root.pos, size=root.size)
            Color(0.06, 0.12, 0.18, 0.34)
            top_glow = Rectangle(pos=root.pos, size=root.size)
            Color(0.05, 0.16, 0.12, 0.24)
            bottom_glow = Rectangle(pos=root.pos, size=root.size)

        def _update_bg(*_):
            x_pos, y_pos = root.pos
            width, height = root.size
            bg.pos = root.pos
            bg.size = root.size
            top_glow.pos = (x_pos, y_pos + height * 0.44)
            top_glow.size = (width, height * 0.56)
            bottom_glow.pos = (x_pos, y_pos)
            bottom_glow.size = (width, height * 0.54)

        root.bind(pos=_update_bg, size=_update_bg)

        title = Label(
            text="[b][color=8fd2ff]LEADERBOARD[/color][/b]",
            markup=True,
            font_size="30sp",
            size_hint=(0.9, 0.10),
            pos_hint={"center_x": 0.5, "top": 0.98},
        )
        root.add_widget(title)

        subtitle = Label(
            text="Top 10 players on this device",
            font_size="12sp",
            color=(0.72, 0.87, 0.98, 0.82),
            size_hint=(0.9, 0.04),
            pos_hint={"center_x": 0.5, "top": 0.90},
        )
        root.add_widget(subtitle)

        summary_bar = BoxLayout(size_hint=(0.92, 0.07), pos_hint={"center_x": 0.5, "top": 0.85}, spacing=8, padding=[10, 0, 10, 0])
        with summary_bar.canvas.before:
            Color(0.08, 0.13, 0.20, 0.88)
            summary_bg = RoundedRectangle(pos=summary_bar.pos, size=summary_bar.size, radius=[12])
        with summary_bar.canvas.after:
            Color(0.45, 0.70, 0.96, 0.50)
            summary_edge = Line(rounded_rectangle=(summary_bar.x, summary_bar.y, summary_bar.width, summary_bar.height, 12), width=1.0)

        def _update_summary(*_):
            summary_bg.pos = summary_bar.pos
            summary_bg.size = summary_bar.size
            summary_edge.rounded_rectangle = (summary_bar.x, summary_bar.y, summary_bar.width, summary_bar.height, 12)

        summary_bar.bind(pos=_update_summary, size=_update_summary)

        summary_title = Label(
            text="Entries",
            color=(0.86, 0.95, 1.0, 1.0),
            font_size="12sp",
            halign="left",
            valign="middle",
        )
        summary_title.bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))
        summary_count = Label(
            text="0/10",
            color=(0.99, 0.90, 0.56, 1.0),
            font_size="12sp",
            bold=True,
            size_hint_x=0.30,
            halign="right",
            valign="middle",
        )
        summary_count.bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))
        summary_bar.add_widget(summary_title)
        summary_bar.add_widget(summary_count)
        root.add_widget(summary_bar)

        panel = BoxLayout(orientation="vertical", size_hint=(0.92, 0.57), pos_hint={"center_x": 0.5, "y": 0.20}, padding=[10, 10, 10, 10], spacing=8)
        with panel.canvas.before:
            Color(0.07, 0.11, 0.18, 0.95)
            panel_rect = RoundedRectangle(pos=panel.pos, size=panel.size, radius=[14])
            Color(0.43, 0.67, 0.98, 0.40)
            panel_border = Line(rounded_rectangle=(panel.x, panel.y, panel.width, panel.height, 14), width=1.2)

        def _update_panel(*_):
            panel_rect.pos = panel.pos
            panel_rect.size = panel.size
            panel_border.rounded_rectangle = (panel.x, panel.y, panel.width, panel.height, 14)

        panel.bind(pos=_update_panel, size=_update_panel)

        header_row = BoxLayout(size_hint_y=None, height=28)
        header_row.add_widget(Label(text="Rank", font_size="11sp", color=(0.72, 0.88, 1.0, 0.86), size_hint_x=0.16))
        header_row.add_widget(Label(text="Player", font_size="11sp", color=(0.72, 0.88, 1.0, 0.86), size_hint_x=0.52, halign="left", valign="middle"))
        header_row.add_widget(Label(text="Score", font_size="11sp", color=(0.72, 0.88, 1.0, 0.86), size_hint_x=0.20))
        header_row.add_widget(Label(text="Mode", font_size="11sp", color=(0.72, 0.88, 1.0, 0.86), size_hint_x=0.24, halign="right", valign="middle"))
        panel.add_widget(header_row)

        empty_label = Label(
            text="Loading leaderboard...",
            size_hint_y=None,
            height=32,
            font_size="11sp",
            color=(0.83, 0.90, 0.98, 0.68),
            halign="left",
            valign="middle",
        )
        empty_label.bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))
        panel.add_widget(empty_label)

        scroll = ScrollView(do_scroll_x=False, bar_width=4)
        list_container = BoxLayout(orientation="vertical", spacing=8, size_hint_y=None)
        list_container.bind(minimum_height=list_container.setter("height"))
        scroll.add_widget(list_container)
        panel.add_widget(scroll)
        root.add_widget(panel)

        btn_back = Button(
            text="[b]BACK TO MENU[/b]",
            markup=True,
            size_hint=(0.92, 0.10),
            pos_hint={"center_x": 0.5, "y": 0.05},
            font_size="12sp",
            bold=True,
        )
        btn_back.background_normal = ""
        btn_back.background_down = ""
        btn_back.background_color = (0.14, 0.20, 0.36, 1.0)
        btn_back.bind(on_release=lambda *_: screen.go_back())
        self._wire_click_sounds(btn_back)
        root.add_widget(btn_back)

        screen.add_widget(root)
        screen.ids = {
            'leaderboard_count_label': summary_count,
            'leaderboard_empty_label': empty_label,
            'leaderboard_container': list_container,
        }
        return screen

    def _build_settings_screen(self):
        """Build premium mobile-style settings screen with grouped glass cards."""
        screen = SettingsScreen(name="settings")
        root = FloatLayout()

        with root.canvas.before:
            Color(0.02, 0.03, 0.03, 1.0)
            bg_base = Rectangle(pos=root.pos, size=root.size)
            Color(0.05, 0.14, 0.10, 0.70)
            bg_top = Rectangle(pos=root.pos, size=root.size)
            Color(0.04, 0.09, 0.13, 0.34)
            bg_bottom = Rectangle(pos=root.pos, size=root.size)

        def _update_bg(*_):
            x_pos, y_pos = root.pos
            width, height = root.size
            bg_base.pos = root.pos
            bg_base.size = root.size
            bg_top.pos = (x_pos, y_pos + height * 0.44)
            bg_top.size = (width, height * 0.56)
            bg_bottom.pos = (x_pos, y_pos)
            bg_bottom.size = (width, height * 0.54)

        root.bind(pos=_update_bg, size=_update_bg)

        title = Label(
            text="[b]GAME SETTINGS[/b]",
            markup=True,
            font_size="36sp",
            color=(0.92, 0.98, 0.95, 1.0),
            size_hint=(0.9, 0.12),
            pos_hint={"center_x": 0.5, "top": 0.98},
        )
        subtitle = Label(
            text="Tune audio, controls, graphics, and gameplay",
            font_size="12sp",
            color=(0.70, 0.84, 0.79, 0.82),
            size_hint=(0.9, 0.05),
            pos_hint={"center_x": 0.5, "top": 0.90},
        )
        root.add_widget(title)
        root.add_widget(subtitle)

        scroll = ScrollView(size_hint=(1.0, 0.70), pos_hint={"x": 0.0, "y": 0.15}, do_scroll_x=False, bar_width=0)
        content = BoxLayout(orientation="vertical", spacing=12, padding=[14, 18, 14, 12], size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        def _make_card(title_text: str):
            card = BoxLayout(orientation="vertical", spacing=10, padding=[12, 10, 12, 10], size_hint_y=None)
            card.height = 180
            with card.canvas.before:
                Color(0.07, 0.10, 0.11, 0.82)
                card_bg = RoundedRectangle(pos=card.pos, size=card.size, radius=[16])
                Color(0.98, 1.0, 1.0, 0.05)
                card_band = RoundedRectangle(pos=card.pos, size=card.size, radius=[16])
            with card.canvas.after:
                Color(0.28, 0.84, 0.72, 0.32)
                card_edge = Line(rounded_rectangle=(card.x, card.y, card.width, card.height, 16), width=1.0)

            def _update_card(*_):
                card_bg.pos = card.pos
                card_bg.size = card.size
                card_band.pos = (card.x + 1.0, card.y + card.height * 0.62)
                card_band.size = (max(0.0, card.width - 2.0), max(0.0, card.height * 0.35))
                card_edge.rounded_rectangle = (card.x, card.y, card.width, card.height, 16)

            card.bind(pos=_update_card, size=_update_card)

            heading = Label(
                text=f"[b]{title_text}[/b]",
                markup=True,
                size_hint_y=None,
                height=26,
                font_size="13sp",
                color=(0.78, 0.96, 0.88, 0.98),
                halign="left",
                valign="middle",
            )
            heading.bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))
            card.add_widget(heading)
            return card

        def _row(label_text: str, control, *, height: float = 44):
            row = BoxLayout(size_hint_y=None, height=height, spacing=10)
            label = Label(text=label_text, size_hint_x=0.48, font_size="12sp", color=(0.88, 0.95, 0.92, 1.0), halign="left", valign="middle")
            label.bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))
            row.add_widget(label)
            row.add_widget(control)
            return row

        # AUDIO
        audio_card = _make_card("AUDIO")
        audio_card.height = 208
        sound_switch = NeonSwitch(size_hint=(None, None), size=(68, 34))
        sound_switch.bind(on_release=lambda *_: screen.toggle_sound(sound_switch.active))
        audio_card.add_widget(_row("Sound", sound_switch, height=46))

        master_box = BoxLayout(orientation="vertical", size_hint_y=None, height=58, spacing=2)
        master_head = BoxLayout(size_hint_y=None, height=22)
        master_head.add_widget(Label(text="Master Volume", color=(0.80, 0.94, 0.88, 1.0), font_size="11sp", halign="left", valign="middle"))
        master_value = Label(text="100%", color=(0.94, 1.0, 0.96, 1.0), font_size="11sp", bold=True, size_hint_x=None, width=52)
        master_head.children[0].bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))
        master_head.add_widget(master_value)
        master_slider = Slider(min=0, max=100, value=100, step=1)
        master_slider.cursor_size = (18, 18)
        master_slider.value_track = True
        master_slider.value_track_color = (0.26, 0.96, 0.68, 0.95)
        master_slider.bind(value=lambda _, v: screen.set_master_volume(v / 100.0))
        master_box.add_widget(master_head)
        master_box.add_widget(master_slider)
        audio_card.add_widget(master_box)

        sfx_box = BoxLayout(orientation="vertical", size_hint_y=None, height=58, spacing=2)
        sfx_head = BoxLayout(size_hint_y=None, height=22)
        sfx_head.add_widget(Label(text="SFX Volume", color=(0.80, 0.94, 0.88, 1.0), font_size="11sp", halign="left", valign="middle"))
        sfx_value = Label(text="100%", color=(0.94, 1.0, 0.96, 1.0), font_size="11sp", bold=True, size_hint_x=None, width=52)
        sfx_head.children[0].bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))
        sfx_head.add_widget(sfx_value)
        sfx_slider = Slider(min=0, max=100, value=100, step=1)
        sfx_slider.cursor_size = (18, 18)
        sfx_slider.value_track = True
        sfx_slider.value_track_color = (0.26, 0.96, 0.68, 0.95)
        sfx_slider.bind(value=lambda _, v: screen.set_sfx_volume(v / 100.0))
        sfx_box.add_widget(sfx_head)
        sfx_box.add_widget(sfx_slider)
        audio_card.add_widget(sfx_box)
        content.add_widget(audio_card)

        # CONTROLS
        controls_card = _make_card("CONTROLS")
        controls_card.height = 156
        sens_box = BoxLayout(orientation="vertical", size_hint_y=None, height=58, spacing=2)
        sens_head = BoxLayout(size_hint_y=None, height=22)
        sens_head.add_widget(Label(text="Swipe Sensitivity", color=(0.80, 0.94, 0.88, 1.0), font_size="11sp", halign="left", valign="middle"))
        sens_value = Label(text="1.00x", color=(0.94, 1.0, 0.96, 1.0), font_size="11sp", bold=True, size_hint_x=None, width=52)
        sens_head.children[0].bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))
        sens_head.add_widget(sens_value)
        sensitivity_slider = Slider(min=50, max=200, value=100, step=1)
        sensitivity_slider.cursor_size = (18, 18)
        sensitivity_slider.value_track = True
        sensitivity_slider.value_track_color = (0.26, 0.96, 0.68, 0.95)
        sensitivity_slider.bind(value=lambda _, v: screen.set_sensitivity(v / 100.0))
        sens_box.add_widget(sens_head)
        sens_box.add_widget(sensitivity_slider)
        controls_card.add_widget(sens_box)

        vibration_switch = NeonSwitch(size_hint=(None, None), size=(68, 34))
        vibration_switch.bind(on_release=lambda *_: screen.toggle_vibration(vibration_switch.active))
        controls_card.add_widget(_row("Vibration", vibration_switch, height=46))
        content.add_widget(controls_card)

        # GRAPHICS
        graphics_card = _make_card("GRAPHICS")
        graphics_card.height = 206
        quality_button = MenuNeonButton(
            text="[b]Balanced[/b]",
            secondary=True,
            size_hint_y=None,
            height=40,
            font_size="11sp",
        )
        quality_button.bind(on_press=lambda *_: screen.cycle_graphics_quality())
        graphics_card.add_widget(_row("Visual Quality", quality_button, height=46))

        environment_button = MenuNeonButton(
            text="[b]Meadow[/b]",
            secondary=True,
            size_hint_y=None,
            height=40,
            font_size="11sp",
        )
        environment_button.bind(on_press=lambda *_: screen.cycle_environment_theme())
        graphics_card.add_widget(_row("Environment", environment_button, height=46))

        grid_switch = NeonSwitch(size_hint=(None, None), size=(68, 34))
        grid_switch.bind(on_release=lambda *_: screen.toggle_grid(grid_switch.active))
        graphics_card.add_widget(_row("Grid", grid_switch, height=46))
        content.add_widget(graphics_card)

        # GAMEPLAY
        gameplay_card = _make_card("GAMEPLAY")
        gameplay_card.height = 206
        mode_button = MenuNeonButton(
            text="[b]Classic[/b]",
            secondary=True,
            size_hint_y=None,
            height=40,
            font_size="11sp",
        )
        mode_button.bind(on_press=lambda *_: screen.cycle_game_mode())
        gameplay_card.add_widget(_row("Game Mode", mode_button, height=46))

        speed_button = MenuNeonButton(
            text="[b]Medium[/b]",
            secondary=True,
            size_hint_y=None,
            height=40,
            font_size="11sp",
        )
        speed_button.bind(on_press=lambda *_: screen.cycle_speed_mode())
        gameplay_card.add_widget(_row("Game Speed", speed_button, height=46))

        skin_button = MenuNeonButton(
            text="[b]Classic[/b]",
            secondary=True,
            size_hint_y=None,
            height=40,
            font_size="11sp",
        )
        skin_button.bind(on_press=lambda *_: screen.cycle_snake_skin())
        gameplay_card.add_widget(_row("Snake Skin", skin_button, height=46))
        content.add_widget(gameplay_card)

        status_label = Label(text="", size_hint_y=None, height=22, font_size="11sp", color=(0.98, 0.78, 0.48, 1.0))
        content.add_widget(status_label)

        scroll.add_widget(content)
        root.add_widget(scroll)

        action_row = BoxLayout(size_hint=(0.92, 0.10), pos_hint={"center_x": 0.5, "y": 0.03}, spacing=10)
        reset_btn = MenuNeonButton(text="[b]RESET PROGRESS[/b]", secondary=True)
        reset_btn._fill_color.rgba = (0.24, 0.10, 0.12, 0.92)
        reset_btn._edge_color.rgba = (1.0, 0.46, 0.48, 0.90)
        reset_btn._glow_color.rgba = (0.98, 0.30, 0.30, 0.20)
        reset_btn.bind(on_press=lambda *_: screen.reset_progress())

        back_btn = MenuNeonButton(text="[b]BACK[/b]", secondary=True)
        back_btn.bind(on_press=lambda *_: screen.go_back())
        action_row.add_widget(reset_btn)
        action_row.add_widget(back_btn)
        self._wire_click_sounds(reset_btn, back_btn)
        root.add_widget(action_row)

        screen.add_widget(root)
        screen.ids = {
            'sound_toggle': sound_switch,
            'master_slider': master_slider,
            'sfx_slider': sfx_slider,
            'master_value_label': master_value,
            'sfx_value_label': sfx_value,
            'sensitivity_slider': sensitivity_slider,
            'sensitivity_value_label': sens_value,
            'vibration_toggle': vibration_switch,
            'quality_button': quality_button,
            'environment_button': environment_button,
            'grid_toggle': grid_switch,
            'mode_button': mode_button,
            'speed_button': speed_button,
            'skin_button': skin_button,
            'status_label': status_label,
        }
        return screen

    def _build_game_over_screen(self):
        """Build game-over screen."""
        screen = GameOverScreen(name="game_over")
        layout = BoxLayout(orientation="vertical", padding=[20, 18], spacing=12)

        with layout.canvas.before:
            Color(0.02, 0.04, 0.06, 1.0)
            bg_rect = Rectangle(pos=layout.pos, size=layout.size)
            Color(0.08, 0.22, 0.20, 0.30)
            bg_glow = Rectangle(pos=layout.pos, size=layout.size)

        def _sync_bg(*_):
            bg_rect.pos = layout.pos
            bg_rect.size = layout.size
            bg_glow.pos = (layout.x, layout.y + layout.height * 0.32)
            bg_glow.size = (layout.width, layout.height * 0.68)

        layout.bind(pos=_sync_bg, size=_sync_bg)

        top_spacer = Widget(size_hint_y=0.08)
        layout.add_widget(top_spacer)

        title = Label(
            text="[b][color=ffd7d7]Game Over[/color][/b]",
            markup=True,
            font_size="40sp",
            size_hint_y=0.14,
        )
        layout.add_widget(title)

        subtitle = Label(
            text="[color=f4f4f4]Thanks for playing[/color]",
            markup=True,
            font_size="16sp",
            size_hint_y=0.07,
        )
        layout.add_widget(subtitle)

        mode_badge_wrap = BoxLayout(size_hint_y=0.09, padding=[0, 0, 0, 0])
        mode_badge = Label(
            text="[b][color=ffd580]MODE: CLASSIC[/color][/b]",
            markup=True,
            font_size="15sp",
            size_hint=(None, None),
            size=(240, 38),
        )
        mode_badge_wrap.add_widget(Widget())
        mode_badge_wrap.add_widget(mode_badge)
        mode_badge_wrap.add_widget(Widget())
        layout.add_widget(mode_badge_wrap)

        summary_panel = BoxLayout(orientation="vertical", size_hint_y=0.40, padding=[14, 12], spacing=8)
        with summary_panel.canvas.before:
            Color(0.08, 0.10, 0.16, 0.95)
            panel_rect = RoundedRectangle(pos=summary_panel.pos, size=summary_panel.size, radius=[18])
            Color(0.86, 0.90, 1.0, 0.24)
            panel_line = Line(rounded_rectangle=(summary_panel.x, summary_panel.y, summary_panel.width, summary_panel.height, 18), width=1.3)

        def _update_summary(*_):
            panel_rect.pos = summary_panel.pos
            panel_rect.size = summary_panel.size
            panel_line.rounded_rectangle = (summary_panel.x, summary_panel.y, summary_panel.width, summary_panel.height, 18)

        summary_panel.bind(pos=_update_summary, size=_update_summary)

        score_title = Label(
            text="[color=bfd0ff]FINAL SCORE[/color]",
            markup=True,
            font_size="13sp",
            size_hint_y=0.18,
        )
        summary_panel.add_widget(score_title)

        score_value = Label(
            text="0",
            color=(0.92, 1.0, 0.97, 1),
            font_size="52sp",
            bold=True,
            size_hint_y=0.40,
        )
        summary_panel.add_widget(score_value)

        stats_row = BoxLayout(size_hint_y=0.24, spacing=10)

        high_card = BoxLayout(orientation="vertical", padding=[8, 6])
        with high_card.canvas.before:
            Color(0.12, 0.16, 0.24, 0.96)
            high_rect = RoundedRectangle(pos=high_card.pos, size=high_card.size, radius=[12])

        high_card.bind(pos=lambda *_: setattr(high_rect, 'pos', high_card.pos), size=lambda *_: setattr(high_rect, 'size', high_card.size))
        high_card.add_widget(Label(text="[color=b7ccff]High Score[/color]", markup=True, font_size="12sp"))
        high_value = Label(text="0", color=(0.98, 0.96, 0.78, 1), font_size="21sp", bold=True)
        high_card.add_widget(high_value)

        level_card = BoxLayout(orientation="vertical", padding=[8, 6])
        with level_card.canvas.before:
            Color(0.12, 0.16, 0.24, 0.96)
            level_rect = RoundedRectangle(pos=level_card.pos, size=level_card.size, radius=[12])

        level_card.bind(pos=lambda *_: setattr(level_rect, 'pos', level_card.pos), size=lambda *_: setattr(level_rect, 'size', level_card.size))
        level_card.add_widget(Label(text="[color=b7ccff]Level[/color]", markup=True, font_size="12sp"))
        level_value = Label(text="1", color=(0.86, 0.96, 1.0, 1), font_size="21sp", bold=True)
        level_card.add_widget(level_value)

        stats_row.add_widget(high_card)
        stats_row.add_widget(level_card)
        summary_panel.add_widget(stats_row)

        summary_label = Label(
            text=screen.summary_text,
            font_size="12sp",
            color=(0.86, 0.90, 0.98, 0.92),
            halign="center",
            valign="middle",
            size_hint_y=0.18,
        )
        summary_label.bind(size=lambda inst, _: setattr(inst, 'text_size', (inst.width * 0.96, inst.height * 0.96)))
        summary_panel.add_widget(summary_label)
        layout.add_widget(summary_panel)

        layout.add_widget(Widget(size_hint_y=0.03))

        restart_btn = Button(text="PLAY AGAIN", size_hint_y=0.12, font_size="16sp", background_color=(0.30, 0.56, 0.34, 1))
        restart_btn.bind(on_press=lambda x: screen.restart_game())
        self._wire_click_sounds(restart_btn)
        layout.add_widget(restart_btn)

        row = BoxLayout(size_hint_y=0.11, spacing=10)
        menu_btn = Button(text="MAIN MENU", font_size="14sp", background_color=(0.28, 0.32, 0.42, 1))
        menu_btn.bind(on_press=lambda x: screen.go_menu())

        lb_btn = Button(text="LEADERBOARD", font_size="14sp", background_color=(0.36, 0.30, 0.46, 1))
        lb_btn.bind(on_press=lambda x: screen.open_leaderboard())

        self._wire_click_sounds(menu_btn, lb_btn)

        row.add_widget(menu_btn)
        row.add_widget(lb_btn)
        layout.add_widget(row)

        layout.add_widget(Widget(size_hint_y=0.06))

        screen.add_widget(layout)
        screen.ids = {
            'summary_label': summary_label,
            'mode_label': mode_badge,
            'score_value': score_value,
            'high_value': high_value,
            'level_value': level_value,
        }
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
            message = self.game_controller.effect_message
            color = (0.98, 0.92, 0.72, 1.0)
            if "Poison" in message:
                color = (0.86, 0.62, 1.0, 1.0)
            elif "Burst" in message:
                color = (1.0, 0.78, 0.44, 1.0)
            elif "Combo" in message:
                color = (0.92, 0.98, 0.72, 1.0)
            elif "Slow" in message:
                color = (0.72, 0.90, 1.0, 1.0)
            game_screen.ids['game_board'].spawn_floating_text(food_pos, message, color=color)

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
        self._wire_click_sounds(finish_btn, revive_btn)
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
            game_over_screen.mode_text = f"MODE: {self.game_controller.current_mode.name.upper()}"
            game_over_screen.score_text = str(score)
            game_over_screen.high_score_text = str(high_score)
            game_over_screen.level_text = str(self.progression.level)
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
