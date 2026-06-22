"""
Render a ROP via hython with queue-level control of 'skip existing frames'.
Must run inside Houdini (hython), not standalone Python.
"""
import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
logger = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from path_utils import (
    expand_frame_in_path,
    frame_file_exists,
    has_frame_tokens,
    output_template_for_frames,
)

SKIP_PARM_EXACT = (
    "RS_skipExistingFrames",
    "skip_existing_frames",
    "skipexistingframes",
    "soho_skipgeneration",
    "skip_existing",
    "execute_skipexisting",
)

OUTPUT_PARM_EXACT = (
    "RS_outputFileNamePrefix",
    "vm_picture",
    "picture",
    "sopoutput",
    "filename",
)

OVERRIDE_RES_TOGGLES = (
    "override_camerares",
    "overrideCameraRes",
    "RS_overrideCameraRes",
    "overridecamera",
    "override_resolution",
    "overrideunifiedmaxres",
    "overrideresolution",
    "res_override",
    "override_res",
)

RESX_NAMES = (
    "resx",
    "xres",
    "resolutionx",
    "width",
    "sizex",
    "imagewidth",
    "pixelwidth",
    "rs_xresolution",
    "rs_xres",
    "rs_width",
    "x_resolution",
    "override_resx",
    "camera_resx",
)

RESY_NAMES = (
    "resy",
    "yres",
    "resolutiony",
    "height",
    "sizey",
    "imageheight",
    "pixelheight",
    "rs_yresolution",
    "rs_yres",
    "rs_height",
    "y_resolution",
    "override_resy",
    "camera_resy",
)

RES_EXCLUDE = ("compression", "passes", "quality", "bit", "format", "filter", "mode", "ratio", "scale")

CAMERA_PARM_NAMES = (
    "RS_renderCamera",
    "render_camera",
    "rendercamera",
    "rs_rendercamera",
    "rs_camera",
    "camera",
    "cam",
    "render_cam",
)

# When ON, renderer follows linked camera resolution — turn OFF so ROP override wins.
USE_CAMERA_RES_TOGGLES = (
    "usecamerares",
    "useCameraRes",
    "RS_useCameraRes",
    "use_camera_res",
    "fromcamera",
)

REDSHIFT_OVERRIDE_TOGGLES = (
    "RS_overrideCameraRes",
    "overrideCameraRes",
    "override_camerares",
    "RS_overrideUnifiedMaxRes",
    "overrideUnifiedMaxRes",
    "override_unifiedmaxres",
)

REDSHIFT_RES_PAIRS = (
    ("overrideCameraRes1", "overrideCameraRes2"),
    ("RS_overrideCameraRes1", "RS_overrideCameraRes2"),
    ("rs_overrideres1", "rs_overrideres2"),
    ("override_res1", "override_res2"),
    ("res1", "res2"),
)

REDSHIFT_RES_TUPLES = ("res", "resolution", "Resolution", "camres", "outputres")


def _rop_path(name):
    if name.startswith("/"):
        return name
    return f"/out/{name}"


def apply_skip_existing(node, enabled):
    import hou

    if node is None:
        return 0
    changed = 0
    val = 1 if enabled else 0
    for pname in SKIP_PARM_EXACT:
        p = node.parm(pname)
        if p is not None:
            try:
                p.set(val)
                changed += 1
                logger.info(f"  {pname} = {val}")
            except Exception as e:
                logger.warning(f"  Could not set {pname}: {e}")
    for parm in node.parms():
        try:
            if parm.parmTemplate().type() != hou.parmTemplateType.Toggle:
                continue
        except Exception:
            continue
        n = parm.name().lower()
        if "skip" in n and ("exist" in n or "rendered" in n):
            try:
                parm.set(val)
                changed += 1
                logger.info(f"  {parm.name()} = {val}")
            except Exception:
                pass
    return changed


def apply_output_path(node, output_path):
    if not output_path or node is None:
        return
    import hou

    for pname in OUTPUT_PARM_EXACT:
        p = node.parm(pname)
        if p is not None:
            try:
                p.set(output_path)
                logger.info(f"  output {pname} = {output_path}")
                return
            except Exception as e:
                logger.warning(f"  Could not set {pname}: {e}")


def _force_parm_value(parm, value):
    """Set parm even if it has keyframes or expressions (session-only, HIP not saved)."""
    import hou

    try:
        parm.deleteAllKeyframes()
    except hou.OperationFailed:
        pass
    except Exception:
        pass
    try:
        if parm.expression():
            parm.setExpression("")
    except hou.OperationFailed:
        pass
    except Exception:
        pass
    parm.set(value)


def _enable_resolution_override(node):
    import hou

    for parm in node.parms():
        try:
            if parm.parmTemplate().type() != hou.parmTemplateType.Toggle:
                continue
        except Exception:
            continue
        n = parm.name().lower()
        if n in OVERRIDE_RES_TOGGLES or (
            "override" in n and ("res" in n or "camera" in n) and "skip" not in n
        ):
            try:
                _force_parm_value(parm, 1)
                logger.info(f"  {parm.name()} = 1 (override resolution)")
            except Exception:
                pass


