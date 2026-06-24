import json

import logging

import os

import subprocess

import threading

import time

from frame_preview import FramePreviewWatcher

from path_utils import (

    ensure_output_directory,

    missing_render_frames,

    normalize_output_template,

    path_for_hrender,

)

from app_paths import config_path, hython_script_path
from render_progress import (
    HRM_FRAME_RE,
    HRM_WORK_RE,
    parse_redshift_rop_total_seconds,
    work_progress_from_line,
)

from telegram_notifier import send_message

from i18n import log_msg

def _notify_telegram(message, log_callback=None, language="en"):

    ok, err = send_message(message)

    if not ok and log_callback and err:

        log_callback(log_msg(language, "rr_tg_err", err=err))

def _format_elapsed(seconds):
    total = int(max(0, round(seconds)))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"

def _format_telegram_start(
    hip_path, rop, renderer, start_frame, end_frame, size_x, size_y, skip_existing_frames
):
    skip_label = "ON" if skip_existing_frames else "OFF"
    return (
        "🚀 Start render:\n"
        f"HIP: {hip_path},\n"
        f"ROP={rop},\n"
        f"Renderer={renderer},\n"
        f"frames: {start_frame} - {end_frame},\n"
        f"size: {size_x} x {size_y},\n"
        f"skip existing: {skip_label}"
    )

def _format_telegram_finish(hip_path, rop, duration_str):
    return (
        "✅ Finished render:\n"
        f"HIP: {hip_path},\n"
        f"ROP={rop},\n"
        f"Render time: {duration_str}"
    )

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

current_process = None
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def get_hrender_path():

    cfg = config_path()

    try:

        with open(cfg, "r", encoding="utf-8") as f:

            config = json.load(f)

            hython_path = config.get("hython_path", "")

            if hython_path:

                houdini_bin = os.path.dirname(hython_path)

                for cand in (

                    os.path.join(houdini_bin, "hrender.exe"),

                    os.path.join(houdini_bin, "hrender.py"),

                    os.path.join(houdini_bin, "hrender"),

                ):

                    if os.path.exists(cand):

                        return cand

    except Exception as e:

        logger.warning(f"Could not read config for hrender path: {e}")

    return "hrender"

def get_hython_path():

    cfg = config_path()

    try:

        with open(cfg, "r", encoding="utf-8") as f:

            hython_path = json.load(f).get("hython_path", "")

            if hython_path and os.path.exists(hython_path):

                return hython_path

    except Exception as e:

        logger.warning(f"Could not read config to find hython: {e}")

    return ""

def _resolve_work_total(scene, rop, start_frame, end_frame, output_path, skip_existing):
    total = max(0, int(end_frame) - int(start_frame) + 1)
    if not skip_existing or not output_path:
        return total
    try:
        missing = missing_render_frames(output_path, start_frame, end_frame, scene, rop)
        return len(missing)
    except Exception:
        return total

def _scene_frame_from_state(progress_state):
    frame = progress_state.get("last_scene_frame")
    if frame is None:
        return -1
    try:
        return int(frame)
    except (TypeError, ValueError):
        return -1


def _handle_output_line(line, start_frame, end_frame, progress_callback, progress_state):
    if not line:
        return progress_state
    stripped = line.strip()
    if not stripped:
        return progress_state

    rs_total = parse_redshift_rop_total_seconds(stripped)
    if rs_total is not None and rs_total > 0:
        progress_state["pending_sec"] = rs_total
        wt = int(progress_state.get("work_total") or 0)
        if progress_callback and wt > 0:
            done = int(progress_state.get("last_work_done", 0)) + 1
            progress_callback(
                min(1.0, done / wt),
                done,
                wt,
                rs_total,
                _scene_frame_from_state(progress_state),
            )
            progress_state["last_work_done"] = done
        return progress_state

    if not progress_callback:
        return progress_state

    m_frame = HRM_FRAME_RE.search(stripped)
    if m_frame:
        progress_state["last_scene_frame"] = int(m_frame.group(1))

    if HRM_WORK_RE.search(stripped):
        wp = work_progress_from_line(stripped, start_frame, end_frame)
    elif m_frame:
        full_span = max(0, int(end_frame) - int(start_frame) + 1)
        work_total = int(progress_state.get("work_total") or 0)
        if 0 < work_total < full_span:
            return progress_state
        wp = work_progress_from_line(stripped, start_frame, end_frame)
    else:
        wp = None

    if wp is None:
        return progress_state
    ratio, done, total = wp
    last_done = int(progress_state.get("last_work_done", 0))
    if done > last_done:
        frame_sec = progress_state.pop("pending_sec", None)
        if not frame_sec or frame_sec <= 0:
            frame_sec = -1.0
        else:
            frame_sec = float(frame_sec)
        progress_callback(
            ratio, done, total, frame_sec, _scene_frame_from_state(progress_state)
        )
        progress_state["last_work_done"] = done
        if total > 0:
            progress_state["work_total"] = total
    return progress_state

