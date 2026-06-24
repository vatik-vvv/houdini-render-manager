import json
import os
import sys
from PySide6.QtWidgets import QApplication
from app_paths import app_icon_path, config_path
from ui_main import RenderManager

CONFIG_FILE = config_path()


def ensure_files_exist():
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "telegram": {
                "bot_token": "",
                "chat_id": "",
                "preview_max_side": 2000,
                "send_mp4_on_complete": False,
                "mp4_use_preview_max_side": True,
                "mp4_max_side": 0,
            },
            "ui": {
                "width": 1200,
                "height": 800,
                "log_position": "bottom",
                "sleep_on_queue_finish": False,
            },
            "filters": {
                "redshift": False,
                "karma": False,
                "other": False,
            },
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)


def main():
    ensure_files_exist()
    app = QApplication(sys.argv)
    app.setApplicationName("Houdini Render Manager")
    icon_path = app_icon_path()
    if os.path.exists(icon_path):
        from PySide6.QtGui import QIcon

        app.setWindowIcon(QIcon(icon_path))
    window = RenderManager()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

