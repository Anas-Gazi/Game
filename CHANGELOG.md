# Changelog

All notable changes to this project will be documented in this file.

This project follows semantic versioning:
- MAJOR.MINOR.PATCH
- MAJOR: breaking changes
- MINOR: new features
- PATCH: bug fixes and small improvements

## [1.1.0] - 2026-03-19

### Added
- New ambient/background audio tracks for multiple environments.
- Additional UI and rendering polish assets.
- Internal backup snapshots used during rapid UI/UX recovery and rollback safety.

### Changed
- Refined in-game HUD and bottom controls to a compact classic style.
- Increased map-visible area by reducing gameplay control strip height.
- Improved readability of gameplay action controls and top status chips.
- Updated project documentation for release-quality GitHub presentation.

### Fixed
- Reduced graphics flicker from high-intensity ambient/pulse effects.
- Smoothed snake border-wrap rendering across left, right, top, and bottom edges.
- Improved transition continuity during edge crossing to reduce visible snapping.

## [1.0.0] - 2026-03-17

### Added
- Realistic multi-layer snake rendering and visual polish.
- Speed mode system (Slow, Medium, Fast) with saved preference.
- Menu redesign with PC-style layout and user-friendly controls.
- Full screen UI redesign for Game, Progression, Leaderboard, Settings, and Game Over.
- Daily reward status integration and improved menu stats display.
- Windows build pipeline using PyInstaller.
- Automated release packaging script for itch.io upload.

### Changed
- Updated UI behavior and spacing to improve readability and desktop feel.
- Improved release documentation and player install instructions.
