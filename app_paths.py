"""Paths for dev run vs PyInstaller frozen executable."""
import os
import shutil
import sys


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def app_dir():
    """Config and writable files: folder with the .exe when frozen."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def bundle_dir():
    """Bundled resources (hython helper scripts) inside the PyInstaller extract."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", app_dir())
    return os.path.dirname(os.path.abspath(__file__))


def bundled_script(filename):
    path = os.path.join(bundle_dir(), filename)
    if os.path.isfile(path):
        return path
    fallback = os.path.join(app_dir(), filename)
    return fallback if os.path.isfile(fallback) else path


def hython_script_path(filename):
    """Stable .py path for hython — beside .exe when frozen (PyInstaller _MEIPASS is internal)."""
    src = bundled_script(filename)
    if not os.path.isfile(src) or not is_frozen():
        return src
    dest = os.path.join(app_dir(), filename)
    try:
        if not os.path.isfile(dest) or os.path.getmtime(src) > os.path.getmtime(dest):
            shutil.copy2(src, dest)
    except OSError:
        return src
    return dest if os.path.isfile(dest) else src


def find_bundled_file(filename):
    """Resolve a bundled asset (logo, icons) for dev and frozen runs."""
    for base in (bundle_dir(), app_dir()):
        path = os.path.join(base, filename)
        if os.path.isfile(path):
            return path
    return ""


def config_path():
    return os.path.join(app_dir(), "config.json")


APP_ICON_ICO = "HouRM_icon.ico"
APP_ICON_PNG = "HouRM_icon.png"


def app_icon_path():
    """Multi-size .ico for Qt and shell; .png fallback."""
    for name in (APP_ICON_ICO, APP_ICON_PNG):
        for base in (bundle_dir(), app_dir()):
            path = os.path.join(base, name)
            if os.path.isfile(path):
                return path
    return os.path.join(bundle_dir(), APP_ICON_ICO)
