# Snake Legends

A polished Snake game built with Python and Kivy, featuring multiple game modes, progression systems, dynamic environments, and production-style release tooling.

## Highlights

- Smooth fixed-step gameplay with interpolated rendering.
- Multiple game modes: Classic, No Wall, Time Attack, Hardcore.
- Progression, achievements, combo scoring, and local high-score persistence.
- Environment-aware food variants and dynamic map atmosphere.
- Keyboard and touch controls.
- Windows packaging flow for player-friendly distribution.
- Android-ready Buildozer configuration.

## Latest Updates

### First Major Update (v1.0.0)

- Introduced full-screen UI overhaul across Menu, Game, Progression, Leaderboard, Settings, and Game Over.
- Added speed mode preferences and improved user-facing gameplay controls.
- Improved visual quality with layered snake rendering and premium effects.
- Added Windows release pipeline using PyInstaller and scripted release packaging.

### Current Update (v1.1.0)

- Improved in-game HUD and controls with a compact classic layout for better map visibility.
- Reduced visible graphics flicker by stabilizing high-intensity visual oscillation.
- Smoothed edge wrap rendering so snake transitions are continuous across all borders.
- Added/updated audio assets and ambient tracks for richer game presentation.
- Strengthened gameplay polish and rendering consistency after recent UX iterations.

For complete details, see `CHANGELOG.md`.

## Project Structure

```text
snake_game/
├── main.py
├── config/
├── core/
├── game/
├── modes/
├── progression/
├── retention/
├── services/
├── systems/
├── ui/
├── assets/
│   ├── images/
│   └── sounds/
├── build_windows.ps1
├── buildozer.spec
└── CHANGELOG.md
```

## Controls

- `W`, `A`, `S`, `D` or Arrow Keys: Move
- `Space`: Pause/Resume
- `Shift`: Boost
- `R`: Restart run
- `Esc`: Return to menu

## Run Locally

1. Create and activate a Python `3.13` virtual environment.
2. Install dependencies:

```bash
pip install kivy==2.3.1
```

3. Launch:

```bash
python main.py
```

## Build Windows Release

From the `snake_game` folder:

```powershell
./build_windows.ps1
```

Build outputs:

```text
dist/SnakeLegends/
release/SnakeLegends-windows.zip
```

Distribute `release/SnakeLegends-windows.zip` to players.

## Build Android With Buildozer

Buildozer is recommended on Linux/WSL.

Debug build:

```bash
buildozer android debug
```

Release build:

```bash
buildozer android release
```

## Release Workflow

1. Update `CHANGELOG.md`.
2. Build release package (`./build_windows.ps1`).
3. Validate packaged executable.
4. Push code and optional tag:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

## Notes

- Save data is stored locally via the save service.
- Asset fallback paths are implemented to keep runtime resilient.
- The repository currently contains historical backup snapshots used during UI/UX recovery.
