"""Map current frame number to queue progress ratio (0..1)."""
import re

HRM_FRAME_RE = re.compile(r"HRM_FRAME\s+(\d+)", re.I)
HRM_WORK_RE = re.compile(r"HRM_WORK\s+(\d+)\s+(\d+)", re.I)
REDSHIFT_ROP_TOTAL_RE = re.compile(r"total time\s+([\d.]+)\s*sec", re.I)


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


def parse_redshift_rop_total_seconds(line):
    """ROP total time per frame (extraction + render), not beauty-pass only."""
    if not line or "rop node" not in line.lower():
        return None
    m = REDSHIFT_ROP_TOTAL_RE.search(line)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def ratio_for_work(done, total):
    try:
        done = int(done)
        total = int(total)
    except (TypeError, ValueError):
        return None
    if total <= 0:
        return 1.0 if done > 0 else 0.0
    return min(1.0, max(0.0, done / float(total)))


def work_progress_from_line(line, start_frame, end_frame):
    """After our script marks a frame done: (ratio, work_done, work_total) or None."""
    if not line:
        return None
    m = HRM_WORK_RE.search(line)
    if m:
        done, total = int(m.group(1)), int(m.group(2))
        return ratio_for_work(done, total), done, total
    m = HRM_FRAME_RE.search(line)
    if m:
        frame = int(m.group(1))
        if frame < int(start_frame) or frame > int(end_frame):
            return None
        total = int(end_frame) - int(start_frame) + 1
        done = frame - int(start_frame) + 1
        return ratio_for_frame(frame, start_frame, end_frame), done, total
    return None
