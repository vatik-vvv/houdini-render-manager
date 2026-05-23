import json

import logging

import os

import subprocess

import time



from frame_preview import FramePreviewWatcher

from path_utils import (

    ensure_output_directory,

    normalize_output_template,

    path_for_hrender,

)

from app_paths import app_dir, bundled_script, config_path
from render_progress import progress_from_line

from telegram_notifier import send_message





def _notify_telegram(message, log_callback=None):

    ok, err = send_message(message)

    if not ok and log_callback and err:

        log_callback(f"⚠️ Telegram: {err}")


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

SCRIPT_DIR = app_dir()





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





def _handle_output_line(line, start_frame, end_frame, progress_callback, last_ratio):

    if not progress_callback or not line:

        return last_ratio

    ratio = progress_from_line(line, start_frame, end_frame)

    if ratio is not None and ratio >= last_ratio:

        progress_callback(ratio)

        return ratio

    return last_ratio





def _build_hython_render_cmd(

    hython_path, scene, rop, start_frame, end_frame, actual_x, actual_y, output_for_cmd, skip_existing_frames, resize_pct=100.0

):

    script = os.path.join(SCRIPT_DIR, "render_rop.py")

    cmd = [

        hython_path,

        script,

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

            log_callback(f"📤 Превью в Telegram: каждые {send2bot} кадр(а), по мере готовности файла")



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

            log_callback(f"   Разрешение рендера: {actual_x}x{actual_y} (Resize {resize_pct:g}%)")

        _notify_telegram(message, log_callback)



        if progress_callback:

            progress_callback(0.0)



        output_for_cmd = ""

        if output_path:

            output_for_cmd = path_for_hrender(normalize_output_template(output_path.strip()))

            ensure_output_directory(output_for_cmd, scene, log_callback, op_name=rop)



        hython_path = os.path.normpath(get_hython_path())

        render_rop_script = bundled_script("render_rop.py")

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

                log_callback("   Принудительный рендер всех кадров (Skip в очереди выключен)")

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

                log_callback(

                    "⚠️ hython/render_rop.py недоступен — пропуск существующих кадров "

                    "задаётся только параметрами ROP в HIP"

                )



        logger.info(f"Running command: {' '.join(cmd)}")

        if log_callback:

            log_callback(f"📝 Команда: {' '.join(cmd)}")



        current_process = subprocess.Popen(

            cmd,

            stdout=subprocess.PIPE,

            stderr=subprocess.PIPE,

            text=True,

            bufsize=1,

        )



        last_ratio = 0.0

        while True:

            output_line = current_process.stdout.readline()

            if output_line == "" and current_process.poll() is not None:

                break

            if output_line:

                line = output_line.strip()

                if line:

                    logger.info(line)

                    if log_callback:

                        log_callback(f"   {line}")

                    last_ratio = _handle_output_line(

                        line, start_frame, end_frame, progress_callback, last_ratio

                    )

            if preview_watcher:

                preview_watcher.poll()



        stderr_output = current_process.stderr.read()

        if stderr_output:

            logger.error(f"Stderr: {stderr_output}")

            if log_callback:

                log_callback(f"⚠️ Stderr: {stderr_output}")

            for line in stderr_output.splitlines():

                last_ratio = _handle_output_line(

                    line.strip(), start_frame, end_frame, progress_callback, last_ratio

                )



        retcode = current_process.wait()

        current_process = None



        if preview_watcher:

            preview_watcher.flush()



        if progress_callback:

            progress_callback(1.0 if retcode == 0 else last_ratio)



        if retcode == 0:

            duration_str = _format_elapsed(time.monotonic() - render_started_at)

            message = _format_telegram_finish(scene, rop, duration_str)

            logger.info(message.replace("\n", " "))

            if log_callback:

                log_callback(message)

            _notify_telegram(message, log_callback)

        else:

            message = f"❌ Render failed with code {retcode}: {scene}, ROP={rop}"

            logger.error(message)

            if log_callback:

                log_callback(message)

            _notify_telegram(message, log_callback)



    except subprocess.CalledProcessError as e:

        message = f"Render failed: {e.stderr}"

        logger.error(message)

        if log_callback:

            log_callback(f"❌ {message}")

        _notify_telegram(f"❌ Failed render: {scene}, ROP={rop}. Error: {e.stderr}", log_callback)

    except Exception as e:

        message = f"Unexpected error: {e}"

        logger.error(message)

        if log_callback:

            log_callback(f"❌ {message}")

        _notify_telegram(f"❌ Error: {e}", log_callback)

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