def _disable_use_camera_resolution(node):
    import hou

    for parm in node.parms():
        try:
            if parm.parmTemplate().type() != hou.parmTemplateType.Toggle:
                continue
        except Exception:
            continue
        n = parm.name().lower()
        if n in USE_CAMERA_RES_TOGGLES or (
            "use" in n and "camera" in n and "res" in n and "override" not in n
        ):
            try:
                _force_parm_value(parm, 0)
                logger.info(f"  {parm.name()} = 0 (do not use camera resolution)")
            except Exception:
                pass


def _get_render_camera(node):
    import hou

    for pname in CAMERA_PARM_NAMES:
        p = node.parm(pname)
        if p is None:
            continue
        try:
            cam_path = p.eval()
        except Exception:
            continue
        if not cam_path:
            continue
        cam = hou.node(cam_path)
        if cam is not None:
            return cam
    return None


def _set_first_matching_parm(node, names, value):
    import hou

    parm_by_name = {p.name(): p for p in node.parms()}
    for name in names:
        p = parm_by_name.get(name)
        if p is None:
            for pname, candidate in parm_by_name.items():
                if pname.lower() == name.lower():
                    p = candidate
                    break
        if p is None:
            continue
        try:
            _force_parm_value(p, value)
            logger.info(f"  {p.name()} = {value}")
            return True
        except Exception:
            continue
    return False


def _set_resolution_by_patterns(node, width, height):
    import hou

    set_x = set_y = False
    for parm in node.parms():
        pname = parm.name().lower()
        if any(ex in pname for ex in RES_EXCLUDE):
            continue
        try:
            if width > 0 and not set_x and pname in RESX_NAMES:
                _force_parm_value(parm, width)
                logger.info(f"  {parm.name()} = {width}")
                set_x = True
            if height > 0 and not set_y and pname in RESY_NAMES:
                _force_parm_value(parm, height)
                logger.info(f"  {parm.name()} = {height}")
                set_y = True
        except Exception:
            continue
    return set_x and set_y


def _set_resolution_tuples(node, width, height):
    import hou

    for tname in REDSHIFT_RES_TUPLES:
        pt = node.parmTuple(tname)
        if pt is None or len(pt) < 2:
            continue
        try:
            pt.set((width, height))
            logger.info(f"  {tname} = ({width}, {height})")
            return True
        except Exception:
            continue
    return False


def _set_redshift_numbered_pairs(node, width, height):
    ok = False
    for x_name, y_name in REDSHIFT_RES_PAIRS:
        px, py = node.parm(x_name), node.parm(y_name)
        if px is None or py is None:
            continue
        try:
            _force_parm_value(px, width)
            _force_parm_value(py, height)
            logger.info(f"  {x_name} = {width}, {y_name} = {height}")
            ok = True
        except Exception:
            continue
    return ok


def _apply_redshift_resolution(node, width, height):
    """Redshift: enable override first, then set absolute res (not resFraction)."""
    for pname in REDSHIFT_OVERRIDE_TOGGLES:
        p = node.parm(pname)
        if p is None:
            continue
        try:
            _force_parm_value(p, 1)
            logger.info(f"  {pname} = 1")
        except Exception:
            pass

    _disable_use_camera_resolution(node)

    _set_redshift_numbered_pairs(node, width, height)
    _set_resolution_tuples(node, width, height)

    for pname in ("resx", "resy", "Rsresx", "Rsresy", "imageWidth", "imageHeight"):
        p = node.parm(pname)
        if p is None:
            continue
        try:
            if "resx" in pname.lower() or ("width" in pname.lower() and "bit" not in pname.lower()):
                _force_parm_value(p, width)
                logger.info(f"  {pname} = {width}")
            elif "resy" in pname.lower() or "height" in pname.lower():
                _force_parm_value(p, height)
                logger.info(f"  {pname} = {height}")
        except Exception:
            pass

    for uname in (
        "unifiedMaxResX",
        "unifiedMaxResY",
        "RS_unifiedMaxResX",
        "RS_unifiedMaxResY",
        "maxresx",
        "maxresy",
    ):
        p = node.parm(uname)
        if p is None:
            continue
        try:
            if uname.lower().endswith("x") or "resx" in uname.lower():
                _force_parm_value(p, width)
                logger.info(f"  {uname} = {width}")
            else:
                _force_parm_value(p, height)
                logger.info(f"  {uname} = {height}")
        except Exception:
            pass


def _read_rop_resolution(node):
    rx = ry = None
    px = node.parm("resx")
    py = node.parm("resy")
    if px is not None:
        try:
            rx = int(px.eval())
        except Exception:
            pass
    if py is not None:
        try:
            ry = int(py.eval())
        except Exception:
            pass
    return rx, ry


def _set_camera_resolution(camera, width, height):
    if camera is None:
        return False
    set_x = _set_first_matching_parm(camera, RESX_NAMES, width)
    set_y = _set_first_matching_parm(camera, RESY_NAMES, height)
    if not (set_x and set_y):
        _set_resolution_by_patterns(camera, width, height)
    logger.info(f"  camera {camera.path()} resolution -> {width}x{height}")
    return True


