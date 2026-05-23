"""Map current frame number to queue progress ratio (0..1)."""
import re

HRM_FRAME_RE = re.compile(r"HRM_FRAME\s+(\d+)", re.I)
FRAME_HINT_RES = (
    re.compile(r"(?:^|\s)frame\s*[:=]?\s*(\d+)", re.I),
    re.compile(r"rendering\s+frame\s+(\d+)", re.I),
    re.compile(r"render\s+.*?frame\s+(\d+)", re.I),
)


def ratio_for_frame(frame, start_frame, end_frame):
    """0.0 at start_frame, 1.0 at end_frame (linear by frame index in queue)."""
    try:
        frame = int(frame)
        start_frame = int(start_frame)
        end_frame = int(end_frame)
    except (TypeError, ValueError):
        return 0.0
    if end_frame < start_frame:
        return 1.0
    span = end_frame - start_frame
    if span == 0:
        return 1.0
    return min(1.0, max(0.0, (frame - start_frame) / float(span)))


def parse_frame_from_line(line, start_frame, end_frame):
    if not line:
        return None
    m = HRM_FRAME_RE.search(line)
    if m:
        return int(m.group(1))
    for pattern in FRAME_HINT_RES:
        m = pattern.search(line)
        if m:
            return int(m.group(1))
    return None


def progress_from_line(line, start_frame, end_frame):
    frame = parse_frame_from_line(line, start_frame, end_frame)
    if frame is None or frame < start_frame or frame > end_frame:
        return None
    return ratio_for_frame(frame, start_frame, end_frame)
