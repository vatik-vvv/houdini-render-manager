import os
import json
import sys
from PySide6.QtWidgets import QApplication
from app_paths import app_dir, config_path, bundled_script
from ui_main import RenderManager

CONFIG_FILE = config_path()
QUEUE_FILE = os.path.join(app_dir(), "queue.json")

def ensure_files_exist():
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "telegram": {
                "bot_token": "",
                "chat_id": "",
                "preview_max_side": 2000
            },
            "ui": {
                "width": 1200,
                "height": 800
            },
            "filters": {
                "redshift": False,
                "karma": False,
                "other": False
            }
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)

    if not os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4, ensure_ascii=False)

def main():
    ensure_files_exist()
    app = QApplication(sys.argv)
    app.setApplicationName("Houdini Render Manager")
    icon_path = os.path.join(app_dir(), "app_icon.png")
    if not os.path.exists(icon_path):
        icon_path = os.path.join(getattr(sys, "_MEIPASS", app_dir()), "app_icon.png")
    if os.path.exists(icon_path):
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(icon_path))
    window = RenderManager()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
