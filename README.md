# Houdini Render Manager

PySide6 desktop app for scanning Houdini `.hip` files for ROP nodes, managing a render queue, and sending Telegram notifications.

## Requirements

- Python 3.10+
- [Houdini](https://www.sidefx.com/) with `hython.exe` on your system
- Windows (primary target; paths in config use Windows style)

## Setup

```powershell
cd e:\hou_Rmanager
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy the example config and edit paths and Telegram settings:

```powershell
Copy-Item config.example.json config.json
```

`config.json` and `queue.json` are gitignored so local tokens and queue state are not committed.

## Run

```powershell
python main.py
```

When several HIP files are listed, **Scan HIP** uses the current (last-clicked) file; the label under the HIP list shows which file will be scanned.

**Queue UI:** status column is color-coded; duration is computed from start/end times; a progress line shows the active job during render; HIP/output paths show a short label with full path in the tooltip; **Enable all** / **Disable all** toggle every row; duplicate HIP+ROP pairs are skipped when adding to the queue.

**Paths:** ROP scan keeps Houdini expressions (`$HIP`, `$F4`, …) via `unexpandedValue`; render uses [`path_utils.py`](path_utils.py) to create folders and pass templates to `hrender` without breaking `$HIP`. Tooltip shows resolved path preview.

**Phase 3:** **Add all visible** ROPs; right-click menus on HIP list and queue; **Stop** asks for confirmation.

## Build executable

```powershell
pip install pyinstaller
pyinstaller main.spec
```

Output: `dist/HoudiniRenderManager.exe` (one-file build). Place `config.json` next to the exe (copy from `config.example.json`). Helper scripts `scan_rops.py` and `render_rop.py` are bundled inside the exe for `hython`.

Build artifacts under `build/` are ignored by git.

## Project layout

| File | Purpose |
|------|---------|
| `main.py` | Application entry point |
| `ui_main.py` | PySide6 UI |
| `queue_manager.py` | Queue persistence |
| `houdini_adapter.py` | Houdini integration helpers |
| `render_runner.py` | Render execution |
| `scan_rops.py` | ROP scan script (run via `hython`) |
| `telegram_notifier.py` | Telegram Bot API |
