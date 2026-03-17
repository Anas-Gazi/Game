"""Game constants and configuration."""
import sys
from enum import Enum
from pathlib import Path


BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def resource_path(*parts: str) -> str:
    """Return a runtime-safe path for local and packaged builds."""
    return str(BASE_DIR.joinpath(*parts))


class GameMode(Enum):
    """Available game modes."""
    CLASSIC = "classic"
    NO_WALL = "no_wall"
    TIME_ATTACK = "time_attack"
    HARDCORE = "hardcore"


class FoodType(Enum):
    """Food types with different effects."""
    NORMAL = "normal"
    BONUS = "bonus"  # High points, disappears after time
    POISON = "poison"  # Negative effect


# ============== BOARD SETTINGS ==============
BOARD_COLS = 20
BOARD_ROWS = 32
START_LENGTH = 4

# ============== GAMEPLAY TIMING ==============
BASE_MOVE_INTERVAL = 0.1  # Base speed (10 moves/sec)
MIN_MOVE_INTERVAL = 0.04  # Max speed cap
SPEED_STEP = 0.002  # Speed increase per score step
SPEED_SCORE_STEP = 50  # Score needed for one speed increase
BOOST_INTERVAL_FACTOR = 0.7  # Speed multiplier when boosting

# ============== TIME ATTACK ==============
TIME_ATTACK_DURATION = 60.0  # 60 seconds

# ============== HARDCORE MODE ==============
HARDCORE_BASE_MOVE_INTERVAL = 0.06  # Start faster

# ============== INPUT ==============
TOUCH_SWIPE_THRESHOLD = 30  # Minimum swipe distance (pixels)
DIRECTION_BUFFER_SIZE = 2  # Buffer queued input directions

# ============== WALLS ==============
WALL_COUNT = 8  # Number of wall groups in classic mode
WALL_SAFE_RADIUS = 5  # Safe zone around snake spawn

# ============== FOOD ==============
FOOD_SCORE = 10
BONUS_FOOD_SCORE = 25
BONUS_FOOD_LIFETIME = 5.0  # Seconds before disappearing
POISON_FOOD_PENALTY = -5  # Score penalty
POISON_EFFECTS_DURATION = 3.0  # Duration of poison effect
POISON_SPEED_MULTIPLIER = 1.3  # Speed increase when poisoned
SPECIAL_FOOD_SPAWN_RATE = 0.15  # 15% chance of special food

# ============== VISUAL EFFECTS ==============
PARTICLE_COUNT = 12
PARTICLE_LIFETIME = 0.6
GLOW_INTENSITY = 0.8
TRAIL_SEGMENTS = 5
TRAIL_FADE_SPEED = 0.3

# ============== SNAKE COLORS (REALISTIC) ==============
SNAKE_HEAD_COLOR = (0.33, 0.48, 0.20, 1.0)      # Olive green head
SNAKE_BODY_COLOR = (0.29, 0.44, 0.18, 1.0)      # Main body tone
SNAKE_DORSAL_COLOR = (0.20, 0.31, 0.13, 1.0)    # Darker top stripe
SNAKE_BELLY_COLOR = (0.70, 0.66, 0.50, 1.0)     # Light belly tone
SNAKE_EYE_COLOR = (0.95, 0.85, 0.25, 1.0)       # Amber eyes

# ============== SCREEN SHAKE ==============
COLLISION_SHAKE_INTENSITY = 0.15
COLLISION_SHAKE_DURATION = 0.2

# ============== COMBO SYSTEM ==============
COMBO_TIMEOUT = 0.8  # Time between eats to maintain combo
COMBO_MULTIPLIER_BASE = 1.0
COMBO_MULTIPLIER_INCREMENT = 0.1  # +10% per combo level
MAX_COMBO_LEVEL = 10

# ============== SPEED MODES ==============
SPEED_MODES = {
    "slow": 1.5,      # 1.5x slower (0.15 seconds per move)
    "medium": 1.0,    # Normal speed (0.1 seconds per move)
    "fast": 0.7,      # 0.7x slower = faster (0.07 seconds per move)
}
DEFAULT_SPEED_MODE = "medium"

# ============== PROGRESSION ==============
LEVEL_THRESHOLD = 100  # XP needed to level up
XP_BASE = 10  # Base XP per food
XP_MULTIPLIER_BONUS = 1.5  # XP multiplier for bonus food
LEVELS_MAX = 50

# ============== ACHIEVEMENTS ==============
ACHIEVEMENTS = {
    "first_food": {"name": "First Meal", "xp": 50},
    "ten_points": {"name": "Double Digit", "xp": 100},
    "fifty_points": {"name": "Nifty Fifty", "xp": 200},
    "hundred_points": {"name": "Century", "xp": 500},
    "combo_5": {"name": "On Fire", "xp": 150},
    "ten_minutes": {"name": "Endurance", "xp": 300},
    "100_level": {"name": "Maximum Power", "xp": 1000},
}

