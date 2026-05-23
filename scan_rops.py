import hou
import sys
import json
import logging
import re

# Configure logging to stderr only (so stdout contains only JSON)
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Exact parm names first (Redshift: RS_outputFileNamePrefix = "Filename Prefix" in UI)
OUTPUT_PARM_EXACT = {
    "redshift_rop": [
        "RS_outputFileNamePrefix",
    ],
    "karma": ["picture", "filename", "outputimage"],
    "ifd": ["vm_picture", "picture"],
    "geometry": ["sopoutput", "filename"],
}
OUTPUT_PARM_EXACT_DEFAULT = ["vm_picture", "picture", "picture_path", "outputpicture"]

CAMERA_PARM_MARKERS = (
    "camera", "rendercamera", "render_camera", "rs_rendercamera",
    "rs_camera", "camnode", "camerapath",
)


def _parm_string(parm, prefer_unexpanded=True):
    getters = ("unexpandedValue", "eval") if prefer_unexpanded else ("eval", "unexpandedValue")
    for getter in getters:
        try:
            val = getattr(parm, getter)()
            if isinstance(val, str) and val.strip():
                return val.strip()
        except Exception:
            continue
    return ""


def _is_path_like(val):
    if not isinstance(val, str) or not val.strip():
        return False
    val = val.strip()
    return (
        "/" in val or "\\" in val or "$" in val
        or val.lower().endswith((".exr", ".png", ".jpg", ".jpeg", ".rat", ".tif", ".tiff"))
    )


def _is_camera_parm_name(pname):
    pl = pname.lower()
    return any(marker in pl for marker in CAMERA_PARM_MARKERS)


def _looks_like_camera_node_path(val):
    """Houdini node paths (/obj/...) are cameras, not render outputs."""
    if not val:
        return False
    v = val.replace("\\", "/").strip()
    if re.match(r"^/obj/", v, re.I):
        return True
    if re.match(r"^/out/", v, re.I) and "render" not in v.lower():
        return True
    return False


def _looks_like_render_output(val, pname=""):
    if not _is_path_like(val):
        return False
    if _looks_like_camera_node_path(val):
        return False
    pl = (pname or "").lower()
    if _is_camera_parm_name(pname):
        return False
    v = val.replace("\\", "/").lower()
    if any(tok in v for tok in ("render", "$hip", "$os", "$f", "%", "#")):
        return True
    if any(tok in v for tok in (".exr", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".rat")):
        return True
    if any(tok in pl for tok in ("picture", "output", "filename", "prefix", "vm_picture", "sopoutput")):
        return True
    return not v.startswith("/")


def _exact_parm_names_for_type(type_name):
    tl = type_name.lower()
    if "redshift" in tl:
        return OUTPUT_PARM_EXACT["redshift_rop"]
    if "karma" in tl:
        return OUTPUT_PARM_EXACT["karma"]
    if "ifd" in tl or "mantra" in tl:
        return OUTPUT_PARM_EXACT["ifd"]
    if "geometry" in tl:
        return OUTPUT_PARM_EXACT["geometry"]
    return OUTPUT_PARM_EXACT_DEFAULT


def _redshift_image_extension(node):
    for pname in ("RS_outputFormat", "RS_outputFormat1", "image_format", "file_format"):
        parm = node.parm(pname)
        if parm is None:
            continue
        try:
            label = parm.evalAsString().lower() if hasattr(parm, "evalAsString") else str(parm.eval()).lower()
        except Exception:
            continue
        for ext, key in (("exr", "exr"), ("png", "png"), ("jpg", "jpg"), ("jpeg", "jpg"), ("tif", "tif")):
            if key in label:
                return ext
        try:
            idx = int(parm.eval())
            return {0: "exr", 1: "png", 2: "jpg", 3: "tif"}.get(idx, "png")
        except Exception:
            pass
    return "png"