def apply_resolution(node, width, height, resize_pct=100.0):
    if not node or (width <= 0 and height <= 0):
        return
    import hou

    type_name = node.type().name().lower()
    absolute_mode = width > 0 and height > 0

    if "redshift" in type_name:
        _apply_redshift_resolution(node, width, height)
    else:
        _enable_resolution_override(node)
        _disable_use_camera_resolution(node)

    if not _set_first_matching_parm(node, RESX_NAMES, width) or not _set_first_matching_parm(
        node, RESY_NAMES, height
    ):
        _set_resolution_by_patterns(node, width, height)

    # Only use resFraction when we did not pass explicit pixel size (relative scale mode).
    if (
        not absolute_mode
        and resize_pct > 0
        and abs(resize_pct - 100.0) > 0.001
    ):
        fraction = resize_pct / 100.0
        for pname in ("resFraction", "RS_resFraction", "resolutionScale", "unifiedScale"):
            p = node.parm(pname)
            if p is not None:
                try:
                    _force_parm_value(p, fraction)
                    logger.info(f"  {pname} = {fraction}")
                except Exception:
                    pass

    rx, ry = _read_rop_resolution(node)
    override_on = False
    for pname in REDSHIFT_OVERRIDE_TOGGLES:
        p = node.parm(pname)
        if p is not None:
            try:
                if int(p.eval()) == 1:
                    override_on = True
                    break
            except Exception:
                pass

    tol = max(2, int(max(width, height) * 0.02))
    rop_ok = rx is not None and abs(rx - width) <= tol and abs(ry - height) <= tol
    if not rop_ok and "redshift" in type_name:
        logger.warning(
            f"  ROP res after apply: {rx}x{ry}, expected {width}x{height} "
            f"(override={'ON' if override_on else 'OFF'})"
        )
        cam = _get_render_camera(node)
        if cam is not None:
            _set_camera_resolution(cam, width, height)
        else:
            logger.warning("  Render camera not found — cannot apply camera resolution fallback")


def _frames_to_render(start, end, skip_on, output, hip, rop_name):
    """Frames that still need rendering (skip-existing aware)."""
    all_frames = list(range(start, end + 1))
    if not skip_on or not output:
        return all_frames
    template = output_template_for_frames(output)
    if not has_frame_tokens(template):
        return all_frames
    needed = []
    for frame in all_frames:
        path = expand_frame_in_path(template, frame, hip, rop_name)
        if not frame_file_exists(path):
            needed.append(frame)
    return needed


def render_frame_range(node, start, end, skip_on=False, output="", hip="", rop_name=""):
    import hou

    frames_to_render = _frames_to_render(start, end, skip_on, output, hip, rop_name)
    work_total = len(frames_to_render)
    needed = set(frames_to_render)
    work_done = 0

    for frame in range(start, end + 1):
        if skip_on and frame not in needed:
            continue
        try:
            node.render(frame_range=(frame, frame))
        except TypeError:
            node.render(frame=frame)
        except hou.OperationFailed as e:
            logger.error(str(e))
            sys.exit(1)
        work_done += 1
        if skip_on and work_total > 0:
            print(f"HRM_WORK {work_done} {work_total}", flush=True)
        else:
            print(f"HRM_FRAME {frame}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Render ROP with queue skip override")
    parser.add_argument("--hip", required=True)
    parser.add_argument("--rop", required=True)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--width", type=int, default=0)
    parser.add_argument("--height", type=int, default=0)
    parser.add_argument("--output", default="")
    parser.add_argument("--skip-existing", type=int, default=0, choices=(0, 1))
    parser.add_argument("--resize-pct", type=float, default=100.0)
    args = parser.parse_args()

    import hou

    hip = args.hip
    logger.info(f"Loading HIP: {hip}")
    hou.hipFile.load(hip, suppress_save_prompt=True, ignore_load_warnings=True)

    node = hou.node(_rop_path(args.rop))
    if node is None:
        logger.error(f"ROP not found: {args.rop}")
        sys.exit(1)

    skip_on = bool(args.skip_existing)
    logger.info(f"Queue skip existing frames: {'ON' if skip_on else 'OFF'}")
    apply_skip_existing(node, skip_on)
    if args.width or args.height:
        logger.info(f"Resolution override: {args.width}x{args.height} (resize {args.resize_pct}%)")
        apply_resolution(node, args.width, args.height, args.resize_pct)
    apply_output_path(node, args.output)

    logger.info(f"Rendering frames {args.start}-{args.end} on {node.path()}")
    if skip_on and args.output:
        todo = _frames_to_render(args.start, args.end, skip_on, args.output, hip, args.rop)
        logger.info(f"Frames to render (skip existing): {len(todo)} / {args.end - args.start + 1}")
    render_frame_range(
        node,
        args.start,
        args.end,
        skip_on=skip_on,
        output=args.output,
        hip=hip,
        rop_name=args.rop,
    )
    logger.info("Render finished.")


if __name__ == "__main__":
    main()
