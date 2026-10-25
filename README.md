# Mofid Games · بازی‌های مفید

Interactive projection-floor games for the Mofid Securities (کارگزاری مفید) exhibition. Each game lives in its own folder.

| Game | Folder | Windows build |
|---|---|---|
| **Market Hockey · هاکی بازار** | [`hocky/`](hocky/) | `MarketHockey-windows` |
| *(next game)* | — | — |

## Getting the Windows version

1. Open the repo on GitHub → **Actions** → **Build Windows**.
2. Open the latest green run (or click **Run workflow** to build now) and download **MarketHockey-windows** under *Artifacts*.
3. Unzip it anywhere writable on the Windows PC (e.g. `C:\MofidGames\MarketHockey`). Avoid `Program Files`, because settings are saved next to the `.exe`.
4. Run **`MarketHockey.exe`** (the game) and **`ControlPanel.exe`** (live settings). The first time, Windows may show *“Windows protected your PC”*: click **More info → Run anyway**.

Tagged versions (`v1.0.0`, …) also appear under **Releases** as a zip.

## Developing

Each game folder has its own `README.md`, `requirements.txt` and tests. Builds are made by
`.github/workflows/build-windows.yml`. To add a new game, add an entry to its `matrix.include` list and give the
game a `packaging/<App>.spec` file.
