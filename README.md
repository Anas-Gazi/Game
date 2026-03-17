# Snake Game

A production-style Snake game built with Python and Kivy, structured for Android packaging with Buildozer.

## Folder Structure

```text
snake_game/
├── main.py
├── ads_manager.py
├── game/
│   ├── collision.py
│   ├── food.py
│   ├── game_controller.py
│   ├── settings.py
│   └── snake.py
├── ui/
│   ├── game_over_screen.kv
│   ├── game_screen.kv
│   └── menu_screen.kv
├── assets/
│   ├── images/
│   │   ├── background.png
│   │   ├── food.png
│   │   ├── snake_body.png
│   │   └── snake_head.png
│   └── sounds/
│       ├── click.wav
│       ├── eat.wav
│       └── game_over.wav
├── utils/
│   ├── score_manager.py
│   └── storage.py
├── buildozer.spec
└── README.md
```

## Features

- Grid-based smooth snake movement with 60 FPS rendering
- Swipe controls for mobile devices
- Direction reversal protection
- Score and locally persisted high score
- Difficulty ramp based on score
- Pause, resume, restart, and game over flow
- Particle burst when food is eaten
- Audio hooks for click, eat, and game over events
- Android-ready Buildozer configuration
- Monetization-ready ad manager stubs for banner and rewarded ads

## Run Locally

1. Create and activate a Python 3.13 virtual environment. Avoid Python 3.14 for now because Kivy Windows wheels are not available there in this setup.
2. Install Kivy:

```bash
pip install kivy==2.3.1
```

3. Start the game:

```bash
python main.py
```

## Build Windows Release For Players

This project now includes a PyInstaller build flow for Windows so players do not need Python or Kivy installed.

1. From the `snake_game` folder, run:

```powershell
./build_windows.ps1
```

2. The build script creates:

```text
dist/SnakeLegends/
release/SnakeLegends-windows.zip
```

3. Upload `release/SnakeLegends-windows.zip` to itch.io.

4. Players only need to:
- download the zip
- extract the zip
- open the `SnakeLegends` folder
- run `SnakeLegends.exe`

No Python installation is required for players.

## Quick itch.io Publish (No Setup For Players)

Use this every time you release:

1. Build the Windows package:

```powershell
./build_windows.ps1
```

2. Upload this file to itch.io:

```text
release/SnakeLegends-windows.zip
```

3. In itch.io settings:
- Kind of project: `Downloadable`
- Platforms: `Windows`
- Pricing: `Free` (or your choice)

4. In your game page instructions, tell players:
- Download zip
- Extract zip
- Open folder
- Run `SnakeLegends.exe`

## Copy-Paste itch.io Page Text

### Short Description

Classic Snake, upgraded with modern visuals, multiple game modes, progression, and competitive high scores.

### Full Description

Snake Legends is a polished modern Snake game made with Python and Kivy.

What you get:
- Multiple game modes (Classic, No Wall, Time Attack, Hardcore)
- Real-time scoring, combo system, and high score tracking
- Level progression and unlockable cosmetics
- Smooth controls (keyboard + swipe support)
- Modern UI with a clean PC-friendly layout

How to play:
- Move: `W A S D`
- Pause/Resume: `Space`
- Goal: Eat food, avoid collisions, and beat your best score.

Install steps:
1. Download `SnakeLegends-windows.zip`
2. Extract the zip
3. Open the extracted folder
4. Run `SnakeLegends.exe`

No Python installation is required.

### Controls (Paste in itch.io Metadata)

- `W` = Up
- `A` = Left
- `S` = Down
- `D` = Right
- `Space` = Pause / Resume

### Recommended Screenshots to Upload

1. Main menu (showing game modes)
2. In-game action with HUD visible
3. Game over summary screen
4. Leaderboard screen
5. Settings screen

## Release Checklist

- [ ] Run `./build_windows.ps1`
- [ ] Confirm file exists: `release/SnakeLegends-windows.zip`
- [ ] Test `SnakeLegends.exe` from extracted zip
- [ ] Upload zip to itch.io
- [ ] Update version notes/changelog
- [ ] Publish page

## Versioning Workflow

Use this lightweight release flow for each update:

1. Update `CHANGELOG.md` with new features, changes, and fixes.
2. Bump the version number using semantic versioning:
- `MAJOR.MINOR.PATCH`
- Example: `1.0.0` -> `1.0.1` for fixes, `1.1.0` for new features.
3. Build a new release zip with `./build_windows.ps1`.
4. Upload the new zip to itch.io and add the version notes.
5. Create a matching git tag (optional but recommended):

```bash
git tag v1.0.0
git push origin v1.0.0
```

See release history in `CHANGELOG.md`.

## Build Android APK With Buildozer

Buildozer is typically run inside Linux or WSL. On Windows, use WSL2 or a Linux machine.

1. Install system dependencies for Buildozer and Android SDK tooling.
2. Open the project directory.
3. Run:

```bash
buildozer android debug
```

4. The generated APK will be available under the `bin/` directory.

To build a release package:

```bash
buildozer android release
```

## Google Play Store Publishing Checklist

1. Replace placeholder art and sound assets with production assets.
2. Set your final package domain and app signing configuration in `buildozer.spec`.
3. Prepare store listing assets: icon, screenshots, feature graphic, privacy policy.
4. Integrate real AdMob SDK logic into `ads_manager.py` if monetization is required.
5. Generate a signed AAB or APK for release.
6. Upload the release build in the Google Play Console.
7. Complete content rating, target audience, data safety, and app access forms.

## Notes

- The repository includes placeholder media files so the asset pipeline is ready.
- The game gracefully falls back to simple shapes if any asset fails to load.
- High score data is stored in Kivy's user data directory on desktop and Android.
