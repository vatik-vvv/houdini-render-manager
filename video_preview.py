"""Build MP4 preview from rendered image sequence for Telegram."""
from __future__ import annotations

import os
import tempfile

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    from PIL import Image
except ImportError:
    Image = None


def _load_bgr(path, max_side):
    if cv2 is not None:
        data = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if data is None:
            return None
        if data.ndim == 2:
            bgr = cv2.cvtColor(data, cv2.COLOR_GRAY2BGR)
        elif data.shape[2] >= 3:
            bgr = cv2.cvtColor(data[:, :, :3], cv2.COLOR_BGR2RGB)
            bgr = cv2.cvtColor(bgr, cv2.COLOR_RGB2BGR)
        else:
            bgr = data
    elif Image is not None and np is not None:
        with Image.open(path) as img:
            rgb = np.array(img.convert("RGB"))
        bgr = rgb[:, :, ::-1].copy()
    else:
        return None

    h, w = bgr.shape[:2]
    side = max(w, h)
    if max_side > 0 and side > max_side:
        scale = max_side / float(side)
        nw = max(1, int(w * scale))
        nh = max(1, int(h * scale))
        if cv2 is not None:
            bgr = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA)
        else:
            from PIL import Image as PILImage

            bgr = np.array(
                PILImage.fromarray(bgr[:, :, ::-1]).resize((nw, nh), PILImage.LANCZOS)
            )[:, :, ::-1]
    return bgr


def collect_sequence_frames(output_path, start_frame, end_frame, hip_file=None, op_name=None):
    from path_utils import resolve_render_frames_on_disk

    found = resolve_render_frames_on_disk(
        output_path, start_frame, end_frame, hip_file, op_name
    )
    return sorted(found.items())


def build_mp4_from_sequence(
    output_path,
    start_frame,
    end_frame,
    hip_file=None,
    op_name=None,
    max_side=1920,
    fps=24,
    max_frames=300,
):
    """
    Encode an MP4 from rendered frames. Returns (temp_mp4_path, error_message).
    Samples evenly if there are more than max_frames files.
    """
    if cv2 is None:
        return None, "OpenCV (cv2) не установлен — нужен для MP4 превью"

    frames = collect_sequence_frames(output_path, start_frame, end_frame, hip_file, op_name)
    if not frames:
        return None, "Нет кадров для MP4 превью"

    if len(frames) > max_frames:
        step = max(1, len(frames) // max_frames)
        frames = frames[::step]

    if len(frames) == 1:
        frames = frames * 2

    first = _load_bgr(frames[0][1], max_side)
    if first is None:
        return None, "Не удалось прочитать первый кадр"

    h, w = first.shape[:2]
    fd, out_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not writer.isOpened():
        try:
            os.remove(out_path)
        except OSError:
            pass
        return None, "VideoWriter не смог создать MP4"

    try:
        writer.write(first)
        for _, path in frames[1:]:
            bgr = _load_bgr(path, max_side)
            if bgr is None:
                continue
            if bgr.shape[1] != w or bgr.shape[0] != h:
                bgr = cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)
            writer.write(bgr)
    finally:
        writer.release()

    if not os.path.isfile(out_path) or os.path.getsize(out_path) <= 0:
        return None, "MP4 файл пуст"
    return out_path, ""
