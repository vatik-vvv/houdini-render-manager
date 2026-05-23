# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
Houdini Render Manager is a Python-based GUI application (built with PySide6) designed to automate the process of scanning Houdini (.hip) files for ROP (Render Operator) nodes, managing a render queue, and notifying the user via Telegram upon render completion/failure.

## Architecture
- **UI Layer (`ui_main.py`, `main.py`)**: PySide6 interface for managing HIP files, scanning ROPs, and controlling the render queue.
- **Houdini Integration (`scan_rops.py`, `houdini_adapter.py`)**: Uses `hython` to execute Python scripts inside the Houdini environment to extract render settings and frame ranges.
- **Queue Management (`queue_manager.py`)**: Simple JSON-based persistence for the render queue (`queue.json`).
- **Execution Engine (`render_runner.py`)**: Handles the actual triggering of renders (currently uses `hrender`).
- **Notifications (`telegram_notifier.py`)**: Integrates with the Telegram Bot API to send status updates.
- **Configuration (`config.json`)**: Stores user preferences, Houdini paths, and Telegram bot credentials.

## Common Development Tasks
- **Run Application**: `python main.py`
- **Scan HIP for ROPs**: The application invokes `hython scan_rops.py <hip_file>` via subprocess.
- **Build Executable**: The project contains a `main.spec` file, suggesting it's packaged using PyInstaller. Use `pyinstaller main.spec` to build.

## Key Constraints & Notes
- **Houdini Dependency**: The application requires a valid installation of Houdini and a path to `hython.exe`.
- **JSON Persistence**: State is managed via `config.json` and `queue.json`. Ensure these files are handled carefully to avoid data loss.
- **Telegram Bot**: Requires a valid `bot_token` and `chat_id` in `config.json` for notifications to work.