def _consume_render_output(
    process,
    start_frame,
    end_frame,
    progress_callback,
    progress_state,
    log_callback,
    preview_watcher,
):
    lock = threading.Lock()

    def on_line(raw_line):
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            return
        logger.info(line)
        if log_callback:
            log_callback(f"   {line}")
        nonlocal progress_state
        with lock:
            progress_state = _handle_output_line(
                line, start_frame, end_frame, progress_callback, progress_state
            )
        if preview_watcher:
            preview_watcher.poll()

    def pump(pipe):
        try:
            for raw in iter(pipe.readline, ""):
                on_line(raw)
        finally:
            pipe.close()

    stderr_thread = threading.Thread(target=pump, args=(process.stderr,), daemon=True)
    stderr_thread.start()
    pump(process.stdout)
    stderr_thread.join()
    return progress_state

def _build_hython_render_cmd(
    hython_path, render_script, scene, rop, start_frame, end_frame, actual_x, actual_y, output_for_cmd, skip_existing_frames, resize_pct=100.0
):
    cmd = [
        hython_path,
        render_script,

        "--hip",

        scene,

        "--rop",

        rop,

        "--start",

        str(start_frame),

        "--end",

        str(end_frame),

        "--skip-existing",

        "1" if skip_existing_frames else "0",

        "--resize-pct",

        str(resize_pct),

    ]

    if actual_x > 0:

        cmd.extend(["--width", str(actual_x)])

    if actual_y > 0:

        cmd.extend(["--height", str(actual_y)])

    if output_for_cmd:

        cmd.extend(["--output", output_for_cmd])

    return cmd

def _build_hrender_cmd(

    hrender_path, hython_path, scene, rop, start_frame, end_frame, actual_x, actual_y, output_for_cmd

):

    hrender_basename = os.path.basename(hrender_path).lower()

    hrender_dir = os.path.dirname(hrender_path)

    if hrender_path.lower().endswith(".py"):

        if hython_path and os.path.exists(hython_path):

            cmd = [hython_path, hrender_path, "-e", "-f", str(start_frame), str(end_frame)]

        else:

            raise RuntimeError("hrender.py found but hython is not configured in config.json")

    elif hrender_basename == "hrender" and not hrender_path.lower().endswith(".exe"):

        alt_py = os.path.join(hrender_dir, "hrender.py") if hrender_dir else ""

        if alt_py and os.path.exists(alt_py):

            if hython_path and os.path.exists(hython_path):

                cmd = [hython_path, alt_py, "-e", "-f", str(start_frame), str(end_frame)]

            else:

                raise RuntimeError("Configure hython_path in config.json to run hrender.py")

        else:

            cmd = [hrender_path, "-e", "-f", str(start_frame), str(end_frame)]

    else:

        cmd = [hrender_path, "-e", "-f", str(start_frame), str(end_frame)]

    if rop:

        rop_path = rop if rop.startswith("/") else f"/out/{rop}"

        cmd.extend(["-d", rop_path])

    if output_for_cmd:

        cmd.extend(["-o", output_for_cmd])

    if actual_x:

        cmd.extend(["-w", str(actual_x)])

    if actual_y:

        cmd.extend(["-h", str(actual_y)])

    cmd.append(scene)

    return cmd