# ============== UNLOCKS ==============
SNAKE_SKINS = {
    "default": {"name": "Classic", "unlocked_at_level": 1},
    "python": {"name": "Python", "unlocked_at_level": 1},
    "viper": {"name": "Viper", "unlocked_at_level": 1},
    "cobra": {"name": "Cobra", "unlocked_at_level": 1},
    "neon": {"name": "Neon", "unlocked_at_level": 5},
    "gold": {"name": "Gold", "unlocked_at_level": 10},
    "shadow": {"name": "Shadow", "unlocked_at_level": 15},
    "fire": {"name": "Fire", "unlocked_at_level": 25},
    "ice": {"name": "Ice", "unlocked_at_level": 35},
}

SNAKE_SKIN_PALETTES = {
    "default": {
        "head": (0.33, 0.48, 0.20, 1.0),
        "body": (0.29, 0.44, 0.18, 1.0),
        "dorsal": (0.20, 0.31, 0.13, 1.0),
        "belly": (0.70, 0.66, 0.50, 1.0),
        "eye": (0.95, 0.85, 0.25, 1.0),
        "glow": (0.16, 0.25, 0.12, 0.24),
    },
    "python": {
        "head": (0.42, 0.50, 0.19, 1.0),
        "body": (0.36, 0.46, 0.18, 1.0),
        "dorsal": (0.23, 0.32, 0.12, 1.0),
        "belly": (0.78, 0.73, 0.56, 1.0),
        "eye": (0.94, 0.82, 0.22, 1.0),
        "glow": (0.20, 0.28, 0.12, 0.24),
    },
    "viper": {
        "head": (0.45, 0.34, 0.16, 1.0),
        "body": (0.39, 0.30, 0.15, 1.0),
        "dorsal": (0.23, 0.18, 0.09, 1.0),
        "belly": (0.75, 0.65, 0.49, 1.0),
        "eye": (0.93, 0.78, 0.20, 1.0),
        "glow": (0.24, 0.18, 0.10, 0.24),
    },
    "cobra": {
        "head": (0.26, 0.23, 0.19, 1.0),
        "body": (0.22, 0.20, 0.16, 1.0),
        "dorsal": (0.12, 0.11, 0.09, 1.0),
        "belly": (0.63, 0.58, 0.47, 1.0),
        "eye": (0.90, 0.76, 0.20, 1.0),
        "glow": (0.14, 0.14, 0.12, 0.24),
    },
}

FOOD_STYLES = {
    "default": {"name": "Classic", "unlocked_at_level": 1},
    "fruit": {"name": "Fruit", "unlocked_at_level": 3},
    "candy": {"name": "Candy", "unlocked_at_level": 7},
    "gem": {"name": "Gem", "unlocked_at_level": 12},
}

# ============== DAILY REWARDS ==============
DAILY_REWARD_BASE = 50  # Base reward points
DAILY_REWARD_STREAK_BONUS = 10  # Bonus per streak day
MAX_STREAK = 365
STREAK_RESET_HOURS = 48  # Hours to reset streak if not logged in

# ============== MONETIZATION ==============
SHOW_INTERSTITIAL_AFTER_DEATHS = 3  # Every N game overs
REWARDED_AD_REVIVE_LIMIT = 3  # Ad revives per day
ADS_REMOVAL_PRICE = 9.99  # USD

# ============== FILE PATHS ==============
SAVE_DATA_FILENAME = "savegame.json"
LEADERBOARD_FILENAME = "leaderboard.json"

# ============== AUDIO ==============
EAT_SOUND = resource_path("assets", "sounds", "eat.wav")
GAME_OVER_SOUND = resource_path("assets", "sounds", "game_over.wav")
CLICK_SOUND = resource_path("assets", "sounds", "click.wav")
LEVEL_UP_SOUND = resource_path("assets", "sounds", "levelup.wav")  # New
COMBO_SOUND = resource_path("assets", "sounds", "combo.wav")  # New

# ============== IMAGES ==============
BACKGROUND_IMAGE = resource_path("assets", "images", "background.png")
SNAKE_HEAD_IMAGE = resource_path("assets", "images", "snake_head.png")
SNAKE_BODY_IMAGE = resource_path("assets", "images", "snake_body.png")
FOOD_IMAGE = resource_path("assets", "images", "food.png")
BONUS_FOOD_IMAGE = resource_path("assets", "images", "bonus_food.png")
POISON_FOOD_IMAGE = resource_path("assets", "images", "poison_food.png")
WALL_IMAGE = resource_path("assets", "images", "wall.png")

# ============== WINDOW ==============
WINDOW_WIDTH = 420
WINDOW_HEIGHT = 760
WINDOW_RESIZABLE = True
TARGET_FPS = 60
