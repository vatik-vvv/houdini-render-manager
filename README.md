# Houdini Render Manager

PySide6 desktop app for scanning Houdini `.hip` files for ROP nodes, managing a render queue, and sending Telegram notifications.

**Repository:** https://github.com/vatik-vvv/houdini-render-manager

## Requirements

- Python 3.10+
- [Houdini](https://www.sidefx.com/) with `hython.exe`
- Windows (primary target)

## Setup

```powershell
cd E:\hou_Rmanager
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item config.example.json config.json
```

Edit `config.json`: `hython_path`, Telegram `bot_token` / `chat_id`. Queue and UI state are stored in `config.json` (gitignored).

## Run

```powershell
python main.py
```

## Build executable

```powershell
pip install pyinstaller
pyinstaller main.spec
```

Output: `dist/HoudiniRenderManager.exe`. Copy `config.example.json` to `dist/config.json` next to the exe.

## Project layout

| File | Purpose |
|------|---------|
| `main.py` | Entry point |
| `ui_main.py` | PySide6 UI and queue |
| `app_paths.py` | Paths for dev vs frozen exe |
| `render_runner.py` | Subprocess render + Telegram |
| `render_rop.py` | `hython` render script (skip frames, resize) |
| `scan_rops.py` | `hython` ROP scan script |
| `path_utils.py` | `$HIP`, `$OS`, frame paths |
| `frame_preview.py` | Telegram frame previews |
| `render_progress.py` | Frame progress from render log |
| `telegram_notifier.py` | Telegram Bot API |
| `config.example.json` | Example configuration |
| `main.spec` | PyInstaller spec |

Optional: `tools/install_gh.ps1`, `publish_to_github.ps1` — one-time GitHub publish helpers.