def run_render(

    scene,

    rop,

    renderer,

    start_frame=1,

    end_frame=100,

    size_x=1920,

    size_y=1080,

    resize_pct=100,

    output_path="",

    log_callback=None,

    send2bot=0,

    hip_file=None,

    frame_callback=None,

    progress_callback=None,

    skip_existing_frames=False,

    render_width=None,

    render_height=None,

    language="en",

):

    global current_process

    preview_watcher = None

    if output_path and frame_callback and send2bot > 0:

        preview_watcher = FramePreviewWatcher(

            output_path,

            start_frame,

            end_frame,

            send2bot,

            hip_file=hip_file or scene,

            op_name=rop,

            on_frame_ready=frame_callback,

            skip_existing_frames=skip_existing_frames,

        )

        if log_callback:

            log_callback(log_msg(language, "rr_preview_interval", send2bot=send2bot))

    try:

        if render_width and render_height:

            actual_x = max(1, int(render_width))

            actual_y = max(1, int(render_height))

        else:

            actual_x = max(1, int(size_x * resize_pct / 100))

            actual_y = max(1, int(size_y * resize_pct / 100))

        scene = os.path.normpath(scene)

        message = _format_telegram_start(
            scene, rop, renderer, start_frame, end_frame, actual_x, actual_y, skip_existing_frames
        )

        render_started_at = time.monotonic()

        if log_callback:

            log_callback(message)

            log_callback(
                log_msg(
                    language,
                    "rr_resolution",
                    actual_x=actual_x,
                    actual_y=actual_y,
                    resize_pct=resize_pct,
                )
            )

        _notify_telegram(message, log_callback, language)

        if progress_callback:
            total_frames = max(0, int(end_frame) - int(start_frame) + 1)
            progress_callback(0.0, 0, total_frames, -1.0, -1)

        output_for_cmd = ""

        if output_path:

            output_for_cmd = path_for_hrender(normalize_output_template(output_path.strip()))

            ensure_output_directory(output_for_cmd, scene, log_callback, op_name=rop)

        hython_path = os.path.normpath(get_hython_path())

        render_rop_script = hython_script_path("render_rop.py")

        use_hython_render = (
            hython_path
            and os.path.exists(hython_path)
            and os.path.exists(render_rop_script)
        )

        if "redshift" in str(renderer).lower() and not use_hython_render:
            raise RuntimeError(
                "Redshift: для Resize нужен hython и render_rop.py (настройте hython_path в config.json). "
                "hrender -w/-h не меняет разрешение Redshift ROP."
            )

        if use_hython_render:

            cmd = _build_hython_render_cmd(
                hython_path,
                render_rop_script,
                scene,

                rop,

                start_frame,

                end_frame,

                actual_x,

                actual_y,

                output_for_cmd,

                skip_existing_frames,

                resize_pct,

            )

            if log_callback and not skip_existing_frames:

                log_callback(log_msg(language, "rr_force_all_frames"))

        else:

            cmd = _build_hrender_cmd(

                get_hrender_path(),

                hython_path,

                scene,

                rop,

                start_frame,

                end_frame,

                actual_x,

                actual_y,

                output_for_cmd,

            )

            if log_callback and not skip_existing_frames:

                log_callback(log_msg(language, "rr_hython_unavailable"))

        logger.info(f"Running command: {' '.join(cmd)}")

        if log_callback:

            log_callback(log_msg(language, "rr_command", cmd=" ".join(cmd)))

        popen_kw = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1,
        }
        if os.name == "nt":
            popen_kw["creationflags"] = CREATE_NO_WINDOW

        current_process = subprocess.Popen(cmd, **popen_kw)

        progress_state = {
            "last_work_done": 0,
            "pending_sec": None,
            "work_total": _resolve_work_total(
                scene, rop, start_frame, end_frame, output_path, skip_existing_frames
            ),
        }

        progress_state = _consume_render_output(
            current_process,
            start_frame,
            end_frame,
            progress_callback,
            progress_state,
            log_callback,
            preview_watcher,
        )

        retcode = current_process.wait()

        current_process = None

        if preview_watcher:

            preview_watcher.flush()

        if progress_callback:
            total_frames = max(0, int(end_frame) - int(start_frame) + 1)
            last_done = progress_state.get("last_work_done", 0)
            if retcode == 0:
                done = last_done if last_done > 0 else total_frames
                progress_callback(
                    1.0, done, done, -1.0, _scene_frame_from_state(progress_state)
                )
            elif total_frames > 0:
                progress_callback(
                    last_done / total_frames,
                    last_done,
                    total_frames,
                    -1.0,
                    _scene_frame_from_state(progress_state),
                )
            else:
                progress_callback(0.0, 0, 0, -1.0, -1)

        if retcode == 0:

            duration_str = _format_elapsed(time.monotonic() - render_started_at)

            message = _format_telegram_finish(scene, rop, duration_str)

            logger.info(message.replace("\n", " "))

            if log_callback:

                log_callback(message)

            _notify_telegram(message, log_callback, language)

        else:

            message = f"❌ Render failed with code {retcode}: {scene}, ROP={rop}"

            logger.error(message)

            if log_callback:

                log_callback(message)

            _notify_telegram(message, log_callback, language)

    except subprocess.CalledProcessError as e:

        message = f"Render failed: {e.stderr}"

        logger.error(message)

        if log_callback:

            log_callback(f"❌ {message}")

        _notify_telegram(f"❌ Failed render: {scene}, ROP={rop}. Error: {e.stderr}", log_callback, language)

    except Exception as e:

        message = f"Unexpected error: {e}"

        logger.error(message)

        if log_callback:

            log_callback(f"❌ {message}")

        _notify_telegram(f"❌ Error: {e}", log_callback, language)

    finally:

        current_process = None

def stop_render():

    global current_process

    if current_process:

        try:

            current_process.terminate()

            current_process.wait(timeout=5)

            logger.info("Render process terminated")

            return True

        except Exception as e:

            logger.error(f"Error stopping process: {e}")

            try:

                current_process.kill()

                return True

            except Exception:

                return False

    return False

