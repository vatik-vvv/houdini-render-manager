import json
import logging
import os
import tempfile

import sys

import requests

from app_paths import config_path

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    import cv2
except ImportError:
    cv2 = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONFIG_FILE = config_path()

DEFAULT_PREVIEW_MAX_SIDE = 2000
PREVIEW_MIN_SIDE = 64
PREVIEW_MAX_SIDE_LIMIT = 8000

BOT_TOKEN = ""
CHAT_ID = ""
PREVIEW_MAX_SIDE = DEFAULT_PREVIEW_MAX_SIDE
SEND_MP4_ON_COMPLETE = False
MP4_MAX_SIDE = 0
MP4_USE_PREVIEW_MAX = True

SUPPORTED_PREVIEW_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".bmp", ".webp",
}


def _load_config():
    global BOT_TOKEN, CHAT_ID, PREVIEW_MAX_SIDE, SEND_MP4_ON_COMPLETE, MP4_MAX_SIDE, MP4_USE_PREVIEW_MAX
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            tg = cfg.get("telegram", {})
            BOT_TOKEN = tg.get("bot_token", "")
            CHAT_ID = str(tg.get("chat_id", ""))
            raw_max = tg.get("preview_max_side", DEFAULT_PREVIEW_MAX_SIDE)
            try:
                PREVIEW_MAX_SIDE = int(raw_max)
            except (TypeError, ValueError):
                PREVIEW_MAX_SIDE = DEFAULT_PREVIEW_MAX_SIDE
            PREVIEW_MAX_SIDE = max(PREVIEW_MIN_SIDE, min(PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE_LIMIT))
            SEND_MP4_ON_COMPLETE = bool(tg.get("send_mp4_on_complete", True))
            MP4_USE_PREVIEW_MAX = bool(tg.get("mp4_use_preview_max_side", True))
            try:
                MP4_MAX_SIDE = int(tg.get("mp4_max_side", 0))
            except (TypeError, ValueError):
                MP4_MAX_SIDE = 0
        except Exception as e:
            logger.warning(f"Error loading Telegram config: {e}")
    else:
        logger.warning("config.json not found, notifications disabled.")


_load_config()


def reload_config():
    _load_config()


def check_preview_dependencies():
    """
    Returns (ok, user_message, install_hint).
    install_hint is a shell command or short instruction.
    """
    missing = []
    if Image is None:
        missing.append("Pillow")
    if np is None:
        missing.append("numpy")
    if not missing:
        return True, "", ""

    names = ", ".join(missing)
    if getattr(sys, "frozen", False):
        hint = "Пересоберите exe: pip install -r requirements.txt && pyinstaller main.spec"
        return False, f"В сборке отсутствуют: {names}", hint

    py = sys.executable
    hint = f'"{py}" -m pip install -r requirements.txt'
    return False, f"Не установлены: {names}", hint


def _resolve_max_side(max_side):
    if max_side is None:
        reload_config()
        return PREVIEW_MAX_SIDE
    try:
        value = int(max_side)
    except (TypeError, ValueError):
        value = DEFAULT_PREVIEW_MAX_SIDE
    return max(PREVIEW_MIN_SIDE, min(value, PREVIEW_MAX_SIDE_LIMIT))


def get_mp4_max_side():
    reload_config()
    if MP4_USE_PREVIEW_MAX or MP4_MAX_SIDE <= 0:
        return PREVIEW_MAX_SIDE
    return max(PREVIEW_MIN_SIDE, min(MP4_MAX_SIDE, PREVIEW_MAX_SIDE_LIMIT))


def send_message(text, timeout=5, bot_token=None, chat_id=None):
    """Send message to Telegram with timeout. Returns (ok, detail)."""
    reload_config()
    token = (bot_token or BOT_TOKEN or "").strip()
    chat = str(chat_id if chat_id is not None else CHAT_ID).strip()
    if not token or not chat:
        return False, "Telegram bot_token или chat_id не заданы в config.json"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat, "text": text}

    try:
        response = requests.post(url, json=payload, timeout=timeout)
        if response.status_code == 200:
            return True, ""
        return False, f"Telegram API {response.status_code}: {response.text[:200]}"
    except requests.Timeout:
        return False, f"Таймаут Telegram (>{timeout}s)"
    except Exception as e:
        return False, str(e)


def test_bot_connection(bot_token=None, chat_id=None, timeout=5):
    token = (bot_token or BOT_TOKEN or "").strip()
    if not token:
        return False, "bot_token пуст"
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            return True, ""
        return False, f"Telegram API {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, str(e)


def _tone_map_to_uint8(arr):
    """Convert float/HDR or high bit-depth array to 8-bit RGB for JPEG preview."""
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    arr = np.maximum(arr, 0)
    if arr.size == 0:
        return np.zeros((1, 1, 3), dtype=np.uint8)
    if np.issubdtype(arr.dtype, np.floating):
        peak = float(np.percentile(arr, 99.5))
        peak = max(peak, 1e-4)
        arr = np.clip(arr / peak, 0.0, 1.0)
        arr = (arr * 255.0).astype(np.uint8)
    elif arr.dtype == np.uint16:
        arr = (arr / 256).astype(np.uint8)
    elif arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return arr


def _numpy_to_pil_rgb(arr):
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    elif arr.ndim == 3:
        channels = arr.shape[2]
        if channels == 4:
            arr = arr[:, :, :3]
        elif channels == 1:
            arr = np.repeat(arr, 3, axis=2)
        elif channels >= 3:
            arr = arr[:, :, :3]
    arr = _tone_map_to_uint8(arr.astype(np.float64) if np.issubdtype(arr.dtype, np.floating) else arr)
    return Image.fromarray(arr, mode="RGB")


