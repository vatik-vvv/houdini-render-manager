"""Detect finished render frames on disk and trigger Telegram preview."""
import os
import time

from path_utils import expand_frame_in_path, normalize_output_template

PREVIEW_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".exr"}


def is_preview_frame(frame_path):
    basename = os.path.basename(frame_path).lower()
    if "aov" in basename:
        return False
    ext = os.path.splitext(frame_path)[1].lower()
    return ext in PREVIEW_EXTENSIONS


def frame_output_path(output_template, frame, hip_file=None, op_name=None):
    if not output_template:
        return ""
    template = normalize_output_template(output_template.strip())
    return expand_frame_in_path(template, frame, hip_file, op_name)


class FramePreviewWatcher:
    """Poll output paths; fire callback when a frame file is stable (Telegram preview)."""

    def __init__(
        self,
        output_path,
        start_frame,
        end_frame,
        send2bot,
        hip_file=None,
        op_name=None,
        on_frame_ready=None,
        skip_existing_frames=True,
        poll_interval=1.0,
        stable_polls=2,
    ):
        self.output_path = output_path
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.send2bot = send2bot
        self.hip_file = hip_file
        self.op_name = op_name
        self.on_frame_ready = on_frame_ready
        self.skip_existing_frames = skip_existing_frames
        self.poll_interval = poll_interval
        self.stable_polls = max(1, stable_polls)
        self._last_poll = 0.0
        self._sent_frames = set()
        self._size_history = {}
        self._baseline = self._snapshot_baseline() if skip_existing_frames else {}

    def _snapshot_baseline(self):
        baseline = {}
        for frame in range(self.start_frame, self.end_frame + 1):
            path = frame_output_path(self.output_path, frame, self.hip_file, self.op_name)
            if not path or not os.path.isfile(path):
                continue
            try:
                st = os.stat(path)
                if st.st_size > 0:
                    baseline[path] = (st.st_size, st.st_mtime)
            except OSError:
                pass
        return baseline

    def _is_unchanged_preexisting(self, path, size):
        if not self.skip_existing_frames:
            return False
        base = self._baseline.get(path)
        if base is None:
            return False
        base_size, base_mtime = base
        if size != base_size:
            return False
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return True
        return mtime <= base_mtime + 0.001

    def _should_send(self, frame):
        if self.send2bot <= 0:
            return False
        offset = frame - self.start_frame
        if offset < 0:
            return False
        return offset % self.send2bot == 0

    def _frame_ready(self, frame):
        path = frame_output_path(self.output_path, frame, self.hip_file, self.op_name)
        if not path or not is_preview_frame(path) or not os.path.isfile(path):
            return None
        try:
            size = os.path.getsize(path)
        except OSError:
            return None
        if size <= 0:
            return None

        prev = self._size_history.get(path)
        if prev is not None and prev[0] == size:
            stable_count = prev[1] + 1
        else:
            stable_count = 0
        self._size_history[path] = (size, stable_count)

        if stable_count + 1 >= self.stable_polls:
            return path
        return None

    def poll(self, force=False):
        if not self.on_frame_ready or self.send2bot <= 0 or not self.output_path:
            return
        now = time.time()
        if not force and now - self._last_poll < self.poll_interval:
            return
        self._last_poll = now

        for frame in range(self.start_frame, self.end_frame + 1):
            if frame in self._sent_frames or not self._should_send(frame):
                continue
            path = frame_output_path(self.output_path, frame, self.hip_file, self.op_name)
            if path and os.path.isfile(path):
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
                if size > 0 and self._is_unchanged_preexisting(path, size):
                    self._sent_frames.add(frame)
                    continue
            path = self._frame_ready(frame)
            if path:
                self._sent_frames.add(frame)
                self.on_frame_ready(frame, path)

    def flush(self, timeout=120.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            before = len(self._sent_frames)
            self.poll(force=True)
            pending = [
                f
                for f in range(self.start_frame, self.end_frame + 1)
                if self._should_send(f) and f not in self._sent_frames
            ]
            if not pending:
                break
            if len(self._sent_frames) == before:
                time.sleep(self.poll_interval)
            else:
                time.sleep(0.3)
        self.poll(force=True)