def get_redshift_output_path(node):
    """
    Redshift stores the full filename pattern in RS_outputFileNamePrefix, e.g.
    $HIP/render/sc-09/$OS/$OS.$F4.png  ($OS = ROP node name, e.g. front)
    """
    prefix_parm = node.parm("RS_outputFileNamePrefix")
    if prefix_parm is None:
        logger.warning(f"Redshift ROP {node.name()}: RS_outputFileNamePrefix not found")
        return ""

    path = _parm_string(prefix_parm, prefer_unexpanded=True)
    if not path:
        try:
            path = str(prefix_parm.unexpandedValue()).strip()
        except Exception:
            path = ""

    if not path or _looks_like_camera_node_path(path):
        logger.warning(f"Redshift ROP {node.name()}: empty or invalid prefix")
        return ""

    ext = _redshift_image_extension(node)

    # Directory-only prefix -> standard Redshift layout
    if not has_frame_tokens(path) and not re.search(r"\.\w{2,5}$", path, re.I):
        base = path.rstrip("/\\")
        if "$OS" not in path:
            path = f"{base}/$OS/$OS.$F4.{ext}"
        else:
            path = f"{base}.$F4.{ext}"

    # Has $OS folder but missing filename (ends with /$OS/)
    elif path.rstrip("/\\").endswith("$OS") or (
        "$OS" in path and not re.search(r"\$OS\.\$F", path) and not re.search(rf"\$OS\.{ext}", path, re.I)
    ):
        base = path.rstrip("/\\")
        path = f"{base}/$OS.$F4.{ext}"

    logger.info(f"Redshift {node.name()} output template: {path}")
    return path


def has_frame_tokens(path):
    return bool(re.search(r"\$F\d*|\$F\b|#+|%0\d+d", path or ""))


def get_rop_output_path(node):
    """Read render output path from ROP parms; never use camera object paths."""
    type_name = node.type().name()
    if "redshift" in type_name.lower():
        return get_redshift_output_path(node)

    parm_by_name = {p.name(): p for p in node.parms()}

    for exact_name in _exact_parm_names_for_type(type_name):
        parm = parm_by_name.get(exact_name)
        if parm is None:
            for pname, p in parm_by_name.items():
                if pname.lower() == exact_name.lower():
                    parm = p
                    break
        if parm is None:
            continue
        val = _parm_string(parm)
        if _looks_like_render_output(val, exact_name):
            logger.info(f"Output path from {exact_name}: {val}")
            return val

    output_substrings = (
        "outputfilenameprefix", "outputfilename", "filenameprefix",
        "vm_picture", "picture_path", "picture", "sopoutput", "outputfile",
    )
    for pname, parm in parm_by_name.items():
        if _is_camera_parm_name(pname):
            continue
        pl = pname.lower()
        if not any(sub in pl for sub in output_substrings):
            if "output" not in pl and "picture" not in pl:
                continue
        val = _parm_string(parm)
        if _looks_like_render_output(val, pname):
            logger.info(f"Output path from parm {pname}: {val}")
            return val

    for pname, parm in parm_by_name.items():
        if _is_camera_parm_name(pname):
            continue
        val = _parm_string(parm)
        if _looks_like_render_output(val, pname):
            logger.info(f"Output path from fallback parm {pname}: {val}")
            return val

    logger.warning(f"No output path found for ROP {node.name()} ({type_name})")
    return ""