def _load_with_opencv(image_path):
    if cv2 is None or np is None:
        return None, "Для EXR установите: pip install opencv-python-headless numpy"
    data = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if data is None:
        return None, f"OpenCV не смог прочитать файл: {os.path.basename(image_path)}"
    if data.ndim == 2:
        rgb = data
    else:
        if data.shape[2] >= 3:
            rgb = cv2.cvtColor(data[:, :, :3], cv2.COLOR_BGR2RGB)
        else:
            rgb = data[:, :, 0]
    return _numpy_to_pil_rgb(rgb), ""


def _load_with_pillow(image_path):
    if Image is None:
        return None, "Pillow не установлен (pip install Pillow)"
    try:
        with Image.open(image_path) as img:
            img.load()
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (0, 0, 0))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")
            return img.copy(), ""
    except Exception as e:
        return None, str(e)


def _load_preview_image(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    if ext not in SUPPORTED_PREVIEW_EXTENSIONS:
        return None, f"Формат {ext} не поддерживается для превью (PNG/JPG/TIF/EXR)"

    if ext == ".exr":
        return _load_with_opencv(image_path)

    img, err = _load_with_pillow(image_path)
    if img is not None:
        return img, ""

    if ext in (".tif", ".tiff", ".exr"):
        return _load_with_opencv(image_path)

    return None, err or "Не удалось открыть изображение"


def _prepare_jpeg(image_path, max_side=DEFAULT_PREVIEW_MAX_SIDE):
    """Resize/convert any supported render file to JPEG. Returns (temp_path, error)."""
    if Image is None:
        return None, "Pillow не установлен (pip install Pillow)"

    max_side = _resolve_max_side(max_side)
    temp_path = None
    try:
        img, load_err = _load_preview_image(image_path)
        if img is None:
            return None, load_err or "Не удалось загрузить изображение"

        width, height = img.size
        scale = min(1.0, max_side / float(max(width, height))) if max(width, height) > 0 else 1.0
        if scale < 1.0:
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            img = img.resize(new_size, Image.LANCZOS)

        fd, temp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        img.save(temp_path, format="JPEG", quality=85, optimize=True)
        return temp_path, ""
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return None, f"Ошибка конвертации в JPEG: {e}"


def _send_photo_file(file_path, caption=None, mime="image/jpeg", timeout=30):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(file_path, "rb") as photo_file:
        files = {"photo": (os.path.basename(file_path), photo_file, mime)}
        data = {"chat_id": CHAT_ID}
        if caption:
            data["caption"] = caption[:1024]
        response = requests.post(url, data=data, files=files, timeout=timeout)
    if response.status_code == 200:
        return True, ""
    return False, f"Telegram API {response.status_code}: {response.text[:300]}"


def _send_video_file(file_path, caption=None, timeout=120):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    with open(file_path, "rb") as video_file:
        files = {"video": (os.path.basename(file_path), video_file, "video/mp4")}
        data = {"chat_id": CHAT_ID}
        if caption:
            data["caption"] = caption[:1024]
        response = requests.post(url, data=data, files=files, timeout=timeout)
    if response.status_code == 200:
        return True, ""
    return False, f"Telegram API {response.status_code}: {response.text[:300]}"


def send_video(video_path, caption=None, timeout=120):
    reload_config()
    if not SEND_MP4_ON_COMPLETE:
        return False, "MP4 превью отключено в настройках"
    if not BOT_TOKEN or not CHAT_ID:
        return False, "Telegram bot_token или chat_id не заданы в config.json"
    if not video_path or not os.path.isfile(video_path):
        return False, f"Файл не найден: {video_path}"
    size_mb = os.path.getsize(video_path) / (1024 * 1024)
    if size_mb > 49:
        return False, f"MP4 {size_mb:.1f} MB — лимит Telegram ~50 MB"
    try:
        return _send_video_file(video_path, caption=caption, timeout=timeout)
    except requests.Timeout:
        return False, f"Таймаут Telegram (>{timeout}s)"
    except Exception as e:
        return False, str(e)


def send_image(image_path, caption=None, max_side=None, timeout=30):
    """
    Convert render frame to resized JPEG and send to Telegram.
    max_side: None = value from config (telegram.preview_max_side, default 2000).
    Returns (success: bool, error_detail: str).
    """
    reload_config()
    if not BOT_TOKEN or not CHAT_ID:
        return False, "Telegram bot_token или chat_id не заданы в config.json"
    if not image_path or not os.path.isfile(image_path):
        return False, f"Файл не найден: {image_path}"

    max_side = _resolve_max_side(max_side)
    temp_path = None
    try:
        temp_path, prep_err = _prepare_jpeg(image_path, max_side)
        if not temp_path:
            return False, prep_err or "Не удалось подготовить JPEG"

        size_mb = os.path.getsize(temp_path) / (1024 * 1024)
        if size_mb > 9.5:
            return False, (
                f"JPEG {size_mb:.1f} MB — лимит Telegram ~10 MB "
                f"(уменьшите preview_max_side в настройках, сейчас {max_side}px)"
            )
        return _send_photo_file(temp_path, caption=caption, mime="image/jpeg", timeout=timeout)
    except requests.Timeout:
        return False, f"Таймаут Telegram (>{timeout}s)"
    except Exception as e:
        return False, str(e)
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
