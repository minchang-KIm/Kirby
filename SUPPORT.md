# Windsprig Support

## Requirements

Browser play requires desktop Chromium, a physical keyboard or compatible gamepad, and a viewport of at least 1024×576. The Windows x64 release supports Windows 10 or newer. Keep the extracted Windows folder together; do not run the executable from inside the ZIP.

## Saves

- Browser profiles are local to the current browser profile and site origin.
- Windows profiles are stored under `%LOCALAPPDATA%/Windsprig`.
- The game keeps one known-good backup and attempts deterministic recovery if the primary save is interrupted or invalid.

To reset browser progress, close the game, open Chromium's site settings for the Windsprig play origin, remove that site's stored data, and reload. This permanently removes profiles for that browser origin.

## Controller troubleshooting

Connect controllers before joining, press a face button to join, and keep each player on one stable device. If a controller is not detected, disconnect duplicate virtual controllers, reconnect the device, verify it appears in the operating system, reload the browser or restart the Windows build, and review the in-game Controls screen. Players 3 and 4 require compatible gamepads.

## Get help

Search or open a public issue at [github.com/minchang-KIm/windsprig/issues](https://github.com/minchang-KIm/windsprig/issues). Include the Windsprig version, browser or Windows version, input device, exact reproduction steps, and any visible recovery code. Do not post private vulnerability details; use the route in `SECURITY.md`.