try:
    if len(sys.argv) < 2:
        raise ValueError("HIP file path not provided")
    
    hip_file = sys.argv[1]
    logger.info(f"Loading HIP file: {hip_file}")
    hou.hipFile.load(hip_file)
    
    rops = []
    out_node = hou.node("/out")
    
    if not out_node:
        logger.warning("No /out node found in HIP file")
        print(json.dumps([]))
    else:
        for node in out_node.children():
            if node.type().name().endswith("ROP"):
                try:
                    # Safely get frame parameters
                    f1_parm = node.parm("f1")
                    f2_parm = node.parm("f2")
                    skip_parm = None
                    for skip_name in ["skiprendered", "skiprenderedframes", "skip_existing", "skipexisting", "skiprenderedframe"]:
                        skip_parm = node.parm(skip_name)
                        if skip_parm is not None:
                            break
                    start = f1_parm.eval() if f1_parm else 1
                    end = f2_parm.eval() if f2_parm else 100
                    skip_existing = bool(skip_parm.eval()) if skip_parm else False
                    
                    logger.info(f"Processing ROP: {node.name()}, type: {node.type().name()}")
                    
                    # Get render resolution - X from ROP, Y from camera
                    size_x = None
                    size_y = None
                    
                    # Get render resolution - prioritize camera over ROP
                    size_x = None
                    size_y = None
                    
                    # First, try to find camera and get resolution from it
                    camera_node = None
                    camera_parm_names = ["camera", "rendercamera", "rs_rendercamera", "rs_camera", "cam", "render_cam", "RS_renderCamera"]
                    logger.info(f"Looking for camera in ROP {node.name()}")
                    for cam_parm_name in camera_parm_names:
                        cam_parm = node.parm(cam_parm_name)
                        if cam_parm:
                            try:
                                cam_path = cam_parm.eval()
                                logger.info(f"Found camera parm {cam_parm_name}: {cam_path}")
                                if cam_path:
                                    camera_node = hou.node(cam_path)
                                    if camera_node:
                                        logger.info(f"Found camera node: {cam_path}")
                                        break
                            except Exception as e:
                                logger.debug(f"Error evaluating camera parm {cam_parm_name}: {e}")
                    
                    # If camera found, get resolution from camera parameters
                    if camera_node:
                        cam_x_patterns = ["resx", "xres", "resolutionx", "x_resolution", "x_res"]
                        cam_y_patterns = ["resy", "yres", "resolutiony", "y_resolution", "y_res"]
                        for parm in camera_node.parms():
                            pname = parm.name().lower()
                            if size_x is None and any(token in pname for token in cam_x_patterns):
                                try:
                                    val = int(parm.eval())
                                    if val > 0:
                                        size_x = val
                                        logger.info(f"Got X resolution from camera: {size_x}")
                                except:
                                    pass
                            if size_y is None and any(token in pname for token in cam_y_patterns):
                                try:
                                    val = int(parm.eval())
                                    if val > 0:
                                        size_y = val
                                        logger.info(f"Got Y resolution from camera: {size_y}")
                                except:
                                    pass
                    
                    # If camera didn't provide resolution, try ROP parameters
                    if size_x is None or size_y is None:
                        x_patterns = ["resx", "xres", "resolutionx", "width", "sizex", "imagewidth", "pixelwidth", "rs_xresolution", "rs_xres", "rs_width", "x_resolution", "x_res", "rs_overrideres1", "override_res1", "res_overridex"]
                        y_patterns = ["resy", "yres", "resolutiony", "height", "sizey", "imageheight", "pixelheight", "rs_yresolution", "rs_yres", "rs_height", "y_resolution", "y_res", "rs_overrideres2", "override_res2", "res_overridey"]
                        exclude_patterns = ["compression", "passes", "quality", "bit", "format", "filter", "mode", "type", "ratio", "scale"]
                        for parm in node.parms():
                            pname = parm.name().lower()
                            if size_x is None and any(token in pname for token in x_patterns) and not any(excl in pname for excl in exclude_patterns):
                                try:
                                    val = int(parm.eval())
                                    if val > 0 and val < 10000:  # Reasonable resolution limit
                                        size_x = val
                                        logger.info(f"Got X resolution from ROP parm '{parm.name()}': {size_x}")
                                except:
                                    pass
                            if size_y is None and any(token in pname for token in y_patterns) and not any(excl in pname for excl in exclude_patterns):
                                try:
                                    val = int(parm.eval())
                                    if val > 0 and val < 10000:
                                        size_y = val
                                        logger.info(f"Got Y resolution from ROP parm '{parm.name()}': {size_y}")
                                except:
                                    pass
                    
                    output_path = get_rop_output_path(node)
                    
                    rops.append({
                        "name": node.name(),
                        "type": node.type().name(),
                        "start_frame": int(start),
                        "end_frame": int(end),
                        "skip_existing": skip_existing,
                        "size_x": size_x,
                        "size_y": size_y,
                        "output_path": output_path,
                        "hip": hip_file
                    })
                    logger.info(f"Found ROP: {node.name()} ({node.type().name()}), frames {start}-{end}, size: {size_x}x{size_y}, skip: {skip_existing}")
                except Exception as e:
                    logger.warning(f"Error processing ROP {node.name()}: {e}")
                    continue
        
        # Use a dedicated print that doesn't trigger other Houdini stdout noise
        # and ensure it's the only thing in stdout
        sys.stdout.write(json.dumps(rops))
        sys.stdout.flush()
        logger.info(f"Total ROPs found: {len(rops)}")
        
except Exception as e:
    logger.error(f"Error scanning HIP file: {e}")
    print(json.dumps([]))
    sys.exit(1)

